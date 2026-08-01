"""
Intent Classifier for the Customer Support Agent.

Classifies incoming user messages into:
  - "order_query"   : User is asking about a specific order (status, tracking, delivery, return/cancel)
  - "general_query" : User wants info about the company, product, policy, pricing, etc.

Also extracts an order ID if one is present in the message.
No LLM call is needed — uses regex + keyword matching for speed and zero extra cost.
"""

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Order-related keywords
# ---------------------------------------------------------------------------
ORDER_KEYWORDS = [
    "order", "orders", "track", "tracking", "shipment", "shipping",
    "delivery", "deliver", "dispatched", "dispatch", "shipped",
    "package", "parcel", "status", "cancel", "cancellation", "return",
    "refund", "exchange", "where is my", "when will", "estimated arrival",
    "out for delivery", "in transit", "received", "not received",
    "invoice", "purchase", "bought", "buy", "placed",
]

# Regex patterns to extract order IDs from messages
ORDER_ID_PATTERNS = [
    r"\bORD[-_]?\d{1,10}\b",          # ORD-001, ORD_1234, ORD123
    r"\bORDER[-_]?\d{1,10}\b",        # ORDER-001
    r"#\d{4,10}\b",                    # #12345
    r"\b\d{6,10}\b",                   # plain 6-10 digit numbers
]

# ---------------------------------------------------------------------------
# Smalltalk patterns — matched BEFORE the order/general pipeline
# ---------------------------------------------------------------------------
# These are simple phrases that should get an instant canned reply,
# never hitting RAG, Pinecone, Cohere, or the LLM.
SMALLTALK_PATTERNS = [
    # Greetings
    r"^\s*(hi|hey|hello|howdy|hiya|sup|what'?s up|yo|greetings|good\s*(morning|afternoon|evening|day|night))[!?.,\s]*$",
    # Farewells
    r"^\s*(bye|goodbye|see\s*ya|see\s*you|later|take\s*care|farewell|ciao|ttyl|gtg)[!?.,\s]*$",
    # Thanks
    r"^\s*(thanks?|thank\s*you|thx|ty|cheers|much\s*appreciated)[!?.,\s]*$",
    # Confirmation / acknowledgement
    r"^\s*(ok|okay|sure|got\s*it|alright|cool|sounds\s*good|perfect|great|awesome)[!?.,\s]*$",
    # How are you style
    r"^\s*(how\s*are\s*you|how'?s\s*it\s*going|how\s*do\s*you\s*do|how\s*are\s*things)[?!.,\s]*$",
]

_SMALLTALK_RE = re.compile(
    "|".join(SMALLTALK_PATTERNS),
    re.IGNORECASE,
)

# Compiled combined order ID regex
_ORDER_ID_RE = re.compile(
    "|".join(ORDER_ID_PATTERNS),
    re.IGNORECASE,
)

# Compiled keyword regex (word-boundary safe)
_ORDER_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in ORDER_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class IntentResult:
    intent: str               # "smalltalk" | "order_query" | "general_query"
    order_id: Optional[str]   # Extracted order ID, if found
    needs_order_id: bool      # True when it's an order query but no ID found


# ---------------------------------------------------------------------------
# Main classifier function
# ---------------------------------------------------------------------------
def classify_intent(message: str) -> IntentResult:
    """
    Classify the intent of a user message.

    Returns an IntentResult with:
      - intent        : "smalltalk" | "order_query" | "general_query"
      - order_id      : extracted order ID string, or None
      - needs_order_id: True if it's an order query but no order ID was found
    """
    msg = message.strip()

    # Step 0: Smalltalk fast-path — checked FIRST, no pipeline needed
    if _SMALLTALK_RE.match(msg):
        return IntentResult(intent="smalltalk", order_id=None, needs_order_id=False)

    # Step 1: Check for order-related keywords
    is_order_related = bool(_ORDER_KEYWORD_RE.search(msg))

    # Step 2: Try to extract an order ID
    match = _ORDER_ID_RE.search(msg)
    order_id = match.group(0).strip() if match else None

    # Step 3: Determine intent
    if is_order_related or order_id:
        intent = "order_query"
        needs_order_id = order_id is None
    else:
        intent = "general_query"
        needs_order_id = False

    return IntentResult(
        intent=intent,
        order_id=order_id,
        needs_order_id=needs_order_id,
    )
