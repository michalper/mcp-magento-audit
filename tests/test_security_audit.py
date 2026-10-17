import json
import subprocess

from mcp_magento_audit import _process
from mcp_magento_audit import security_audit as sa


def _touch_binary(project_path, relative):
    binary = project_path / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
    return binary


def _report(advisories: dict) -> str:
    return json.dumps({"advisories": advisories, "abandoned": {}})


def test_no_composer_lock_is_not_scanned(tmp_path):
    result = sa.audit(tmp_path)

    assert result.scanned is False
    assert "composer.lock" in result.reason
    assert result.advisory_count == 0


def test_missing_composer_binary_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: None)

    result = sa.audit(tmp_path)

    assert result.scanned is False
    assert "composer not found" in result.reason


def test_composer_phar_in_project_is_preferred_over_path(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    phar = _touch_binary(tmp_path, "composer.phar")

    captured: dict = {}

    def fake_run(args, cwd):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")

    monkeypatch.setattr(sa, "_run", fake_run)
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    result = sa.audit(tmp_path)

    assert captured["args"][0] == str(phar)
    assert result.scanned is True
    assert result.advisory_count == 0


def test_advisories_are_parsed_per_package(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    advisories = {
        "vendor/module": [
            {
                "advisoryId": "PKSA-abcd-1234",
                "title": "Remote code execution",
                "cve": "CVE-2024-12345",
                "severity": "critical",
                "link": "https://example.test/advisory",
            }
        ]
    }

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 1, stdout=_report(advisories), stderr="")

    monkeypatch.setattr(sa, "_run", fake_run)

    result = sa.audit(tmp_path)

    assert result.scanned is True
    assert result.advisory_count == 1
    advisory = result.advisories[0]
    assert advisory.package == "vendor/module"
    assert advisory.cve == "CVE-2024-12345"
    assert advisory.severity == "critical"
    assert advisory.title == "Remote code execution"


def test_invalid_report_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 255, stdout="", stderr="composer: command failed")

    monkeypatch.setattr(sa, "_run", fake_run)

    result = sa.audit(tmp_path)

    assert result.scanned is False
    assert "command failed" in result.reason


def test_timeout_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    def fake_run(args, cwd):
        raise subprocess.TimeoutExpired(cmd=args, timeout=sa.TIMEOUT_SECONDS)

    monkeypatch.setattr(sa, "_run", fake_run)

    result = sa.audit(tmp_path)

    assert result.scanned is False
    assert "could not run composer audit" in result.reason


def test_advisories_beyond_cap_are_truncated_but_count_is_true_total(tmp_path, monkeypatch):
    (tmp_path / "composer.lock").write_text("{}")
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/usr/local/bin/composer")

    entries = [
        {"advisoryId": f"PKSA-{i}", "title": f"issue {i}", "cve": None, "link": ""}
        for i in range(sa.MAX_STORED_ADVISORIES + 5)
    ]

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(
            args, 1, stdout=_report({"vendor/module": entries}), stderr=""
        )

    monkeypatch.setattr(sa, "_run", fake_run)

    result = sa.audit(tmp_path)

    assert result.advisory_count == sa.MAX_STORED_ADVISORIES + 5
    assert len(result.advisories) == sa.MAX_STORED_ADVISORIES
