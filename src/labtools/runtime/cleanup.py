"""Independent cleanup attempts with original-failure preservation."""
from contextlib import contextmanager


@contextmanager
def cleanup_actions(*actions):
    """Run labelled callbacks in order; preserve any active exception."""
    primary = None
    try:
        yield
    except BaseException as exc:
        primary = exc
        raise
    finally:
        failures = []
        for label, action in actions:
            try:
                action()
            except Exception as exc:
                exc.add_note(f"Cleanup action: {label}")
                failures.append(exc)
                if primary is not None:
                    primary.add_note(f"Cleanup failed ({label}): {exc!r}")
        if failures and primary is None:
            raise ExceptionGroup("Acquisition cleanup failed", failures)
