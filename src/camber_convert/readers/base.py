"""Reader registry.

A "reader" is a function that takes a file path and returns a `Dataset`.
Each reader registers the file extension(s) it handles. `read()` dispatches
on the extension. Adding support for a new vendor format is therefore a
self-contained change: write one module, decorate it with `@register(".ext")`,
import it here. This is the extension point that makes community contributions
(and CLA-covered university contributions) small and reviewable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..model import Dataset

Reader = Callable[[str], Dataset]

# extension (lowercase, incl. dot) -> reader function
REGISTRY: dict[str, Reader] = {}


class UnsupportedFormatError(Exception):
    """Raised when no reader is registered for a file's extension."""


def register(*extensions: str) -> Callable[[Reader], Reader]:
    """Decorator: register a reader for one or more file extensions."""

    def decorator(fn: Reader) -> Reader:
        for ext in extensions:
            REGISTRY[ext.lower()] = fn
        return fn

    return decorator


def supported_extensions() -> list[str]:
    return sorted(REGISTRY.keys())


def read(path: str) -> Dataset:
    """Read `path` into a `Dataset`, choosing a reader by file extension."""
    ext = Path(path).suffix.lower()
    reader = REGISTRY.get(ext)
    if reader is None:
        raise UnsupportedFormatError(
            f"No reader for '{ext}' files. "
            f"Supported: {', '.join(supported_extensions()) or '(none registered)'}."
        )
    return reader(path)
