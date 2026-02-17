"""
Summarize URLs, PDFs, or YouTube (Molty summarize-style). Uses research_skill for URLs, PyMuPDF/pdfplumber for PDF, optional yt-dlp for YouTube.
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class SummarizeSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "summarize"

    @property
    def description(self) -> str:
        return "Summarize a URL, PDF file path, or YouTube URL. Params: url= or file= (path to PDF)."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch and summarize."},
                "file": {"type": "string", "description": "Path to PDF file to summarize."},
            },
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        url = params.get("url")
        file_path = params.get("file")
        text = ""
        if url:
            if "youtube.com" in url or "youtu.be" in url:
                try:
                    import subprocess
                    proc = await asyncio.to_thread(
                        lambda: subprocess.run(["yt-dlp", "--skip-download", "--print", "description", url],
                        capture_output=True, text=True, timeout=30)
                    )
                    text = (proc.stdout or "")[:15000] if proc and hasattr(proc, 'stdout') else ""
                except Exception as e:
                    viki_logger.debug(f"yt-dlp: {e}")
                    research = getattr(self._controller, "skill_registry", None) and self._controller.skill_registry.get_skill("research") if self._controller else None
                    if research:
                        text = await research.execute({"url": url}) or ""
                    else:
                        text = ""
            else:
                research = getattr(self._controller, "skill_registry", None) and self._controller.skill_registry.get_skill("research") if self._controller else None
                if research:
                    text = await research.execute({"url": url}) or ""
        elif file_path and os.path.isfile(file_path):
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                text = "\n".join([page.get_text() for page in doc])[:15000]
                doc.close()
            except ImportError:
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        text = "\n".join([p.extract_text() or "" for p in pdf.pages])[:15000]
                except ImportError:
                    return "Install PyMuPDF or pdfplumber for PDF summarization."
            except Exception as e:
                return f"PDF error: {e}"
        else:
            return "Provide url= or file= (path to PDF)."

        if not text or len(text.strip()) < 50:
            return "Could not extract enough text to summarize."

        # Summarize via model_router if available
        if self._controller and hasattr(self._controller, "model_router"):
            try:
                model = self._controller.model_router.get_model(capabilities=["general"])
                messages = [{"role": "user", "content": f"Summarize the following in at most 300 words:\n\n{text[:12000]}"}]
                summary = await model.chat(messages, temperature=0.3)
                return f"SUMMARY:\n{summary}" if summary else f"Raw excerpt:\n{text[:1500]}"
            except Exception as e:
                viki_logger.debug(f"Summarize LLM: {e}")
        return f"EXTRACT (no LLM summary):\n{text[:2000]}..."
