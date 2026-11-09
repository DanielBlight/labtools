"""Qt-free formatting of operator-facing exception diagnostics."""

from __future__ import annotations


def format_operator_exception(error: BaseException) -> str:
    """Return concise primary, note, and grouped-child diagnostics."""
    lines: list[str] = []

    def append_exception(current: BaseException, prefix: str = "") -> None:
        lines.append(f"{prefix}{type(current).__name__}: {current}")
        for note in getattr(current, "__notes__", ()):
            lines.append(f"{prefix}Note: {note}")
        if isinstance(current, BaseExceptionGroup):
            for index, child in enumerate(current.exceptions, start=1):
                append_exception(child, f"{prefix}Failure {index}: ")

    append_exception(error)
    return "\n".join(lines)
