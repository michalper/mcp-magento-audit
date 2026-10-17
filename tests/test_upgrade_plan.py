import json
from pathlib import Path

from mcp_magento_audit.composer import load_project
from mcp_magento_audit.magento_versions import PhpRequirement
from mcp_magento_audit.module_risk import Issue, ModuleRiskResult, ToolRun
from mcp_magento_audit.outdated_packages import OutdatedPackage, OutdatedPackagesResult
from mcp_magento_audit.release_notes import ReleaseNotes
from mcp_magento_audit.security_audit import Advisory, SecurityAuditResult
from mcp_magento_audit.upgrade_plan import build

STORE = Path(__file__).parent / "fixtures" / "store"


def _write_compatible_project(tmp_path):
    (tmp_path / "composer.json").write_text(json.dumps({"require": {"php": "*"}}))
    (tmp_path / "composer.lock").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "name": "magento/product-community-edition",
                        "version": "2.4.7",
                        "require": {"php": "*"},
                    }
                ]
            }
        )
    )
    return tmp_path


def _stub_release_notes(monkeypatch, found: bool = True):
    notes = ReleaseNotes(
        found=found,
        source="live" if found else "unavailable",
        url="https://example.test/release" if found else None,
        published_at="2023-03-14T00:00:00Z" if found else None,
        notes="..." if found else None,
        reason=None if found else "could not fetch",
    )
    monkeypatch.setattr("mcp_magento_audit.upgrade_plan.release_notes_for_version", lambda v: notes)
    return notes


def _stub_security_audit(monkeypatch, result: SecurityAuditResult | None = None):
    result = result or SecurityAuditResult(
        scanned=False, reason="composer not found", advisory_count=0, advisories=()
    )
    monkeypatch.setattr("mcp_magento_audit.upgrade_plan.audit_security", lambda path: result)
    return result


def _stub_outdated_packages(monkeypatch, result: OutdatedPackagesResult | None = None):
    result = result or OutdatedPackagesResult(
        scanned=False, reason="composer not found", outdated_count=0, packages=()
    )
    monkeypatch.setattr("mcp_magento_audit.upgrade_plan.check_outdated", lambda path: result)
    return result


def test_blocking_package_produces_a_blocker(monkeypatch):
    requirement = PhpRequirement(php_requirement="~8.1.0||~8.2.0||~8.3.0", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch)
    _stub_security_audit(monkeypatch)
    _stub_outdated_packages(monkeypatch)

    project = load_project(STORE)
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is False
    composer_blockers = [b for b in plan.blockers if b.source == "composer"]
    assert any(b.description == "legacy/module" for b in composer_blockers)
    assert plan.release_notes.found is True


def test_no_blockers_means_ready(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch, found=False)
    _stub_security_audit(monkeypatch, SecurityAuditResult(True, None, 0, ()))
    _stub_outdated_packages(monkeypatch, OutdatedPackagesResult(True, None, 0, ()))

    project = load_project(_write_compatible_project(tmp_path))
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is True
    assert plan.blockers == ()
    assert plan.release_notes.found is False
    # No phpstan.neon in this fixture, so that signal never ran — ready=True
    # must not be mistaken for "every signal was checked and came back clean".
    assert any("phpstan" in u for u in plan.unverified)


def test_ready_stays_true_but_unverified_lists_missing_tools(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch, found=False)
    _stub_security_audit(monkeypatch)
    _stub_outdated_packages(monkeypatch)

    project_path = _write_compatible_project(tmp_path)
    (project_path / "app" / "code").mkdir(parents=True)

    project = load_project(project_path)
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is True
    assert plan.blockers == ()
    joined = " ".join(plan.unverified)
    assert "code_compatibility" in joined
    assert "phpcs" in joined
    assert "phpstan" in joined
    assert "rector" in joined
    assert "security_audit" in joined
    assert "outdated_packages" in joined


def test_security_advisory_produces_a_blocker(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch, found=False)
    _stub_outdated_packages(monkeypatch)
    advisory = Advisory(
        package="vendor/module",
        advisory_id="PKSA-abcd-1234",
        title="Remote code execution",
        cve="CVE-2024-12345",
        severity="critical",
        link="https://example.test/advisory",
    )
    _stub_security_audit(monkeypatch, SecurityAuditResult(True, None, 1, (advisory,)))

    project = load_project(_write_compatible_project(tmp_path))
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is False
    security_blockers = [b for b in plan.blockers if b.source == "security"]
    assert len(security_blockers) == 1
    assert security_blockers[0].description == "vendor/module"
    assert "CVE-2024-12345" in security_blockers[0].detail


def test_outdated_packages_are_informational_not_blockers(tmp_path, monkeypatch):
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch, found=False)
    _stub_security_audit(monkeypatch, SecurityAuditResult(True, None, 0, ()))
    outdated_pkg = OutdatedPackage(
        package="vendor/module", current="1.0.0", latest="2.0.0", status="update-possible"
    )
    _stub_outdated_packages(monkeypatch, OutdatedPackagesResult(True, None, 1, (outdated_pkg,)))

    project = load_project(_write_compatible_project(tmp_path))
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is True
    assert plan.blockers == ()
    assert plan.outdated_packages.outdated_count == 1
    assert plan.outdated_packages.packages == (outdated_pkg,)


def test_vendor_scope_issues_do_not_produce_blockers(tmp_path, monkeypatch):
    """A phpcs error in a third-party vendor/ module isn't something the
    project's own team can fix, so — unlike the same error in app/code — it
    must not block `ready`. It's still visible via module_risk.issues."""
    requirement = PhpRequirement(php_requirement="*", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch, found=False)
    _stub_security_audit(monkeypatch, SecurityAuditResult(True, None, 0, ()))
    _stub_outdated_packages(monkeypatch)

    vendor_issue = Issue(
        tool="phpcs",
        file="vendor/acme/module-foo/Model.php",
        line=10,
        severity="error",
        source="Magento2.Legacy.DeprecatedClasses",
        message="deprecated",
        scope="vendor",
    )
    risk = ModuleRiskResult(
        phpcs=ToolRun(True, None, "app/code"),
        phpstan=ToolRun(False, "no phpstan.neon", ""),
        rector=ToolRun(False, "no rector.php", ""),
        vendor_phpcs=ToolRun(True, None, "vendor (1 third-party magento2-module package(s))"),
        vendor_packages=("vendor/acme/module-foo",),
        object_manager_misuse=ToolRun(True, None, "app/code"),
        core_overrides=ToolRun(True, None, "app/code vs vendor/magento"),
        dangling_references=ToolRun(True, None, "app/code"),
        issue_count=1,
        issues=(vendor_issue,),
    )
    monkeypatch.setattr("mcp_magento_audit.upgrade_plan.scan_module_risk", lambda path: risk)

    project = load_project(_write_compatible_project(tmp_path))
    plan = build(project, target_php="8.3", target_magento="2.4.7")

    assert plan.ready is True
    assert plan.blockers == ()
    assert plan.module_risk.issues == (vendor_issue,)
