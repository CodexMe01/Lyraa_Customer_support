import os
import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.llms.groq import Groq
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from agent.rag import query_rag
from agent.tools import check_order_status, escalate_to_human
from agent.intent import classify_intent

load_dotenv()

# ── Per-tenant agent cache ─────────────────────────────────────────────────────
# Dict keyed by tenant_id (str UUID). Each tenant gets an independent ReAct agent
# built with their custom system prompt.
_support_agents: dict[str, ReActAgent] = {}

# ---------------------------------------------------------------------------
# Smalltalk helpers  (unchanged from single-tenant version)
# ---------------------------------------------------------------------------
import re

_SMALLTALK_RESPONSES = {
    "greeting": [
        "Hey there! 👋 How can I help you today?",
        "Hello! Welcome to support. What can I do for you?",
        "Hi! Great to hear from you. What do you need help with?",
        "Hey! I'm here and ready to help. What's on your mind?",
    ],
    "farewell": [
        "Goodbye! Have a wonderful day! 😊",
        "Take care! Feel free to come back if you need anything.",
        "See you later! Don't hesitate to reach out anytime.",
    ],
    "thanks": [
        "You're welcome! Is there anything else I can help you with?",
        "Happy to help! Let me know if you need anything else.",
        "Glad I could assist! Anything else on your mind?",
    ],
    "acknowledgement": [
        "Great! Let me know if there's anything else I can help with.",
        "Perfect! Feel free to ask if you need anything.",
    ],
    "how_are_you": [
        "I'm doing great, thanks for asking! 😊 How can I assist you today?",
        "All good here! Ready to help. What do you need?",
    ],
}

_FAREWELL_RE = re.compile(r"\b(bye|goodbye|see\s*ya|see\s*you|later|take\s*care|farewell|ciao|ttyl|gtg)\b", re.I)
_THANKS_RE   = re.compile(r"\b(thanks?|thank\s*you|thx|ty|cheers|much\s*appreciated)\b", re.I)
_ACK_RE      = re.compile(r"\b(ok|okay|sure|got\s*it|alright|cool|sounds\s*good|perfect|great|awesome)\b", re.I)
_HOW_RE      = re.compile(r"\b(how\s*are\s*you|how'?s\s*it\s*going)\b", re.I)


def _smalltalk_reply(message: str, greeting_override: Optional[str] = None) -> str:
    """Pick a context-appropriate canned reply for a smalltalk message."""
    msg = message.strip()
    if _FAREWELL_RE.search(msg):
        return random.choice(_SMALLTALK_RESPONSES["farewell"])
    if _THANKS_RE.search(msg):
        return random.choice(_SMALLTALK_RESPONSES["thanks"])
    if _ACK_RE.search(msg):
        return random.choice(_SMALLTALK_RESPONSES["acknowledgement"])
    if _HOW_RE.search(msg):
        return random.choice(_SMALLTALK_RESPONSES["how_are_you"])
    # Use tenant's custom greeting if set
    if greeting_override:
        return greeting_override
    return random.choice(_SMALLTALK_RESPONSES["greeting"])


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def get_support_agent(tenant_id: str, agent_config=None) -> ReActAgent:
    """
    Build and return the ReAct agent for *tenant_id*.

    The agent is cached per-tenant. If *agent_config* has a custom
    *system_prompt*, it is passed to the LLM context.
    Cached as a dict-level singleton — rebuilt only if not present.
    """
    tenant_id = str(tenant_id)

    if tenant_id in _support_agents:
        return _support_agents[tenant_id]

    # ── Tenant-scoped RAG tool ────────────────────────────────────────────────
    def _rag_tool_fn(question: str) -> str:
        return query_rag(question, tenant_id)

    rag_tool = FunctionTool.from_defaults(
        fn=_rag_tool_fn,
        name="query_knowledge_base",
        description="Useful for querying company documentation, policies, and product info.",
    )

    order_tool = FunctionTool.from_defaults(
        fn=check_order_status,
        name="check_order_status",
        description="Useful for checking the status of a specific order ID.",
    )

    escalate_tool = FunctionTool.from_defaults(
        fn=escalate_to_human,
        name="escalate_to_human",
        description="Use this when the user asks for a human, or if you cannot resolve their issue.",
    )

    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    llm = Groq(model=groq_model, api_key=groq_api_key)

    # Build system context from tenant config
    system_prompt = None
    if agent_config and getattr(agent_config, "system_prompt", None):
        system_prompt = agent_config.system_prompt

    agent = ReActAgent.from_tools(
        [rag_tool, order_tool, escalate_tool],
        llm=llm,
        verbose=True,
        system_prompt=system_prompt,
    )

    _support_agents[tenant_id] = agent
    print(f"[Agent] Support agent for tenant '{tenant_id}' initialised and cached.")
    return agent


