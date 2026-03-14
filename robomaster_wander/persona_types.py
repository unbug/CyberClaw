from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Step:
    kind: str
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = None

    def __post_init__(self):
        object.__setattr__(self, "kwargs", self.kwargs or {})


@dataclass
class Macro:
    name: str
    steps: List[Step]
    tags: Tuple[str, ...] = ()
    weight: float = 1.0
    cooldown_s: float = 0.0
    allow_fire: bool = False
