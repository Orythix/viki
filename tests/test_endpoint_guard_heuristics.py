"""Unit tests for endpoint_guard heuristics (no filesystem watchers)."""
from __future__ import annotations

import os

import pytest

from viki.core.endpoint_guard import (
    assess_path_risk,
    candidate_download_directories,
    severity_meets,
)


def test_severity_meets_ordering():
    assert severity_meets("low", "low")
    assert severity_meets("low", "high")
    assert severity_meets("medium", "medium")
    assert severity_meets("medium", "high")
    assert not severity_meets("high", "medium")
    assert not severity_meets("high", "low")


def test_double_extension_high():
    base = os.path.join("/tmp", "Downloads", "report.pdf.exe")
    sev, reason = assess_path_risk(base)
    assert sev == "high"
    assert "Double extension" in reason


def test_ransom_hint_high():
    base = os.path.join("/tmp", "HOW_TO_RESTORE_FILES.txt")
    sev, reason = assess_path_risk(base)
    assert sev == "high"
    assert "ransomware" in reason.lower() or "recovery" in reason.lower()


@pytest.mark.parametrize(
    "parent,ext,expected_sev",
    [
        ("Downloads", ".exe", "medium"),
        ("Downloads", ".sh", "medium"),
        ("download", ".ps1", "medium"),
        ("tmp", ".bat", "medium"),
        ("Projects", ".exe", "low"),
        ("Projects", ".sh", "low"),
    ],
)
def test_high_risk_ext_by_parent(parent, ext, expected_sev):
    path = os.path.join("/fake", parent, f"setup{ext}")
    sev, _reason = assess_path_risk(path)
    assert sev == expected_sev


def test_benign_low():
    path = os.path.join("/fake", "Documents", "notes.txt")
    sev, reason = assess_path_risk(path)
    assert sev == "low"
    assert reason == "" or "txt" not in reason.lower()


def test_candidate_download_directories_includes_home_downloads(monkeypatch, tmp_path):
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    dl = fake_home / "Downloads"
    dl.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("XDG_DOWNLOAD_DIR", raising=False)
    dirs = candidate_download_directories()
    assert any(str(dl.resolve()) == os.path.abspath(d) for d in dirs)
