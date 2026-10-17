from pathlib import Path

from mcp_magento_audit.composer import load_project
from mcp_magento_audit.magento_versions import PhpRequirement
from mcp_magento_audit.updates import check

STORE = Path(__file__).parent / "fixtures" / "sklep"


def test_check_against_target_php(monkeypatch):
    requirement = PhpRequirement(php_requirement="~8.1.0||~8.2.0||~8.3.0", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )

    project = load_project(STORE)
    result = check(project, target_php="8.3", target_magento="2.4.7")

    verdicts = {v.package: v.verdict for v in result.packages}
    assert verdicts["magento/product-community-edition"] == "ok"
    assert verdicts["stary/modul"] == "blocks"
    assert verdicts["phpunit/phpunit"] == "ok"
    assert result.summary == {"ok": 2, "blocks": 1, "unknown": 0}
    assert result.project_magento_version == "2.4.7"
    assert result.php_data_source == "hardcoded"
    assert result.target_magento_php_requirement == "~8.1.0||~8.2.0||~8.3.0"


def test_package_without_php_requirement_is_ok(monkeypatch):
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento",
        lambda version: PhpRequirement(php_requirement=None, source="unknown"),
    )

    project = load_project(STORE)
    result = check(project, target_php="8.3", target_magento="99.0")

    assert result.target_magento_php_requirement is None
    assert result.php_data_source == "unknown"
