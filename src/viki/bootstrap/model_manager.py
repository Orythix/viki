"""Hardware-aware model recommendation and download manager."""

from __future__ import annotations

import asyncio
import subprocess
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
    provider: str  # ollama, huggingface
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
    # Ollama models
    ModelInfo(
        "gemma4:12b",
        "Gemma 4 12B",
        "ollama",
        ModelFormat.GGUF,
        "12B",
        "Q4_K_M",
        8192,
        8192,
        7600,
        description="Google's latest — strong reasoning + instruction following",
        url="ollama pull gemma4:12b",
    ),
    ModelInfo(
        "gemma4:27b",
        "Gemma 4 27B",
        "ollama",
        ModelFormat.GGUF,
        "27B",
        "Q4_K_M",
        16384,
        16384,
        17000,
        description="Gemma 4 large — best quality on high-end hardware",
        url="ollama pull gemma4:27b",
    ),
    ModelInfo(
        "phi3:mini",
        "Phi-3 Mini 3.8B",
        "ollama",
        ModelFormat.GGUF,
        "3.8B",
        "Q4_K_M",
        3072,
        3072,
        2400,
        description="Microsoft's efficient small model — great for fast responses",
        url="ollama pull phi3:mini",
    ),
    ModelInfo(
        "phi3:medium",
        "Phi-3 Medium 14B",
        "ollama",
        ModelFormat.GGUF,
        "14B",
        "Q4_K_M",
        8192,
        8192,
        8300,
        description="Phi-3 medium — quality / speed sweet spot",
        url="ollama pull phi3:medium",
    ),
    ModelInfo(
        "llama3.2:3b",
        "Llama 3.2 3B",
        "ollama",
        ModelFormat.GGUF,
        "3B",
        "Q4_K_M",
        2048,
        2048,
        2000,
        description="Meta's efficient lightweight",
        url="ollama pull llama3.2:3b",
    ),
    ModelInfo(
        "llama3.2:1b",
        "Llama 3.2 1B",
        "ollama",
        ModelFormat.GGUF,
        "1B",
        "Q4_K_M",
        1024,
        1024,
        700,
        description="Ultra lightweight for CPU-only systems",
        url="ollama pull llama3.2:1b",
    ),
    ModelInfo(
        "llama3.3:70b",
        "Llama 3.3 70B",
        "ollama",
        ModelFormat.GGUF,
        "70B",
        "Q4_K_M",
        40960,
        40960,
        42000,
        description="Meta's largest — requires high-end hardware",
        url="ollama pull llama3.3:70b",
    ),
    ModelInfo(
        "qwen3:8b",
        "Qwen 3 8B",
        "ollama",
        ModelFormat.GGUF,
        "8B",
        "Q4_K_M",
        5120,
        5120,
        5000,
        description="Alibaba's strong reasoning model",
        url="ollama pull qwen3:8b",
    ),
    ModelInfo(
        "qwen3:14b",
        "Qwen 3 14B",
        "ollama",
        ModelFormat.GGUF,
        "14B",
        "Q4_K_M",
        8192,
        8192,
        9000,
        description="Qwen 14B — excellent coding + reasoning",
        url="ollama pull qwen3:14b",
    ),
    ModelInfo(
        "qwen3:32b",
        "Qwen 3 32B",
        "ollama",
        ModelFormat.GGUF,
        "32B",
        "Q4_K_M",
        20480,
        20480,
        20000,
        description="Qwen 32B — high-quality reasoning",
        url="ollama pull qwen3:32b",
    ),
    ModelInfo(
        "deepseek-r1:7b",
        "DeepSeek R1 7B",
        "ollama",
        ModelFormat.GGUF,
        "7B",
        "Q4_K_M",
        4096,
        4096,
        4500,
        description="DeepSeek distilled reasoning model",
        url="ollama pull deepseek-r1:7b",
    ),
    ModelInfo(
        "deepseek-r1:14b",
        "DeepSeek R1 14B",
        "ollama",
        ModelFormat.GGUF,
        "14B",
        "Q4_K_M",
        8192,
        8192,
        9000,
        description="DeepSeek 14B distilled — strong reasoning",
        url="ollama pull deepseek-r1:14b",
    ),
    ModelInfo(
        "deepseek-r1:32b",
        "DeepSeek R1 32B",
        "ollama",
        ModelFormat.GGUF,
        "32B",
        "Q4_K_M",
        20480,
        20480,
        20000,
        description="DeepSeek 32B — near SOTA reasoning",
        url="ollama pull deepseek-r1:32b",
    ),
    ModelInfo(
        "mistral:7b",
        "Mistral 7B",
        "ollama",
        ModelFormat.GGUF,
        "7B",
        "Q4_K_M",
        4096,
        4096,
        4200,
        description="Mistral AI's original — solid all-rounder",
        url="ollama pull mistral:7b",
    ),
    ModelInfo(
        "codellama:7b",
        "Code Llama 7B",
        "ollama",
        ModelFormat.GGUF,
        "7B",
        "Q4_K_M",
        4096,
        4096,
        3800,
        description="Meta's code-specialized model",
        url="ollama pull codellama:7b",
    ),
    # Embedding models
    ModelInfo(
        "nomic-embed-text",
        "Nomic Embed Text",
        "ollama",
        ModelFormat.GGUF,
        "137M",
        "F16",
        512,
        512,
        274,
        is_embedding=True,
        description="Lightweight embeddings for memory/retrieval",
        url="ollama pull nomic-embed-text",
    ),
    ModelInfo(
        "mxbai-embed-large",
        "MXBAI Embed Large",
        "ollama",
        ModelFormat.GGUF,
        "334M",
        "F16",
        1024,
        1024,
        670,
        is_embedding=True,
        description="High-quality embeddings",
        url="ollama pull mxbai-embed-large",
    ),
]