def invalidate_agent(tenant_id: str) -> None:
    """
    Remove a tenant's cached agent.
    Call this after an agent_config update so the next request picks up
    the new system prompt.
    """
    _support_agents.pop(str(tenant_id), None)
    print(f"[Agent] Invalidated cached agent for tenant '{tenant_id}'.")


# ---------------------------------------------------------------------------
# Chat entrypoints
# ---------------------------------------------------------------------------

def chat_with_agent(message: str, tenant_id: str, agent_config=None) -> dict:
    """
    Route the user message based on detected intent before hitting the agent.

    Returns:
        {"response": str, "intent": str}

    Routing logic:
      0. smalltalk      → instant canned reply (no pipeline)
      1. general_query  → query tenant-scoped RAG directly
      2. order_query + order_id found → call check_order_status() directly
      3. order_query + no order_id    → ask the user for their order ID
      4. fallback       → full ReAct agent
    """
    tenant_id = str(tenant_id)
    result = classify_intent(message)
    greeting = getattr(agent_config, "greeting_msg", None) if agent_config else None

    print(f"[Intent] intent={result.intent} | order_id={result.order_id} | needs_order_id={result.needs_order_id}")

    # ── Path 0: Smalltalk ──────────────────────────────────────────────────────
    if result.intent == "smalltalk":
        return {"response": _smalltalk_reply(message, greeting_override=greeting), "intent": "smalltalk"}

    # ── Path 1: General query → RAG ───────────────────────────────────────────
    if result.intent == "general_query":
        response = query_rag(message, tenant_id)
        return {"response": response, "intent": "general_query"}

    # ── Path 2: Order query with ID ───────────────────────────────────────────
    if result.intent == "order_query" and result.order_id:
        response = check_order_status(result.order_id)
        return {"response": response, "intent": "order_query"}

    # ── Path 3: Order query, missing ID ──────────────────────────────────────
    if result.intent == "order_query" and result.needs_order_id:
        response = (
            "I'd be happy to help you with your order! "
            "Could you please share your **order ID**? "
            "It usually looks like ORD-12345 or a 6-10 digit number and can be found "
            "in your confirmation email."
        )
        return {"response": response, "intent": "order_query"}

    # ── Fallback: ReAct agent ─────────────────────────────────────────────────
    agent = get_support_agent(tenant_id, agent_config)
    agent_response = agent.chat(message)
    return {"response": str(agent_response), "intent": "ambiguous"}


async def stream_chat_with_agent(message: str, tenant_id: str, agent_config=None):
    """
    Async generator that streams response tokens as Server-Sent Events (SSE).

    Yields strings in the format:
        data: {"token": "...", "intent": "...", "done": bool}\n\n
    """
    from agent.rag import get_query_engine

    tenant_id = str(tenant_id)
    result = classify_intent(message)
    intent = result.intent
    greeting = getattr(agent_config, "greeting_msg", None) if agent_config else None

    print(f"[Stream] intent={intent} | order_id={result.order_id} | tenant={tenant_id}")

    # ── Path 0: Smalltalk ──────────────────────────────────────────────────────
    if intent == "smalltalk":
        reply = _smalltalk_reply(message, greeting_override=greeting)
        yield f"data: {json.dumps({'token': reply, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 1: General query → streaming RAG ─────────────────────────────────
    if intent == "general_query":
        engine = get_query_engine(tenant_id)
        if engine is None:
            chunk = json.dumps({"token": "Knowledge base unavailable.", "intent": intent, "done": True})
            yield f"data: {chunk}\n\n"
            return
        streaming_response = engine.query(message)
        try:
            for token in streaming_response.response_gen:
                chunk = json.dumps({"token": token, "intent": intent, "done": False})
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0)
        except Exception:
            chunk = json.dumps({"token": str(streaming_response), "intent": intent, "done": False})
            yield f"data: {chunk}\n\n"
        yield f"data: {json.dumps({'token': '', 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 2: Order query with ID ───────────────────────────────────────────
    if intent == "order_query" and result.order_id:
        response = check_order_status(result.order_id)
        yield f"data: {json.dumps({'token': response, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 3: Order query, missing ID ──────────────────────────────────────
    if intent == "order_query" and result.needs_order_id:
        response = (
            "I'd be happy to help you with your order! "
            "Could you please share your **order ID**? "
            "It usually looks like ORD-12345 or a 6-10 digit number and can be found "
            "in your confirmation email."
        )
        yield f"data: {json.dumps({'token': response, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Fallback: ReAct agent (non-streaming) ─────────────────────────────────
    agent = get_support_agent(tenant_id, agent_config)
    agent_response = agent.chat(message)
    yield f"data: {json.dumps({'token': str(agent_response), 'intent': 'ambiguous', 'done': True})}\n\n"
