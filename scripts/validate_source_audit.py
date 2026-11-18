"""Bounded offline source-audit gates with durable logs and JSON evidence.

Run in the existing environment. Ruff uses --fix; changes stop acceptance before tests.
No dependency installation, Git mutation or hardware permission is performed.
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
    result["interrupted"] = False
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
            except KeyboardInterrupt:
                stop_tree(process)
                result["returncode"] = process.returncode
                result["timed_out"] = False
                result["interrupted"] = True
    result["passed"] = (
        result["returncode"] == 0
        and not result["timed_out"]
        and not result["interrupted"]
    )
    print(f"{'PASS' if result['passed'] else 'FAIL'} {label}: {log}", flush=True)
    return result


def counts(path):
    """Validate pytest XML rather than accepting an exit code alone."""
    root = ElementTree.parse(path).getroot()
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Not a JUnit testsuite document")
    suites = [suite for suite in root.iter("testsuite") if not list(suite.iterfind("testsuite"))]
    if not suites:
        raise ValueError("No test suites recorded")
    total = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        values = {name: int(suite.get(name, "0")) for name in total}
        if any(value < 0 for value in values.values()):
            raise ValueError("Negative JUnit count")
        if sum(values[name] for name in ("failures", "errors", "skipped")) > values["tests"]:
            raise ValueError("Inconsistent JUnit counts")
        for name in total:
            total[name] += values[name]
    if total["tests"] == 0:
        raise ValueError("No tests executed")
    return total


def check_pytest_result(result, xml):
    """Fail closed on missing/broken evidence, failures, errors or any skips."""
    try:
        result["counts"] = counts(xml)
    except (OSError, ElementTree.ParseError, ValueError) as error:
        result["passed"] = False
        result["reason"] = f"Invalid or missing pytest XML: {error}"
        return
    if any(result["counts"][name] for name in ("failures", "errors", "skipped")):
        result["passed"] = False
        result["reason"] = "Failures, errors or skips do not establish offline acceptance"


def source_hashes():
    """Detect Ruff/test edits, including newly created Python files."""
    paths = {
        path for folder in ("src", "tests", "scripts")
        for path in (ROOT / folder).rglob("*.py")
    }
    paths.update(ROOT / name for name in ("pyproject.toml", "uv.lock") if (ROOT / name).is_file())
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=["all", "lint", "core", "widgets", "full"], default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT.parent / f"labtools-source-audit-{stamp}"
    output = output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("Evidence output must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MPLBACKEND"] = "Agg"
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
        "source_sha256": source_hashes(),
        "environment": {"QT_QPA_PLATFORM": "offscreen", "MPLBACKEND": "Agg"},
        "hardware_permission": False,
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
            command, limit = [
                "-m", "ruff", "check", "--fix", "src", "tests",
                "scripts/validate_source_audit.py",
            ], 60
        else:
            xml = output / f"{gate}.xml"
            tests = CORE_TESTS if gate == "core" else WIDGET_TESTS
            command = ["-m", "pytest", "-vv", "-ra", f"--junitxml={xml}"]
            command += ["-m", "not hardware", "tests"] if gate == "full" else tests
            limit = 600 if gate == "full" else 240
        result = execute(gate, command, output, env, limit)
        if gate != "lint":
            check_pytest_result(result, xml)
        after = source_hashes()
        changed = sorted(
            name for name in set(evidence["source_sha256"]) | set(after)
            if evidence["source_sha256"].get(name) != after.get(name)
        )
        if changed:
            result["passed"] = False
            result["changed_paths"] = changed
            result["reason"] = "Source changed during validation; review edits before rerunning"
        evidence["results"].append(result)
        if not result["passed"]:
            break
    completed = [r["gate"] for r in evidence["results"] if r["gate"] in selected and r["passed"]]
    passed = completed == selected
    evidence["source_sha256_after"] = source_hashes()
    evidence["all_gates_passed"] = args.gate == "all" and passed
    evidence["requested_gates_passed"] = passed
    (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"EVIDENCE: {output / 'results.json'}", flush=True)
    print("ALL OFFLINE GATES PASSED" if evidence["all_gates_passed"] else "FULL ACCEPTANCE NOT ESTABLISHED", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
