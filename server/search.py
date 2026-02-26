import asyncio
import logging
import os

import httpx
import trafilatura

logger = logging.getLogger(__name__)

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_URL = "https://google.serper.dev/search"

# Max chars of extracted content per page (keep context manageable for local LLM)
MAX_CONTENT_PER_PAGE = 2000
# How many pages to actually fetch content from
MAX_PAGES_TO_FETCH = 3
# Timeout for fetching individual pages
FETCH_TIMEOUT = 10.0


async def _fetch_page_content(url: str) -> str | None:
    """Fetch a URL and extract main text content using trafilatura."""
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        # trafilatura is sync, run in thread pool
        text = await asyncio.to_thread(
            trafilatura.extract,
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )

        if text and len(text.strip()) > 100:
            return text.strip()[:MAX_CONTENT_PER_PAGE]
        return None
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None


async def web_search(query: str) -> str:
    """Search the web and return results with actual page content."""

    # Step 1: Get search results from Serper
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            SERPER_URL,
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query},
        )
        response.raise_for_status()
        data = response.json()

    organic = data.get("organic", [])[:5]
    if not organic:
        return f"No search results found for: {query}"

    # Step 2: Fetch actual page content from top results (in parallel)
    urls_to_fetch = [r.get("link", "") for r in organic[:MAX_PAGES_TO_FETCH] if r.get("link")]
    logger.info(f"Fetching content from {len(urls_to_fetch)} pages...")

    page_contents = await asyncio.gather(
        *[_fetch_page_content(url) for url in urls_to_fetch],
        return_exceptions=True,
    )

    # Step 3: Build rich context for the LLM
    lines = [f"Web search results for: {query}\n"]

    # Include answer box if Serper provides one
    answer_box = data.get("answerBox", {})
    if answer_box:
        ab_answer = answer_box.get("answer") or answer_box.get("snippet", "")
        if ab_answer:
            lines.append(f"DIRECT ANSWER: {ab_answer}\n")

    # Include knowledge graph if available
    kg = data.get("knowledgeGraph", {})
    if kg:
        kg_desc = kg.get("description", "")
        if kg_desc:
            lines.append(f"KNOWLEDGE GRAPH: {kg.get('title', '')} - {kg_desc}\n")

    for i, result in enumerate(organic, 1):
        title = result.get("title", "No title")
        snippet = result.get("snippet", "No snippet")
        link = result.get("link", "")
        lines.append(f"--- Source {i}: {title} ---")
        lines.append(f"URL: {link}")
        lines.append(f"Snippet: {snippet}")

        # Add full page content if we fetched it
        if i <= len(page_contents):
            content = page_contents[i - 1]
            if isinstance(content, str) and content:
                lines.append(f"Full content:\n{content}")
            else:
                lines.append("(Could not extract page content)")

        lines.append("")

    result_text = "\n".join(lines)
    logger.info(f"Total search context length: {len(result_text)} chars")
    return result_text
