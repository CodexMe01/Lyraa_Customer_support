import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def send_slack_alert(message: str) -> bool:
    """
    Send an alert to the configured Slack channel.
    Requires SLACK_BOT_TOKEN and SLACK_CHANNEL_ID in .env.
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")
    
    if not token or not channel_id:
        print("Slack credentials not found. Cannot send alert.")
        return False
        
    client = WebClient(token=token)
    
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        return True
    except SlackApiError as e:
        print(f"Error sending message to Slack: {e.response['error']}")
        return False
