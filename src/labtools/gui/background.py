"""Compatibility exports for Qt-free background processing."""

from labtools.processing.background import (
    apply_background_subtraction,
    parse_background_csv,
)

__all__ = ["apply_background_subtraction", "parse_background_csv"]
