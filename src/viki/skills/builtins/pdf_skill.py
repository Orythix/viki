"""
PDF edit skill (Nano PDF-style): extract text, optional simple edit. Heavy: PyMuPDF or pdfplumber.
Paths are restricted to allowed roots (workspace, data).
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.utils.path_sandbox import validate_output_path


class PdfSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def description(self) -> str:
        return "Extract text from PDF or apply simple edit (replace text). Params: path, action=extract|edit, target=, replacement= (for edit)."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to PDF."},
                "action": {"type": "string", "enum": ["extract", "edit"], "default": "extract"},
                "target": {"type": "string", "description": "Text to replace (for edit)."},
                "replacement": {"type": "string", "description": "New text (for edit)."},
            },
            "required": ["path"],
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        path = params.get("path")
        if not path:
            return "Provide path= to an existing PDF file."
        ok, path_or_err = validate_output_path(path, controller=self._controller)
        if not ok:
            return path_or_err
        path = path_or_err
        if not os.path.isfile(path):
            return "File not found or not a PDF file."
        action = (params.get("action") or "extract").lower()

        if action == "extract":
            try:
                import fitz
                doc = fitz.open(path)
                text = "\n".join([page.get_text() for page in doc])[:15000]
                doc.close()
                return f"EXTRACT:\n{text}" if text.strip() else "No text in PDF."
            except ImportError:
                try:
                    import pdfplumber
                    with pdfplumber.open(path) as pdf:
                        text = "\n".join([(p.extract_text() or "") for p in pdf.pages])[:15000]
                    return f"EXTRACT:\n{text}" if text.strip() else "No text in PDF."
                except ImportError:
                    return "Install PyMuPDF (fitz) or pdfplumber for PDF extraction."
            except Exception as e:
                return f"PDF extract error: {e}"

        if action == "edit":
            target = params.get("target")
            replacement = params.get("replacement")
            if not target or replacement is None:
                return "For edit provide target= and replacement=."
            try:
                import fitz
                doc = fitz.open(path)
                for page in doc:
                    text_instances = page.search_for(target)
                    for inst in text_instances:
                        page.add_redact_annot(inst, replacement)
                    page.apply_redactions()
                out_path = path.replace(".pdf", "_edited.pdf")
                doc.save(out_path)
                doc.close()
                return f"Saved edited PDF to {out_path}"
            except ImportError:
                return "PDF edit requires PyMuPDF (fitz)."
            except Exception as e:
                return f"PDF edit error: {e}"

        return "Unknown action. Use extract or edit."