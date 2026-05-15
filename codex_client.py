"""Codex app-server integration for HelpAI.

This module talks to `codex app-server` over its JSON-RPC stdio transport.
Codex owns OAuth tokens and backend requests; HelpAI only sends local prompts
and receives assistant message deltas.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from helpai_version import __version__ as APP_VERSION

logger = logging.getLogger(__name__)


class CodexError(RuntimeError):
    """Base error for Codex provider failures."""


class CodexUnavailableError(CodexError):
    """Raised when the Codex CLI/app-server cannot be started."""


class CodexAuthError(CodexError):
    """Raised when Codex OAuth is not available."""


class CodexRpcError(CodexError):
    """Raised when the app-server returns a JSON-RPC error."""


def find_codex_executable() -> str | None:
    """Return the best command path for the Codex CLI on this machine."""
    for name in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(name)
        if path:
            return path
    return None


class JsonRpcProcessTransport:
    """Line-delimited JSON-RPC transport backed by `codex app-server`."""

    def __init__(
        self,
        command: list[str] | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ):
        codex_path = find_codex_executable()
        if command is None:
            if not codex_path:
                raise CodexUnavailableError(
                    "Codex CLI is not installed. Install it with: npm install -g @openai/codex"
                )
            command = [codex_path, "app-server"]
        self._command = command
        self._process_factory = process_factory
        self._process: subprocess.Popen | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._process is not None:
            return

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = self._process_factory(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            raise CodexUnavailableError(
                "Codex CLI is not installed. Install it with: npm install -g @openai/codex"
            ) from exc

        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            process.terminate()
        except Exception:
            logger.debug("Failed to terminate Codex app-server", exc_info=True)

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = 30.0):
        self.start()
        process = self._require_process()
        request_id = self._allocate_id()
        response_queue: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue

        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write(process, payload)

        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"Timed out waiting for Codex app-server method '{method}'") from exc

        if "error" in response:
            raise CodexRpcError(f"Codex app-server error for {method}: {response['error']}")
        return response.get("result", {})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.start()
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        self._write(self._require_process(), payload)

    def next_notification(self, timeout: float | None = None) -> dict[str, Any]:
        return self._notifications.get(timeout=timeout)

    def _allocate_id(self) -> int:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def _require_process(self) -> subprocess.Popen:
        if self._process is None or self._process.stdin is None:
            raise CodexUnavailableError("Codex app-server is not running.")
        return self._process

    def _write(self, process: subprocess.Popen, payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise CodexUnavailableError("Codex app-server stdin is closed.")
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Ignoring non-JSON Codex app-server output: %s", line)
                continue

            request_id = message.get("id")
            if request_id is not None and ("result" in message or "error" in message):
                with self._pending_lock:
                    pending = self._pending.pop(request_id, None)
                if pending is not None:
                    pending.put(message)
                    continue
            self._notifications.put(message)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            logger.debug("codex app-server: %s", line.rstrip())


class CodexClient:
    """High-level HelpAI provider facade for Codex OAuth requests."""

    def __init__(self, transport_factory: Callable[[], Any] | None = None):
        self._transport_factory = transport_factory or JsonRpcProcessTransport
        self._transport = None
        self._initialized = False

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._initialized = False

    def is_available(self) -> bool:
        return find_codex_executable() is not None

    def get_account(self, refresh_token: bool = True) -> dict[str, Any]:
        self._ensure_initialized()
        return self._transport.request(
            "account/read",
            {"refreshToken": refresh_token},
            timeout=30.0,
        )

    def is_chatgpt_logged_in(self) -> bool:
        try:
            account = self.get_account(refresh_token=True).get("account")
        except CodexError:
            return False
        return bool(account and account.get("type") == "chatgpt")

    def start_login(self, device_code: bool = False) -> dict[str, Any]:
        self._ensure_initialized()
        login_type = "chatgptDeviceCode" if device_code else "chatgpt"
        return self._transport.request("account/login/start", {"type": login_type}, timeout=30.0)

    def generate_text(
        self,
        prompt: str,
        *,
        image_urls: list[str] | None = None,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        cwd: str | None = None,
        timeout: float = 240.0,
    ) -> str:
        self._ensure_chatgpt_auth()

        thread_params: dict[str, Any] = {
            "cwd": str(Path(cwd or os.getcwd()).resolve()),
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "developerInstructions": (
                "Answer the user's request directly. Do not run shell commands, edit files, "
                "inspect the repository, or use tools. HelpAI is only asking for text generation."
            ),
        }
        if model:
            thread_params["model"] = model

        thread_result = self._transport.request("thread/start", thread_params, timeout=timeout)
        thread_id = thread_result.get("thread", {}).get("id")
        if not thread_id:
            raise CodexRpcError(f"Codex app-server did not return a thread id: {thread_result!r}")

        input_items: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_url in image_urls or []:
            input_items.append({"type": "image", "url": image_url})

        turn_result = self._transport.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": input_items,
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
            },
            timeout=timeout,
        )
        turn_id = turn_result.get("turn", {}).get("id")
        return self._collect_turn(thread_id, turn_id, on_token, timeout)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._transport = self._transport_factory()
        self._transport.start()
        self._transport.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "helpai",
                    "title": "HelpAI",
                    "version": APP_VERSION,
                },
                "capabilities": {"experimentalApi": True},
            },
            timeout=30.0,
        )
        self._transport.notify("initialized", {})
        self._initialized = True

    def _ensure_chatgpt_auth(self) -> None:
        account_response = self.get_account(refresh_token=True)
        account = account_response.get("account")
        if not account or account.get("type") != "chatgpt":
            raise CodexAuthError(
                "Codex OAuth is not signed in. Open Settings -> Codex and sign in, "
                "or run `codex login` in a terminal."
            )

    def _collect_turn(
        self,
        thread_id: str,
        turn_id: str | None,
        on_token: Callable[[str], None] | None,
        timeout: float,
    ) -> str:
        raw = ""
        while True:
            notification = self._transport.next_notification(timeout=timeout)
            method = notification.get("method")
            params = notification.get("params") or {}
            if params.get("threadId") not in (None, thread_id):
                continue
            if turn_id and params.get("turnId") not in (None, turn_id):
                continue

            if method == "item/agentMessage/delta":
                delta = params.get("delta") or ""
                if delta:
                    raw += delta
                    if on_token is not None:
                        on_token(raw)
            elif method == "turn/completed":
                turn = params.get("turn") or {}
                if not turn_id or turn.get("id") in (None, turn_id):
                    return raw.strip()
            elif method == "error":
                message = params.get("message") or params
                raise CodexRpcError(f"Codex app-server error: {message}")


_default_client: CodexClient | None = None


def get_default_client() -> CodexClient:
    global _default_client
    if _default_client is None:
        _default_client = CodexClient()
    return _default_client
