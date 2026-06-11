"""
Artifact delivery manifest (Phase 4).

Every long-horizon mission ends with a manifest at:

    workspace/missions/<mission_id>/manifest.json

listing produced files, tests run, and any eval scores. This mirrors Manus'
deliverable-centric UX and gives downstream tooling a single audit point.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArtifactEntry:
    path: str
    description: str = ""
    sha256: str | None = None
    size_bytes: int | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestRecord:
    name: str
    command: str
    passed: bool
    duration_sec: float
    output_excerpt: str = ""


@dataclass
class EvalRecord:
    suite: str
    score: float
    pass_rate: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactManifest:
    mission_id: str
    goal: str
    workspace_dir: str
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    artifacts: list[ArtifactEntry] = field(default_factory=list)
    tests: list[TestRecord] = field(default_factory=list)
    evals: list[EvalRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def manifest_dir(self) -> str:
        return os.path.join(self.workspace_dir, "missions", self.mission_id)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.manifest_dir, "manifest.json")

    def add_artifact(
        self,
        path: str,
        description: str = "",
        compute_hash: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactEntry:
        sha = None
        size = None
        if compute_hash and os.path.isfile(path):
            try:
                size = os.path.getsize(path)
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(64 * 1024), b""):
                        h.update(chunk)
                sha = h.hexdigest()
            except OSError:
                pass
        entry = ArtifactEntry(
            path=os.path.abspath(path),
            description=description,
            sha256=sha,
            size_bytes=size,
            metadata=metadata or {},
        )
        self.artifacts.append(entry)
        return entry

    def add_test(
        self, name: str, command: str, passed: bool, duration_sec: float, output_excerpt: str = ""
    ) -> TestRecord:
        rec = TestRecord(
            name=name,
            command=command,
            passed=passed,
            duration_sec=duration_sec,
            output_excerpt=(output_excerpt or "")[:2000],
        )
        self.tests.append(rec)
        return rec

    def add_eval(
        self,
        suite: str,
        score: float,
        pass_rate: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> EvalRecord:
        rec = EvalRecord(suite=suite, score=score, pass_rate=pass_rate, extra=extra or {})
        self.evals.append(rec)
        return rec

    def note(self, text: str) -> None:
        self.notes.append(text)

    def finalize(self) -> str:
        self.completed_at = time.time()
        os.makedirs(self.manifest_dir, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=False)
        return self.manifest_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "goal": self.goal,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "artifacts": [a.__dict__ for a in self.artifacts],
            "tests": [t.__dict__ for t in self.tests],
            "evals": [e.__dict__ for e in self.evals],
            "notes": self.notes,
        }

    @classmethod
    def load(cls, mission_id: str, workspace_dir: str) -> ArtifactManifest | None:
        path = os.path.join(workspace_dir, "missions", mission_id, "manifest.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        m = cls(
            mission_id=data["mission_id"],
            goal=data.get("goal", ""),
            workspace_dir=workspace_dir,
            started_at=data.get("started_at", time.time()),
            completed_at=data.get("completed_at"),
            notes=list(data.get("notes", [])),
        )
        for a in data.get("artifacts", []):
            m.artifacts.append(ArtifactEntry(**a))
        for t in data.get("tests", []):
            m.tests.append(TestRecord(**t))
        for e in data.get("evals", []):
            m.evals.append(EvalRecord(**e))
        return m
