"""Matching a concrete version against a Composer version constraint.

Only handles "does this one concrete version satisfy this constraint",
not intersecting two ranges — that's all `check_updates` needs, and it
avoids pulling in a general-purpose semver library.
"""

from __future__ import annotations


class ConstraintError(Exception):
    """The constraint or version string could not be parsed."""


def satisfies(constraint: str, version: str) -> bool:
    """Whether a concrete PHP version (e.g. '8.3' or '8.3.1') satisfies a
    Composer constraint (e.g. '^7.4', '~8.2.0||~8.3.0', '>=7.4 <8.1')."""
    if not constraint.strip():
        raise ConstraintError("constraint is empty")

    target = _parse_version(version)
    groups = constraint.split("||")
    return any(
        all(_clause_matches(clause.strip(), target) for clause in group.split() if clause.strip())
        for group in groups
    )


def _parse_version(text: str) -> tuple[int, ...]:
    text = text.strip()
    parts = text.split(".")
    if not text or not all(part.isdigit() for part in parts):
        raise ConstraintError(f"cannot parse version: {text!r}")
    return tuple(int(part) for part in parts)


def _pad(version: tuple[int, ...], length: int) -> tuple[int, ...]:
    return version + (0,) * (length - len(version))


def _compare(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    length = max(len(a), len(b))
    a, b = _pad(a, length), _pad(b, length)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _clause_matches(clause: str, target: tuple[int, ...]) -> bool:
    if clause == "*":
        return True

    for operator in (">=", "<=", ">", "<"):
        if clause.startswith(operator):
            bound = _parse_version(clause[len(operator) :])
            cmp = _compare(target, bound)
            if operator == ">=":
                return cmp >= 0
            if operator == "<=":
                return cmp <= 0
            if operator == ">":
                return cmp > 0
            return cmp < 0

    if clause.startswith("^"):
        lower = _parse_version(clause[1:])
        upper = (lower[0] + 1, 0, 0)
        return _compare(target, lower) >= 0 and _compare(target, upper) < 0

    if clause.startswith("~"):
        lower = _parse_version(clause[1:])
        upper = (lower[0], lower[1] + 1, 0) if len(lower) >= 3 else (lower[0] + 1, 0, 0)
        return _compare(target, lower) >= 0 and _compare(target, upper) < 0

    exact = _parse_version(clause)
    return _compare(target, exact) == 0
