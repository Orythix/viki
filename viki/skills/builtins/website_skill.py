"""
Website skill: generate a minimal static site or scaffold in the workspace.
Manus-style "delivers websites".
"""
import os
import re
from typing import Dict, Any, List

from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.utils.path_sandbox import validate_output_path


def _md_to_html_simple(md: str) -> str:
    """Minimal Markdown to HTML (bold, links, headers, lists)."""
    if not md:
        return ""
    html = md
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)
    html = re.sub(r"\n\n+", "</p><p>", html)
    html = re.sub(r"\n", "<br/>", html)
    if not html.strip().startswith("<"):
        html = f"<p>{html}</p>"
    return html


class WebsiteSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "website"

    @property
    def description(self) -> str:
        return (
            "Create a static website in the workspace. Actions: create_site(output_dir=..., title=..., pages=[{path, title, content_md}, ...]), "
            "or scaffold(template=minimal|landing|doc, output_dir=..., title=...)."
        )

    def _write_page(self, output_dir: str, site_title: str, path: str, title: str, content_md: str) -> str:
        content_html = _md_to_html_simple(content_md or "")
        full_path = os.path.join(output_dir, path.lstrip("/"))
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | {site_title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header><h1>{site_title}</h1></header>
  <main>
    <h2>{title}</h2>
    {content_html}
  </main>
</body>
</html>"""
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html)
        return full_path

    async def execute(self, params: Dict[str, Any]) -> str:
        output_dir = params.get("output_dir") or params.get("path") or params.get("output")
        if not output_dir:
            return "Provide output_dir= where to create the site."
        ok, path_or_err = validate_output_path(output_dir, controller=self._controller)
        if not ok:
            return path_or_err

        output_dir = path_or_err
        title = params.get("title") or "My Site"
        action = params.get("action", "create_site")

        if action == "scaffold":
            template = (params.get("template") or "minimal").lower()
            os.makedirs(output_dir, exist_ok=True)
            if template == "landing":
                pages = [
                    {"path": "index.html", "title": "Home", "content_md": f"# Welcome to {title}\n\nA simple landing page."},
                ]
            elif template == "doc":
                pages = [
                    {"path": "index.html", "title": "Home", "content_md": f"# {title}\n\nDocumentation home."},
                    {"path": "about.html", "title": "About", "content_md": "## About\n\nAbout this site."},
                ]
            else:
                pages = [
                    {"path": "index.html", "title": "Home", "content_md": f"# {title}\n\nMinimal static site."},
                ]
            for p in pages:
                self._write_page(output_dir, title, p["path"], p["title"], p.get("content_md", ""))
            css_path = os.path.join(output_dir, "style.css")
            with open(css_path, "w", encoding="utf-8") as f:
                f.write("body { font-family: system-ui, sans-serif; max-width: 720px; margin: 0 auto; padding: 1rem; }\nheader { border-bottom: 1px solid #eee; }\na { color: #06c; }\n")
            return f"Scaffold '{template}' created in {output_dir} (index, style.css)."

        # create_site
        pages = params.get("pages") or params.get("page_list")
        if not pages or not isinstance(pages, list):
            return "Provide pages= (list of {path, title, content_md}). Or use action=scaffold with template=minimal|landing|doc."
        os.makedirs(output_dir, exist_ok=True)
        written = []
        for p in pages:
            path = p.get("path", "index.html")
            page_title = p.get("title", "Page")
            content_md = p.get("content_md", p.get("content", ""))
            written.append(self._write_page(output_dir, title, path, page_title, content_md))
        css_path = os.path.join(output_dir, "style.css")
        if not os.path.isfile(css_path):
            with open(css_path, "w", encoding="utf-8") as f:
                f.write("body { font-family: system-ui, sans-serif; max-width: 720px; margin: 0 auto; padding: 1rem; }\nheader { border-bottom: 1px solid #eee; }\na { color: #06c; }\n")
        return f"Site created in {output_dir}: {len(written)} page(s)."
