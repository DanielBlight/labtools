"""Narrow application-owned IDQ count service; native imports stay lazy."""

from __future__ import annotations

from ipaddress import IPv4Address


def canonical_idq_address(address: str) -> str:
    """Return the canonical textual IP supported by the existing controller."""
    if not isinstance(address, str) or not address.strip():
        raise ValueError("IDQ address must be a nonempty IP address")
    try:
        return str(IPv4Address(address.strip()))
    except ValueError as exc:
        raise ValueError(f"Invalid IDQ IP address: {address!r}") from exc


def idq_resource_name(address: str) -> str:
    return f"time-controller:{canonical_idq_address(address)}"


class IDQCountService:
    """Own one controller and expose only intensity-map count operations."""

    def __init__(self, address: str, *, controller_factory=None):
        address = canonical_idq_address(address)
        if controller_factory is None:
            from labtools.devices.idq_time_controller import IDQTimeController

            controller_factory = IDQTimeController
        self.address = address
        self._controller = controller_factory(address)
        try:
            self._controller.connect()
        except BaseException as primary:
            try:
                self._controller.disconnect()
            except BaseException as cleanup:  # noqa: BLE001 - retain partial-startup cleanup failure
                primary.add_note(f"Partial IDQ startup cleanup failed: {cleanup!r}")
            raise
        self._closed = False

    def configure_channel(self, channel, *, threshold_v, edge, enabled=True):
        if self._closed:
            raise RuntimeError("IDQ count service is closed")
        return self._controller.configure_channel(
            channel, threshold_v=threshold_v, edge=edge, enabled=enabled
        )

    def get_simultaneous_counts(self, channels, integration_time_s):
        if self._closed:
            raise RuntimeError("IDQ count service is closed")
        return self._controller.get_simultaneous_counts(channels, integration_time_s)

    def close(self):
        if self._closed:
            return
        try:
            self._controller.disconnect()
        finally:
            self._closed = True
