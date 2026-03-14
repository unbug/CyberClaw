import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:
    from .behavior_tree import Action, Blackboard, Condition, Cooldown, RandomSelector, RepeatForever, Selector, Sequence, Status
except ImportError:
    from behavior_tree import Action, Blackboard, Condition, Cooldown, RandomSelector, RepeatForever, Selector, Sequence, Status


@dataclass
class WanderCtx:
    patrol: Any
    now: float
    pose: Tuple[float, float, float]
    dist: Optional[float]
    dist_t: float
    pos_t: float
    gyaw: float


def _stop(ctx: WanderCtx, _bb: Blackboard) -> Status:
    try:
        ctx.patrol.chassis.drive_speed(x=0, y=0, z=0)
    except Exception:
        pass
    return Status.SUCCESS


class TimedDrive(Action):
    def __init__(self, duration_s: float, speed_fn):
        self.duration_s = float(duration_s)
        self.speed_fn = speed_fn
        self._t0: Optional[float] = None
        super().__init__(self._tick)

    def reset(self) -> None:
        self._t0 = None

    def _tick(self, ctx: WanderCtx, bb: Blackboard) -> Status:
        if self._t0 is None:
            self._t0 = ctx.now
        if ctx.now - self._t0 >= self.duration_s:
            return Status.SUCCESS
        v = float(self.speed_fn(ctx, bb))
        try:
            ctx.patrol.chassis.drive_speed(x=v, y=0, z=0)
        except Exception:
            raise
        return Status.RUNNING


class Wiggle(Action):
    def __init__(self, duration_s: float = 1.2, z_speed: float = 45.0):
        self.duration_s = float(duration_s)
        self.z_speed = float(z_speed)
        self._t0: Optional[float] = None
        super().__init__(self._tick)

    def reset(self) -> None:
        self._t0 = None

    def _tick(self, ctx: WanderCtx, _bb: Blackboard) -> Status:
        if self._t0 is None:
            self._t0 = ctx.now
        dt = ctx.now - self._t0
        if dt >= self.duration_s:
            try:
                ctx.patrol.chassis.drive_speed(x=0, y=0, z=0)
            except Exception:
                pass
            return Status.SUCCESS
        z = self.z_speed if int(dt * 4) % 2 == 0 else -self.z_speed
        try:
            ctx.patrol.chassis.drive_speed(x=0, y=0, z=z)
        except Exception:
            raise
        return Status.RUNNING


class LookAround(Action):
    def __init__(self, period_s: float = 2.0):
        self.period_s = float(period_s)
        self._t0: Optional[float] = None
        self._phase = 0
        super().__init__(self._tick)

    def reset(self) -> None:
        self._t0 = None
        self._phase = 0

    def _tick(self, ctx: WanderCtx, _bb: Blackboard) -> Status:
        if self._t0 is None:
            self._t0 = ctx.now
        if ctx.now - self._t0 >= self.period_s:
            return Status.SUCCESS
        try:
            if self._phase == 0:
                ok = ctx.patrol.gimbal.moveto(pitch=0, yaw=-35, pitch_speed=30, yaw_speed=60).wait_for_completed(timeout=1.5)
                self._phase = 1 if ok else 3
            elif self._phase == 1:
                ok = ctx.patrol.gimbal.moveto(pitch=0, yaw=35, pitch_speed=30, yaw_speed=60).wait_for_completed(timeout=1.5)
                self._phase = 2 if ok else 3
            elif self._phase == 2:
                ctx.patrol.gimbal.moveto(pitch=0, yaw=0, pitch_speed=30, yaw_speed=60).wait_for_completed(timeout=1.5)
                self._phase = 3
        except Exception:
            self._phase = 3
        return Status.RUNNING


class ScanChooseTurn(Action):
    def __init__(self):
        self._angles = [0, 60, -60, 120, -120]
        self._i = 0
        self._measurements: Dict[int, float] = {}
        self._heading_offset = 0.0
        self._waiting = False
        self._wait_start: Optional[float] = None
        self._move_end_t: float = 0.0
        self._last_turn_ok = True
        super().__init__(self._tick)

    def reset(self) -> None:
        self._i = 0
        self._measurements = {}
        self._heading_offset = 0.0
        self._waiting = False
        self._wait_start = None
        self._move_end_t = 0.0
        self._last_turn_ok = True

    def _read_distance(self, ctx: WanderCtx) -> float:
        with ctx.patrol.lock:
            dist = ctx.patrol.last_dist
        return dist if dist else ctx.patrol.mapper.max_range_m

    def _tick(self, ctx: WanderCtx, bb: Blackboard) -> Status:
        if self._i == 0:
            try:
                ctx.patrol.chassis.drive_speed(x=0, y=0, z=0)
            except Exception:
                pass

        if self._i >= len(self._angles):
            d0 = self._measurements.get(0, 0.0)
            best_ang = 0
            max_d = max(self._measurements.values()) if self._measurements else 0.0
            if d0 >= 1.0 and (max_d - d0) <= 0.25:
                best_ang = 0
            else:
                turn_cost_per_60 = 0.25
                best_score = -1e9
                for ang, d in self._measurements.items():
                    score = d - turn_cost_per_60 * (abs(ang) / 60.0)
                    if score > best_score:
                        best_score = score
                        best_ang = ang
                    elif score == best_score and abs(ang) < abs(best_ang):
                        best_ang = ang
            max_d = self._measurements.get(best_ang, max_d)
            if max_d < 0.6:
                best_ang = 180
            final_turn = best_ang - self._heading_offset
            final_turn = (final_turn + 180) % 360 - 180
            bb["target_turn_deg"] = final_turn
            return Status.SUCCESS

        ang = self._angles[self._i]

        if not self._waiting:
            turn_needed = ang - self._heading_offset
            turn_needed = (turn_needed + 180) % 360 - 180
            if abs(turn_needed) > 0.5:
                ok = ctx.patrol._try_move(x=0, y=0, z=turn_needed, z_speed=45, timeout=5)
                if not ok:
                    self._measurements[ang] = 0.0
                    self._i += 1
                    return Status.RUNNING
                self._heading_offset += turn_needed
            self._waiting = True
            self._wait_start = ctx.now
            self._move_end_t = time.time()
            return Status.RUNNING

        if self._wait_start is None:
            self._wait_start = ctx.now

        with ctx.patrol.lock:
            dist_t = ctx.patrol.last_dist_time
            dist = ctx.patrol.last_dist

        if dist_t > self._move_end_t or (ctx.now - self._wait_start) > 1.0:
            d = dist if dist else ctx.patrol.mapper.max_range_m
            d_eff = ctx.patrol._angle_penalty_distance(-math.radians(ang), d)
            self._measurements[ang] = float(d_eff)
            with ctx.patrol.lock:
                _rx, _ry, _ryaw = ctx.patrol.x, ctx.patrol.y, ctx.patrol.yaw
                _gyaw = ctx.patrol.gimbal_yaw
            ctx.patrol.mapper.update(_rx, _ry, _ryaw, _gyaw, d)
            self._waiting = False
            self._wait_start = None
            self._i += 1
        return Status.RUNNING


