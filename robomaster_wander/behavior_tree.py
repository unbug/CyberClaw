import random
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Status(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


Blackboard = Dict[str, Any]


class Node:
    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        raise NotImplementedError()

    def reset(self) -> None:
        return


class Sequence(Node):
    def __init__(self, children: List[Node]):
        self.children = children
        self._i = 0

    def reset(self) -> None:
        self._i = 0
        for c in self.children:
            c.reset()

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        while self._i < len(self.children):
            st = self.children[self._i].tick(ctx, bb)
            if st == Status.SUCCESS:
                self._i += 1
                continue
            if st == Status.FAILURE:
                self.reset()
                return Status.FAILURE
            return Status.RUNNING
        self.reset()
        return Status.SUCCESS


class Selector(Node):
    def __init__(self, children: List[Node]):
        self.children = children
        self._i = 0

    def reset(self) -> None:
        self._i = 0
        for c in self.children:
            c.reset()

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        while self._i < len(self.children):
            st = self.children[self._i].tick(ctx, bb)
            if st == Status.FAILURE:
                self._i += 1
                continue
            if st == Status.SUCCESS:
                self.reset()
                return Status.SUCCESS
            return Status.RUNNING
        self.reset()
        return Status.FAILURE


class Condition(Node):
    def __init__(self, predicate: Callable[[Any, Blackboard], bool]):
        self.predicate = predicate

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        return Status.SUCCESS if self.predicate(ctx, bb) else Status.FAILURE


class Action(Node):
    def __init__(self, fn: Callable[[Any, Blackboard], Status]):
        self.fn = fn

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        return self.fn(ctx, bb)


class Cooldown(Node):
    def __init__(self, child: Node, cooldown_s: float, key: Optional[str] = None):
        self.child = child
        self.cooldown_s = float(cooldown_s)
        self.key = key or f"cooldown:{id(self)}"

    def reset(self) -> None:
        self.child.reset()

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        now = getattr(ctx, "now", time.time())
        last = bb.get(self.key, 0.0)
        if now - float(last) < self.cooldown_s:
            return Status.FAILURE
        st = self.child.tick(ctx, bb)
        if st == Status.SUCCESS:
            bb[self.key] = now
        return st


class RateLimit(Node):
    def __init__(self, child: Node, period_s: float, key: Optional[str] = None):
        self.child = child
        self.period_s = float(period_s)
        self.key = key or f"ratelimit:{id(self)}"
        self._cached: Optional[Status] = None

    def reset(self) -> None:
        self.child.reset()
        self._cached = None

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        now = getattr(ctx, "now", time.time())
        last = bb.get(self.key, 0.0)
        if now - float(last) < self.period_s:
            return self._cached or Status.FAILURE
        bb[self.key] = now
        st = self.child.tick(ctx, bb)
        self._cached = st
        return st


class RandomSelector(Node):
    def __init__(self, children: List[Node], weights: Optional[List[float]] = None, seed_key: str = "rng_seed"):
        self.children = children
        self.weights = weights
        self.seed_key = seed_key
        self._order: List[int] = []
        self._i = 0

    def reset(self) -> None:
        self._order = []
        self._i = 0
        for c in self.children:
            c.reset()

    def _shuffle(self, bb: Blackboard) -> None:
        rng = random.Random(bb.get(self.seed_key, None))
        idxs = list(range(len(self.children)))
        if self.weights is None:
            rng.shuffle(idxs)
            self._order = idxs
            return
        pool = idxs[:]
        w = list(self.weights) if len(self.weights) == len(self.children) else [1.0] * len(self.children)
        order = []
        for _ in range(len(self.children)):
            total = sum(max(0.0, wi) for wi in w)
            if total <= 0.0:
                rng.shuffle(pool)
                order.extend(pool)
                break
            r = rng.random() * total
            acc = 0.0
            chosen = None
            for i in range(len(pool)):
                wi = max(0.0, w[pool[i]])
                acc += wi
                if acc >= r:
                    chosen = pool.pop(i)
                    break
            if chosen is None:
                chosen = pool.pop()
            order.append(chosen)
        self._order = order

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        if not self._order:
            self._shuffle(bb)
        while self._i < len(self._order):
            st = self.children[self._order[self._i]].tick(ctx, bb)
            if st == Status.FAILURE:
                self._i += 1
                continue
            if st == Status.SUCCESS:
                self.reset()
                return Status.SUCCESS
            return Status.RUNNING
        self.reset()
        return Status.FAILURE


class RepeatForever(Node):
    def __init__(self, child: Node):
        self.child = child

    def reset(self) -> None:
        self.child.reset()

    def tick(self, ctx: Any, bb: Blackboard) -> Status:
        st = self.child.tick(ctx, bb)
        if st in (Status.SUCCESS, Status.FAILURE):
            self.child.reset()
        return Status.RUNNING
