# CLAUDE.md - Project Guide for AI Assistants

## Project Overview

Local AI chat application powered by Ollama (Qwen 3.5 35B-A3B) with a ChatGPT-style React frontend, FastAPI backend, web search via Serper API, and SQLite persistence. Fully local LLM inference — no cloud AI APIs.

## Architecture

```
React (Vite, port 5173) → FastAPI (port 8000) → Ollama (port 11434, qwen3.5:35b-a3b)
                               │
                               ├── Serper API (web search) → trafilatura (content extraction)
                               └── SQLite (chat.db - conversations + messages)
```

## Key Files

### Backend (server/)
- `main.py` — FastAPI app, routes, SSE streaming, tool call orchestration
- `ollama_client.py` — Ollama API client, system prompt, sliding window context builder, summary generation
- `search.py` — Serper API + trafilatura web page content extraction
- `db.py` — aiosqlite CRUD (conversations, messages, summaries)
- `.env` — SERPER_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL (not committed, see .env.example)

### Frontend (client/src/)
- `App.tsx` — Main layout, conversation state management
- `App.css` — All styles (dark theme, ChatGPT-like)
- `api.ts` — API client, SSE streaming via ReadableStream
- `types.ts` — TypeScript interfaces (Conversation, Message, SSE events)
- `components/ChatArea.tsx` — Message display, streaming handler, thinking block
- `components/Message.tsx` — Markdown rendering (react-markdown + rehype-highlight)
- `components/MessageInput.tsx` — Auto-resizing textarea, Enter to send
- `components/Sidebar.tsx` — Conversation list, new chat, delete

## Running

```bash
# Backend (conda env: local-chat)
cd server && conda activate local-chat && python main.py

# Frontend
cd client && npm run dev

# Ollama must be running: ollama serve
```

## Key Design Decisions

### Tool Calling Flow
Qwen's thinking mode interferes with tool calls during streaming. Solution: non-streaming first pass to detect tool calls, then streaming second pass for the final answer.

1. `chat_no_stream()` with tools → detect tool calls
2. If tool calls: execute search → `stream_chat()` without tools → stream answer
3. If no tool calls: send first-pass content or stream fresh response

### Sliding Window Context
Conversations don't send full history to Ollama. After 20 messages:
- Older messages are summarized (3-5 sentences) by the model
- Summary stored in `conversations.summary` DB column
- Ollama receives: system prompt + summary + last 20 messages
- Re-summarization triggers every 10 new messages beyond window
- `CONTEXT_WINDOW_SIZE = 20` in ollama_client.py

### Web Search Pipeline
Not just snippets — actual page content:
1. Serper API → top 5 results (titles, snippets, URLs)
2. trafilatura fetches top 3 URLs in parallel, extracts clean text
3. Max 2000 chars per page to keep context manageable
4. Includes Serper answer box / knowledge graph if available

### SSE Event Types
```
token        — streaming content token
thinking     — model's chain-of-thought (shown then hidden)
tool_status  — "Searching the web for: ..."
done         — stream complete, includes conversation_id
error        — error message
```

## Database Schema

```sql
conversations: id, title, summary, summary_up_to_index, created_at
messages: id, conversation_id (FK CASCADE), role (user/assistant/tool), content, created_at
```

## Environment

- Python 3.13, conda env `local-chat`
- Node.js, Vite dev server proxies /api → localhost:8000
- Ollama model: qwen3.5:35b-a3b (35B total, 3B active MoE, Q4_K_M, ~25GB VRAM)
- Hardware baseline: MacBook Pro M4 Pro, 48GB RAM, ~10 tok/s

## Common Issues

- **Tool calls not detected**: Qwen + streaming + tools can silently drop tool calls. The non-streaming first pass fixes this.
- **Unicode in macOS filenames**: Screenshots have narrow no-break spaces (U+202F). Use Python `shutil.copy()` not shell `cp`.
- **`verbatimModuleSyntax`**: TypeScript config requires `import type` for type-only imports.
- **Old DB with temp IDs**: If you see duplicate key React errors, delete `server/chat.db` and restart.
