from html.parser import HTMLParser

import httpx

from src.application.ports.integrations.web_resource_fetcher import FetchedWebResource, IWebResourceFetcher


class HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.casefold() == "title":
            self._in_title = True
        name = attributes.get("name")
        if tag.casefold() == "meta" and name is not None and name.casefold() == "description":
            self.description = attributes.get("content")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
            self.title = " ".join(part.strip() for part in self._title_parts if part.strip()) or None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


class HTTPWebResourceFetcher(IWebResourceFetcher):
    async def fetch(self, url: str) -> FetchedWebResource | None:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "cortex-learning-resources/1.0"})
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        parser = HTMLMetadataParser()
        parser.feed(response.text[:100_000])
        title = normalize_metadata_text(parser.title)
        excerpt = normalize_metadata_text(parser.description)
        if not title and not excerpt:
            return None
        return FetchedWebResource(title=title, excerpt=excerpt)


def normalize_metadata_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").split())
    return normalized[:500] or None
