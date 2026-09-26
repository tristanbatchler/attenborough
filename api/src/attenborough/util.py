from collections.abc import Callable

# Root of the app's logger hierarchy ("attenborough.admin", "attenborough.ip", ...).
ROOT_LOGGER_NAME = "attenborough"

_URL_PATH_SEPARATOR = "/"


def url_path_segments(path: str) -> list[str]:
    """The non-empty segments of a URL path: "/protected/secret" -> ["protected", "secret"]."""
    return [segment for segment in path.split(_URL_PATH_SEPARATOR) if segment]


def relative_url_path(path: str) -> str:
    """A URL path without its leading slash: "/backup/db.zip" -> "backup/db.zip"."""
    return path.removeprefix(_URL_PATH_SEPARATOR)


def inherit_signature[**P, T](
    _source: Callable[P, object],
) -> Callable[[Callable[..., T]], Callable[P, T]]:
    def decorator(target: Callable[..., T]) -> Callable[P, T]:
        return target

    return decorator
