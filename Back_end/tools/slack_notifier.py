import os
import re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def _sanitize_channel_name(name: str) -> str:
    """
    Slack channel names must be lowercase, max 80 chars,
    and contain only letters, numbers, hyphens, and underscores.
    """
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_-]", "-", name)   # replace invalid chars
    name = re.sub(r"-{2,}", "-", name)            # collapse consecutive hyphens
    return name[:80]


def create_or_get_slack_channel(client: WebClient, channel_name: str) -> str | None:
    """
    Return the channel ID for *channel_name*, creating it if it does not exist.

    Steps:
      1. List existing public channels and look for a name match.
      2. If not found, call conversations.create to provision a new channel.
      3. Cache the resolved ID in the SLACK_CHANNEL_ID env-var for this process.

    Returns the channel ID string, or None on failure.
    """
    safe_name = _sanitize_channel_name(channel_name)

    try:
        # --- 1. Search existing channels (paginated) ---
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor

            resp = client.conversations_list(**kwargs)
            for ch in resp.get("channels", []):
                if ch["name"] == safe_name:
                    channel_id = ch["id"]
                    os.environ["SLACK_CHANNEL_ID"] = channel_id
                    print(f"[Slack] Found existing channel '{safe_name}' → {channel_id}")
                    return channel_id

            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        # --- 2. Channel not found → create it ---
        resp = client.conversations_create(name=safe_name, is_private=False)
        channel_id = resp["channel"]["id"]
        os.environ["SLACK_CHANNEL_ID"] = channel_id
        print(f"[Slack] Created new channel '{safe_name}' → {channel_id}")

        # --- 3. Invite members so the channel is visible in Slack ---
        members_to_invite: list[str] = []

        # Always invite the bot itself (so it can post)
        try:
            bot_info = client.auth_test()
            bot_user_id = bot_info.get("user_id")
            if bot_user_id:
                members_to_invite.append(bot_user_id)
        except SlackApiError:
            pass

        # Optionally invite a human admin set via SLACK_INVITE_USER_ID in .env
        human_user_id = os.environ.get("SLACK_INVITE_USER_ID")
        if human_user_id and human_user_id not in members_to_invite:
            members_to_invite.append(human_user_id)

        if members_to_invite:
            try:
                client.conversations_invite(
                    channel=channel_id,
                    users=",".join(members_to_invite)
                )
                print(f"[Slack] Invited {members_to_invite} to '{safe_name}'")
            except SlackApiError as inv_err:
                # already_in_channel is fine; log others
                if inv_err.response.get("error") != "already_in_channel":
                    print(f"[Slack] Could not invite to '{safe_name}': {inv_err.response.get('error')}")

        return channel_id

    except SlackApiError as e:
        err = e.response.get("error", "unknown")
        if err == "missing_scope":
            needed = e.response.get("needed", "channels:read, channels:manage (or groups:read, groups:write for private)")
            print(
                f"[Slack] missing_scope error for channel '{safe_name}'.\n"
                f"  Needed scope(s): {needed}\n"
                f"  Fix: Go to https://api.slack.com/apps → select your app\n"
                f"       OAuth & Permissions → Scopes → Bot Token Scopes\n"
                f"       Add: channels:read  channels:manage  groups:read  groups:write\n"
                f"       Then click 'Reinstall to Workspace' and update SLACK_BOT_TOKEN in .env"
            )
        else:
            print(f"[Slack] Could not create/find channel '{safe_name}': {err}")
        return None


def send_slack_alert(
    message: str,
    user_id: str | None = None,
    channel_name: str | None = None,
) -> bool:
    """
    Send an alert to a Slack channel.

    Channel resolution priority:
      1. ``SLACK_CHANNEL_ID`` env-var  (set externally or cached by a prior call)
      2. *channel_name* argument       (used to look-up or auto-create the channel)
      3. A channel derived from *user_id* (``lyraa-user-<user_id>``)
      4. Fall back to ``lyraa-general`` as a last resort.

    Requires ``SLACK_BOT_TOKEN`` in the environment.

    Args:
        message:      Text to post.
        user_id:      Optional user identifier used to name a per-user channel.
        channel_name: Explicit channel name to use / create when no channel ID
                      is configured.

    Returns:
        True on success, False on any error.
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("[Slack] SLACK_BOT_TOKEN not set. Cannot send alert.")
        return False

    client = WebClient(token=token)

    # --- Resolve channel ID ---
    channel_id = os.environ.get("SLACK_CHANNEL_ID")

    if not channel_id:
        # Determine a channel name to create/find
        if not channel_name:
            if user_id:
                channel_name = f"lyraa-user-{user_id}"
            else:
                channel_name = "lyraa-general"

        print(f"[Slack] SLACK_CHANNEL_ID not set. Auto-resolving channel '{channel_name}' …")
        channel_id = create_or_get_slack_channel(client, channel_name)

        if not channel_id:
            print("[Slack] Failed to resolve a channel. Aborting.")
            return False

    # --- Send the message ---
    try:
        client.chat_postMessage(channel=channel_id, text=message)
        return True
    except SlackApiError as e:
        print(f"[Slack] Error posting message: {e.response['error']}")
        return False
