"""News integration. RSS feeds by default, optional NewsAPI key."""

import urllib.request
import urllib.parse
import json
import re
import html
from xml.etree import ElementTree
from datetime import datetime, timezone

from .base import tool_fn, IntegrationCache


_cache = IntegrationCache(default_ttl=300)

RSS_FEEDS = {
    "general": "https://feeds.bbci.co.uk/news/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
}


def _fetch_rss(feed_url: str, limit: int = 5) -> list[dict]:
    """Fetch and parse an RSS feed."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()

    root = ElementTree.fromstring(data)
    items = []

    for item in root.iter("item"):
        title = html.unescape(item.findtext("title", "") or "")
        description = html.unescape(item.findtext("description", "") or "")
        link = item.findtext("link", "") or ""
        pub_date = item.findtext("pubDate", "") or ""

        desc_clean = re.sub(r"<[^>]+>", "", description).strip()
        if len(desc_clean) > 200:
            desc_clean = desc_clean[:200] + "..."

        items.append({
            "title": title,
            "description": desc_clean,
            "link": link,
            "date": pub_date,
        })

        if len(items) >= limit:
            break

    return items


def _fetch_newsapi(category: str, api_key: str, limit: int = 5) -> list[dict]:
    """Fetch news from NewsAPI."""
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?category={category}&pageSize={limit}&apiKey={api_key}"
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    articles = data.get("articles", [])
    items = []
    for a in articles:
        title = a.get("title", "") or ""
        description = a.get("description", "") or ""
        if len(description) > 200:
            description = description[:200] + "..."
        items.append({
            "title": title,
            "description": description,
            "link": a.get("url", ""),
            "date": a.get("publishedAt", ""),
        })
    return items


def _format_items(items: list[dict]) -> str:
    if not items:
        return "[no news found]"

    lines = [f"News ({len(items)} stories):", ""]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['title']}")
        if item["description"]:
            lines.append(f"   {item['description']}")
        if item["link"]:
            lines.append(f"   {item['link']}")
        lines.append("")
    return "\n".join(lines)


def _get_headlines(category: str = "general", max_results: int = 5) -> str:
    """Get top news headlines by category."""
    category = category.lower()
    if category not in RSS_FEEDS:
        available = ", ".join(RSS_FEEDS.keys())
        return f"[error] unknown category '{category}'. Available: {available}"

    cached = _cache.get(f"headlines:{category}")
    if cached:
        return cached

    try:
        items = _fetch_rss(RSS_FEEDS[category], limit=max_results)
        result = _format_items(items)
        _cache.set(f"headlines:{category}", result, ttl=300)
        return result
    except Exception as e:
        return f"[error] news headlines: {e}"


def _search_news(query: str, max_results: int = 5) -> str:
    """Search news across RSS feeds."""
    cached = _cache.get(f"news_search:{query}")
    if cached:
        return cached

    try:
        all_items = []
        for category in RSS_FEEDS.values():
            try:
                items = _fetch_rss(category, limit=max_results)
                all_items.extend(items)
            except Exception:
                continue

        query_lower = query.lower()
        matched = [
            item for item in all_items
            if query_lower in item["title"].lower()
            or query_lower in item["description"].lower()
        ]
        matched = matched[:max_results]

        if not matched:
            return f"[no news matching '{query}']"

        result = _format_items(matched)
        _cache.set(f"news_search:{query}", result, ttl=300)
        return result
    except Exception as e:
        return f"[error] news search: {e}"


get_headlines = tool_fn(
    "get_headlines",
    "Get top news headlines by category. Categories: general, world, technology, science, business.",
    _get_headlines,
)

search_news = tool_fn(
    "search_news",
    "Search recent news articles for a specific topic or keyword.",
    _search_news,
)


def get_tools(config: dict) -> list:
    tools = [get_headlines, search_news]

    api_key = config.get("news", {}).get("api_key", "")
    if api_key:
        def _api_headlines(category: str = "general", max_results: int = 5) -> str:
            try:
                items = _fetch_newsapi(category, api_key, limit=max_results)
                return _format_items(items)
            except Exception as e:
                return f"[error] NewsAPI: {e}"

        newsapi_headlines = tool_fn(
            "get_headlines_detailed",
            "Get top headlines via NewsAPI (more sources). Requires configured API key.",
            _api_headlines,
        )
        tools.append(newsapi_headlines)

    return tools
