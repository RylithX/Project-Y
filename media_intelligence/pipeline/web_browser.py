"""
Universal Web Browsing Engine.
Provides web search (DuckDuckGo Lite) and web article reader mode / content extraction.
"""
import re
import urllib.parse
from typing import List, Dict, Tuple, Optional, Any
import aiohttp
from ..sources.web_page import WebPageSource
from ..types import WebPageContent

class UniversalWebBrowser:

    def __init__(self):
        self.page_source = WebPageSource()

    async def search(self, query: str, max_results: int = 5) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """Searches DuckDuckGo Lite and returns top results with titles, snippets, and URLs."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded = urllib.parse.quote_plus(query.strip())
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(url, data={"q": query.strip()}, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status != 200:
                        return [], f"Search returned HTTP {resp.status}"
                    html_text = await resp.text(errors="replace")

            # Parse DuckDuckGo Lite HTML results
            results = []
            link_pattern = re.compile(r'<a[^>]+class=[\'"]result-link[\'"][^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
            snippet_pattern = re.compile(r'<td[^>]+class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)

            links = link_pattern.findall(html_text)
            snippets = snippet_pattern.findall(html_text)

            for i, (raw_href, raw_title) in enumerate(links[:max_results]):
                clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                clean_url = raw_href
                if "uddg=" in raw_href:
                    m = re.search(r'uddg=([^&]+)', raw_href)
                    if m:
                        clean_url = urllib.parse.unquote(m.group(1))

                snip = ""
                if i < len(snippets):
                    snip = re.sub(r'<[^>]+>', '', snippets[i]).strip()

                results.append({
                    "title": clean_title,
                    "url": clean_url,
                    "snippet": snip
                })

            return results, None
        except Exception as e:
            return [], str(e)

    async def browse(self, url: str) -> WebPageContent:
        """Fetches and extracts clean readable markdown and metadata from a web page."""
        return await self.page_source.fetch_page_content(url)

    async def search_and_read(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """Searches the web and automatically reads the top matching article for deep context."""
        results, err = await self.search(query, max_results=max_results)
        if err or not results:
            return {"query": query, "results": [], "error": err, "deep_page": None}

        # Automatically fetch the top result page content
        top_url = results[0]["url"]
        page_content = None
        try:
            page_content = await self.browse(top_url)
        except Exception:
            pass

        return {
            "query": query,
            "results": results,
            "top_page": page_content.__dict__ if page_content else None,
            "error": None
        }

async def browse_url(url: str) -> WebPageContent:
    browser = UniversalWebBrowser()
    return await browser.browse(url)

async def search_and_read(query: str, max_results: int = 3) -> Dict[str, Any]:
    browser = UniversalWebBrowser()
    return await browser.search_and_read(query, max_results=max_results)
