"""Filesystem workspace helpers for delegation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List

from runtime.models import DelegationRecord
from runtime.policy.engine import PolicyEngine


def _safe_relpath(path: str) -> str:
    normalized = os.path.normpath(path).lstrip("/")
    if normalized.startswith(".."):
        raise ValueError(f"invalid relative path '{path}'")
    return normalized


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class DelegationWorkspace:
    """Creates and manages per-delegation isolated workspace directories."""

    def __init__(self, base_dir: str = ".agent-runtime/workspaces") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def prepare(
        self,
        *,
        run_id: str,
        delegation: DelegationRecord,
        repo_root: str,
        policy: PolicyEngine,
        context_payload: Dict[str, object],
    ) -> Dict[str, str]:
        root = self.base_dir / run_id / delegation.delegation_id
        input_dir = root / "input"
        src_dir = input_dir / "src"
        artifacts_dir = input_dir / "artifacts"
        work_dir = root / "work"
        output_dir = root / "output"
        output_artifacts = output_dir / "artifacts"

        for path in (input_dir, src_dir, artifacts_dir, work_dir, output_dir, output_artifacts):
            path.mkdir(parents=True, exist_ok=True)

        (input_dir / "request.json").write_text(
            json.dumps(delegation.request.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (input_dir / "context.json").write_text(
            json.dumps(context_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        repo = Path(repo_root).resolve()
        copied = []
        for original in delegation.request.copy_in_paths:
            allowed, rel, reason = policy.decide_repo_path(
                repo_root=repo,
                requested_path=original,
                allowlist=delegation.request.path_allowlist,
                denylist=delegation.request.path_denylist,
            )
            if not allowed:
                raise ValueError(reason)
            src = repo / rel
            if not src.exists() or not src.is_file():
                raise ValueError(f"copy-in source missing: {rel}")
            dst = src_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)

        return {
            "root": str(root),
            "input": str(input_dir),
            "work": str(work_dir),
            "output": str(output_dir),
            "copied_paths": copied,
        }

    def collect_manifest(self, *, run_id: str, delegation_id: str) -> Dict[str, object]:
        root = self.base_dir / run_id / delegation_id
        output_artifacts = root / "output" / "artifacts"
        files: List[Dict[str, object]] = []
        if output_artifacts.exists():
            for path in sorted(output_artifacts.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                files.append(
                    {
                        "path": rel,
                        "size": path.stat().st_size,
                        "sha256": _hash_file(path),
                    }
                )
        manifest = {"files": files}
        (root / "output" / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest

