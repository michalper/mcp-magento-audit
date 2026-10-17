import pytest

from mcp_magento_audit.composer_semver import ConstraintError, satisfies


@pytest.mark.parametrize(
    ("constraint", "version", "expected"),
    [
        ("^7.4", "7.4", True),
        ("^7.4", "8.0", False),
        ("^7.4", "7.9", True),
        ("^7.4", "7.4.33", True),
        ("~8.2.0", "8.2.5", True),
        ("~8.2.0", "8.3.0", False),
        ("~8.2", "8.9", True),
        ("~8.2", "9.0", False),
        ("~8.2.0||~8.3.0", "8.3.1", True),
        ("~8.2.0||~8.3.0", "8.4.0", False),
        (">=7.4 <8.1", "7.4", True),
        (">=7.4 <8.1", "8.1", False),
        (">=7.4 <8.1", "8.0.9", True),
        ("*", "7.0", True),
        ("*", "9.9.9", True),
    ],
)
def test_satisfies(constraint: str, version: str, expected: bool):
    assert satisfies(constraint, version) is expected


@pytest.mark.parametrize("constraint", ["abc", "", "^"])
def test_invalid_constraint_raises(constraint: str):
    with pytest.raises(ConstraintError):
        satisfies(constraint, "8.3")


def test_invalid_version_raises():
    with pytest.raises(ConstraintError):
        satisfies("^7.4", "abc")
