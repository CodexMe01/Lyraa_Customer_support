import sys
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

def check_order_status(order_id: str) -> str:
    """Mock tool to check order status."""
    # In a real app, this would hit a database or external API.
    return f"Order {order_id} is currently being processed and will ship tomorrow."

def escalate_to_human(issue_description: str, user_id: str) -> str:
    """Escalates an issue to a human agent."""
    from tools.slack_notifier import send_slack_alert
    
    alert_msg = f"URGENT HANDOFF REQUEST from {user_id}:\n{issue_description}"
    success = send_slack_alert(alert_msg)
    
    if success:
        return "Your issue has been escalated to a human agent. They will contact you shortly."
    else:
        return "Failed to escalate to a human agent at this time."