class TurnToTarget(Action):
    def __init__(self):
        super().__init__(self._tick)

    def _tick(self, ctx: WanderCtx, bb: Blackboard) -> Status:
        deg = float(bb.get("target_turn_deg", 0.0))
        if abs(deg) < 1.0:
            return Status.SUCCESS
        ok = ctx.patrol._try_move(x=0, y=0, z=deg, z_speed=45, timeout=8)
        if not ok:
            return Status.FAILURE
        bb["target_turn_deg"] = 0.0
        return Status.SUCCESS


def build_tree() -> Any:
    def telemetry_ok(ctx: WanderCtx, _bb: Blackboard) -> bool:
        drop_s = 3.5
        if (ctx.now - ctx.dist_t) > drop_s:
            return False
        if (ctx.now - ctx.pos_t) > drop_s:
            return False
        return True

    def danger(ctx: WanderCtx, _bb: Blackboard) -> bool:
        p = ctx.patrol
        dist = ctx.dist
        if dist is not None and dist < 0.55:
            return True
        try:
            if p.detect_visual_obstacle():
                return True
        except Exception:
            pass
        try:
            obs = p._visual_obstacles_snapshot()
            best = None
            for oa, od in obs:
                if od is None:
                    continue
                if abs(oa) <= math.radians(15):
                    best = od if best is None else min(best, od)
            if best is not None and best < 1.2:
                return True
        except Exception:
            pass
        return False

    def update_progress(ctx: WanderCtx, bb: Blackboard) -> Status:
        rx, ry, _ = ctx.pose
        last = bb.get("last_pose", (rx, ry))
        moved = math.hypot(rx - last[0], ry - last[1])
        if moved > 0.03:
            bb["last_pose"] = (rx, ry)
            bb["last_progress_t"] = ctx.now
        return Status.SUCCESS

    def stuck(ctx: WanderCtx, bb: Blackboard) -> bool:
        last_t = float(bb.get("last_progress_t", ctx.now))
        dist = ctx.dist
        if dist is None:
            return False
        v = ctx.patrol._cruise_speed(dist)
        return (ctx.now - last_t) > 2.5 and v > 0.08

    def cruise_speed(ctx: WanderCtx, _bb: Blackboard) -> float:
        if ctx.dist is None:
            return 0.0
        return ctx.patrol._cruise_speed(ctx.dist)

    safety = Selector(
        [
            Sequence([Condition(danger), Action(_stop)]),
            Sequence(
                [
                    Condition(lambda ctx, bb: not telemetry_ok(ctx, bb)),
                    Action(_stop),
                    Action(lambda _ctx, _bb: Status.FAILURE),
                ]
            ),
        ]
    )

    recover = Selector(
        [
            Sequence(
                [
                    Condition(stuck),
                    Action(_stop),
                    Action(lambda ctx, bb: Status.SUCCESS if ctx.patrol._unstick() else Status.FAILURE),
                ]
            )
        ]
    )

    scan_and_turn = Sequence([Action(_stop), ScanChooseTurn(), TurnToTarget()])

    explore = Selector(
        [
            Sequence([Condition(lambda ctx, bb: ctx.dist is not None and ctx.dist > 1.5), TimedDrive(2.0, cruise_speed)]),
            scan_and_turn,
        ]
    )

    playful = RandomSelector(
        [
            Cooldown(Sequence([Action(_stop), LookAround(2.5)]), 8.0, key="cd:look"),
            Cooldown(Sequence([Action(_stop), Wiggle(1.2)]), 12.0, key="cd:wiggle"),
        ],
        weights=[0.6, 0.4],
    )

    root = RepeatForever(
        Sequence(
            [
                Action(update_progress),
                Selector(
                    [
                        safety,
                        recover,
                        Cooldown(playful, 2.0, key="cd:play"),
                        explore,
                    ]
                ),
            ]
        )
    )
    return root
