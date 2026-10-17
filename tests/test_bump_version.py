import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
bump_version = importlib.util.module_from_spec(_spec)
sys.modules["bump_version"] = bump_version
_spec.loader.exec_module(bump_version)


def _write_fixtures(tmp_path, version: str):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\nname = "x"\nversion = "{version}"\ndescription = "y"\n')

    server_json = tmp_path / "server.json"
    server_json.write_text(
        "{\n"
        f'  "version": "{version}",\n'
        '  "packages": [\n'
        '    {\n'
        f'      "version": "{version}"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    return pyproject, server_json


def test_current_version_reads_pyproject(tmp_path):
    pyproject, _ = _write_fixtures(tmp_path, "1.2.3")
    assert bump_version.current_version(pyproject) == "1.2.3"


@pytest.mark.parametrize(
    "arg, expected",
    [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0"), ("9.9.9", "9.9.9")],
)
def test_next_version(arg, expected):
    assert bump_version.next_version("1.2.3", arg) == expected


def test_next_version_rejects_unknown_keyword():
    with pytest.raises(bump_version.BumpError, match="unknown bump type"):
        bump_version.next_version("1.2.3", "sideways")


def test_next_version_rejects_same_version():
    with pytest.raises(bump_version.BumpError, match="already at"):
        bump_version.next_version("1.2.3", "1.2.3")


def test_next_version_rejects_malformed_explicit_version():
    # "1.2" matches neither a known bump keyword nor the X.Y.Z pattern, so
    # it's reported the same way as any other unrecognized argument.
    with pytest.raises(bump_version.BumpError, match="unknown bump type"):
        bump_version.next_version("1.2.3", "1.2")


def test_bump_updates_both_files(tmp_path):
    pyproject, server_json = _write_fixtures(tmp_path, "0.1.1")

    old, new = bump_version.bump(pyproject, server_json, "patch")

    assert (old, new) == ("0.1.1", "0.1.2")
    assert 'version = "0.1.2"' in pyproject.read_text()
    server_text = server_json.read_text()
    assert server_text.count('"version": "0.1.2"') == 2
    assert "0.1.1" not in server_text


def test_bump_leaves_files_untouched_on_bad_argument(tmp_path):
    pyproject, server_json = _write_fixtures(tmp_path, "0.1.1")

    with pytest.raises(bump_version.BumpError):
        bump_version.bump(pyproject, server_json, "sideways")

    assert 'version = "0.1.1"' in pyproject.read_text()
    assert server_json.read_text().count('"version": "0.1.1"') == 2


def test_bump_rejects_server_json_with_wrong_number_of_version_fields(tmp_path):
    pyproject, server_json = _write_fixtures(tmp_path, "0.1.1")
    server_json.write_text('{\n  "version": "0.1.1"\n}\n')

    with pytest.raises(bump_version.BumpError, match="expected exactly 2"):
        bump_version.bump(pyproject, server_json, "patch")

    # pyproject.toml must not be left bumped if server.json couldn't follow.
    assert 'version = "0.1.1"' in pyproject.read_text()
