import json
import subprocess

import pytest

from mcp_magento_audit import _process


def test_extract_json_parses_clean_json():
    assert _process.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_skips_leading_noise():
    noisy = "DEPRECATED: Scanning CSS/JS files is deprecated.\n" + json.dumps({"a": 1})
    assert _process.extract_json(noisy) == {"a": 1}


def test_extract_json_raises_when_no_json_object_present():
    with pytest.raises(json.JSONDecodeError):
        _process.extract_json("nothing but noise, no braces here")


def test_exec_prefix_is_empty_without_the_env_var(monkeypatch):
    monkeypatch.delenv(_process.EXEC_PREFIX_ENV_VAR, raising=False)
    assert _process.exec_prefix() == []


def test_exec_prefix_shell_splits_the_env_var(monkeypatch):
    monkeypatch.setenv(_process.EXEC_PREFIX_ENV_VAR, "docker compose exec -T app")
    assert _process.exec_prefix() == ["docker", "compose", "exec", "-T", "app"]


def _capture_subprocess_run(monkeypatch):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(_process.subprocess, "run", fake_run)
    return captured


def test_run_passes_args_through_unchanged_without_a_prefix(monkeypatch, tmp_path):
    monkeypatch.delenv(_process.EXEC_PREFIX_ENV_VAR, raising=False)
    captured = _capture_subprocess_run(monkeypatch)
    binary = tmp_path / "vendor" / "bin" / "phpcs"

    _process.run([str(binary), "--report=json"], tmp_path, 10)

    assert captured["args"] == [str(binary), "--report=json"]


def test_run_wraps_and_relativizes_paths_under_cwd_with_a_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv(_process.EXEC_PREFIX_ENV_VAR, "ddev exec --")
    captured = _capture_subprocess_run(monkeypatch)
    binary = tmp_path / "vendor" / "bin" / "phpcs"
    target = tmp_path / "app" / "code"

    _process.run([str(binary), "--report=json", str(target)], tmp_path, 10)

    assert captured["args"] == [
        "ddev",
        "exec",
        "--",
        "vendor/bin/phpcs",
        "--report=json",
        "app/code",
    ]


def test_run_leaves_a_flag_and_an_outside_absolute_path_alone_under_a_prefix(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(_process.EXEC_PREFIX_ENV_VAR, "ddev exec --")
    captured = _capture_subprocess_run(monkeypatch)
    outside = "/opt/homebrew/bin/composer"

    _process.run(["--format=json", outside], tmp_path, 10)

    assert captured["args"] == ["ddev", "exec", "--", "--format=json", outside]


def test_find_composer_prefers_composer_phar(tmp_path):
    (tmp_path / "composer.phar").touch()
    assert _process.find_composer(tmp_path) == tmp_path / "composer.phar"


def test_find_composer_falls_back_to_bare_name_under_a_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv(_process.EXEC_PREFIX_ENV_VAR, "ddev exec --")
    monkeypatch.setattr(_process.shutil, "which", lambda name: None)

    assert _process.find_composer(tmp_path) == _process.Path("composer")


def test_find_composer_uses_host_path_without_a_prefix(monkeypatch, tmp_path):
    monkeypatch.delenv(_process.EXEC_PREFIX_ENV_VAR, raising=False)
    monkeypatch.setattr(_process.shutil, "which", lambda name: "/opt/homebrew/bin/composer")

    assert _process.find_composer(tmp_path) == _process.Path("/opt/homebrew/bin/composer")
