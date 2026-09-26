import json
import tempfile
import unittest
from pathlib import Path

from other_league_rankings.discord import DiscordPublishError, DiscordWebhookPublisher


class Response:
    status_code = 200
    text = ""
    content = b"{}"

    def json(self):
        return {"id": "message-1"}


class FakeSession:
    def __init__(self, response=None):
        self.response = response or Response()
        self.call = None

    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        return self.response


class DiscordTests(unittest.TestCase):
    def test_rejects_missing_or_non_discord_webhook_url(self):
        with self.assertRaises(DiscordPublishError):
            DiscordWebhookPublisher(FakeSession()).post_forum("", "Week 3", "hello", (Path("a"), Path("b")))
        with self.assertRaises(DiscordPublishError):
            DiscordWebhookPublisher(FakeSession()).post_forum("https://example.com/webhook/secret", "Week 3", "hello", (Path("a"), Path("b")))

    def test_forum_payload_has_thread_name_and_two_attachments(self):
        session = FakeSession()
        publisher = DiscordWebhookPublisher(session)
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "ranks.png"
            second = Path(temp_dir) / "odds.png"
            first.write_bytes(b"rank-image")
            second.write_bytes(b"odds-image")
            response = publisher.post_forum("https://discord.com/api/webhooks/123/secret", "Week 3 · League", "Rankings", (first, second))

        self.assertEqual(response["id"], "message-1")
        url, request = session.call
        self.assertNotIn("secret", str(request))
        payload = json.loads(request["data"]["payload_json"])
        self.assertEqual(payload["thread_name"], "Week 3 · League")
        self.assertEqual(len(payload["attachments"]), 2)
        self.assertEqual([part[0] for part in request["files"]], ["files[0]", "files[1]"])
        self.assertIn("wait", request["params"])

    def test_failure_does_not_echo_webhook_secret(self):
        class BadResponse(Response):
            status_code = 400
            text = "bad request"

        secret = "topsecret"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.png"
            path.write_bytes(b"x")
            with self.assertRaises(DiscordPublishError) as caught:
                DiscordWebhookPublisher(FakeSession(BadResponse())).post_forum(
                    f"https://discord.com/api/webhooks/123/{secret}", "Week 1", "test", (path, path)
                )
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
