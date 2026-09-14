"""
Universal Web Page, Wiki, and Article Extractor Plugin.
Uses a robust HTMLParser engine with browser headers to extract full structured article text from Wikipedia, Fandom, blogs, docs, and modern websites.
"""
import re
import time
import html
import json
from typing import Dict, List, Optional, Tuple, Set
from urllib.parse import urlparse, unquote
from html.parser import HTMLParser
import aiohttp

from ..core.base_source import BaseMediaSource
from ..core.registry import register_source
from ..types import MediaMetadata, WebPageContent

class StructuredHTMLArticleReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ignore_tags = {
            "script", "style", "noscript", "iframe", "svg", "nav", "footer", 
            "header", "aside", "form", "select", "button", "canvas", "audio", "video"
        }
        self.in_ignore = 0
        self.blocks: List[str] = []
        self.current_tag: Optional[str] = None
        self.current_text: List[str] = []
        self.title = ""
        self.in_title = False
        self.headings: List[str] = []
        self.meta: Dict[str, str] = {}
        self.seen_texts: Set[str] = set()

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        t = tag.lower()
        if t in self.ignore_tags:
            self.in_ignore += 1
            return
        if self.in_ignore > 0:
            return

        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if t == "title":
            self.in_title = True
        elif t == "meta":
            prop = attr_dict.get("property") or attr_dict.get("name")
            cont = attr_dict.get("content")
            if prop and cont:
                self.meta[prop.lower()] = html.unescape(cont.strip())

        if t in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "td", "th", "dt", "dd"]:
            self._flush()
            self.current_tag = t

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in self.ignore_tags:
            self.in_ignore = max(0, self.in_ignore - 1)
            return
        if self.in_ignore > 0:
            return
        if t == "title":
            self.in_title = False
        if t == self.current_tag:
            self._flush()

    def handle_data(self, data: str):
        if self.in_ignore > 0:
            return
        if self.in_title:
            self.title += data
            return
        if self.current_tag:
            self.current_text.append(data)

    def _flush(self):
        if self.current_text and self.current_tag:
            raw = "".join(self.current_text)
            clean = re.sub(r'\s+', ' ', raw).strip()
            clean = re.sub(r'\[\s*(?:\d+|edit|citation needed)\s*\]', '', clean, flags=re.IGNORECASE).strip()
            
            # Filter out single-word language links & tiny nav items
            if len(clean) >= 6 and clean not in self.seen_texts:
                self.seen_texts.add(clean)
                if self.current_tag.startswith("h"):
                    lvl = int(self.current_tag[1])
                    self.headings.append(clean)
                    self.blocks.append(f"{'#' * lvl} {clean}")
                elif self.current_tag == "li":
                    self.blocks.append(f"* {clean}")
                elif self.current_tag == "blockquote":
                    self.blocks.append(f"> {clean}")
                elif self.current_tag == "pre":
                    self.blocks.append(f"```\n{clean}\n```")
                else:
                    self.blocks.append(clean)
        self.current_text = []
        self.current_tag = None

