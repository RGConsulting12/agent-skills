"""Minimal Phase 2A policy enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


class PolicyError(ValueError):
    """Raised when a policy rule is violated."""


@dataclass
class PolicyConfig:
    """Minimal host-agnostic policy config."""

    require_action_approval_for_delegation_accept: bool = True


class PolicyEngine:
    """Enforces minimal allowlist/denylist and action approvals."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    @staticmethod
    def _normalize_repo_relative(repo_root: Path, value: str) -> str | None:
        """Normalize path or pattern into repo-relative POSIX form."""
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                rel = candidate.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                return None
        else:
            rel = candidate.as_posix()
        normalized = os.path.normpath(rel).lstrip("/")
        if normalized in {".", ""}:
            return ""
        if normalized.startswith(".."):
            return None
        return normalized

    @staticmethod
    def _matches_rule(candidate: str, rule: str) -> bool:
        if rule in {"", "."}:
            return True
        if fnmatch(candidate, rule):
            return True
        return candidate == rule or candidate.startswith(f"{rule.rstrip('/')}/")

    def decide_repo_path(
        self,
        *,
        repo_root: Path,
        requested_path: str,
        allowlist: Iterable[str],
        denylist: Iterable[str],
    ) -> tuple[bool, str, str]:
        """Return decision, normalized path, and rejection reason."""
        normalized = self._normalize_repo_relative(repo_root, requested_path)
        if normalized is None:
            return False, "", f"path escapes repo root: {requested_path}"

        allow_rules: list[str] = []
        for item in allowlist:
            rule = self._normalize_repo_relative(repo_root, item)
            if rule is not None:
                allow_rules.append(rule)

        deny_rules: list[str] = []
        for item in denylist:
            rule = self._normalize_repo_relative(repo_root, item)
            if rule is not None:
                deny_rules.append(rule)

        if allow_rules and not any(
            self._matches_rule(normalized, rule) for rule in allow_rules
        ):
            return False, normalized, f"path not in allowlist: {requested_path}"
        if any(self._matches_rule(normalized, rule) for rule in deny_rules):
            return False, normalized, f"path blocked by denylist: {requested_path}"
        return True, normalized, ""

    @staticmethod
    def _is_within(base: Path, candidate: Path) -> bool:
        try:
            candidate.resolve().relative_to(base.resolve())
        except ValueError:
            return False
        return True

    def enforce_path_rules(
        self,
        *,
        repo_root: Path,
        path_allowlist: Iterable[str],
        path_denylist: Iterable[str],
        requested_paths: Iterable[str],
    ) -> None:
        """Ensure requested paths are allowlisted and not denylisted."""
        for raw in requested_paths:
            allowed, _normalized, reason = self.decide_repo_path(
                repo_root=repo_root,
                requested_path=raw,
                allowlist=path_allowlist,
                denylist=path_denylist,
            )
            if not allowed:
                raise PolicyError(reason)

    @staticmethod
    def enforce_tool_allowlist(tool_allowlist: Iterable[str], requested_tool: str) -> None:
        """Ensure requested tool is explicitly allowlisted."""
        allowed = set(tool_allowlist)
        if requested_tool not in allowed:
            raise PolicyError(f"tool not in allowlist: {requested_tool}")

    def action_approval_required(self, category: str) -> bool:
        """Return whether an action category requires explicit approval."""
        if category == "delegation_accept":
            return self.config.require_action_approval_for_delegation_accept
        return False

