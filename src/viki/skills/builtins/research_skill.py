import asyncio
import warnings
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Dict, Any, List
from urllib.parse import urlparse
import ipaddress
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

# Prefer ddgs (new package name); fall back to duckduckgo_search and suppress rename warning
HAS_DDG = False
DDGS = None
try:
    from ddgs import DDGS as _DDGS
    DDGS = _DDGS
    HAS_DDG = True
except ImportError:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
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
        # --- AIR GAP PROTECTION ---
        if self.controller and getattr(self.controller, "air_gap", False):
            if self.controller and hasattr(self.controller, "track_touched_item"):
                self.controller.track_touched_item("blocked_actions", "Network: Attempted web access while AIR-GAPPED")
            return "Safety Block: Internet access is DISABLED (Air-Gap active)."

        if 'url' in params:
            return await self._read_page(params['url'])

        if 'query' in params:
            if not HAS_DDG:
                raise RuntimeError("Error: Search library not installed. Run: pip install ddgs")
            return await self._search(params['query'])
            
        raise RuntimeError("Error: Specify 'query' to search or 'url' to read a page.")

    async def _search(self, query: str) -> str:
        try:
            def ddg_search():
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    with DDGS() as ddgs:
                        return list(ddgs.text(
                            query,
                            region='wt-wt',
                            safesearch='off',
                            max_results=5
                        ))

            results = await asyncio.to_thread(ddg_search)
            
            if not results:
                return f"No results found for '{query}'."
            
            # --- Knowledge Extraction Bridge ---
            if self.controller:
                 if hasattr(self.controller, "track_touched_item"):
                      self.controller.track_touched_item("touched_files", "Network: DuckDuckGo Search")
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
            raise RuntimeError(f"Search error: {str(e)}")

    def _extract_facts_from_text(self, text: str, max_facts: int = 3) -> List[str]:
        """
        Lightweight deterministic fact extractor.
        We split into sentences and keep the most informative ones.
        """
        if not text:
            return []

        normalized = re.sub(r"\s+", " ", str(text)).strip()
        if not normalized:
            return []

        # Sentence split (best-effort).
        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        seen = set()
        facts: List[str] = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) < 25:
                continue
            lower = s.lower()
            if lower in seen:
                continue
            # Skip common low-signal boilerplate.
            if any(b in lower for b in ["cookie", "subscribe", "privacy policy", "terms of service"]):
                continue
            facts.append(s)
            seen.add(lower)
            if len(facts) >= max_facts:
                break
        return facts

    async def _extract_knowledge_from_results(self, query: str, results: List[dict]):
        """Distills snippets into trigger/fact pairs for LearningModule."""
        if not self.controller or not hasattr(self.controller, 'learning'): return
        
        viki_logger.info(f"Research: Extracting autonomous knowledge from '{query}'")
        for r in results[:3]: # Only top 3 for quality
            body = r.get('body', r.get('snippet', '')) or ""
            title = r.get('title', '') or ""
            url = r.get('href', r.get('link', 'web')) or "web"

            facts = self._extract_facts_from_text(body, max_facts=3)
            if not facts and len(body) > 30:
                # Fallback: store the snippet as a single fact.
                facts = [body.strip()[:500]]

            for fact in facts:
                fact_with_source = f"SOURCE: {url} | {fact}"
                await asyncio.to_thread(
                    self.controller.learning.save_lesson,
                    trigger=f"RESEARCH_FACT: {query} ({title})",
                    fact=fact_with_source,
                    source=url,
                    source_task="web_search",
                )

    def _validate_url(self, url: str) -> tuple[bool, str]:  #NOSONAR
        """Validate URL to prevent SSRF attacks.
        
        SECURITY FIX: HIGH-002 - Enhanced SSRF protection including:
        - IPv6 loopback and private addresses
        - DNS rebinding protection
        - Additional bypass vectors
        """
        try:
            parsed = urlparse(url)
            
            # Only allow http and https
            if parsed.scheme not in ['http', 'https']:
                return False, f"Protocol '{parsed.scheme}' not allowed"
            
            # Get hostname
            hostname = parsed.hostname
            if not hostname:
                return False, "Invalid hostname"
            
            # Block localhost variations (including IPv6)
            localhost_variants = [
                'localhost', '127.0.0.1', '0.0.0.0', '::1', 
                '[::1]', '0:0:0:0:0:0:0:1', '0:0:0:0:0:0:0:0',
                '127.0.0.0', '127.255.255.255',  # Loopback range
            ]
            if hostname.lower() in localhost_variants:
                return False, "Access to localhost not allowed"
            
            # Block hostname that starts with common internal prefixes
            if hostname.lower().startswith(('127.', '192.168.', '10.', '172.')):
                # Additional check for 172.16.0.0 - 172.31.255.255 range
                try:
                    parts = hostname.split('.')
                    if len(parts) == 4:
                        first = int(parts[0])
                        second = int(parts[1])
                        if first == 172 and 16 <= second <= 31:
                            return False, "Access to private IP range not allowed"
                except (ValueError, IndexError):
                    pass
            
            # Try to resolve to IP and check if it's private
            try:
                import socket
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
                
                # Block private/local IPs (SSRF protection)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False, f"Access to private IP addresses not allowed: {ip_str}"
                
                # Block cloud metadata endpoints (169.254.169.254 and IPv6 equivalent)
                if ip_str == '169.254.169.254':
                    return False, "Access to cloud metadata endpoints not allowed"
                
                # Block IPv6 private/link-local/multicast ranges
                if ip.version == 6:
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                        return False, "Access to restricted IPv6 addresses not allowed"
                    # Block AWS IPv6 metadata endpoint
                    if str(ip).startswith('fd00:ec2:'):
                        return False, "Access to cloud metadata endpoints not allowed"
                        
            except (socket.gaierror, ValueError) as e:
                # If we can't resolve, allow it (might be blocked by network anyway)
                # But log for monitoring
                viki_logger.debug(f"Could not resolve hostname {hostname}: {e}")
                # Allow it; network may still block.
            
            # Block URL-encoded variations of localhost
            import urllib.parse
            try:
                decoded_hostname = urllib.parse.unquote(hostname)
                if decoded_hostname != hostname:
                    # Recursively validate decoded version
                    return self._validate_url(url.replace(hostname, decoded_hostname))
            except Exception:
                pass
            
            # Block suspicious TLDs that might be used for DNS rebinding
            # (This is a heuristic - not foolproof)
            suspicious_tlds = ['.local', '.internal', '.localhost', '.localdomain']
            for tld in suspicious_tlds:
                if hostname.lower().endswith(tld):
                    return False, f"Access to internal hostname not allowed: {hostname}"

            # Check destination allowlist
            if self.controller and hasattr(self.controller, "capabilities"):
                cap = self.controller.capabilities.get("internet_research")
                if cap and cap.meta.get("destination_allowlist"):
                    allowlist = cap.meta["destination_allowlist"]
                    if not any(hostname.lower().endswith(domain.lower()) for domain in allowlist):
                        if hasattr(self.controller, "track_touched_item"):
                             self.controller.track_touched_item("blocked_actions", f"Network: {hostname}")
                        return False, f"Access to domain '{hostname}' is not in the allowlist."
            
            # Track allowed access
            if self.controller and hasattr(self.controller, "track_touched_item"):
                 self.controller.track_touched_item("touched_files", f"Network: {hostname}")

            return True, url
            
        except Exception as e:
            return False, f"URL validation error: {str(e)}"
    
    async def _read_page(self, url: str) -> str:  #NOSONAR
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            
            # Validate URL to prevent SSRF
            is_valid, result = self._validate_url(url)
            if not is_valid:
                return f"URL validation failed: {result}"
            
            # SECURITY FIX: DNS rebinding protection
            # Store the resolved IP and verify it doesn't change during request
            import socket
            try:
                hostname = urlparse(url).hostname
                resolved_ip = socket.gethostbyname(hostname)
            except Exception:
                resolved_ip = None
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                # Re-enable SSL verification for security
                async with session.get(url, allow_redirects=True, ssl=True) as response:
                    # DNS rebinding check: verify final IP matches expected
                    if resolved_ip:
                        final_url = str(response.url)
                        final_hostname = urlparse(final_url).hostname
                        try:
                            final_ip = socket.gethostbyname(final_hostname)
                            if final_ip != resolved_ip:
                                viki_logger.warning(f"DNS rebinding detected: {hostname} -> {final_ip}")
                                return "Security: DNS rebinding attempt blocked"
                        except Exception:
                            pass
                    
                    if response.status != 200:
                        raise RuntimeError(f"Error: HTTP {response.status} when fetching {url}")
                    
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        raise RuntimeError(f"Error: URL returned non-HTML content ({content_type})")
                    
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
            raw_text = '\n'.join(lines)
            
            # --- TOKEN OPTIMIZATION for Local Models ---
            from core.utils.token_optimizer import condense_text
            # Use query for semantic trimming if possible
            # We'll need to store the query in _last_query or similar
            clean_text = condense_text(raw_text, max_chars=2500)
            
            # Persist extracted facts from the page content.
            if self.controller and hasattr(self.controller, "learning"):
                facts = self._extract_facts_from_text(clean_text, max_facts=3)
                for fact in facts:
                    fact_with_source = f"SOURCE: {url} | {fact}"
                    await asyncio.to_thread(
                        self.controller.learning.save_lesson,
                        trigger=f"RESEARCH_FACT: URL({url})",
                        fact=fact_with_source,
                        source=url,
                        source_task="web_page",
                    )
            
            return f"CONTENT FROM {url}:\n\n{clean_text}"
            
        except asyncio.TimeoutError:
            raise RuntimeError(f"Error: Timeout reading {url} (15s limit exceeded)")
        except Exception as e:
            viki_logger.error(f"Page read error for {url}: {e}")
            raise RuntimeError(f"Error reading page: {str(e)}")
