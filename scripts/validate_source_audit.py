"""Bounded offline source-audit gates with durable logs and JSON evidence.

Run with the existing labtools environment; never installs dependencies or mutates Git.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
PYTHON_FILES = [
    "src/labtools/gui/hyperspectral_controller.py",
    "src/labtools/gui/hyperspectral_gui.py",
    "src/labtools/measurements/hyperspectral.py",
    "tests/test_audit_hyperspectral_regressions.py",
    "tests/test_audit_hyperspectral_worker.py",
    "tests/test_audit_hyperspectral_lifecycle.py",
    "scripts/validate_source_audit.py",
]
CORE_TESTS = [
    "tests/test_audit_hyperspectral_regressions.py",
    "tests/test_audit_hyperspectral_lifecycle.py",
    "tests/test_hyperspectral_service.py",
    "tests/test_hyperspectral_failure_matrix.py",
    "tests/test_hyperspectral_view.py",
    "tests/test_hyperspectral_presentation_interaction.py",
    "tests/test_measurements_hyperspectral.py",
    "tests/test_measurements_hyperspectral_contract.py",
]
WIDGET_TESTS = [
    "tests/test_audit_hyperspectral_worker.py",
    "tests/test_hyperspectral_gui.py",
]


def stop_tree(process):
    """Stop only the validation process tree created by this runner."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False, capture_output=True, timeout=15,
            )
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


def execute(label, args, output, env, limit):
    command = [sys.executable, *args]
    log = output / f"{label}.log"
    print(f"RUN {label}: {subprocess.list2cmdline(command)}", flush=True)
    result = {"gate": label, "command": command, "limit_seconds": limit, "log": str(log)}
    with log.open("w", encoding="utf-8") as handle:
        options = {"start_new_session": True} if os.name != "nt" else {}
        with subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=handle,
            stderr=subprocess.STDOUT, **options,
        ) as process:
            try:
                result["returncode"] = process.wait(timeout=limit)
                result["timed_out"] = False
            except subprocess.TimeoutExpired:
                stop_tree(process)
                result["returncode"] = process.returncode
                result["timed_out"] = True
    result["passed"] = result["returncode"] == 0 and not result["timed_out"]
    print(f"{'PASS' if result['passed'] else 'FAIL'} {label}: {log}", flush=True)
    return result


def counts(path):
    suites = ElementTree.parse(path).getroot().iter("testsuite")
    total = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for name in total:
            total[name] += int(suite.get(name, "0"))
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=["all", "lint", "core", "widgets", "full"], default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / ".labtools-validation" / f"source-audit-{stamp}"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    versions = {}
    for package in ("pytest", "PyQt6", "ruff", "numpy", "matplotlib"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    evidence = {
        "created_utc": stamp, "root": str(ROOT), "python": sys.version,
        "executable": sys.executable, "versions": versions, "requested_gate": args.gate,
        "results": [], "all_gates_passed": False, "hardware_acceptance": "not performed",
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in PYTHON_FILES
        },
    }
    selected = ["lint", "core", "widgets", "full"] if args.gate == "all" else [args.gate]
    for gate in selected:
        if gate in {"core", "widgets"}:
            module = "PyQt6.QtCore" if gate == "core" else "PyQt6.QtWidgets"
            probe = execute(f"{gate}-prerequisites", ["-c", f"import {module}"], output, env, 60)
            evidence["results"].append(probe)
            if not probe["passed"]:
                break
        if gate == "lint":
            command, limit = ["-m", "ruff", "check", *PYTHON_FILES], 60
        else:
            xml = output / f"{gate}.xml"
            tests = CORE_TESTS if gate == "core" else WIDGET_TESTS
            command = ["-m", "pytest", "-q", f"--junitxml={xml}"]
            command += ["-m", "not hardware"] if gate == "full" else tests
            limit = 600 if gate == "full" else 240
        result = execute(gate, command, output, env, limit)
        if gate != "lint":
            if not xml.exists():
                result["passed"] = False
                result["reason"] = "Missing pytest XML; completion not established"
            else:
                result["counts"] = counts(xml)
                if gate != "full" and result["counts"]["skipped"]:
                    result["passed"] = False
                    result["reason"] = "Targeted skips are not acceptance"
        evidence["results"].append(result)
        if not result["passed"]:
            break
    completed = [r["gate"] for r in evidence["results"] if r["gate"] in selected and r["passed"]]
    passed = completed == selected
    evidence["all_gates_passed"] = args.gate == "all" and passed
    evidence["requested_gates_passed"] = passed
    (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"EVIDENCE: {output / 'results.json'}", flush=True)
    print("ALL OFFLINE GATES PASSED" if evidence["all_gates_passed"] else "FULL ACCEPTANCE NOT ESTABLISHED", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
