import os
import asyncio
import json
import random
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.llms.groq import Groq
from dotenv import load_dotenv

try:
    from Back_end.agent.rag import query_rag
    from Back_end.agent.tools import check_order_status, escalate_to_human
    from Back_end.agent.intent import classify_intent
except ImportError:
    from agent.rag import query_rag
    from agent.tools import check_order_status, escalate_to_human
    from agent.intent import classify_intent

load_dotenv()

# ── Singleton cache ────────────────────────────────────────────────────────────
# The ReAct agent is expensive to build — build once, reuse forever.
_support_agent = None


def get_support_agent():
    """Build and return the ReAct agent with tools. Cached as a module-level singleton."""
    global _support_agent
    if _support_agent is not None:
        return _support_agent

    # RAG Tool
    rag_tool = FunctionTool.from_defaults(
        fn=query_rag,
        name="query_knowledge_base",
        description="Useful for querying company documentation, policies, and product info."
    )

    # Order Status Tool
    order_tool = FunctionTool.from_defaults(
        fn=check_order_status,
        name="check_order_status",
        description="Useful for checking the status of a specific order ID."
    )

    # Escalation Tool
    escalate_tool = FunctionTool.from_defaults(
        fn=escalate_to_human,
        name="escalate_to_human",
        description="Use this when the user asks for a human, or if you cannot resolve their issue."
    )

    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")  # fast Groq model
    llm = Groq(model=groq_model, api_key=groq_api_key)

    _support_agent = ReActAgent.from_tools(
        [rag_tool, order_tool, escalate_tool],
        llm=llm,
        verbose=True
    )
    print("[Agent] Support agent initialized and cached.")
    return _support_agent


# ---------------------------------------------------------------------------
# Smalltalk helpers
# ---------------------------------------------------------------------------
import re

_SMALLTALK_RESPONSES = {
    "greeting": [
        "Hey there! 👋 How can I help you today?",
        "Hello! Welcome to Lyraa support. What can I do for you?",
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


def _smalltalk_reply(message: str) -> str:
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
    return random.choice(_SMALLTALK_RESPONSES["greeting"])


def chat_with_agent(message: str) -> dict:
    """
    Route the user message based on detected intent before hitting the agent.

    Returns a dict:
        {
            "response": str,
            "intent":   "smalltalk" | "order_query" | "general_query" | "ambiguous"
        }

    Routing logic:
      0. smalltalk      → instant canned reply (no pipeline)
      1. general_query  → query RAG directly (no ReAct overhead)
      2. order_query + order_id found → call check_order_status() directly
      3. order_query + no order_id    → politely ask the user for their order ID
    """
    result = classify_intent(message)

    print(f"[Intent] intent={result.intent} | order_id={result.order_id} | needs_order_id={result.needs_order_id}")

    # ── Path 0: Smalltalk — instant reply, zero pipeline cost ──────────────
    if result.intent == "smalltalk":
        return {"response": _smalltalk_reply(message), "intent": "smalltalk"}

    # ── Path 1: Pure general / company-info query ──────────────────────────
    if result.intent == "general_query":
        response = query_rag(message)
        return {"response": response, "intent": "general_query"}

    # ── Path 2: Order query with an ID already present ─────────────────────
    if result.intent == "order_query" and result.order_id:
        response = check_order_status(result.order_id)
        return {"response": response, "intent": "order_query"}

    # ── Path 3: Order query but user forgot to mention their order ID ───────
    if result.intent == "order_query" and result.needs_order_id:
        response = (
            "I'd be happy to help you with your order! "
            "Could you please share your **order ID**? "
            "It usually looks like ORD-12345 or a 6-10 digit number and can be found "
            "in your confirmation email."
        )
        return {"response": response, "intent": "order_query"}

    # ── Fallback: Let the full ReAct agent handle anything ambiguous ────────
    agent = get_support_agent()
    agent_response = agent.chat(message)
    return {"response": str(agent_response), "intent": "ambiguous"}


async def stream_chat_with_agent(message: str):
    """
    Async generator that streams response tokens as Server-Sent Events (SSE).

    Yields strings in the format:
        data: {"token": "...", "intent": "..."}\n\n

    Routing:
      - smalltalk      → instant canned reply, single chunk
      - general_query  → LlamaIndex streaming query engine (token-by-token from Groq)
      - order_query    → instant response, yielded as a single chunk
      - ambiguous      → ReAct agent (non-streaming, yields full response when done)
    """
    try:
        from Back_end.agent.rag import get_query_engine
    except ImportError:
        from agent.rag import get_query_engine

    result = classify_intent(message)
    intent = result.intent

    print(f"[Stream] intent={intent} | order_id={result.order_id}")

    # ── Path 0: Smalltalk — instant reply, zero pipeline cost ──────────────
    if intent == "smalltalk":
        reply = _smalltalk_reply(message)
        yield f"data: {json.dumps({'token': reply, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 1: General query — stream tokens directly from Groq via LlamaIndex ──
    if intent == "general_query":
        engine = get_query_engine()
        if engine is None:
            chunk = json.dumps({"token": "Knowledge base unavailable.", "intent": intent, "done": True})
            yield f"data: {chunk}\n\n"
            return
        # Use streaming query engine
        streaming_response = engine.query(message)
        # LlamaIndex streaming_response.response_gen is a generator of token strings
        try:
            for token in streaming_response.response_gen:
                chunk = json.dumps({"token": token, "intent": intent, "done": False})
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0)  # yield control to the event loop
        except Exception:
            # Fallback: yield full response at once
            chunk = json.dumps({"token": str(streaming_response), "intent": intent, "done": False})
            yield f"data: {chunk}\n\n"
        yield f"data: {json.dumps({'token': '', 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 2: Order query with ID — instant, yield as one chunk ──────────
    if intent == "order_query" and result.order_id:
        response = check_order_status(result.order_id)
        yield f"data: {json.dumps({'token': response, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Path 3: Order query, missing ID — instant canned reply ────────────
    if intent == "order_query" and result.needs_order_id:
        response = (
            "I'd be happy to help you with your order! "
            "Could you please share your **order ID**? "
            "It usually looks like ORD-12345 or a 6-10 digit number and can be found "
            "in your confirmation email."
        )
        yield f"data: {json.dumps({'token': response, 'intent': intent, 'done': True})}\n\n"
        return

    # ── Fallback: ReAct agent (non-streaming) ─────────────────────────────
    agent = get_support_agent()
    agent_response = agent.chat(message)
    intent = "ambiguous"
    yield f"data: {json.dumps({'token': str(agent_response), 'intent': intent, 'done': True})}\n\n"