@register_source(priority=10)
class WebPageSource(BaseMediaSource):

    def match(self, url_or_path: str) -> bool:
        if not url_or_path:
            return False
        u = url_or_path.strip().lower()
        return u.startswith("http://") or u.startswith("https://")

    async def extract_metadata(self, url_or_path: str) -> MediaMetadata:
        content = await self.fetch_page_content(url_or_path)
        return MediaMetadata(
            url_or_path=url_or_path,
            platform="wiki" if "wiki" in content.domain else "web",
            media_type="article",
            title=content.title,
            author=content.author or content.domain,
            description=content.description[:1000],
            extracted_at=time.time(),
            extra={"domain": content.domain, "word_count": content.word_count}
        )

    async def fetch_page_content(self, url: str) -> WebPageContent:
        url = url.strip()
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # 1. Specialized Wikipedia & MediaWiki API Fetcher (High-speed & 100% clean)
        if "wikipedia.org" in domain and "/wiki/" in url:
            wiki_content = await self._fetch_wikipedia_api(url, parsed)
            if wiki_content:
                return wiki_content

        # 2. Universal Fetcher with Browser Headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

        html_text = ""
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
                    if resp.status == 200:
                        html_text = await resp.text(errors="replace")
                    else:
                        html_text = f"<html><body><p>HTTP {resp.status} while fetching {url}</p></body></html>"
        except Exception as e:
            html_text = f"<html><body><p>Failed to retrieve webpage: {e}</p></body></html>"

        return self._parse_html(url, domain, html_text)

    async def _fetch_wikipedia_api(self, url: str, parsed) -> Optional[WebPageContent]:
        try:
            domain_parts = parsed.netloc.split('.')
            lang = domain_parts[0] if len(domain_parts) >= 3 else "en"
            title_encoded = parsed.path.split('/wiki/', 1)[-1]
            title = unquote(title_encoded)

            api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts|info&explaintext=1&inprop=url&titles={title_encoded}&format=json&redirects=1"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MediaIntelligence/2.0"}

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pages = data.get("query", {}).get("pages", {})
                        for pid, pdata in pages.items():
                            if pid == "-1":
                                continue
                            art_title = pdata.get("title", title.replace('_', ' '))
                            full_extract = pdata.get("extract", "").strip()

                            if full_extract:
                                cleaned_text = re.sub(r'={2,5}\s*(.*?)\s*={2,5}', r'\n\n## \1\n', full_extract)
                                cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()

                                md_lines = [
                                    f"# {art_title} (Wikipedia)",
                                    f"**Source URL:** {url}\n",
                                    cleaned_text[:30000]
                                ]
                                md_content = "\n\n".join(md_lines)
                                first_para = full_extract.split('\n\n')[0] if '\n\n' in full_extract else full_extract[:400]

                                return WebPageContent(
                                    url=url,
                                    title=art_title,
                                    domain=parsed.netloc,
                                    author="Wikipedia Contributors",
                                    description=first_para[:600],
                                    markdown_content=md_content,
                                    main_text=cleaned_text[:30000],
                                    headings=re.findall(r'##\s+(.*)', md_content)[:25],
                                    opengraph={"og:title": art_title, "og:site_name": "Wikipedia"},
                                    word_count=len(cleaned_text.split()),
                                    fetched_at=time.time()
                                )
        except Exception as e:
            print(f"[WIKIPEDIA API NOTICE] {e}")
        return None

    def _parse_html(self, url: str, domain: str, raw_html: str) -> WebPageContent:
        parser = StructuredHTMLArticleReader()
        try:
            parser.feed(raw_html)
        except Exception:
            pass

        title = parser.title.strip() or domain
        og_dict = parser.meta
        if og_dict.get("og:title"):
            title = og_dict["og:title"]
        elif og_dict.get("twitter:title"):
            title = og_dict["twitter:title"]

        author = og_dict.get("author") or og_dict.get("og:site_name") or domain
        desc = og_dict.get("description") or og_dict.get("og:description") or og_dict.get("twitter:description", "")

        blocks = parser.blocks
        # Remove leading language-selection blocks if present
        filtered_blocks = []
        skip_noise = True
        for b in blocks:
            if skip_noise:
                if b.startswith("#") or len(b) > 40:
                    skip_noise = False
                    filtered_blocks.append(b)
            else:
                filtered_blocks.append(b)

        if not filtered_blocks:
            filtered_blocks = blocks

        main_text = "\n\n".join(filtered_blocks[:300])
        if not main_text or len(main_text) < 40:
            # Fallback simple text stripper
            raw_text = re.sub(r'<[^>]+>', ' ', raw_html)
            raw_text = html.unescape(raw_text)
            raw_text = re.sub(r'\s+', ' ', raw_text).strip()
            main_text = raw_text[:25000]

        word_count = len(main_text.split())

        md_lines = [f"# {title}", f"**Source:** [{domain}]({url})\n"]
        if filtered_blocks:
            md_lines.extend(filtered_blocks[:300])
        else:
            md_lines.append(main_text[:25000])

        full_markdown = "\n\n".join(md_lines)[:30000]

        return WebPageContent(
            url=url,
            title=title,
            domain=domain,
            author=author,
            description=desc,
            markdown_content=full_markdown,
            main_text=main_text[:30000],
            headings=parser.headings[:30],
            opengraph=og_dict,
            word_count=word_count,
            fetched_at=time.time()
        )
