"""Minimal Phase 2A policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass
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
        allow = [Path(item) for item in path_allowlist]
        deny = [Path(item) for item in path_denylist]
        for raw in requested_paths:
            req = Path(raw)
            absolute = (repo_root / req).resolve()
            if not self._is_within(repo_root, absolute):
                raise PolicyError(f"path escapes repo root: {raw}")
            if allow:
                allowed = any(self._is_within((repo_root / item).resolve(), absolute) for item in allow)
                if not allowed:
                    raise PolicyError(f"path not in allowlist: {raw}")
            denied = any(self._is_within((repo_root / item).resolve(), absolute) for item in deny)
            if denied:
                raise PolicyError(f"path blocked by denylist: {raw}")

    @staticmethod
    def enforce_tool_allowlist(tool_allowlist: Iterable[str], requested_tool: str) -> None:
        """Ensure requested tool is explicitly allowlisted."""
        allowed = set(tool_allowlist)
        if requested_tool not in allowed:
            raise PolicyError(f"tool not in allowlist: {requested_tool}")

