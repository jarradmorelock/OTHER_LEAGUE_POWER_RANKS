"""Safe Discord Forum webhook uploads."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit


class DiscordPublishError(RuntimeError):
    """A Discord post could not be confirmed."""


WEBHOOK_PATH = re.compile(r"^/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]+/?$")


class DiscordWebhookPublisher:
    def __init__(self, session: Any = None, timeout: int = 45) -> None:
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.timeout = timeout

    def post_forum(
        self,
        webhook_url: str,
        thread_name: str,
        content: str,
        image_paths: tuple[Path, Path],
    ) -> dict[str, Any]:
        _validate_webhook(webhook_url)
        if not thread_name.strip():
            raise DiscordPublishError("Forum thread name cannot be empty")
        if len(image_paths) != 2 or any(not Path(path).is_file() for path in image_paths):
            raise DiscordPublishError("A Forum post requires exactly two existing image files")
        attachments = [{"id": index, "filename": Path(path).name} for index, path in enumerate(image_paths)]
        payload = {
            "content": content[:2000],
            "thread_name": thread_name[:100],
            "allowed_mentions": {"parse": []},
            "attachments": attachments,
        }
        opened = []
        files = []
        try:
            for index, path in enumerate(image_paths):
                handle = Path(path).open("rb")
                opened.append(handle)
                files.append((f"files[{index}]", (Path(path).name, handle, "image/png")))
            response = self.session.post(
                webhook_url,
                params={"wait": "true"},
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files=files,
                timeout=self.timeout,
            )
        except Exception as exc:
            # Never interpolate request exceptions: requests commonly includes
            # the full webhook URL, whose path contains its secret token.
            raise DiscordPublishError(f"Discord request failed ({type(exc).__name__})") from None
        finally:
            for handle in opened:
                handle.close()
        status = int(getattr(response, "status_code", 0))
        if status < 200 or status >= 300:
            raise DiscordPublishError(f"Discord rejected the Forum post (HTTP {status})")
        try:
            payload_out = response.json()
        except (ValueError, AttributeError):
            payload_out = {}
        return payload_out if isinstance(payload_out, dict) else {}


def _validate_webhook(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise DiscordPublishError("Discord webhook URL is missing")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise DiscordPublishError("Discord webhook URL is invalid") from None
    if parsed.scheme != "https" or parsed.hostname not in {"discord.com", "discordapp.com"} or not WEBHOOK_PATH.fullmatch(parsed.path):
        raise DiscordPublishError("Discord webhook URL is invalid")
