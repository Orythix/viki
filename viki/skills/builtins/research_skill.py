import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from urllib.parse import urlparse
import ipaddress
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
    def __init__(self, controller=None):
        self.controller = controller
        self._name = "research"
        self._description = "Invisible / Headless web research. PREFERRED for answering questions. Use: research(query='...') to search."
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
            
            # --- Knowledge Extraction Bridge ---
            if self.controller:
                 await self._extract_knowledge_from_results(query, results)

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

    async def _extract_knowledge_from_results(self, query: str, results: List[dict]):
        """Distills snippets into trigger/fact pairs for LearningModule."""
        if not self.controller or not hasattr(self.controller, 'learning'): return
        
        viki_logger.info(f"Research: Extracting autonomous knowledge from '{query}'")
        for r in results[:3]: # Only top 3 for quality
            body = r.get('body', r.get('snippet', ''))
            if len(body) > 30:
                # Store as a lesson using thread pool to avoid blocking
                await asyncio.to_thread(
                    self.controller.learning.save_lesson,
                    trigger=f"Tell me about {query} ({r.get('title', '')})",
                    fact=body,
                    source=r.get('href', 'web')
                )

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Validate URL to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)
            
            # Only allow http and https
            if parsed.scheme not in ['http', 'https']:
                return False, f"Protocol '{parsed.scheme}' not allowed"
            
            # Get hostname
            hostname = parsed.hostname
            if not hostname:
                return False, "Invalid hostname"
            
            # Try to resolve to IP and check if it's private
            try:
                import socket
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
                
                # Block private/local IPs (SSRF protection)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False, f"Access to private IP addresses not allowed: {ip_str}"
                
                # Block cloud metadata endpoints
                if ip_str.startswith('169.254'):
                    return False, "Access to cloud metadata endpoints not allowed"
                    
            except (socket.gaierror, ValueError):
                # If we can't resolve, allow it (might be blocked by network anyway)
                pass
            
            # Block localhost variations
            if hostname.lower() in ['localhost', '127.0.0.1', '0.0.0.0', '::1']:
                return False, "Access to localhost not allowed"
            
            return True, url
            
        except Exception as e:
            return False, f"URL validation error: {str(e)}"
    
    async def _read_page(self, url: str) -> str:
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            
            # Validate URL to prevent SSRF
            is_valid, result = self._validate_url(url)
            if not is_valid:
                return f"URL validation failed: {result}"
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                # Re-enable SSL verification for security
                async with session.get(url, allow_redirects=True, ssl=True) as response:
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
