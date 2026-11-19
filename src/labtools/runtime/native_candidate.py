"""Disabled native-candidate service composition; no default native factories."""

from labtools.acquisition.spectrum_service import SpectrumService
from labtools.config.native_candidate import DISABLED_REASON, NativeCandidatePlan
from labtools.runtime.workspace_map_transport import WorkspaceMapTransport
from labtools.runtime.workspace_spectrum_transport import WorkspaceSpectrumTransport


class NativeExecutionDisabled(RuntimeError):
    """The candidate has no authorized hardware execution route."""


class DisabledNativeCandidate:
    """Bind reviewed inputs to existing boundaries, but refuse every public operation.

    Factories are trusted developer injection, never names imported from a manifest.
    Binding constructs no devices. No session/registry/executor is created here.
    """

    def __init__(self, *, plan, ownership, map_factories, spectrometer_factory):
        if not isinstance(plan, NativeCandidatePlan):
            raise TypeError("A successful NativeCandidatePlan is required")
        plan.verify_sources()
        if ownership.config != plan.reservation_config:
            raise ValueError("Ownership resources/configuration do not match the preflight plan")
        self.plan = plan
        self._map = WorkspaceMapTransport(
            ownership=ownership, configuration_id=plan.configuration_id, factories=map_factories,
        )
        self._spectrum = WorkspaceSpectrumTransport(
            ownership=ownership, spectrometer_factory=spectrometer_factory,
        )
        self.spectrum = SpectrumService(self._disabled_backend)

    def acquire_map(self, *args, **kwargs):
        raise NativeExecutionDisabled(DISABLED_REASON)

    def _disabled_backend(self, *args, **kwargs):
        raise NativeExecutionDisabled(DISABLED_REASON)

    def describe(self):
        return {"execution_enabled": False, "disabled_reason": DISABLED_REASON,
                "binding_plan": self.plan.describe()}
