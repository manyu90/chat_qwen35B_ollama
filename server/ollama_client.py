import os
import json
import logging
from datetime import date

import httpx
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:35b-a3b")

# Sliding window: keep last N messages as full context
CONTEXT_WINDOW_SIZE = 20

SYSTEM_PROMPT = f"""You are a helpful AI assistant. Today's date is {date.today().strftime('%B %d, %Y')}.

When you need current or recent information, use the web_search tool. Always include the current year ({date.today().year}) in your search queries for time-sensitive topics.

When presenting information from web searches, cite your sources and be clear about what is current vs. historical data.

You can run Python code using the run_python tool for calculations, data analysis, plots, and fetching data. Always call plt.show() for plots."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use this when the user "
                "asks about recent events, current data, or anything you need to look up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python code in a sandboxed environment. Use this for "
                "calculations, data analysis, plotting, and fetching data. "
                "Available packages: numpy, pandas, matplotlib, seaborn, scipy, "
                "scikit-learn, yfinance, requests, and standard library modules "
                "(math, statistics, datetime, json, csv, collections, itertools, re, random). "
                "For plots, use matplotlib and call plt.show() to display them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute",
                    }
                },
                "required": ["code"],
            },
        },
    },
]


def _build_ollama_messages(
    db_messages: list[dict],
    new_user_message: str | None = None,
    summary: str = "",
) -> list[dict]:
    """
    Build the Ollama messages array with sliding window context management.

    If the conversation is short (<=CONTEXT_WINDOW_SIZE), send everything.
    If it's long, prepend the summary of older messages and only include
    the most recent CONTEXT_WINDOW_SIZE messages in full.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if summary and len(db_messages) > CONTEXT_WINDOW_SIZE:
        # Inject summary of older context, then only recent messages
        messages.append({
            "role": "system",
            "content": f"Summary of earlier conversation:\n{summary}",
        })
        recent = db_messages[-CONTEXT_WINDOW_SIZE:]
        logger.info(
            f"Using sliding window: {len(db_messages)} total msgs, "
            f"sending summary + last {len(recent)}"
        )
    else:
        # Conversation is short enough — send everything
        recent = db_messages

    for msg in recent:
        messages.append({"role": msg["role"], "content": msg["content"]})

    if new_user_message:
        messages.append({"role": "user", "content": new_user_message})

    return messages


async def generate_summary(messages_to_summarize: list[dict]) -> str:
    """
    Ask Ollama to summarize a batch of conversation messages.
    This runs as a quick non-streaming call with no tools.
    """
    if not messages_to_summarize:
        return ""

    # Build a transcript of the messages to summarize
    transcript_lines = []
    for msg in messages_to_summarize:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        # Truncate very long messages (e.g. tool results) for the summary
        if len(content) > 500:
            content = content[:500] + "..."
        transcript_lines.append(f"{role}: {content}")

    transcript = "\n".join(transcript_lines)

    summary_prompt = [
        {
            "role": "system",
            "content": (
                "You are a summarizer. Condense the following conversation into a brief "
                "summary (3-5 sentences). Capture key topics discussed, any decisions made, "
                "important facts mentioned, and user preferences expressed. "
                "Be concise but preserve important context."
            ),
        },
        {
            "role": "user",
            "content": f"Summarize this conversation:\n\n{transcript}",
        },
    ]

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": summary_prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            summary = data.get("message", {}).get("content", "")
            logger.info(f"Generated summary ({len(summary)} chars) for {len(messages_to_summarize)} messages")
            return summary
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return ""


async def stream_chat(
    messages: list[dict],
    include_tools: bool = True,
) -> AsyncGenerator[dict, None]:
    """
    Stream a chat response from Ollama.

    Yields parsed JSON chunks from the Ollama streaming API.
    Each chunk has at minimum: {"message": {"role": ..., "content": ...}, "done": bool}
    The final chunk (done=true) contains the complete assembled message.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
    }
    if include_tools:
        payload["tools"] = TOOLS

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    yield chunk
                except json.JSONDecodeError:
                    continue


async def chat_no_stream(
    messages: list[dict],
    include_tools: bool = True,
    max_retries: int = 5,
) -> dict:
    """
    Non-streaming chat call to Ollama. Returns the full response object.
    Used for the initial tool-call detection pass.

    Retries on 500 errors because Qwen sometimes generates malformed tool
    call JSON that Ollama fails to parse internally.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if include_tools:
        payload["tools"] = TOOLS

    last_error = None
    for attempt in range(1, max_retries + 1):
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            if response.status_code == 200:
                if attempt > 1:
                    logger.info(f"Ollama succeeded on attempt {attempt}/{max_retries}")
                return response.json()

            last_error = response.text
            logger.warning(
                f"Ollama returned {response.status_code} on attempt {attempt}/{max_retries}: {response.text}"
            )

    # All retries exhausted — fall back to a no-tools call so the user
    # still gets a response instead of an error
    logger.error(
        f"Ollama failed all {max_retries} retries with tools; "
        f"falling back to no-tools call"
    )
    payload.pop("tools", None)
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
