import json
import subprocess
from pathlib import Path

from mcp_magento_audit import php_compatibility as pc


def _touch_binary(project_path, relative):
    binary = project_path / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
    return binary


def test_php_single_quoted_escapes_quotes_and_backslashes():
    assert pc._php_single_quoted(r"o'brien\shop") == r"o\'brien\\shop"


def test_config_with_apostrophe_in_path_escapes_it(tmp_path, monkeypatch):
    project_path = tmp_path / "o'brien-shop"
    (project_path / "app" / "code").mkdir(parents=True)
    _touch_binary(project_path, "vendor/bin/rector")

    captured: dict = {}

    def fake_run(args, cwd):
        config_arg = next(a for a in args if a.startswith("--config="))
        captured["content"] = Path(config_arg.removeprefix("--config=")).read_text()
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"totals": {}}), stderr="")

    monkeypatch.setattr(pc, "_run", fake_run)

    result = pc.check(project_path, "8.3")

    assert result.checked is True
    assert "o\\'brien" in captured["content"]
    assert "o'brien-shop/app/code'])" not in captured["content"]


def test_no_app_code_is_trivially_checked(tmp_path):
    result = pc.check(tmp_path, "8.3")
    assert result.checked is True
    assert result.changed_file_count == 0


def test_unsupported_php_version_is_not_checked(tmp_path):
    result = pc.check(tmp_path, "9.9")
    assert result.checked is False
    assert "9.9" in result.reason


def test_missing_rector_binary_is_not_checked(tmp_path):
    (tmp_path / "app" / "code").mkdir(parents=True)

    result = pc.check(tmp_path, "8.3")

    assert result.checked is False
    assert "vendor/bin/rector" in result.reason


def test_reports_changes_from_dry_run(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/rector")

    captured: dict = {}

    def fake_run(args, cwd):
        captured["args"] = args
        report = {
            "totals": {"changed_files": 1, "errors": 0},
            "file_diffs": [
                {
                    "file": "app/code/Foo.php",
                    "diff": "...",
                    "applied_rectors": ["Rector\\Php80\\Rector\\Class_\\SomeRector"],
                    "changes": [{"rector": "Rector\\Php80\\Rector\\Class_\\SomeRector", "line": 3}],
                }
            ],
            "changed_files": ["app/code/Foo.php"],
        }
        return subprocess.CompletedProcess(args, 2, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(pc, "_run", fake_run)

    result = pc.check(tmp_path, "8.3")

    assert "--config=" in " ".join(captured["args"])
    assert any(a == "--output-format=json" for a in captured["args"])
    assert result.checked is True
    assert result.changed_file_count == 1
    assert result.changes[0].file == "app/code/Foo.php"
    assert result.changes[0].line == 3
    assert result.changes[0].rector_rule == "Rector\\Php80\\Rector\\Class_\\SomeRector"


def test_no_changes_reports_empty(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/rector")

    def fake_run(args, cwd):
        report = {"totals": {"changed_files": 0, "errors": 0}}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(pc, "_run", fake_run)

    result = pc.check(tmp_path, "8.3")

    assert result.checked is True
    assert result.changed_file_count == 0
    assert result.changes == ()


def test_invalid_rector_output_is_not_checked(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/rector")

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 255, stdout="", stderr="Fatal error: boom")

    monkeypatch.setattr(pc, "_run", fake_run)

    result = pc.check(tmp_path, "8.3")

    assert result.checked is False
    assert "boom" in result.reason


def test_execution_failure_is_not_checked(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/rector")

    def fake_run(args, cwd):
        raise subprocess.TimeoutExpired(cmd=args, timeout=pc.TIMEOUT_SECONDS)

    monkeypatch.setattr(pc, "_run", fake_run)

    result = pc.check(tmp_path, "8.3")

    assert result.checked is False
    assert "could not run rector" in result.reason
