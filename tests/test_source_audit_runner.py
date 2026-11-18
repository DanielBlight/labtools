"""Offline runner acceptance contracts; never run the repository test suite."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/validate_source_audit.py"
    spec = importlib.util.spec_from_file_location("isolated_source_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_xml(path, tests=2, failures=0, errors=0, skipped=0):
    path.write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"/></testsuites>', encoding="utf-8"
    )


@pytest.mark.parametrize(
    "content",
    [
        "<broken", "<testsuites/>", '<testsuite tests="0"/>',
        '<testsuite tests="-1"/>', '<testsuite tests="nan"/>',
        '<testsuite tests="1" skipped="2"/>', '<unrelated tests="3"/>',
    ],
)
def test_bad_xml_cannot_establish_acceptance(runner, tmp_path, content):
    xml = tmp_path / "results.xml"
    xml.write_text(content, encoding="utf-8")
    result = {"passed": True}
    runner.check_pytest_result(result, xml)
    assert not result["passed"]
    assert "Invalid or missing" in result["reason"]


def test_missing_xml_cannot_establish_acceptance(runner, tmp_path):
    result = {"passed": True}
    runner.check_pytest_result(result, tmp_path / "missing.xml")
    assert not result["passed"]


@pytest.mark.parametrize("field", ["failures", "errors", "skipped"])
def test_xml_failures_errors_and_skips_fail_acceptance(runner, tmp_path, field):
    xml = tmp_path / "results.xml"
    write_xml(xml, **{field: 1})
    result = {"passed": True}
    runner.check_pytest_result(result, xml)
    assert not result["passed"]
    assert result["counts"][field] == 1


def test_success_xml_does_not_override_failed_process(runner, tmp_path):
    xml = tmp_path / "results.xml"
    write_xml(xml)
    result = {"passed": False, "timed_out": True}
    runner.check_pytest_result(result, xml)
    assert not result["passed"]


def test_nested_suites_not_double_counted(runner, tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuites><testsuite tests="2"><testsuite tests="2"/>'
        '</testsuite></testsuites>', encoding="utf-8"
    )
    assert runner.counts(xml) == {"tests": 2, "failures": 0, "errors": 0, "skipped": 0}


@pytest.fixture
def fake_repo(runner, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src/example.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    return root


def test_hashes_detect_new_modified_and_deleted_files(runner, fake_repo):
    first = runner.source_hashes()
    source = fake_repo / "src/example.py"
    source.write_text("value = 2\n", encoding="utf-8")
    assert first != runner.source_hashes()
    source.unlink()
    assert "src/example.py" not in runner.source_hashes()
    (fake_repo / "src/new.py").write_text("", encoding="utf-8")
    assert "src/new.py" in runner.source_hashes()


def test_internal_output_rejected_before_execution(runner, fake_repo, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runner", "--output", str(fake_repo / "logs")])
    with pytest.raises(SystemExit) as caught:
        runner.main()
    assert caught.value.code == 2
    assert not (fake_repo / "logs").exists()


@pytest.mark.parametrize("mode", ["pass", "skip", "malformed", "missing", "ruff_edit"])
def test_all_gate_records_evidence_and_stops_on_incomplete_acceptance(
    runner, fake_repo, tmp_path, monkeypatch, mode
):
    output = tmp_path / "evidence"
    calls = []
    parent_env = dict(os.environ)

    def execute(label, args, destination, env, limit):
        calls.append((label, args))
        assert env["QT_QPA_PLATFORM"] == "offscreen"
        assert env["MPLBACKEND"] == "Agg"
        assert "--run-hardware" not in args
        if label == "lint":
            assert args[:4] == ["-m", "ruff", "check", "--fix"]
            assert "src" in args and "tests" in args
            if mode == "ruff_edit":
                (fake_repo / "src/example.py").write_text("changed = True\n", encoding="utf-8")
        if label in {"core", "widgets", "full"}:
            xml = destination / f"{label}.xml"
            if label == "full":
                assert args[-3:] == ["-m", "not hardware", "tests"]
                assert "-vv" in args
            if label == "full" and mode == "malformed":
                xml.write_text("broken", encoding="utf-8")
            elif not (label == "full" and mode == "missing"):
                write_xml(xml, skipped=int(label == "full" and mode == "skip"))
        return {"gate": label, "passed": True, "returncode": 0, "timed_out": False}

    monkeypatch.setattr(runner, "execute", execute)
    monkeypatch.setattr(sys, "argv", ["runner", "--gate", "all", "--output", str(output)])
    code = runner.main()
    report = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert (code == 0) == (mode == "pass")
    assert report["all_gates_passed"] == (mode == "pass")
    assert report["hardware_acceptance"] == "not performed"
    assert dict(os.environ) == parent_env
    if mode == "ruff_edit":
        assert [label for label, _ in calls] == ["lint"]
        assert report["results"][0]["changed_paths"] == ["src/example.py"]


def test_execute_retains_raw_output_and_nonzero_exit(runner, fake_repo, tmp_path):
    result = runner.execute(
        "child", ["-c", "print('diagnostic'); raise SystemExit(3)"],
        tmp_path, dict(os.environ), 10,
    )
    assert result["returncode"] == 3
    assert not result["passed"]
    assert "diagnostic" in (tmp_path / "child.log").read_text(encoding="utf-8")


def test_timeout_is_not_acceptance(runner, fake_repo, tmp_path):
    result = runner.execute(
        "timeout", ["-c", "import time; time.sleep(30)"],
        tmp_path, dict(os.environ), 0.1,
    )
    assert result["timed_out"]
    assert not result["passed"]


def test_interrupt_stops_only_owned_child_and_records_incomplete(runner, fake_repo, tmp_path, monkeypatch):
    stopped = []

    class Child:
        returncode = -1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def wait(self, timeout):
            raise KeyboardInterrupt

    child = Child()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(runner, "stop_tree", stopped.append)
    result = runner.execute("interrupt", ["-c", "pass"], tmp_path, dict(os.environ), 10)
    assert stopped == [child]
    assert result["interrupted"]
    assert not result["passed"]
