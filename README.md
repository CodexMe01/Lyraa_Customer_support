<div align="center">

# 🤖 Lyraa — AI-Powered Customer Support Agent

**A production-ready, RAG-driven customer support agent with streaming chat, document ingestion, MCP server support, and a polished web frontend.**

[![Python](https://img.shields.io/badge/Python-3.14+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.14+-7C3AED?style=flat)](https://docs.llamaindex.ai)
[![Pinecone](https://img.shields.io/badge/Pinecone-Vector%20DB-00B388?style=flat)](https://pinecone.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Server](#running-the-server)
- [API Reference](#-api-reference)
- [MCP Server](#-mcp-server)
- [Frontend](#-frontend)
- [How It Works](#-how-it-works)
- [Contributing](#-contributing)

---

## 🌟 Overview

**Lyraa** is an intelligent customer support agent that combines **Retrieval-Augmented Generation (RAG)**, **intent classification**, and a **ReAct agent** to deliver fast, context-aware support responses. It handles everything from casual greetings to complex order lookups and company knowledge base queries — all with real-time token streaming.

Designed as a full-stack solution, Lyraa ships with:
- A **FastAPI** backend with SSE streaming chat
- A **Pinecone** vector store for semantic search
- **Cohere Re-ranking** for higher quality retrieval
- **Cloudinary** cloud storage for uploaded documents
- An **MCP (Model Context Protocol)** server for AI agent integrations
- A **vanilla HTML/CSS/JS** frontend with a landing page, chat dashboard, and API docs

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                │
│         Landing Page  │  Agent Dashboard  │  API Docs           │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP / SSE
┌───────────────────────────────▼─────────────────────────────────┐
│                      FastAPI Backend                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Intent Classifier                       │   │
│  │   smalltalk → instant reply  (zero LLM cost)             │   │
│  │   general_query → RAG pipeline                           │   │
│  │   order_query   → Order Status Tool                      │   │
│  │   ambiguous     → ReAct Agent (full reasoning loop)      │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                          │                                       │
│  ┌──────────────┐  ┌─────▼────────┐  ┌─────────────────────┐   │
│  │  RAG Engine  │  │  ReAct Agent │  │   Order Status Tool  │   │
│  │  (LlamaIndex)│  │  (LlamaIndex)│  │   Escalation Tool    │   │
│  └──────┬───────┘  └──────────────┘  └──────────┬──────────┘   │
│         │                                         │              │
│  ┌──────▼───────┐                        ┌────────▼──────────┐  │
│  │   Pinecone   │                        │   Slack Notifier   │  │
│  │ Vector Store │                        │  (Human Escalation)│  │
│  └──────────────┘                        └───────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Ingestion Pipeline                            │  │
│  │  PDF / DOCX / CSV / Images / Web URLs                     │  │
│  │  OCR → Semantic Chunking → Google GenAI Embeddings        │  │
│  │  → Pinecone Upsert                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      MCP Server (FastMCP)                        │
│              ask_support_agent(query, user_id)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **Intent Classification** | Zero-LLM regex/keyword router — routes smalltalk, order queries, and general queries before touching any AI pipeline |
| 💬 **Streaming Chat (SSE)** | Token-by-token streaming via Server-Sent Events for a real-time, responsive chat experience |
| 📚 **RAG Pipeline** | Semantic search over your custom knowledge base using Pinecone + Cohere Re-ranking |
| 🔄 **ReAct Agent** | Full LlamaIndex ReAct agent as a fallback for ambiguous or complex queries |
| 📁 **Document Ingestion** | Ingest PDFs, DOCX, images (OCR), CSVs, TXT, and live web URLs via Tavily web scraping |
| ☁️ **Cloud Storage** | Files uploaded to Cloudinary with per-user folders and 24-hour auto-expiry |
| 🔔 **Human Escalation** | Automatically pages a human agent via Slack when the bot cannot resolve an issue |
| 🔌 **MCP Server** | Expose the support agent as an MCP tool for integration with Claude Desktop and other AI systems |
| 🖥️ **Web Frontend** | Polished multi-page UI: landing page, live chat dashboard, and API documentation |
| 📊 **Observability** | Optional Arize Phoenix tracing for LlamaIndex (non-Windows) |

---

## 🛠 Tech Stack

### Backend

| Layer | Technology |
|---|---|
| API Framework | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| AI Orchestration | [LlamaIndex](https://docs.llamaindex.ai) |
| LLM | [Groq](https://groq.com) (`llama-3.1-8b-instant`) |
| Embeddings | [Google GenAI](https://ai.google.dev) (`text-embedding-004`) |
| Vector Store | [Pinecone](https://pinecone.io) |
| Re-ranking | [Cohere](https://cohere.com) |
| Cloud Storage | [Cloudinary](https://cloudinary.com) |
| Web Scraping | [Tavily](https://tavily.com) |
| MCP Server | [FastMCP](https://github.com/jlowin/fastmcp) |
| Notifications | [Slack SDK](https://slack.dev/python-slack-sdk) |
| OCR | [PyMuPDF](https://pymupdf.readthedocs.io) + [pytesseract](https://github.com/madmaze/pytesseract) |

### Frontend

| Layer | Technology |
|---|---|
| Structure | HTML5 |
| Styling | Vanilla CSS (no frameworks) |
| Logic | Vanilla JavaScript |
| Typography | Inter (Google Fonts) |

---

## 📂 Project Structure

```
Lyraa_agent/
├── Back_end/
│   ├── agent/
│   │   ├── bot.py          # Core routing logic: intent → response path
│   │   ├── intent.py       # Zero-LLM intent classifier (regex + keywords)
│   │   ├── rag.py          # Pinecone + Cohere query engine (singleton)
│   │   └── tools.py        # Order status + human escalation tools
│   ├── app/
│   │   ├── api/
│   │   │   └── endpoints.py    # All FastAPI routes
│   │   ├── config.py           # App-wide configuration constants
│   │   └── main.py             # FastAPI app entry point + lifespan
│   ├── ingestion/
│   │   ├── loaders.py          # Document loaders (PDF, DOCX, images, OCR)
│   │   └── pipeline.py         # Full ingestion: load → chunk → embed → upsert
│   ├── Mcp_server/
│   │   └── server.py           # FastMCP server exposing ask_support_agent()
│   ├── storage/
│   │   └── cloudinary_storage.py   # Cloudinary upload/list/delete/download
│   ├── tools/
│   │   └── slack_notifier.py   # Slack alert sender
│   ├── data/                   # Local staging dir for documents pre-ingestion
│   ├── pyproject.toml
│   └── requirements.txt
│
└── Front_end/
    ├── index.html          # Landing page
    ├── dashboard.html      # Live chat dashboard
    ├── docs.html           # API documentation & MCP connection guide
    ├── index.css           # Shared stylesheet
    ├── script.js           # Landing page JavaScript
    └── dashboard.js        # Dashboard chat logic (SSE streaming)
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Tesseract OCR** (for image/scanned-PDF ingestion) — [installation guide](https://github.com/UB-Mannheim/tesseract/wiki)
- API keys for: Groq, Pinecone, Google GenAI, Cohere, Cloudinary, Tavily, Slack (optional)

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/Lyraa_agent.git
   cd Lyraa_agent/Back_end
   ```

2. **Create and activate a virtual environment:**

   Using `uv` (recommended):

   ```bash
   uv sync
   ```

   Using pip:

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

### Environment Variables

Create a `.env` file in the `Back_end/` directory with the following keys:

```env
# LLM — Groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant

# Embeddings — Google GenAI
GOOGLE_API_KEY=your_google_api_key

# Vector Store — Pinecone
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=lyraa-support

# Re-ranking — Cohere
COHERE_API_KEY=your_cohere_api_key

# Cloud Storage — Cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret

# Web Scraping — Tavily
TAVILY_API_KEY=your_tavily_api_key

# Escalation — Slack (optional)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL_ID=your_channel_id

# Observability — Arize Phoenix (optional, non-Windows only)
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_API_KEY=your_phoenix_api_key
```

### Running the Server

**Start the FastAPI backend:**

```bash
cd Back_end
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive Swagger docs at `http://localhost:8000/docs`.

**Open the frontend:**

```bash
cd Front_end
python -m http.server 3000
# Visit http://localhost:3000
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat` | Synchronous chat (full response) |
| `POST` | `/api/chat/stream` | **Streaming chat** via SSE |
| `POST` | `/api/upload` | Upload a document to Cloudinary |
| `GET` | `/api/documents` | List documents for a user |
| `GET` | `/api/documents/download` | Download a file from Cloudinary |
| `DELETE` | `/api/documents` | Delete a file from Cloudinary |
| `POST` | `/api/add-link` | Scrape a URL and store its content |
| `POST` | `/api/ingest` | Run the RAG ingestion pipeline |
| `POST` | `/api/cleanup` | Manually trigger 24-hr expiry cleanup |

### Chat Example

**POST** `/api/chat`

```json
// Request
{
  "message": "What is your return policy?",
  "user_id": "user-123"
}

// Response
{
  "response": "Our return policy allows returns within 30 days...",
  "intent": "general_query"
}
```

**POST** `/api/chat/stream` — SSE response:

```
data: {"token": "Our ", "intent": "general_query", "done": false}
data: {"token": "return policy...", "intent": "general_query", "done": false}
data: {"token": "", "intent": "general_query", "done": true}
```

### Intent Types

| Intent | Trigger | Routing Path |
|---|---|---|
| `smalltalk` | Greetings, thanks, farewells | Instant canned reply — zero pipeline cost |
| `general_query` | Company, product, or policy questions | RAG → Pinecone + Cohere + Groq |
| `order_query` | Order status, tracking, returns | Direct order tool lookup |
| `ambiguous` | Complex / mixed messages | Full ReAct agent reasoning loop |

---

## 🔌 MCP Server

Lyraa exposes a **Model Context Protocol (MCP)** server, allowing Claude Desktop and other MCP-compatible clients to invoke the support agent as a native tool.

**Start the MCP server:**

```bash
cd Back_end
python Mcp_server/server.py
```

**Available Tool:**

```
Tool Name  : ask_support_agent
Description: Ask the RAG-powered customer support agent a question.
Parameters :
  - query   (str) : The user's question
  - user_id (str) : Optional user identifier (default: "mcp-user")
```

**Claude Desktop configuration** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "lyraa": {
      "command": "python",
      "args": ["path/to/Back_end/Mcp_server/server.py"]
    }
  }
}
```

See `Front_end/docs.html` for a full visual walkthrough.

---

## 🖥 Frontend

A pure HTML/CSS/JS multi-page application — no build step required.

| Page | File | Description |
|---|---|---|
| Landing Page | `index.html` | Marketing overview of Lyraa |
| Agent Dashboard | `dashboard.html` | Live chat UI with SSE streaming |
| API Docs | `docs.html` | API reference + MCP connection guide |

---

## ⚙️ How It Works

### 1. Intent Classification (Zero-Cost Fast Path)

Every user message is first routed by a pure regex/keyword classifier before any AI pipeline is invoked:

```
Message → Intent Classifier
   ├── smalltalk          → instant canned reply (no LLM, no Pinecone)
   ├── general_query      → RAG pipeline (Pinecone → Cohere → Groq)
   ├── order_query + ID   → check_order_status() tool
   ├── order_query, no ID → politely ask for the order ID
   └── ambiguous          → full ReAct agent loop
```

### 2. RAG Pipeline

For `general_query` intents:
1. Embed the query using **Google GenAI** (`text-embedding-004`)
2. Retrieve top-5 semantically similar chunks from **Pinecone**
3. Re-rank retrieved chunks using **Cohere** (keep top-3)
4. Stream the answer token-by-token from **Groq** (Llama 3.1 8B)

### 3. Document Ingestion

```
Document (PDF / DOCX / Image / CSV / Web URL)
   ↓ Load + OCR (PyMuPDF + pytesseract)
   ↓ Semantic Chunking (SemanticSplitterNodeParser + SentenceSplitter fallback)
   ↓ Google GenAI Embeddings
   ↓ Upsert to Pinecone
   ↓ Backup upload to Cloudinary (24-hr TTL auto-expiry)
```

### 4. Human Escalation

When the `escalate_to_human` tool is triggered by the ReAct agent, it sends a formatted alert message to your configured **Slack channel** using the Slack SDK.

---

## 🤝 Contributing

Contributions are welcome! Please open an issue first to discuss the change you'd like to make.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Built with ❤️ using LlamaIndex · FastAPI · Groq · Pinecone · Cohere

</div>
