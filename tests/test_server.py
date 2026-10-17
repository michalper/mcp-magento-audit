from pathlib import Path

from mcp_magento_audit.magento_versions import PhpRequirement
from mcp_magento_audit.server import (
    check_updates,
    outdated_packages,
    project_status,
    security_audit,
)

STORE = str(Path(__file__).parent / "fixtures" / "store")


def test_project_status_full_result():
    result = project_status(STORE)
    assert result["magento_version"] == "2.4.7"
    assert result["package_count"] == 3
    assert result["abandoned"] == ["legacy/module"]


def test_invalid_path_returns_error_not_exception():
    assert "error" in project_status("/no/such/directory")


def test_check_updates_full_result(monkeypatch):
    requirement = PhpRequirement(php_requirement="~8.1.0||~8.2.0||~8.3.0", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )

    result = check_updates(STORE, target_php="8.3", target_magento="2.4.7")

    assert result["php_data_source"] == "hardcoded"
    verdicts = {p["package"]: p["verdict"] for p in result["packages"]}
    assert verdicts["magento/product-community-edition"] == "ok"
    assert verdicts["legacy/module"] == "blocks"
    assert result["code_compatibility"]["checked"] is True


def test_check_updates_invalid_path_returns_error_not_exception():
    assert "error" in check_updates("/no/such/directory", target_php="8.3", target_magento="2.4.7")


def test_security_audit_invalid_path_returns_error_not_exception():
    assert "error" in security_audit("/no/such/directory")


def test_security_audit_without_composer_lock_is_not_scanned(tmp_path):
    result = security_audit(str(tmp_path))

    assert result["scanned"] is False
    assert "composer.lock" in result["reason"]


def test_outdated_packages_invalid_path_returns_error_not_exception():
    assert "error" in outdated_packages("/no/such/directory")


def test_outdated_packages_without_composer_lock_is_not_scanned(tmp_path):
    result = outdated_packages(str(tmp_path))

    assert result["scanned"] is False
    assert "composer.lock" in result["reason"]
