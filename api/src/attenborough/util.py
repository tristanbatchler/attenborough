import asyncio
from collections.abc import Callable, Coroutine
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

_background_tasks: set[asyncio.Task[object]] = set()


def inherit_signature[**P, T](
    _source: Callable[P, object],
) -> Callable[[Callable[..., T]], Callable[P, T]]:
    def decorator(target: Callable[..., T]) -> Callable[P, T]:
        return target

    return decorator


def fire_and_forget[**P, T](
    func: Callable[P, Coroutine[object, object, T]],
    *params: P.args,
    **kwparams: P.kwargs,
) -> None:
    task = asyncio.create_task(func(*params, **kwparams))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
