import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

# Support both old and new package names
HAS_DDG = False
DDGS = None
try:
    from ddgs import DDGS as _DDGS
    DDGS = _DDGS
    HAS_DDG = True
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGS
        DDGS = _DDGS
        HAS_DDG = True
    except ImportError:
        pass

class ResearchSkill(BaseSkill):
    """
    Advanced internet research capability with Async support.
    Supports web search (via DuckDuckGo) and page reading (via aiohttp + BeautifulSoup).
    """
    def __init__(self):
        self._name = "research"
        self._description = "Search the web or read a URL. Use: research(query='...') to search, research(url='...') to read a page."
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to look up on the web"
                },
                "url": {
                    "type": "string",
                    "description": "URL to read and extract content from"
                }
            }
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        if 'url' in params:
            return await self._read_page(params['url'])

        if 'query' in params:
            if not HAS_DDG:
                return "Error: Search library not installed. Run: pip install ddgs"
            return await self._search(params['query'])
            
        return "Error: Specify 'query' to search or 'url' to read a page."

    async def _search(self, query: str) -> str:
        try:
            def ddg_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(
                        query, 
                        region='wt-wt',       # Worldwide (English priority)
                        safesearch='off',      # Unfiltered results
                        max_results=5
                    ))

            results = await asyncio.to_thread(ddg_search)
            
            if not results:
                return f"No results found for '{query}'."
            
            formatted = [f"--- SEARCH RESULTS for '{query}' ---"]
            for i, r in enumerate(results, 1):
                title = r.get('title', 'No title')
                url = r.get('href', r.get('link', 'No URL'))
                body = r.get('body', r.get('snippet', 'No summary'))
                formatted.append(f"Result {i}: {title}\nURL: {url}\nSummary: {body}\n")
            
            return "\n".join(formatted)
        except Exception as e:
            viki_logger.error(f"Search error: {e}")
            return f"Search error: {str(e)}"

    async def _read_page(self, url: str) -> str:
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True, ssl=False) as response:
                    if response.status != 200:
                        return f"Error: HTTP {response.status} when fetching {url}"
                    
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        return f"Error: URL returned non-HTML content ({content_type})"
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
                tag.decompose()
            
            # Try to find main content area first
            main_content = soup.find('main') or soup.find('article') or soup.find('div', {'role': 'main'})
            if main_content:
                text = main_content.get_text(separator='\n')
            else:
                text = soup.get_text(separator='\n')
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = '\n'.join(lines)
            
            # Truncate to avoid overwhelming the LLM
            if len(clean_text) > 4000:
                clean_text = clean_text[:4000] + "\n... (truncated)"
            
            return f"CONTENT FROM {url}:\n\n{clean_text}"
            
        except asyncio.TimeoutError:
            return f"Error: Timeout reading {url} (15s limit exceeded)"
        except Exception as e:
            viki_logger.error(f"Page read error for {url}: {e}")
            return f"Error reading page: {str(e)}"
