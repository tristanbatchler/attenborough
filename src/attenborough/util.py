from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def inherit_signature[**P, T](
    _source: Callable[P, object],
) -> Callable[[Callable[..., T]], Callable[P, T]]:
    def decorator(target: Callable[..., T]) -> Callable[P, T]:
        return target

    return decorator
