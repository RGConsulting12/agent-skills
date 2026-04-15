"""Policy inheritance and narrowing tests for Phase 2B."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.policy.engine import PolicyEngine, PolicyError


class PolicyNarrowingTests(unittest.TestCase):
    def test_override_cannot_widen_path_allowlist(self) -> None:
        engine = PolicyEngine()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            plan_policy = {"paths": {"allowlist": ["runtime/examples"]}}
            delegation_config = {
                "path_allowlist": ["runtime/examples"],
                "path_denylist": [],
                "tool_allowlist": ["noop"],
                "policy_override": {"paths": {"allowlist": ["runtime"]}},
            }
            with self.assertRaises(PolicyError):
                engine.resolve_effective_policy(
                    repo_root=repo,
                    plan_policy=plan_policy,
                    delegation_config=delegation_config,
                )

    def test_required_categories_union(self) -> None:
        engine = PolicyEngine()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            plan_policy = {"approvals": {"required_categories": ["delegation_accept"]}}
            delegation_config = {
                "path_allowlist": ["runtime/examples"],
                "path_denylist": [],
                "tool_allowlist": ["noop"],
                "policy_override": {
                    "approvals": {"required_categories": ["delegation_publish"]}
                },
            }
            effective = engine.resolve_effective_policy(
                repo_root=repo,
                plan_policy=plan_policy,
                delegation_config=delegation_config,
            )
            self.assertEqual(
                effective.required_categories,
                ["delegation_accept", "delegation_publish"],
            )

