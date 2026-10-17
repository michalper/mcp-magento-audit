import json
import re
from pathlib import Path

import pytest

from mcp_magento_audit.composer import ProjectError, load_project

STORE = Path(__file__).parent / "fixtures" / "store"


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
    assert abandoned == ["legacy/module"]


def test_php_requirement_of_specific_package():
    package = next(p for p in load_project(STORE).packages if p.name == "legacy/module")
    assert package.php_requirement == "^7.4"


def test_package_type_defaults_to_library(tmp_path):
    _write(
        tmp_path,
        {"require": {}},
        {"packages": [{"name": "foo/bar", "version": "1.0.0"}]},
    )
    assert load_project(tmp_path).packages[0].type == "library"


def test_package_type_is_read_from_lock(tmp_path):
    _write(
        tmp_path,
        {"require": {}},
        {"packages": [{"name": "vendor/module", "version": "1.0.0", "type": "magento2-module"}]},
    )
    assert load_project(tmp_path).packages[0].type == "magento2-module"


def test_missing_directory_raises_error():
    with pytest.raises(ProjectError, match="is not a directory"):
        load_project("/no/such/directory")


def test_missing_composer_json_raises_error(tmp_path):
    with pytest.raises(ProjectError, match=re.escape("missing file composer.json")):
        load_project(tmp_path)


def test_missing_composer_lock_raises_error(tmp_path):
    (tmp_path / "composer.json").write_text("{}")
    with pytest.raises(ProjectError, match=re.escape("missing file composer.lock")):
        load_project(tmp_path)


def test_unreadable_composer_json_raises_project_error_not_os_error(tmp_path):
    # A permission error (or any other OSError besides "file missing") must
    # surface as ProjectError too — fleet.py's batch triage relies on every
    # per-project load failure being this one exception type, not a raw
    # OSError subtype escaping and aborting the whole batch.
    composer_json = tmp_path / "composer.json"
    composer_json.write_text("{}")
    (tmp_path / "composer.lock").write_text("{}")
    composer_json.chmod(0o000)
    try:
        with pytest.raises(ProjectError, match=re.escape("could not read composer.json")):
            load_project(tmp_path)
    finally:
        composer_json.chmod(0o644)


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


def test_magento_core_checkout_falls_back_to_its_own_root_version(tmp_path):
    """A clone of the magento/magento2 monorepo itself (no
    magento/product-*-edition dependency — the root package *is* the
    product) declares its version in its own composer.json."""
    _write(
        tmp_path,
        {"name": "magento/magento2ce", "version": "2.4.9", "require": {}},
        {"packages": []},
    )
    assert load_project(tmp_path).magento_version == "2.4.9"


def test_unrelated_root_package_does_not_leak_its_version_as_magento_version(tmp_path):
    _write(
        tmp_path,
        {"name": "acme/some-other-project", "version": "9.9.9", "require": {}},
        {"packages": []},
    )
    assert load_project(tmp_path).magento_version is None


def test_product_package_dependency_wins_over_root_version(tmp_path):
    """The common case (a store installed via magento/project-*-edition) is
    preferred over the root composer.json's own version, which in that case
    belongs to the client's own project, not to Magento."""
    _write(
        tmp_path,
        {"name": "acme/client-store", "version": "1.0.0", "require": {}},
        {"packages": [{"name": "magento/product-community-edition", "version": "2.4.7"}]},
    )
    assert load_project(tmp_path).magento_version == "2.4.7"
