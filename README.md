# Local AI Chat with Ollama (Qwen 3.5 35B)

A fully local AI chat application powered by Ollama running Qwen 3.5 35B, with a ChatGPT-style interface, persistent conversation memory, and web search capabilities. Zero cloud LLM costs — all inference runs on your machine.

## Hardware Requirements

Benchmarked on a **MacBook Pro M4 Pro with 48GB unified memory**.

- **Model size in memory**: ~25GB VRAM (Q4_K_M quantization)
- **Peak system memory usage**: ~40GB (including macOS file cache)
- **Inference speed**: ~10 tokens/second for chat
- **Minimum recommended RAM**: 48GB for comfortable usage alongside other apps

The Qwen 3.5 35B model uses a Mixture-of-Experts (MoE) architecture — only ~3.5B parameters are active per token, which is why it runs at decent speed despite the 35B parameter count.

## Setup

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.com
```

Start the Ollama server:
```bash
ollama serve
```

### 2. Pull the Qwen 3.5 35B model (4-bit quantization)

```bash
ollama pull qwen3.5:35b-a3b
```

This downloads the Q4_K_M quantized version (~23GB). The download takes a few minutes depending on your connection.

Verify it's working:
```bash
ollama run qwen3.5:35b-a3b "Hello, what model are you?"
```

### 3. Backend setup

```bash
# Create a conda environment
conda create -n local-chat python=3.13 -y
conda activate local-chat

# Install dependencies
cd server
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your Serper API key (get one at https://serper.dev)
```

### 4. Frontend setup

```bash
cd client
npm install
```

### 5. Run

In two terminal tabs:

```bash
# Terminal 1: Backend
cd server
conda activate local-chat
python main.py
# Runs on http://localhost:8000

# Terminal 2: Frontend
cd client
npm run dev
# Runs on http://localhost:5173
```

Open **http://localhost:5173** in your browser.

## Architecture

```
Browser (React)  <-->  FastAPI Backend  <-->  Ollama (localhost:11434)
                            |
                            +--> Serper API (web search)
                            |      |
                            |      +--> trafilatura (content extraction)
                            |
                            +--> SQLite (conversation memory)
```

### Conversation Memory

Conversations are persisted in a local SQLite database (`server/chat.db`). Each conversation stores the full message history — user messages, assistant responses, and tool results. When you return to a conversation, the entire history is loaded and sent to the model as context, giving it memory of what was discussed.

The database uses WAL mode for concurrent read/write performance and foreign key cascades for clean conversation deletion.

### Web Search with Content Extraction

When the model decides it needs current information, it calls the `web_search` tool. The search pipeline works as follows:

1. **Serper API** returns top 5 Google search results (titles, snippets, URLs)
2. **trafilatura** fetches the actual web pages from the top 3 URLs and extracts clean article text — stripping ads, navigation, boilerplate HTML
3. The extracted content (up to 2000 chars per page) plus any Serper answer box data is assembled into a rich context block
4. This context is fed back to the local Qwen model, which summarizes and answers based on **actual article content**, not just search snippets

This approach gives the local model access to real, current information while keeping the entire pipeline local (only the search query hits Serper's API — the LLM summarization is fully local).

### Thinking Tokens

Qwen 3.5 supports chain-of-thought reasoning. The model's internal "thinking" is streamed to the UI in real-time — you can see the model reason through a problem before it produces its answer. The thinking block appears during generation and hides once the final answer starts streaming, similar to DeepSeek's approach.

## Tech Stack

- **Frontend**: React + TypeScript + Vite, with react-markdown for rendering
- **Backend**: FastAPI + aiosqlite + httpx
- **LLM**: Ollama with Qwen 3.5 35B (Q4_K_M)
- **Search**: Serper API + trafilatura for content extraction
- **Streaming**: Server-Sent Events (SSE) for real-time token streaming

## Project Structure

```
├── client/                  # React frontend
│   └── src/
│       ├── App.tsx          # Main layout + state
│       ├── App.css          # Dark theme styles
│       ├── api.ts           # API client + SSE streaming
│       ├── types.ts         # TypeScript interfaces
│       └── components/
│           ├── ChatArea.tsx      # Messages + streaming handler
│           ├── Message.tsx       # Markdown message rendering
│           ├── MessageInput.tsx  # Auto-resizing input
│           └── Sidebar.tsx       # Conversation list
│
├── server/                  # FastAPI backend
│   ├── main.py              # Routes, SSE streaming, tool call orchestration
│   ├── db.py                # SQLite CRUD operations
│   ├── ollama_client.py     # Ollama API client
│   ├── search.py            # Serper + trafilatura web search
│   └── .env.example         # Environment template
```

## License

MIT
