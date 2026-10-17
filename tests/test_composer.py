import json
from pathlib import Path

import pytest

from mcp_magento_audit.composer import ProjectError, load_project

STORE = Path(__file__).parent / "fixtures" / "sklep"


def _write(tmp_path, composer_json, composer_lock):
    (tmp_path / "composer.json").write_text(json.dumps(composer_json))
    (tmp_path / "composer.lock").write_text(json.dumps(composer_lock))


def test_reads_magento_version_and_php_requirement():
    project = load_project(STORE)
    assert project.magento_version == "2.4.7"
    assert project.project_php_requirement == "~8.2.0||~8.3.0"


def test_counts_packages_from_both_groups():
    assert len(load_project(STORE).packages) == 3


def test_detects_abandoned_package():
    abandoned = [p.name for p in load_project(STORE).abandoned_packages]
    assert abandoned == ["stary/modul"]


def test_php_requirement_of_specific_package():
    package = next(p for p in load_project(STORE).packages if p.name == "stary/modul")
    assert package.php_requirement == "^7.4"


def test_missing_directory_raises_error():
    with pytest.raises(ProjectError, match="is not a directory"):
        load_project("/no/such/directory")


def test_missing_composer_json_raises_error(tmp_path):
    with pytest.raises(ProjectError, match="missing file composer.json"):
        load_project(tmp_path)


def test_missing_composer_lock_raises_error(tmp_path):
    (tmp_path / "composer.json").write_text("{}")
    with pytest.raises(ProjectError, match="missing file composer.lock"):
        load_project(tmp_path)


def test_invalid_json_raises_error(tmp_path):
    (tmp_path / "composer.json").write_text("not json")
    (tmp_path / "composer.lock").write_text("{}")
    with pytest.raises(ProjectError, match="is not valid JSON"):
        load_project(tmp_path)


def test_non_object_json_raises_error(tmp_path):
    (tmp_path / "composer.json").write_text("[]")
    (tmp_path / "composer.lock").write_text("{}")
    with pytest.raises(ProjectError, match="does not contain a JSON object"):
        load_project(tmp_path)


def test_package_abandoned_via_own_flag(tmp_path):
    _write(
        tmp_path,
        {"require": {}},
        {"packages": [{"name": "foo/bar", "version": "1.0.0", "abandoned": True}]},
    )
    project = load_project(tmp_path)
    assert [p.name for p in project.abandoned_packages] == ["foo/bar"]


def test_project_without_magento_has_no_magento_version(tmp_path):
    _write(tmp_path, {"require": {}}, {"packages": []})
    assert load_project(tmp_path).magento_version is None


def test_enterprise_edition_is_recognised(tmp_path):
    _write(
        tmp_path,
        {"require": {}},
        {"packages": [{"name": "magento/product-enterprise-edition", "version": "2.4.7"}]},
    )
    assert load_project(tmp_path).magento_version == "2.4.7"
