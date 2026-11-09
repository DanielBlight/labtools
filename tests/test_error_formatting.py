"""Qt-free tests for operator exception formatting."""

from labtools.gui.error_formatting import format_operator_exception


def test_formats_primary_exception_and_cleanup_notes():
    error = ValueError("scan failed")
    error.add_note(
        "Cleanup failed (close shutter): RuntimeError('shutter close failed')"
    )
    error.add_note(
        "Cleanup failed (return mirror home): RuntimeError('mirror home failed')"
    )

    assert format_operator_exception(error) == (
        "ValueError: scan failed\n"
        "Note: Cleanup failed (close shutter): "
        "RuntimeError('shutter close failed')\n"
        "Note: Cleanup failed (return mirror home): "
        "RuntimeError('mirror home failed')"
    )


def test_formats_labelled_exception_group_children_and_notes():
    shutter = RuntimeError("shutter close failed")
    shutter.add_note("Cleanup action: close shutter")
    mirror = RuntimeError("mirror home failed")
    mirror.add_note("Cleanup action: return mirror home")
    group = ExceptionGroup("Acquisition cleanup failed", [shutter, mirror])
    group.add_note("LabJack cleanup also failed: OSError('close failed')")

    assert format_operator_exception(group) == (
        "ExceptionGroup: Acquisition cleanup failed (2 sub-exceptions)\n"
        "Note: LabJack cleanup also failed: OSError('close failed')\n"
        "Failure 1: RuntimeError: shutter close failed\n"
        "Failure 1: Note: Cleanup action: close shutter\n"
        "Failure 2: RuntimeError: mirror home failed\n"
        "Failure 2: Note: Cleanup action: return mirror home"
    )
