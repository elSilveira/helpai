import unittest

import codex_client
from codex_client import CodexAuthError, CodexClient


class FakeTransport:
    def __init__(self, responses=None, notifications=None):
        self.responses = responses or {}
        self.notifications = list(notifications or [])
        self.calls = []
        self.notifies = []
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def request(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}))
        response = self.responses.get(method)
        if callable(response):
            return response(params or {})
        return response or {}

    def notify(self, method, params=None):
        self.notifies.append((method, params or {}))

    def next_notification(self, timeout=None):
        if not self.notifications:
            raise TimeoutError("no notifications")
        return self.notifications.pop(0)


class FailingInitializeTransport(FakeTransport):
    def request(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}))
        if method == "initialize":
            raise TimeoutError("initialize timed out")
        return {}


class CodexClientTests(unittest.TestCase):
    def test_generate_text_streams_agent_deltas_from_codex_app_server(self):
        transport = FakeTransport(
            responses={
                "account/read": {
                    "account": {
                        "type": "chatgpt",
                        "email": "user@example.com",
                        "planType": "pro",
                    },
                    "requiresOpenaiAuth": True,
                },
                "thread/start": {"thread": {"id": "thread-1"}},
                "turn/start": {"turn": {"id": "turn-1"}},
            },
            notifications=[
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "delta": "hello",
                    },
                },
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "delta": " world",
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                },
            ],
        )
        client = CodexClient(transport_factory=lambda: transport)
        streamed = []

        result = client.generate_text("Say hello", on_token=streamed.append)

        self.assertEqual(result, "hello world")
        self.assertEqual(streamed, ["hello", "hello world"])
        self.assertTrue(transport.started)
        self.assertEqual(transport.calls[0][0], "initialize")
        self.assertEqual(transport.notifies[0], ("initialized", {}))
        self.assertIn(("account/read", {"refreshToken": True}), transport.calls)

        turn_call = [call for call in transport.calls if call[0] == "turn/start"][0]
        self.assertEqual(turn_call[1]["threadId"], "thread-1")
        self.assertEqual(turn_call[1]["input"], [{"type": "text", "text": "Say hello"}])

    def test_generate_text_requires_chatgpt_oauth_account(self):
        transport = FakeTransport(
            responses={
                "account/read": {"account": None, "requiresOpenaiAuth": True},
            }
        )
        client = CodexClient(transport_factory=lambda: transport)

        with self.assertRaises(CodexAuthError) as ctx:
            client.generate_text("Say hello")

        self.assertIn("Codex OAuth is not signed in", str(ctx.exception))
        self.assertNotIn("turn/start", [method for method, _ in transport.calls])

    def test_generate_text_sends_image_inputs_after_prompt_text(self):
        transport = FakeTransport(
            responses={
                "account/read": {
                    "account": {"type": "chatgpt", "email": "user@example.com", "planType": "plus"},
                    "requiresOpenaiAuth": True,
                },
                "thread/start": {"thread": {"id": "thread-1"}},
                "turn/start": {"turn": {"id": "turn-1"}},
            },
            notifications=[
                {
                    "method": "item/agentMessage/delta",
                    "params": {"threadId": "thread-1", "turnId": "turn-1", "delta": "seen"},
                },
                {
                    "method": "turn/completed",
                    "params": {"threadId": "thread-1", "turn": {"id": "turn-1"}},
                },
            ],
        )
        client = CodexClient(transport_factory=lambda: transport)

        client.generate_text("Describe", image_urls=["data:image/png;base64,abc"])

        turn_call = [call for call in transport.calls if call[0] == "turn/start"][0]
        self.assertEqual(
            turn_call[1]["input"],
            [
                {"type": "text", "text": "Describe"},
                {"type": "image", "url": "data:image/png;base64,abc"},
            ],
        )

    def test_start_login_returns_browser_oauth_details(self):
        transport = FakeTransport(
            responses={
                "account/login/start": {
                    "type": "chatgpt",
                    "loginId": "login-1",
                    "authUrl": "https://example.com/auth",
                },
            }
        )
        client = CodexClient(transport_factory=lambda: transport)

        login = client.start_login()

        self.assertEqual(login["authUrl"], "https://example.com/auth")
        self.assertIn(("account/login/start", {"type": "chatgpt"}), transport.calls)

    def test_warmup_initializes_transport_without_starting_turn(self):
        transport = FakeTransport()
        client = CodexClient(transport_factory=lambda: transport)

        client.warmup()

        self.assertTrue(transport.started)
        self.assertEqual(transport.calls, [("initialize", {
            "clientInfo": {
                "name": "helpai",
                "title": "HelpAI",
                "version": codex_client.APP_VERSION,
            },
            "capabilities": {"experimentalApi": True},
        })])
        self.assertEqual(transport.notifies, [("initialized", {})])

    def test_close_default_client_closes_and_resets_shared_client(self):
        class FakeDefaultClient:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        fake_client = FakeDefaultClient()
        original_default = codex_client._default_client
        try:
            codex_client._default_client = fake_client

            codex_client.close_default_client()

            self.assertTrue(fake_client.closed)
            self.assertIsNone(codex_client._default_client)
        finally:
            codex_client._default_client = original_default

    def test_failed_warmup_closes_uninitialized_transport(self):
        transport = FailingInitializeTransport()
        client = CodexClient(transport_factory=lambda: transport)

        with self.assertRaises(TimeoutError):
            client.warmup()

        self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
