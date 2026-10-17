import json
from pathlib import Path

from mcp_magento_audit.fleet import overview
from mcp_magento_audit.magento_versions import PhpRequirement

STORE = str(Path(__file__).parent / "fixtures" / "store")


def _write_compatible_project(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "composer.json").write_text(json.dumps({"require": {"php": "*"}}))
    (tmp_path / "composer.lock").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "name": "magento/product-community-edition",
                        "version": "2.4.9",
                        "require": {"php": "*"},
                    }
                ]
            }
        )
    )
    return tmp_path


def test_blocked_and_not_blocked_projects_are_both_counted(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="~8.1.0||~8.2.0||~8.3.0", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )

    compatible = _write_compatible_project(tmp_path / "compatible")

    result = overview([STORE, str(compatible)], target_php="8.3", target_magento="2.4.7")

    assert result.total == 2
    assert result.loaded == 2
    assert result.errored == 0
    assert result.blocked == 1
    assert result.not_blocked == 1

    by_path = {p.path: p for p in result.projects}
    store_overview = by_path[str(Path(STORE).resolve())]
    assert store_overview.blocked is True
    assert any(b.description == "legacy/module" for b in store_overview.blockers)

    compatible_overview = by_path[str(compatible.resolve())]
    assert compatible_overview.blocked is False
    assert compatible_overview.blockers == ()
    assert compatible_overview.magento_version == "2.4.9"


def test_invalid_project_is_reported_with_its_own_error_not_a_crash(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    compatible = _write_compatible_project(tmp_path / "compatible")
    missing = str(tmp_path / "does-not-exist")

    result = overview([missing, str(compatible)], target_php="8.3", target_magento="2.4.7")

    assert result.total == 2
    assert result.loaded == 1
    assert result.errored == 1
    assert result.not_blocked == 1

    by_path = {p.path: p for p in result.projects}
    assert by_path[missing].error is not None
    assert by_path[missing].blocked is False


def test_empty_paths_list_returns_empty_overview():
    result = overview([], target_php="8.3", target_magento="2.4.7")

    assert result.total == 0
    assert result.loaded == 0
    assert result.errored == 0
    assert result.blocked == 0
    assert result.not_blocked == 0
    assert result.projects == ()
