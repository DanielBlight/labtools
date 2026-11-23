"""Exclusive multi-step leases with context-local, explicitly borrowed owners."""

from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE = ContextVar("labtools_batch", default=None)


class Batch:
    def __init__(self, ownership, owners):
        self.ownership = ownership
        self.resources = tuple(dict.fromkeys(name for owner in owners for name in ownership.config.for_workflow(owner)))
        self.lease = ownership.session.reserve("Sequence", self.resources)
        self.active = True

    @contextmanager
    def borrow(self, owner):
        if not self.active or not set(self.ownership.config.for_workflow(owner)) <= set(self.resources):
            raise PermissionError("Workflow is not covered by this batch lease")
        previous = _ACTIVE.get()
        owners = previous[1] | {owner} if previous is not None and previous[0] is self else {owner}
        token = _ACTIVE.set((self, owners))
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    def release(self):
        self.active = False
        self.lease.release()


class BorrowedLease:
    def release(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def borrowed(ownership, owner):
    current = _ACTIVE.get()
    if current is None:
        return False
    batch, expected = current
    if batch.ownership is not ownership or owner not in expected or not batch.active:
        return False
    states = {item.name: item.owner for item in ownership.status().resources}
    return all(states[name] == "Sequence" for name in ownership.config.for_workflow(owner))


def has_owner(ownership, owner):
    if borrowed(ownership, owner):
        return True
    states = {item.name: item.owner for item in ownership.status().resources}
    return all(states[name] == owner for name in ownership.config.for_workflow(owner))
