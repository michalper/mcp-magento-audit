import json
from pathlib import Path

from mcp_magento_audit.composer import load_project
from mcp_magento_audit.magento_versions import PhpRequirement
from mcp_magento_audit.release_notes import ReleaseNotes
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


def test_blocking_package_produces_a_blocker(monkeypatch):
    requirement = PhpRequirement(php_requirement="~8.1.0||~8.2.0||~8.3.0", source="hardcoded")
    monkeypatch.setattr(
        "mcp_magento_audit.updates.php_requirement_for_magento", lambda version: requirement
    )
    _stub_release_notes(monkeypatch)

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
