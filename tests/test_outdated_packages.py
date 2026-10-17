import json
import subprocess

from mcp_magento_audit import _process
from mcp_magento_audit import outdated_packages as op


def _touch_binary(project_path, relative):
    binary = project_path / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
    return binary


def _report(installed: list) -> str:
    return json.dumps({"installed": installed})


def test_no_composer_lock_is_not_scanned(tmp_path):
    result = op.check(tmp_path)

    assert result.scanned is False
    assert "composer.lock" in result.reason
    assert result.outdated_count == 0


def test_missing_composer_binary_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: None)

    result = op.check(tmp_path)

    assert result.scanned is False
    assert "composer not found" in result.reason


def test_composer_phar_in_project_is_preferred_over_path(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    phar = _touch_binary(tmp_path, "composer.phar")

    captured: dict = {}

    def fake_run(args, cwd):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=_report([]), stderr="")

    monkeypatch.setattr(op, "_run", fake_run)
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    result = op.check(tmp_path)

    assert captured["args"][0] == str(phar)
    assert "outdated" in captured["args"]
    assert result.scanned is True
    assert result.outdated_count == 0


def test_outdated_packages_are_parsed(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    installed = [
        {
            "name": "vendor/module",
            "version": "1.0.0",
            "latest": "1.2.0",
            "latest-status": "semver-safe-update",
        }
    ]

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 0, stdout=_report(installed), stderr="")

    monkeypatch.setattr(op, "_run", fake_run)

    result = op.check(tmp_path)

    assert result.scanned is True
    assert result.outdated_count == 1
    package = result.packages[0]
    assert package.package == "vendor/module"
    assert package.current == "1.0.0"
    assert package.latest == "1.2.0"
    assert package.status == "semver-safe-update"


def test_invalid_report_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 255, stdout="", stderr="composer: command failed")

    monkeypatch.setattr(op, "_run", fake_run)

    result = op.check(tmp_path)

    assert result.scanned is False
    assert "command failed" in result.reason


def test_timeout_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    def fake_run(args, cwd):
        raise subprocess.TimeoutExpired(cmd=args, timeout=op.TIMEOUT_SECONDS)

    monkeypatch.setattr(op, "_run", fake_run)

    result = op.check(tmp_path)

    assert result.scanned is False
    assert "could not run composer outdated" in result.reason


def test_packages_beyond_cap_are_truncated_but_count_is_true_total(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    installed = [
        {"name": f"vendor/module{i}", "version": "1.0.0", "latest": "1.1.0", "latest-status": "x"}
        for i in range(op.MAX_STORED_PACKAGES + 5)
    ]

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 0, stdout=_report(installed), stderr="")

    monkeypatch.setattr(op, "_run", fake_run)

    result = op.check(tmp_path)

    assert result.outdated_count == op.MAX_STORED_PACKAGES + 5
    assert len(result.packages) == op.MAX_STORED_PACKAGES
