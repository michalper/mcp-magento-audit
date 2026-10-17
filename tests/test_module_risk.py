import json
import subprocess

from mcp_magento_audit import module_risk as mr


def _touch_binary(project_path, relative):
    binary = project_path / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
    return binary


def _report(entries: dict) -> str:
    return json.dumps({"files": entries})


def test_no_app_code_and_no_config_skips_both_tools(tmp_path):
    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is True
    assert result.phpcs.target == "app/code"
    assert result.phpstan.scanned is False
    assert "phpstan.neon" in result.phpstan.reason
    assert result.issue_count == 0


def test_missing_phpcs_binary_is_not_scanned(tmp_path):
    (tmp_path / "app" / "code").mkdir(parents=True)

    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is False
    assert "vendor/bin/phpcs" in result.phpcs.reason


def test_app_code_without_own_phpcs_config_uses_magento2_standard(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    captured: dict = {}

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        captured["args"] = args
        file_path = tmp_path / "app" / "code" / "Vendor" / "Module" / "Model.php"
        messages = [
            {
                "message": "Class \\Foo is deprecated",
                "source": "Magento2.Legacy.DeprecatedClasses",
                "type": "ERROR",
                "line": 42,
            }
        ]
        return subprocess.CompletedProcess(
            args, 2, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert "--standard=Magento2" in captured["args"]
    assert result.phpcs.scanned is True
    assert result.phpcs.target == "app/code"
    phpcs_issues = [i for i in result.issues if i.tool == "phpcs"]
    assert len(phpcs_issues) == 1
    issue = phpcs_issues[0]
    assert issue.file == "app/code/Vendor/Module/Model.php"
    assert issue.severity == "error"
    assert issue.source == "Magento2.Legacy.DeprecatedClasses"
    assert issue.line == 42


def test_project_with_own_phpcs_config_is_used_as_is(tmp_path, monkeypatch):
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    captured: dict = {}

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert "--standard=Magento2" not in captured["args"]
    assert result.phpcs.scanned is True
    assert result.phpcs.target == "phpcs.xml.dist"


def test_phpcs_report_with_leading_deprecation_noise_still_parses(tmp_path, monkeypatch):
    """Real-world regression: phpcs prints "DEPRECATED: Scanning CSS/JS
    files..." notices on stdout *before* the JSON report when a project's
    own ruleset still has CSS sniffs enabled (confirmed against a real
    magento-coding-standard run) — must not be mistaken for an invalid
    report."""
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        file_path = tmp_path / "Model" / "Thing.php"
        messages = [{"message": "real issue", "type": "ERROR", "line": 5}]
        noise = "DEPRECATED: Scanning CSS/JS files is deprecated.\nThe Magento2.Less.X sniff...\n"
        return subprocess.CompletedProcess(
            args, 2, stdout=noise + _report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is True
    phpcs_issues = [i for i in result.issues if i.tool == "phpcs"]
    assert any(i.message == "real issue" for i in phpcs_issues)


def test_invalid_phpcs_output_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        stderr = "the Magento2 coding standard is not installed"
        return subprocess.CompletedProcess(args, 3, stdout="", stderr=stderr)

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is False
    assert "not installed" in result.phpcs.reason


def test_phpcs_execution_failure_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "app" / "code").mkdir(parents=True)
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    def fake_run(args, cwd):
        raise subprocess.TimeoutExpired(cmd=args, timeout=mr.TIMEOUT_SECONDS)

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is False
    assert "could not run phpcs" in result.phpcs.reason
    assert result.phpstan.scanned is False


def test_no_phpstan_config_skips_without_guessing(tmp_path):
    _touch_binary(tmp_path, "vendor/bin/phpstan")

    result = mr.scan(tmp_path)

    assert result.phpstan.scanned is False
    assert "phpstan.neon" in result.phpstan.reason


def test_missing_phpstan_binary_is_not_scanned(tmp_path):
    (tmp_path / "phpstan.neon").write_text("parameters:\n    level: max\n")

    result = mr.scan(tmp_path)

    assert result.phpstan.scanned is False
    assert "vendor/bin/phpstan" in result.phpstan.reason


def test_phpstan_with_own_config_reports_issues(tmp_path, monkeypatch):
    (tmp_path / "phpstan.neon").write_text("parameters:\n    level: max\n")
    _touch_binary(tmp_path, "vendor/bin/phpstan")

    captured: dict = {}

    def fake_run(args, cwd):
        captured["args"] = args
        file_path = tmp_path / "Model" / "Thing.php"
        messages = [
            {
                "message": "Method Thing::bar() has invalid return type Bar.",
                "line": 10,
                "identifier": "class.notFound",
            }
        ]
        return subprocess.CompletedProcess(
            args, 1, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert "analyse" in captured["args"]
    assert f"--memory-limit={mr.PHPSTAN_MEMORY_LIMIT}" in captured["args"]
    assert result.phpstan.scanned is True
    assert result.phpstan.target == "phpstan.neon"
    phpstan_issues = [i for i in result.issues if i.tool == "phpstan"]
    assert len(phpstan_issues) == 1
    issue = phpstan_issues[0]
    assert issue.file == "Model/Thing.php"
    assert issue.severity == "error"
    assert issue.source == "class.notFound"
    assert issue.line == 10


def test_invalid_phpstan_output_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "phpstan.neon").write_text("parameters:\n    level: max\n")
    _touch_binary(tmp_path, "vendor/bin/phpstan")

    def fake_run(args, cwd):
        stderr = "Fatal error: config invalid"
        return subprocess.CompletedProcess(args, 255, stdout="", stderr=stderr)

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.phpstan.scanned is False
    assert "config invalid" in result.phpstan.reason


def test_no_rector_config_skips_without_guessing(tmp_path):
    _touch_binary(tmp_path, "vendor/bin/rector")

    result = mr.scan(tmp_path)

    assert result.rector.scanned is False
    assert "rector.php" in result.rector.reason


def test_missing_rector_binary_is_not_scanned(tmp_path):
    (tmp_path / "rector.php").write_text("<?php return [];\n")

    result = mr.scan(tmp_path)

    assert result.rector.scanned is False
    assert "vendor/bin/rector" in result.rector.reason


def test_rector_uses_own_config_as_is_and_reports_warnings(tmp_path, monkeypatch):
    (tmp_path / "rector.php").write_text("<?php return [];\n")
    _touch_binary(tmp_path, "vendor/bin/rector")

    captured: dict = {}

    def fake_run(args, cwd):
        captured["args"] = args
        report = {
            "totals": {"changed_files": 1, "errors": 0},
            "file_diffs": [
                {
                    "file": "Model/Thing.php",
                    "diff": "...",
                    "changes": [{"rector": "Rector\\DeadCode\\Rector\\Foo", "line": 7}],
                }
            ],
            "changed_files": ["Model/Thing.php"],
        }
        return subprocess.CompletedProcess(args, 2, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert "--config=" not in " ".join(captured["args"])
    assert result.rector.scanned is True
    assert result.rector.target == "rector.php"
    rector_issues = [i for i in result.issues if i.tool == "rector"]
    assert len(rector_issues) == 1
    issue = rector_issues[0]
    assert issue.file == "Model/Thing.php"
    assert issue.line == 7
    assert issue.severity == "warning"
    assert issue.source == "Rector\\DeadCode\\Rector\\Foo"


def test_invalid_rector_output_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "rector.php").write_text("<?php return [];\n")
    _touch_binary(tmp_path, "vendor/bin/rector")

    def fake_run(args, cwd):
        return subprocess.CompletedProcess(args, 255, stdout="", stderr="Fatal error: boom")

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.rector.scanned is False
    assert "boom" in result.rector.reason


def test_issues_are_capped_per_tool_but_issue_count_stays_true(tmp_path, monkeypatch):
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    total = mr.MAX_STORED_ISSUES_PER_TOOL + 10

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        file_path = tmp_path / "Model" / "Thing.php"
        messages = [
            {"message": f"issue {i}", "source": "Magento2.Legacy", "type": "ERROR", "line": i}
            for i in range(total)
        ]
        return subprocess.CompletedProcess(
            args, 2, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.issue_count == total
    assert len(result.issues) == mr.MAX_STORED_ISSUES_PER_TOOL


def test_cap_keeps_errors_over_warnings(tmp_path, monkeypatch):
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        file_path = tmp_path / "Model" / "Thing.php"
        warnings = [
            {"message": f"warning {i}", "type": "WARNING", "line": i}
            for i in range(mr.MAX_STORED_ISSUES_PER_TOOL)
        ]
        errors = [{"message": "real error", "type": "ERROR", "line": 999}]
        messages = warnings + errors
        return subprocess.CompletedProcess(
            args, 2, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert any(i.message == "real error" for i in result.issues)


def test_phpstan_top_level_errors_are_surfaced(tmp_path, monkeypatch):
    (tmp_path / "phpstan.neon").write_text("parameters:\n    level: max\n")
    _touch_binary(tmp_path, "vendor/bin/phpstan")

    def fake_run(args, cwd):
        report = json.dumps({"totals": {"errors": 1}, "errors": ["Internal error: boom"]})
        return subprocess.CompletedProcess(args, 1, stdout=report, stderr="")

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    phpstan_issues = [i for i in result.issues if i.tool == "phpstan"]
    assert any("boom" in i.message for i in phpstan_issues)


def test_phpcs_message_with_null_line_does_not_crash(tmp_path, monkeypatch):
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    _touch_binary(tmp_path, "vendor/bin/phpcs")

    def fake_run(args, cwd):
        if "phpstan" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=_report({}), stderr="")
        file_path = tmp_path / "Model" / "Thing.php"
        messages = [{"message": "file-level issue", "type": "ERROR", "line": None}]
        return subprocess.CompletedProcess(
            args, 2, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.phpcs.scanned is True
    assert any(i.line == 0 for i in result.issues)


def test_combined_issue_count_includes_both_tools(tmp_path, monkeypatch):
    (tmp_path / "phpcs.xml.dist").write_text("<ruleset><rule ref='Magento2'/></ruleset>")
    (tmp_path / "phpstan.neon").write_text("parameters:\n    level: max\n")
    _touch_binary(tmp_path, "vendor/bin/phpcs")
    _touch_binary(tmp_path, "vendor/bin/phpstan")

    def fake_run(args, cwd):
        file_path = tmp_path / "Model" / "Thing.php"
        if "phpstan" in args[0]:
            messages = [{"message": "phpstan issue", "line": 1, "identifier": "x"}]
        else:
            messages = [
                {
                    "message": "phpcs issue",
                    "source": "Magento2.Legacy",
                    "type": "WARNING",
                    "line": 2,
                }
            ]
        return subprocess.CompletedProcess(
            args, 1, stdout=_report({str(file_path): {"messages": messages}}), stderr=""
        )

    monkeypatch.setattr(mr, "_run", fake_run)

    result = mr.scan(tmp_path)

    assert result.issue_count == 2
    assert {i.tool for i in result.issues} == {"phpcs", "phpstan"}
