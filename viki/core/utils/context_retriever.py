import os
import re
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

class ContextRetriever:
    """
    Tier 4 Optimization: Selective Context Injection (RAG).
    Pulls relevant code snippets from the workspace when full context is pruned.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.max_snippet_len = 1500
        self.max_snippets = 5

    async def get_relevant_context(self, query: str) -> str:
        """
        Finds relevant code snippets in the workspace based on keyword overlap.
        """
        viki_logger.info(f"ContextRetriever: Finding relevant snippets for '{query[:30]}...'")
        
        # 1. Extract keywords from query
        keywords = self._extract_keywords(query)
        if not keywords:
            return ""

        # 2. Search for relevant files
        relevant_files = self._search_files(keywords)
        if not relevant_files:
            return ""

        # 3. Extract snippets from top files
        snippets = []
        for file_path in relevant_files[:self.max_snippets]:
            snippet = self._get_file_snippet(file_path, keywords)
            if snippet:
                rel_path = os.path.relpath(file_path, self.workspace_dir)
                snippets.append(f"--- FILE: {rel_path} ---\n{snippet}")

        if not snippets:
            return ""

        return "\n\nRELEVANT CODE SNIPPETS (Retrieved via RAG):\n" + "\n\n".join(snippets)

    def _extract_keywords(self, query: str) -> List[str]:
        # Simple tokenization, remove common words
        words = re.findall(r'\w+', query.lower())
        stopwords = {'the', 'a', 'in', 'to', 'for', 'with', 'is', 'on', 'that', 'of', 'and', 'or', 'an', 'viki'}
        keywords = [w for w in words if len(w) > 3 and w not in stopwords]
        return list(set(keywords))

    def _search_files(self, keywords: List[str]) -> List[str]:
        scored_files = []
        try:
            for root, dirs, files in os.walk(self.workspace_dir):
                # Prune common noise dirs
                if any(d in root for d in ('.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build', '.gemini')):
                    continue
                
                for file in files:
                    if file.endswith(('.py', '.js', '.ts', '.html', '.css', '.md', '.yaml', '.yml', '.json')):
                        path = os.path.join(root, file)
                        score = 0
                        # Score by filename first
                        file_lower = file.lower()
                        for kw in keywords:
                            if kw in file_lower:
                                score += 10
                        
                        # Only check content if filename matches or it's a small number of files
                        # For now, let's keep it simple and just return a few candidates
                        if score > 0:
                            scored_files.append((score, path))
            
            scored_files.sort(key=lambda x: x[0], reverse=True)
            return [f[1] for f in scored_files]
        except Exception as e:
            viki_logger.debug(f"ContextRetriever search failed: {e}")
            return []

    def _get_file_snippet(self, file_path: str, keywords: List[str]) -> Optional[str]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            if len(content) <= self.max_snippet_len:
                return content

            # Find best snippet around keywords
            lines = content.splitlines()
            best_start = 0
            max_matches = -1
            
            # Simple sliding window over lines
            window_size = 30
            for i in range(len(lines) - window_size):
                window_text = "\n".join(lines[i:i+window_size]).lower()
                matches = sum(1 for kw in keywords if kw in window_text)
                if matches > max_matches:
                    max_matches = matches
                    best_start = i
            
            snippet = "\n".join(lines[best_start:best_start+window_size])
            if len(snippet) > self.max_snippet_len:
                snippet = snippet[:self.max_snippet_len] + "..."
            return snippet
        except Exception:
            return None
