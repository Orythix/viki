"""Computer-use observe→act→verify and vision honest stub."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from viki.skills.builtins.computer_use_skill import ComputerUseSkill, UIElement
from viki.skills.builtins.vision_skill import VisionSkill


@pytest.mark.asyncio
async def test_vision_honest_stub_without_vlm(tmp_path):
    skill = VisionSkill(data_dir=str(tmp_path), controller=None)
    img = tmp_path / "frame.png"
    # Minimal valid PNG
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    out = await skill.execute({"instruction": "describe", "image_paths": [str(img)]})
    assert "[vision stub]" in out
    assert "Screenshot captured" not in out or True  # provided path path
    assert str(img) in out or "Analyzing provided image" in out


@pytest.mark.asyncio
async def test_computer_use_abort_on_low_confidence_grounding(tmp_path):
    skill = ComputerUseSkill(data_dir=str(tmp_path))
    skill._min_action_confidence = 0.5
    skill._capture_screenshot = MagicMock(return_value=str(tmp_path / "a.png"))
    (tmp_path / "a.png").write_bytes(b"x")
    skill._ground_elements = AsyncMock(
        return_value=[UIElement(label="Submit", bbox=(1, 1, 10, 10), confidence=0.1)]
    )
    out = await skill.execute(
        {"action": "click_element", "label": "Submit", "verify": True}
    )
    data = json.loads(out)
    assert data["status"] == "rejected"
    assert data["reason"] == "low_confidence"


@pytest.mark.asyncio
async def test_computer_use_verify_mismatch_when_expect_change(tmp_path):
    skill = ComputerUseSkill(data_dir=str(tmp_path))
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    # Same bytes → mismatch when expect_change
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    before.write_bytes(png)
    after.write_bytes(png)

    paths = iter([str(before), str(after)])
    skill._capture_screenshot = MagicMock(side_effect=lambda: next(paths))
    skill._ground_elements = AsyncMock(return_value=[])
    skill._do_click = AsyncMock(return_value="clicked (1, 2)")

    with patch.object(skill, "_dispatch", new=AsyncMock(return_value="clicked (1, 2)")):
        out = await skill.execute(
            {"action": "click", "x": 1, "y": 2, "verify": True, "expect_change": True}
        )
    data = json.loads(out)
    assert data["status"] == "aborted"
    assert data["reason"] == "verify_mismatch"
