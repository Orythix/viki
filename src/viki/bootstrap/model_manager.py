"""Hardware-aware model recommendation and download manager."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from viki._compat import StrEnum
from viki.bootstrap.system_detector import HardwareProfile, SystemInfo


class ModelFormat(StrEnum):
    GGUF = "gguf"
    SAFETENSORS = "safetensors"
    MLX = "mlx"


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str  # lmstudio, huggingface
    format: ModelFormat
    parameter_count: str  # e.g. "7B", "14B", "70B"
    quantization: str  # e.g. "Q4_K_M", "Q8_0"
    ram_required_mb: int
    vram_required_mb: int
    disk_size_mb: int
    is_embedding: bool = False
    description: str = ""
    url: str = ""


@dataclass
class ModelRecommendation:
    primary: ModelInfo | None = None
    fallback: ModelInfo | None = None
    embedding: ModelInfo | None = None
    alternatives: list[ModelInfo] = field(default_factory=list)


_AVAILABLE_MODELS: list[ModelInfo] = [
    # LM Studio models
    ModelInfo(
        "google/gemma-4-e4b",
        "Gemma 4 E4B",
        "lmstudio",
        ModelFormat.GGUF,
        "4B",
        "Q4_K_M",
        3072,
        3072,
        2500,
        description="Google Gemma 4 E4B — fast, efficient local model",
        url="Load in LM Studio: search for google/gemma-4-e4b",
    ),
    ModelInfo(
        "google/gemma-4-12b",
        "Gemma 4 12B",
        "lmstudio",
        ModelFormat.GGUF,
        "12B",
        "Q4_K_M",
        8192,
        8192,
        7600,
        description="Google Gemma 4 12B — strong reasoning + instruction following",
        url="Load in LM Studio: search for google/gemma-4-12b",
    ),
    ModelInfo(
        "qwen/qwen3.5-9b",
        "Qwen 3.5 9B",
        "lmstudio",
        ModelFormat.GGUF,
        "9B",
        "Q4_K_M",
        5120,
        5120,
        5500,
        description="Alibaba Qwen 3.5 9B — strong reasoning and coding",
        url="Load in LM Studio: search for qwen3.5-9b",
    ),
    ModelInfo(
        "meta-llama/llama-3.2-3b",
        "Llama 3.2 3B",
        "lmstudio",
        ModelFormat.GGUF,
        "3B",
        "Q4_K_M",
        2048,
        2048,
        2000,
        description="Meta Llama 3.2 3B — efficient lightweight",
        url="Load in LM Studio: search for llama-3.2-3b",
    ),
    ModelInfo(
        "meta-llama/llama-3.1-8b",
        "Llama 3.1 8B",
        "lmstudio",
        ModelFormat.GGUF,
        "8B",
        "Q4_K_M",
        5120,
        5120,
        4800,
        description="Meta Llama 3.1 8B — solid all-rounder",
        url="Load in LM Studio: search for llama-3.1-8b",
    ),
    ModelInfo(
        "deepseek/deepseek-r1-7b",
        "DeepSeek R1 7B",
        "lmstudio",
        ModelFormat.GGUF,
        "7B",
        "Q4_K_M",
        4096,
        4096,
        4500,
        description="DeepSeek R1 distilled reasoning model",
        url="Load in LM Studio: search for deepseek-r1-7b",
    ),
    ModelInfo(
        "microsoft/phi-3-mini",
        "Phi-3 Mini 3.8B",
        "lmstudio",
        ModelFormat.GGUF,
        "3.8B",
        "Q4_K_M",
        3072,
        3072,
        2400,
        description="Microsoft Phi-3 Mini — great for fast responses",
        url="Load in LM Studio: search for phi-3-mini",
    ),
    # Embedding models
    ModelInfo(
        "nomic-embed-text-v1.5",
        "Nomic Embed Text v1.5",
        "lmstudio",
        ModelFormat.GGUF,
        "137M",
        "F16",
        512,
        512,
        274,
        is_embedding=True,
        description="Lightweight embeddings for memory/retrieval",
        url="Load in LM Studio: search for nomic-embed-text",
    ),
]


def _recommend_models(info: SystemInfo, profile: HardwareProfile) -> ModelRecommendation:
    """Recommend models based on hardware profile."""
    rec = ModelRecommendation()

    ram_gb = info.ram_mb / 1024
    primary_vram = info.gpus[0].vram_mb if info.gpus else 0

    rec.embedding = _find_model("nomic-embed-text-v1.5")

    candidates = []
    for m in _AVAILABLE_MODELS:
        if m.is_embedding:
            continue
        if m.vram_required_mb > primary_vram and primary_vram > 0:
            continue
        if m.ram_required_mb > ram_gb * 1024:
            continue
        candidates.append(m)

    if not candidates:
        candidates = [m for m in _AVAILABLE_MODELS if not m.is_embedding]

    def score(m: ModelInfo) -> float:
        s = 0.0
        if primary_vram > 0 and m.vram_required_mb <= primary_vram:
            s += 3.0
        size_gb = m.disk_size_mb / 1024
        s += min(size_gb / 10, 2.0)
        if m.vram_required_mb > primary_vram * 0.9 and primary_vram > 0:
            s -= 1.0
        if "gemma-4" in m.id:
            s += 1.0
        if "qwen" in m.id:
            s += 0.5
        return s

    candidates.sort(key=score, reverse=True)

    if candidates:
        rec.primary = candidates[0]
    if len(candidates) > 1:
        rec.fallback = candidates[1]
    if len(candidates) > 2:
        rec.alternatives = candidates[2:5]

    return rec


def _find_model(model_id: str) -> ModelInfo | None:
    for m in _AVAILABLE_MODELS:
        if m.id == model_id:
            return m
    return None


class ModelManager:
    """Manage model recommendations and verification via LM Studio API."""

    def __init__(self, lmstudio_url: str = "http://localhost:1234"):
        self.lmstudio_url = lmstudio_url.rstrip("/")

    def recommend(self, info: SystemInfo, profile: HardwareProfile) -> ModelRecommendation:
        return _recommend_models(info, profile)

    async def list_installed(self) -> list[dict[str, Any]]:
        """List models loaded in LM Studio via /v1/models."""
        try:
            req = urllib.request.Request(
                f"{self.lmstudio_url}/v1/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for m in data.get("data", []):
                models.append({"name": m.get("id", ""), "size": ""})
            return models
        except Exception:
            return []

    async def is_installed(self, model_id: str) -> bool:
        installed = await self.list_installed()
        return any(m["name"] == model_id for m in installed)

    async def download(self, model: ModelInfo, progress_callback=None) -> bool:
        """Notify user to load model in LM Studio (no CLI download)."""
        if progress_callback:
            progress_callback(
                f"Please load '{model.name}' in LM Studio manually.\n"
                f"Open LM Studio -> Search -> {model.id} -> Download/Load."
            )
        return True

    async def get_disk_required(self, models: list[ModelInfo]) -> int:
        """Return total disk space required in MB."""
        return sum(m.disk_size_mb for m in models)

    async def verify(self, model_id: str) -> tuple[bool, str]:
        """Verify a model is loaded in LM Studio."""
        installed = await self.list_installed()
        for m in installed:
            if m["name"] == model_id:
                return True, m.get("size", "unknown")
        return False, ""
