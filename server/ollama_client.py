import os
import json
import httpx
from collections.abc import AsyncGenerator

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:35b-a3b")

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
    }
]


def _build_ollama_messages(db_messages: list[dict], new_user_message: str | None = None) -> list[dict]:
    """Convert DB messages into the Ollama message format."""
    messages = []
    for msg in db_messages:
        messages.append({"role": msg["role"], "content": msg["content"]})
    if new_user_message:
        messages.append({"role": "user", "content": new_user_message})
    return messages


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
) -> dict:
    """
    Non-streaming chat call to Ollama. Returns the full response object.
    Used for the initial tool-call detection pass.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if include_tools:
        payload["tools"] = TOOLS

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
