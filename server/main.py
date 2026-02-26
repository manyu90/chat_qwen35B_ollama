import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load env before other local imports so they pick up the values
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db import (
    init_db,
    create_conversation,
    list_conversations,
    get_conversation,
    delete_conversation,
    add_message,
    get_messages,
    count_messages,
    get_conversation_summary,
    update_conversation_summary,
)
from ollama_client import (
    stream_chat,
    chat_no_stream,
    _build_ollama_messages,
    generate_summary,
    CONTEXT_WINDOW_SIZE,
)
from search import web_search


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Local Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _execute_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """
    Execute each tool call and return a list of tool-result messages
    suitable for appending to the Ollama messages array.
    """
    results: list[dict] = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if name == "web_search":
            query = args.get("query", "")
            logger.info(f"Executing web_search for: {query}")
            search_result = await web_search(query)
            logger.info(f"Search result length: {len(search_result)}")
            results.append({"role": "tool", "content": search_result})
        else:
            results.append({"role": "tool", "content": f"Unknown tool: {name}"})

    return results


# ---------------------------------------------------------------------------
# SSE streaming generator
# ---------------------------------------------------------------------------

async def _chat_stream(conversation_id: str, user_message: str):
    """
    Generator that yields SSE events for a chat turn.

    Flow:
    1. Stream from Ollama with tools enabled, forwarding content tokens.
    2. When the stream finishes, check for tool_calls in the final message.
    3. If tool calls found: execute them, emit tool_status events, then
       stream a follow-up Ollama call (no tools) and forward those tokens.
    4. Emit a done event and persist everything to the DB.
    """

    # -- Build messages from conversation history with sliding window -----
    db_msgs = await get_messages(conversation_id)
    summary, summary_up_to = await get_conversation_summary(conversation_id)
    ollama_messages = _build_ollama_messages(
        db_msgs, new_user_message=user_message, summary=summary
    )

    # -- Save user message to DB ------------------------------------------
    await add_message(conversation_id, "user", user_message)

    # -- Step 1: Non-streaming call with tools to detect tool calls --------
    # Qwen's thinking mode can swallow tool calls during streaming,
    # so we do a non-streaming first pass for reliable tool detection.
    yield _sse({"type": "thinking", "content": "Thinking"})

    try:
        first_response = await chat_no_stream(ollama_messages, include_tools=True)
    except Exception as e:
        logger.exception("Ollama non-streaming error")
        yield _sse({"type": "error", "content": f"Ollama error: {str(e)}"})
        yield _sse({"type": "done", "conversation_id": conversation_id})
        return

    first_msg = first_response.get("message", {})
    tool_calls = first_msg.get("tool_calls", [])
    first_content = first_msg.get("content", "")
    first_thinking = first_msg.get("thinking", "")

    # Forward the thinking from the first pass
    if first_thinking:
        yield _sse({"type": "thinking", "content": "...\n" + first_thinking})

    logger.info(f"First pass: tool_calls={len(tool_calls)}, content_len={len(first_content)}, thinking_len={len(first_thinking)}")

    collected_content = ""

    if tool_calls:
        # Notify the frontend about tool activity
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "unknown")
            fn_args = tc.get("function", {}).get("arguments", {})
            query = fn_args.get("query", "") if isinstance(fn_args, dict) else ""
            yield _sse({
                "type": "tool_status",
                "content": f"Searching the web for: {query}" if fn_name == "web_search" else f"Calling tool: {fn_name}",
            })

        # Execute the tool calls
        tool_result_messages = await _execute_tool_calls(tool_calls)

        # Build updated message list for the follow-up call
        follow_up_messages = list(ollama_messages)
        # The assistant message that triggered tool calls (don't include
        # any "let me search" filler content — keep it minimal)
        assistant_tc_msg = {"role": "assistant", "content": "", "tool_calls": tool_calls}
        follow_up_messages.append(assistant_tc_msg)
        follow_up_messages.extend(tool_result_messages)

        # Save tool result messages to DB
        for trm in tool_result_messages:
            await add_message(conversation_id, "tool", trm["content"])

        # Stream the final answer after tool results
        try:
            async for chunk in stream_chat(follow_up_messages, include_tools=False):
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                if thinking:
                    yield _sse({"type": "thinking", "content": thinking})
                token = msg.get("content", "")
                if token:
                    collected_content += token
                    yield _sse({"type": "token", "content": token})
        except Exception as e:
            logger.exception("Ollama follow-up streaming error")
            yield _sse({"type": "error", "content": f"Ollama error on follow-up: {str(e)}"})
            yield _sse({"type": "done", "conversation_id": conversation_id})
            return

        logger.info(f"Follow-up response length: {len(collected_content)}")
    else:
        # No tool calls — stream a response (reuse first_content if available)
        if first_content:
            collected_content = first_content
            yield _sse({"type": "token", "content": first_content})
        else:
            # Stream a fresh response without tools
            try:
                async for chunk in stream_chat(ollama_messages, include_tools=False):
                    msg = chunk.get("message", {})
                    thinking = msg.get("thinking", "")
                    if thinking:
                        yield _sse({"type": "thinking", "content": thinking})
                    token = msg.get("content", "")
                    if token:
                        collected_content += token
                        yield _sse({"type": "token", "content": token})
            except Exception as e:
                yield _sse({"type": "error", "content": f"Ollama error: {str(e)}"})
                yield _sse({"type": "done", "conversation_id": conversation_id})
                return

    # -- Save assistant response to DB ------------------------------------
    if collected_content:
        await add_message(conversation_id, "assistant", collected_content)

    # -- Summarize older messages if conversation is getting long ----------
    total_msgs = await count_messages(conversation_id)
    # Trigger summarization when we have more than the window size
    # and either no summary yet or summary is stale (10+ new messages since last summary)
    if total_msgs > CONTEXT_WINDOW_SIZE:
        msgs_since_summary = total_msgs - summary_up_to
        if not summary or msgs_since_summary > CONTEXT_WINDOW_SIZE + 10:
            all_msgs = await get_messages(conversation_id)
            # Summarize everything except the last CONTEXT_WINDOW_SIZE messages
            msgs_to_summarize = all_msgs[:-CONTEXT_WINDOW_SIZE]
            if msgs_to_summarize:
                logger.info(
                    f"Generating summary for {len(msgs_to_summarize)} older messages "
                    f"(total: {total_msgs})"
                )
                new_summary = await generate_summary(msgs_to_summarize)
                if new_summary:
                    await update_conversation_summary(
                        conversation_id, new_summary, len(msgs_to_summarize)
                    )

    # -- Done event -------------------------------------------------------
    yield _sse({"type": "done", "conversation_id": conversation_id})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a message and receive a streamed SSE response."""
    conversation_id = req.conversation_id

    if not conversation_id:
        # Create a new conversation with the first ~50 chars of the message as title
        title = req.message[:50].strip()
        if len(req.message) > 50:
            title += "..."
        conv = await create_conversation(title)
        conversation_id = conv["id"]
    else:
        # Verify the conversation exists
        conv = await get_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

    return StreamingResponse(
        _chat_stream(conversation_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/conversations")
async def conversations_list():
    """List all conversations, most recent first."""
    return await list_conversations()


@app.get("/api/conversations/{conv_id}")
async def conversation_detail(conv_id: str):
    """Get a single conversation with all its messages."""
    conv = await get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.delete("/api/conversations/{conv_id}")
async def conversation_delete(conv_id: str):
    """Delete a conversation and all its messages."""
    deleted = await delete_conversation(conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
