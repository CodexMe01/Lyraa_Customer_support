<div align="center">

# 🤖 Lyraa — Multi-Tenant AI Customer Support SaaS

**A production-ready, RAG-driven customer support agent with streaming chat, document ingestion, multi-tenant architecture, and a polished web frontend for independent businesses.**

[![Python](https://img.shields.io/badge/Python-3.14+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.14+-7C3AED?style=flat)](https://docs.llamaindex.ai)
[![Pinecone](https://img.shields.io/badge/Pinecone-Vector%20DB-00B388?style=flat)](https://pinecone.io)
[![Supabase](https://img.shields.io/badge/Supabase-Database%20%26%20Auth-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com)
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

**Lyraa** is an intelligent customer support SaaS platform that combines **Retrieval-Augmented Generation (RAG)**, **intent classification**, and a **ReAct agent** to deliver fast, context-aware support responses. 

Evolving from a single-tenant bot into a **multi-tenant SaaS platform**, Lyraa enables independent businesses to each have an isolated knowledge base, custom AI agent persona, admin dashboard, and embeddable widgets for their own websites.

Designed as a full-stack solution, Lyraa ships with:
- A **FastAPI** backend with SSE streaming chat and tenant-aware endpoints
- **Supabase** for robust Authentication (JWT/OAuth) and PostgreSQL database
- A **Pinecone** vector store with namespace isolation (`tenant_<uuid>`) per tenant
- **Cohere Re-ranking** for higher quality retrieval
- **Cloudinary** cloud storage for uploaded documents scoped by tenant
- An **MCP (Model Context Protocol)** server for AI agent integrations
- An **embeddable chat widget** (`widget.js`) to integrate on any website
- A **vanilla HTML/CSS/JS** frontend with landing pages, tenant admin dashboard, and API docs

---

## 🏗 Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Vercel)                       │
│  auth.html (Login)  │  dashboard.html (Admin) │ widget.js (Bot) │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS / SSE / API Keys
┌───────────────────────────────▼─────────────────────────────────┐
│                      FastAPI Backend                            │
│                                                                 │
│  Auth Middleware → validate Supabase JWT or API Key             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Intent Classifier                      │   │
│  │   smalltalk → instant reply  (zero LLM cost)             │   │
│  │   general_query → RAG pipeline (tenant namespace)        │   │
│  │   order_query   → Order Status Tool                      │   │
│  │   ambiguous     → ReAct Agent (full reasoning loop)      │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                          │                                      │
│  ┌──────────────┐  ┌─────▼────────┐  ┌─────────────────────┐    │
│  │  RAG Engine  │  │  ReAct Agent │  │   Order Status Tool │    │
│  │ (LlamaIndex) │  │ (LlamaIndex) │  │   Escalation Tool   │    │
│  └──────┬───────┘  └──────────────┘  └──────────┬──────────┘    │
│         │                                         │             │
│  ┌──────▼──────────┐                     ┌────────▼──────────┐  │
│  │    Pinecone     │                     │   Slack Notifier  │  │
│  │ NS: tenant_<id> │                     │ (Human Escalation)│  │
│  └─────────────────┘                     └───────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Ingestion Pipeline                           │  │
│  │  OCR → Semantic Chunking → Google GenAI Embeddings        │  │
│  │  → Pinecone Upsert (Tenant Namespace)                     │  │
│  └───────────────────────────────────────────────────────────┘  │
└───────────────────────┬──────────────────────┬──────────────────┘
                        │                      │
┌───────────────────────▼───────┐      ┌───────▼──────────────────┐
│          Supabase             │      │       MCP Server         │
│  - Auth (Email/Google)        │      │    ask_support_agent     │
│  - PostgreSQL (Tenants,       │      └──────────────────────────┘
│    API Keys, Configs, Logs)   │
└───────────────────────────────┘
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 🏢 **Multi-Tenant SaaS** | Isolated data, custom agent personas, and API keys for multiple independent businesses on one platform. |
| 🔒 **Authentication & DB** | Powered by **Supabase** for secure user login (JWT, Google OAuth) and robust PostgreSQL relational data. |
| 🌐 **Embeddable Widget** | A drop-in `widget.js` script to instantly add the Lyraa agent to any external website. |
| 🧠 **Intent Classification** | Zero-LLM regex/keyword router — routes smalltalk, order queries, and general queries before AI pipelines. |
| 💬 **Streaming Chat (SSE)** | Token-by-token streaming via Server-Sent Events for a real-time, responsive chat experience. |
| 📚 **Isolated RAG Pipeline** | Semantic search over custom knowledge bases using Pinecone Namespaces + Cohere Re-ranking. |
| 🔄 **ReAct Agent** | Full LlamaIndex ReAct agent as a fallback for ambiguous or complex queries. |
| 📁 **Document Ingestion** | Ingest PDFs, DOCX, images (OCR), CSVs, TXT, and live web URLs (Tavily). Tenant-scoped storage in Cloudinary. |
| 🔔 **Human Escalation** | Automatically pages a human agent via Slack when the bot cannot resolve an issue. |
| 🔌 **MCP Server** | Expose the support agent as an MCP tool for integration with Claude Desktop and other AI systems. |
| 🖥️ **Admin Dashboard** | Tenant dashboard to manage knowledge bases, agent personas, API keys, and analytics. |

---

## 🛠 Tech Stack

### Backend

| Layer | Technology |
|---|---|
| API Framework | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| Auth & Relational DB | [Supabase](https://supabase.com) (PostgreSQL) + `supabase-py` |
| AI Orchestration | [LlamaIndex](https://docs.llamaindex.ai) |
| LLM | [Groq](https://groq.com) (`llama-3.1-8b-instant`) |
| Embeddings | [Google GenAI](https://ai.google.dev) (`text-embedding-004`) |
| Vector Store | [Pinecone](https://pinecone.io) |
| Re-ranking | [Cohere](https://cohere.com) |
| Cloud Storage | [Cloudinary](https://cloudinary.com) |
| Web Scraping | [Tavily](https://tavily.com) |
| MCP Server | [FastMCP](https://github.com/jlowin/fastmcp) |

### Frontend

| Layer | Technology |
|---|---|
| Structure | HTML5 |
| Styling | Vanilla CSS (no frameworks) |
| Logic | Vanilla JavaScript, Supabase JS SDK (`@supabase/supabase-js`) |
| Widget Hosting | [Vercel](https://vercel.com) |

---

## 📂 Project Structure

```text
Lyraa_agent/
├── Back_end/
│   ├── agent/
│   │   ├── bot.py          # Tenant-aware ReAct agent & intent routing
│   │   ├── rag.py          # Pinecone + Cohere query engine (tenant namespaces)
│   │   └── tools.py        # Order status + Slack escalation tools
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints.py       # Core chat & ingest endpoints
│   │   │   └── admin_endpoints.py # Tenant management & API keys
│   │   ├── auth.py         # Supabase JWT & API Key validation
│   │   ├── db.py           # Supabase client singleton
│   │   ├── models.py       # SQLAlchemy ORM models (Tenant, ApiKey, Config)
│   │   └── main.py         # FastAPI application entry point
│   ├── ingestion/
│   │   └── pipeline.py     # Document ingestion to specific Pinecone namespaces
│   ├── Mcp_server/
│   │   └── server.py       # FastMCP server exposing ask_support_agent()
│   └── storage/
│       └── cloudinary_storage.py   # Tenant-prefixed cloud storage
│
└── Front_end/
    ├── index.html          # Landing page
    ├── auth.html           # Supabase sign-up / sign-in
    ├── dashboard.html      # Tenant Admin Dashboard SPA
    ├── widget.js           # Embeddable widget script for external sites
    └── docs.html           # API documentation & MCP connection guide
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Tesseract OCR** (for image/scanned-PDF ingestion)
- **Supabase Project** (Database & Auth setup)
- API keys for: Groq, Pinecone, Google GenAI, Cohere, Cloudinary, Tavily

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/Lyraa_agent.git
   cd Lyraa_agent/Back_end
   ```

2. **Create and activate a virtual environment:**
   ```bash
   uv sync  # or use pip install -r requirements.txt
   ```

3. **Supabase Database Setup:**
   Run the SQL migration script from `Back_end/app/migrations/001_initial.sql` in your Supabase project's SQL Editor to create the necessary tables (`tenants`, `agent_configs`, `api_keys`, etc.).

### Environment Variables

Create a `.env` file in the `Back_end/` directory:

```env
# Supabase
SUPABASE_URL=https://<your_project>.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_JWT_SECRET=your_supabase_jwt_secret

# AI APIs
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant
GOOGLE_API_KEY=your_google_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=lyraa-support
COHERE_API_KEY=your_cohere_api_key

# Integrations
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
TAVILY_API_KEY=your_tavily_api_key
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL_ID=your_channel_id
```

### Running the Server

**Start the FastAPI backend:**
```bash
cd Back_end
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The API is available at `http://localhost:8000` and Swagger docs at `http://localhost:8000/docs`.

**Open the frontend:**
```bash
cd Front_end
python -m http.server 3000
```
Visit `http://localhost:3000/index.html`.

---

## 📡 API Reference

### Public Endpoints (Widget / Integrations)
Requires `X-API-Key` header generated from the tenant dashboard.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Synchronous chat |
| `POST` | `/api/chat/stream` | Streaming chat via SSE |

### Admin Endpoints (Dashboard)
Requires Supabase JWT (`Authorization: Bearer <token>`).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/tenants/me` | Get own tenant profile |
| `POST` | `/api/admin/api-keys` | Generate new API key |
| `GET` | `/api/admin/agent-config` | Get AI agent persona config |
| `POST` | `/api/ingest` | Run the RAG ingestion pipeline |
| `POST` | `/api/upload` | Upload a document to tenant storage |

---

## 🔌 Embeddable Widget

Tenants can easily embed the Lyraa agent on their own websites.
1. Generate an API Key from the Lyraa Dashboard.
2. Paste the following snippet into the `<head>` or `<body>` of the external site:

```html
<script src="https://your-vercel-domain.vercel.app/widget.js"
        data-api-key="lyr_abc123xyz..."></script>
```

This injects a floating chat UI that connects directly to the tenant's custom agent and knowledge base.

---

## 🤝 Contributing

Contributions are welcome!
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
Built with ❤️ by [@PRG](https://prg-portfolio.vercel.app/)
</div>
