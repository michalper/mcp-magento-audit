from pathlib import Path

import pytest

from mcp_magento_audit.composer import ProjectError, load_project

STORE = Path(__file__).parent / "fixtures" / "sklep"


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
