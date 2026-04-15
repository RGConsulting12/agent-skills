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


@dataclass
class EffectivePolicy:
    """Resolved policy contract used for delegation execution."""

    path_allowlist: list[str]
    path_denylist: list[str]
    tool_allowlist: list[str]
    required_categories: list[str]


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

    @staticmethod
    def _normalize_rules(repo_root: Path, values: Iterable[str]) -> list[str]:
        rules: list[str] = []
        for item in values:
            normalized = PolicyEngine._normalize_repo_relative(repo_root, item)
            if normalized is not None:
                rules.append(normalized)
        return sorted(set(rules))

    @staticmethod
    def _intersect_rules(*lists: list[str]) -> list[str]:
        present = [set(items) for items in lists if items]
        if not present:
            return []
        shared = set.intersection(*present)
        return sorted(shared)

    @staticmethod
    def _union_rules(*lists: list[str]) -> list[str]:
        merged = set()
        for items in lists:
            merged.update(items)
        return sorted(merged)

    def resolve_effective_policy(
        self,
        *,
        repo_root: Path,
        plan_policy: dict | None,
        delegation_config: dict,
    ) -> EffectivePolicy:
        """Resolve policy with narrowing-only overrides for delegation execution."""
        plan_policy = plan_policy or {}
        override = dict(delegation_config.get("policy_override", {}))

        plan_paths = dict(plan_policy.get("paths", {}))
        ov_paths = dict(override.get("paths", {}))
        cfg_allow = list(delegation_config.get("path_allowlist", []))
        cfg_deny = list(delegation_config.get("path_denylist", []))

        base_allow = self._normalize_rules(repo_root, plan_paths.get("allowlist", []))
        ov_allow = self._normalize_rules(repo_root, ov_paths.get("allowlist", []))
        cfg_allow_n = self._normalize_rules(repo_root, cfg_allow)
        allow = self._intersect_rules(base_allow, ov_allow, cfg_allow_n)
        if (base_allow or ov_allow or cfg_allow_n) and not allow:
            raise PolicyError("policy narrowing produced empty path allowlist")
        if not allow and not (base_allow or ov_allow):
            # Preserve current Phase 2A behavior where delegation path_allowlist
            # alone constrains allowed paths.
            allow = cfg_allow_n

        base_deny = self._normalize_rules(repo_root, plan_paths.get("denylist", []))
        ov_deny = self._normalize_rules(repo_root, ov_paths.get("denylist", []))
        cfg_deny_n = self._normalize_rules(repo_root, cfg_deny)
        deny = self._union_rules(base_deny, ov_deny, cfg_deny_n)

        plan_tools = dict(plan_policy.get("tools", {}))
        ov_tools = dict(override.get("tools", {}))
        cfg_tools = sorted(set(str(item) for item in delegation_config.get("tool_allowlist", [])))
        base_tools = sorted(set(str(item) for item in plan_tools.get("allowlist", [])))
        ov_tools_list = sorted(set(str(item) for item in ov_tools.get("allowlist", [])))
        tools = self._intersect_rules(base_tools, ov_tools_list, cfg_tools)
        if (base_tools or ov_tools_list or cfg_tools) and not tools:
            raise PolicyError("policy narrowing produced empty tool allowlist")
        if not tools and not (base_tools or ov_tools_list):
            # Preserve current Phase 2A behavior where delegation tool_allowlist
            # alone defines allowed tools.
            tools = cfg_tools

        known_tools = {"noop", "shell"}
        unknown = [item for item in tools if item not in known_tools]
        if unknown:
            raise PolicyError(f"unsupported tool(s) in effective policy: {', '.join(sorted(unknown))}")

        plan_approvals = dict(plan_policy.get("approvals", {}))
        ov_approvals = dict(override.get("approvals", {}))
        categories = self._union_rules(
            sorted(set(str(item) for item in plan_approvals.get("required_categories", []))),
            sorted(set(str(item) for item in ov_approvals.get("required_categories", []))),
        )

        return EffectivePolicy(
            path_allowlist=allow,
            path_denylist=deny,
            tool_allowlist=tools,
            required_categories=categories,
        )

