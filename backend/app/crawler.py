import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.security import assert_public_http_url

EMAIL_RE = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}")
PRIORITY_WORDS = (
    "about",
    "company",
    "contact",
    "team",
    "management",
    "news",
    "vacancy",
    "requisites",
    "o-kompanii",
    "kontakty",
    "rukovodstvo",
    "komanda",
    "novosti",
    "vakansii",
    "rekvizity",
)


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str
    status_code: int
    content_hash: str
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


@dataclass
class CrawlResult:
    pages: list[CrawledPage]
    blocked_urls: list[str]
    errors: list[str]


class SafeCrawler:
    def __init__(self) -> None:
        settings = get_settings()
        self.user_agent = settings.crawler_user_agent
        self.max_pages = settings.crawler_max_pages
        self.timeout = settings.crawler_timeout_seconds
        self.max_bytes = 2_000_000

    async def _robots(self, origin: str, client: httpx.AsyncClient) -> RobotFileParser:
        robots_url = urljoin(origin, "/robots.txt")
        parser = RobotFileParser(robots_url)
        try:
            response = await client.get(robots_url)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                parser.parse([])
        except httpx.HTTPError:
            parser.parse([])
        return parser

    @staticmethod
    def _normalize(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", parsed.query, "")
        )

    async def crawl(self, start_url: str) -> CrawlResult:
        assert_public_http_url(start_url)
        start_url = self._normalize(start_url)
        origin_parts = urlparse(start_url)
        origin = f"{origin_parts.scheme}://{origin_parts.netloc}"
        pages: list[CrawledPage] = []
        blocked: list[str] = []
        errors: list[str] = []
        queue = [start_url]
        seen: set[str] = set()
        limits = httpx.Limits(max_connections=3, max_keepalive_connections=2)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            max_redirects=5,
            limits=limits,
            headers=headers,
        ) as client:
            robots = await self._robots(origin, client)
            while queue and len(pages) < self.max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    assert_public_http_url(url)
                except ValueError as exc:
                    blocked.append(f"{url}: {exc}")
                    continue
                if not robots.can_fetch(self.user_agent, url):
                    blocked.append(url)
                    continue
                try:
                    async with client.stream("GET", url) as response:
                        if 300 <= response.status_code < 400:
                            location = response.headers.get("location")
                            if not location:
                                errors.append(f"{url}: редирект без Location")
                                continue
                            redirect_url = self._normalize(urljoin(url, location))
                            try:
                                assert_public_http_url(redirect_url)
                            except ValueError as exc:
                                blocked.append(f"{redirect_url}: {exc}")
                                continue
                            if urlparse(redirect_url).netloc != origin_parts.netloc:
                                blocked.append(f"{redirect_url}: внешний редирект запрещён")
                                continue
                            queue.insert(0, redirect_url)
                            continue
                        content_type = response.headers.get("content-type", "").lower()
                        if (
                            "text/html" not in content_type
                            and "application/xhtml+xml" not in content_type
                        ):
                            errors.append(f"{url}: неподдерживаемый MIME {content_type[:80]}")
                            continue
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > self.max_bytes:
                                raise ValueError("страница превышает лимит 2 МБ")
                        encoding = response.encoding or "utf-8"
                        html = bytes(data).decode(encoding, errors="replace")
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append(f"{url}: {str(exc)[:300]}")
                    continue
                soup = BeautifulSoup(html, "lxml")
                for element in soup(["script", "style", "noscript", "svg"]):
                    element.decompose()
                text = " ".join(soup.get_text(" ", strip=True).split())[:100_000]
                title = soup.title.get_text(strip=True)[:500] if soup.title else ""
                links: list[str] = []
                for anchor in soup.find_all("a", href=True):
                    candidate = self._normalize(urljoin(url, str(anchor["href"])))
                    parsed = urlparse(candidate)
                    if parsed.netloc == origin_parts.netloc and parsed.scheme in {"http", "https"}:
                        links.append(candidate)
                pages.append(
                    CrawledPage(
                        url=str(response.url),
                        title=title,
                        text=text,
                        status_code=response.status_code,
                        content_hash=hashlib.sha256(bytes(data)).hexdigest(),
                        emails=sorted(set(EMAIL_RE.findall(text)))[:50],
                        phones=sorted(set(PHONE_RE.findall(text)))[:50],
                        links=sorted(set(links)),
                    )
                )
                candidates = [link for link in links if link not in seen and link not in queue]
                candidates.sort(
                    key=lambda link: not any(word in link.lower() for word in PRIORITY_WORDS)
                )
                queue.extend(candidates[: self.max_pages])
                await asyncio.sleep(0.35)
        return CrawlResult(pages=pages, blocked_urls=blocked, errors=errors)