def _recommend_models(info: SystemInfo, profile: HardwareProfile) -> ModelRecommendation:
    """Recommend models based on hardware profile."""
    rec = ModelRecommendation()

    ram_gb = info.ram_mb / 1024
    primary_vram = info.gpus[0].vram_mb if info.gpus else 0

    # Embedding model (always recommend a small one)
    rec.embedding = _find_model("nomic-embed-text")

    # Filter models by hardware capability
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

    # Score and sort candidates by quality-to-hardware match
    def score(m: ModelInfo) -> float:
        s = 0.0
        # Prefer models that fit in VRAM
        if primary_vram > 0 and m.vram_required_mb <= primary_vram:
            s += 3.0
        # Prefer larger models
        size_gb = m.disk_size_mb / 1024
        s += min(size_gb / 10, 2.0)
        # Penalize if barely fits
        if m.vram_required_mb > primary_vram * 0.9 and primary_vram > 0:
            s -= 1.0
        # Boost known-good models
        if "gemma4" in m.id:
            s += 1.0
        if "qwen3" in m.id:
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
    """Manage model recommendations, download, and verification."""

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host

    def recommend(self, info: SystemInfo, profile: HardwareProfile) -> ModelRecommendation:
        return _recommend_models(info, profile)

    async def list_installed(self) -> list[dict[str, Any]]:
        """List models already pulled in Ollama."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            models = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    models.append({"name": parts[0], "size": parts[2] if len(parts) > 2 else ""})
            return models
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return []

    async def is_installed(self, model_id: str) -> bool:
        installed = await self.list_installed()
        return any(m["name"] == model_id for m in installed)

    async def download(self, model: ModelInfo, progress_callback=None) -> bool:
        """Download a model via Ollama with progress tracking."""
        if progress_callback:
            progress_callback(f"Downloading {model.name} ({model.disk_size_mb // 1024} GB)...")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama",
                "pull",
                model.id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            if proc.stdout:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode().strip()
                    if progress_callback and decoded:
                        progress_callback(decoded)

            await proc.wait()
            return proc.returncode == 0

        except FileNotFoundError:
            if progress_callback:
                progress_callback("[red]Ollama not found. Install Ollama first.[/]")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"[red]Download failed: {e}[/]")
            return False

    async def get_disk_required(self, models: list[ModelInfo]) -> int:
        """Return total disk space required in MB."""
        return sum(m.disk_size_mb for m in models)

    async def verify(self, model_id: str) -> tuple[bool, str]:
        """Verify a model is correctly installed."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.strip().splitlines():
                if line.startswith(model_id):
                    parts = line.split()
                    size_str = parts[2] if len(parts) > 2 else "unknown"
                    return True, size_str
            return False, ""
        except Exception:
            return False, ""
