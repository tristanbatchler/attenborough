from collections.abc import Callable

# Root of the app's logger hierarchy ("attenborough.admin", "attenborough.ip", ...).
ROOT_LOGGER_NAME = "attenborough"


def inherit_signature[**P, T](
    _source: Callable[P, object],
) -> Callable[[Callable[..., T]], Callable[P, T]]:
    def decorator(target: Callable[..., T]) -> Callable[P, T]:
        return target

    return decorator
