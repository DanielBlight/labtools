"""Atomic per-user native preferences; no device state, credentials or approval."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class WorkspacePreferences:
    def __init__(self, configuration_id, fingerprint, path=None):
        self.fingerprint = fingerprint
        self.configuration_id = configuration_id
        if path is None:
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
            key = hashlib.sha256(configuration_id.encode()).hexdigest()[:24]
            path = base / "Labtools/native-workspace" / (key + ".json")
        self.path = Path(path)
        self.messages = []

    def read(self):
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size > 256_000:
                raise ValueError("Preference file is too large")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1
                    or data.get("configuration_id") != self.configuration_id
                    or data.get("source_fingerprint") != self.fingerprint):
                raise ValueError("Source configuration changed; using current source defaults")
            if not isinstance(data.get("workflows"), dict):
                raise TypeError("Invalid preference workflows")
            return data["workflows"]
        except (OSError, ValueError, TypeError) as error:
            self.messages.append(str(error))
            return {}

    def write(self, workflows):
        data = {"schema_version": 1, "configuration_id": self.configuration_id,
                "source_fingerprint": self.fingerprint, "workflows": workflows}
        text = json.dumps(data, indent=2, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=self.path.name + ".", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
