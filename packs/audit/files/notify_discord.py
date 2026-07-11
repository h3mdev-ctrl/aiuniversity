#!/usr/bin/env python3
"""
notify_discord.py -- Notification hook that fires a Discord webhook when Claude
pauses waiting for user input.

Set CLAUDE_DISCORD_NOTIFY_URL to a Discord webhook URL. Reads the notification
message from the HOOK_NOTIFICATION_MESSAGE env var (set by Claude Code) and
from the hook JSON stdin payload.

This lets you walk away during a long autonomous session and get pinged on
Discord when Claude needs you.

User-Agent must be curl/8.7.1 -- Discord CDN blocks Python's default urllib UA.
"""
import json
import os
import sys
import urllib.request


def main() -> int:
    webhook_url = os.environ.get("CLAUDE_DISCORD_NOTIFY_URL", "").strip()
    if not webhook_url:
        return 0

    # Try to get the message from env (Claude Code sets HOOK_NOTIFICATION_MESSAGE)
    msg = os.environ.get("HOOK_NOTIFICATION_MESSAGE", "")
    if not msg:
        try:
            data = json.load(sys.stdin)
            msg = data.get("message", "") or data.get("notification", "") or "Claude needs input"
        except Exception:
            msg = "Claude needs input"

    msg = msg[:500]

    payload = json.dumps({
        "embeds": [{
            "title": "Claude needs your attention",
            "description": msg,
            "color": 16776960,  # yellow
        }]
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "curl/8.7.1",
        }
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # notification failure must never block Claude

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
