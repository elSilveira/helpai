"""
Settings UI — multi-panel settings window with sidebar navigation.

Catppuccin Mocha themed.  Each section lives in its own panel,
toggled by icon buttons on the left rail.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging

import keyboard as kb

from audio_capture import list_microphone_choices, list_speaker_choices
import settings as store
from config import (
    APP_NAME,
    APP_VERSION,
    OVERLAY_BG_COLOR,
    OVERLAY_FG_COLOR,
    OVERLAY_ACCENT_COLOR,
    OVERLAY_FONT_FAMILY,
)

logger = logging.getLogger(__name__)

# ── Catppuccin Mocha palette ────────────────────────────────────────────────
_CRUST   = "#11111b"
_MANTLE  = "#181825"
_BASE    = OVERLAY_BG_COLOR       # "#1e1e2e"
_SURFACE0 = "#313244"
_SURFACE1 = "#45475a"
_SURFACE2 = "#585b70"
_OVERLAY0 = "#6c7086"
_SUBTEXT  = "#a6adc8"
_TEXT     = OVERLAY_FG_COLOR      # "#cdd6f4"
_ACCENT   = OVERLAY_ACCENT_COLOR  # "#89b4fa"
_PEACH    = "#fab387"
_GREEN    = "#a6e3a1"
_RED      = "#f38ba8"
_PINK     = "#f5c2e7"
_MAUVE    = "#cba6f7"
_YELLOW   = "#f9e2af"
_TEAL     = "#94e2d5"
_SIDEBAR  = _MANTLE
_CARD     = _SURFACE0

_FONT     = OVERLAY_FONT_FAMILY
_ICON_SIZE = 18


def _make_draggable(window: tk.Tk | tk.Toplevel, *handles: tk.Widget) -> None:
    state = {"x": 0, "y": 0}
    def on_press(e): state["x"], state["y"] = e.x, e.y
    def on_drag(e):
        window.geometry(f"+{window.winfo_x() + e.x - state['x']}+{window.winfo_y() + e.y - state['y']}")
    for h in handles:
        h.bind("<ButtonPress-1>", on_press)
        h.bind("<B1-Motion>", on_drag)


class HotkeyEntry(tk.Entry):
    """An Entry widget that captures a keyboard shortcut on focus."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._hook = None
        self.bind("<FocusIn>", self._start_capture)
        self.bind("<FocusOut>", self._stop_capture)

    def _start_capture(self, _event=None):
        self.config(bg=_SURFACE1, fg=_PINK)
        self.delete(0, tk.END)
        self.insert(0, "Press shortcut…")
        self._hook = kb.hook(self._on_key, suppress=False)

    def _stop_capture(self, _event=None):
        if self._hook is not None:
            kb.unhook(self._hook)
            self._hook = None
        self.config(bg=_SURFACE0, fg=_TEXT)
        if self.get() == "Press shortcut…":
            self.delete(0, tk.END)

    def _on_key(self, event: kb.KeyboardEvent):
        if event.event_type != kb.KEY_DOWN:
            return
        combo = "+".join(m for m in kb.get_hotkey_name().split("+") if m)
        if combo:
            self.delete(0, tk.END)
            self.insert(0, combo)
            non_mod = {"ctrl", "shift", "alt", "windows", "right ctrl",
                       "right shift", "right alt", "left ctrl", "left shift", "left alt"}
            if any(p not in non_mod for p in combo.lower().split("+")):
                self.after(150, lambda: self.master.focus_set())


# ═══════════════════════════════════════════════════════════════════════════
#  Settings Window
# ═══════════════════════════════════════════════════════════════════════════

class SettingsWindow:
    """Multi-panel settings window with sidebar navigation."""

    # Section definitions: (key, icon, label)
    _SECTIONS = [
        ("llm",        "🧠", "AI Model"),
        ("audio",      "🎙", "Audio"),
        ("stt",        "🎤", "Speech"),
        ("hotkeys",    "⌨",  "Hotkeys"),
        ("appearance", "🎨", "Look"),
    ]

    def __init__(self, on_save_and_launch=None):
        self.on_save_and_launch = on_save_and_launch
        self.data = store.load()
        self._choice_maps: dict[str, dict[str, str]] = {}
        self._entries: dict[str, tk.Widget] = {}
        self._nav_buttons: dict[str, tk.Label] = {}
        self._panels: dict[str, tk.Frame] = {}
        self._active_section: str = "llm"

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Settings")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=_BASE)
        self.root.resizable(False, False)

        w, h = 620, 540
        sx = (self.root.winfo_screenwidth() - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")

        self._build()

    # ── Layout skeleton ────────────────────────────────────────────────

    def _build(self):
        # Title bar
        title_bar = tk.Frame(self.root, bg=_CRUST, height=32)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        title_lbl = tk.Label(
            title_bar, text=f"  ⚙  {APP_NAME} Settings",
            bg=_CRUST, fg=_SUBTEXT,
            font=(_FONT, 9, "bold"), anchor="w",
        )
        title_lbl.pack(side=tk.LEFT, padx=4)

        ver_lbl = tk.Label(
            title_bar, text=f"v{APP_VERSION}  ",
            bg=_CRUST, fg=_OVERLAY0,
            font=(_FONT, 8),
        )
        ver_lbl.pack(side=tk.RIGHT, padx=(0, 4))

        close_btn = tk.Label(
            title_bar, text=" ✕ ",
            bg=_CRUST, fg=_SUBTEXT,
            font=(_FONT, 10, "bold"), cursor="hand2",
        )
        close_btn.pack(side=tk.RIGHT, padx=(0, 2))
        close_btn.bind("<Button-1>", lambda _: self.root.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=_RED))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=_SUBTEXT))

        _make_draggable(self.root, title_bar, title_lbl)

        # Body = sidebar + main area
        body = tk.Frame(self.root, bg=_BASE)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Sidebar ────────────────────────────────────────────────────
        sidebar = tk.Frame(body, bg=_SIDEBAR, width=72)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        tk.Frame(sidebar, bg=_SIDEBAR, height=8).pack()

        for key, icon, label in self._SECTIONS:
            btn = tk.Label(
                sidebar, text=f"{icon}\n{label}",
                bg=_SIDEBAR, fg=_OVERLAY0,
                font=(_FONT, 8), width=8,
                cursor="hand2", pady=6,
            )
            btn.pack(pady=2)
            btn.bind("<Button-1>", lambda e, k=key: self._switch_section(k))
            self._nav_buttons[key] = btn

        # Spacer + bottom buttons in sidebar
        tk.Frame(sidebar, bg=_SIDEBAR).pack(fill=tk.BOTH, expand=True)

        save_btn = tk.Label(
            sidebar, text="💾\nSave",
            bg=_SIDEBAR, fg=_GREEN,
            font=(_FONT, 8, "bold"), cursor="hand2", pady=6,
        )
        save_btn.pack(pady=2)
        save_btn.bind("<Button-1>", lambda _: self._save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg=_SURFACE0))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg=_SIDEBAR))

        launch_btn = tk.Label(
            sidebar, text="🚀\nLaunch",
            bg=_SIDEBAR, fg=_ACCENT,
            font=(_FONT, 8, "bold"), cursor="hand2", pady=6,
        )
        launch_btn.pack(pady=(2, 10))
        launch_btn.bind("<Button-1>", lambda _: self._save_and_launch())
        launch_btn.bind("<Enter>", lambda e: launch_btn.config(bg=_SURFACE0))
        launch_btn.bind("<Leave>", lambda e: launch_btn.config(bg=_SIDEBAR))

        # ── Main panel container ───────────────────────────────────────
        self._main = tk.Frame(body, bg=_BASE)
        self._main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0)

        # Build each section panel
        self._build_llm_panel()
        self._build_audio_panel()
        self._build_stt_panel()
        self._build_hotkeys_panel()
        self._build_appearance_panel()

        # Show initial section
        self._switch_section("llm")

    # ── Section switching ──────────────────────────────────────────────

    def _switch_section(self, key: str):
        self._active_section = key
        # Hide all panels
        for p in self._panels.values():
            p.pack_forget()
        # Show active
        self._panels[key].pack(fill=tk.BOTH, expand=True)
        # Update nav highlight
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.config(bg=_SURFACE0, fg=_ACCENT)
            else:
                btn.config(bg=_SIDEBAR, fg=_OVERLAY0)
                btn.bind("<Enter>", lambda e, b=btn: b.config(bg=_SURFACE0) if self._nav_buttons.get(self._active_section) is not b else None)
                btn.bind("<Leave>", lambda e, b=btn, kk=k: b.config(bg=_SIDEBAR) if kk != self._active_section else None)

    # ── Panel builders ─────────────────────────────────────────────────

    def _make_panel(self, key: str) -> tk.Frame:
        """Create a scrollable panel frame and register it."""
        outer = tk.Frame(self._main, bg=_BASE)

        canvas = tk.Canvas(outer, bg=_BASE, highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 8))

        inner = tk.Frame(canvas, bg=_BASE)
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e): canvas.configure(scrollregion=canvas.bbox("all"))
        def _canvas_resize(e): canvas.itemconfig(cw, width=e.width)
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _canvas_resize)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._panels[key] = outer
        return inner

    def _build_llm_panel(self):
        p = self._make_panel("llm")
        f = (_FONT, 11)

        self._panel_header(p, "AI Model Configuration", "Choose between cloud API or fully local inference")

        # Provider card
        card = self._card(p, "Provider")
        self._combo_row(card, "LLM Provider", "LLM_PROVIDER", f,
                        [("OpenAI API", "openai"), ("Ollama (Local)", "ollama")], width=20)
        self._hint(card, "Ollama runs models locally — no API key needed")

        # OpenAI card
        card = self._card(p, "OpenAI")
        self._text_row(card, "API Key", "OPENAI_API_KEY", f, show="•")
        self._text_row(card, "Model", "OPENAI_MODEL", f)
        self._hint(card, "gpt-4o  ·  gpt-4o-mini  ·  gpt-4-turbo")

        # Ollama card
        card = self._card(p, "Ollama (Local)")
        self._text_row(card, "Server URL", "OLLAMA_BASE_URL", f)
        self._combo_row(card, "Model", "OLLAMA_MODEL", f,
                        [("Qwen3 8B  •  fast, top code/math", "qwen3:8b"),
                         ("Qwen3 14B  •  best quality, slower", "qwen3:14b"),
                         ("DeepSeek-R1 7B  •  strong reasoning", "deepseek-r1:7b"),
                         ("DeepSeek-R1 14B  •  top reasoning", "deepseek-r1:14b"),
                         ("Phi-4 Mini 3.8B  •  ultrafast math", "phi4-mini"),
                         ("Phi-4 14B  •  math/reasoning", "phi4:14b"),
                         ("Gemma 3 12B  •  multimodal, 128K", "gemma3:12b"),
                         ("Mistral Nemo 12B  •  fast multilingual", "mistral-nemo:12b"),
                         ("GLM-4 9B  •  beats Llama on code", "glm4:9b"),
                         ("Llama 4 Scout 17B  •  multimodal", "llama4:scout"),
                         ],
                        width=30)

        # Status + setup button row
        import shutil
        ollama_found = shutil.which("ollama") is not None

        setup_row = tk.Frame(card, bg=_CARD)
        setup_row.pack(fill=tk.X, pady=(8, 0))

        status_icon = "✓" if ollama_found else "✗"
        status_color = _GREEN if ollama_found else _YELLOW
        status_text = "Ollama is installed" if ollama_found else "Ollama not found"
        self._ollama_status_lbl = tk.Label(
            setup_row, text=f"  {status_icon}  {status_text}  ",
            bg=_CARD, fg=status_color,
            font=(_FONT, 9), anchor="w",
        )
        self._ollama_status_lbl.pack(side=tk.LEFT)

        btn_text = "  ⚡ Pull Model  " if ollama_found else "  ⚡ Install Ollama + Pull Model  "
        setup_btn = tk.Label(
            setup_row, text=btn_text,
            bg=_ACCENT, fg=_CRUST,
            font=(_FONT, 9, "bold"), cursor="hand2", pady=4, padx=6,
        )
        setup_btn.pack(side=tk.RIGHT)
        setup_btn.bind("<Button-1>", lambda _: self._setup_ollama())
        setup_btn.bind("<Enter>", lambda e: setup_btn.config(bg=_MAUVE))
        setup_btn.bind("<Leave>", lambda e: setup_btn.config(bg=_ACCENT))

    def _build_audio_panel(self):
        p = self._make_panel("audio")
        f = (_FONT, 11)

        self._panel_header(p, "Audio Capture", "Microphone and loopback recording settings")

        card = self._card(p, "Source")
        self._combo_row(card, "Capture Mode", "AUDIO_SOURCE", f,
                        [("Other participant", "other"), ("My voice only", "me"), ("Both streams", "both")], width=20)
        self._combo_row(card, "Audio Capture", "AUDIO_CAPTURE_ENABLED", f,
                        [("Enabled", True), ("Disabled", False)], width=20)
        self._spin_row(card, "Chunk Duration (s)", "AUDIO_CHUNK_DURATION", f, 5, 120)
        self._spin_row(card, "Ring Buffer (s)", "AUDIO_RING_BUFFER_SECONDS", f, 30, 300)
        self._spin_row(card, "Transcription Interval", "TRANSCRIPTION_INTERVAL", f, 1, 10)

        card = self._card(p, "Devices")
        self._combo_row(card, "Microphone", "AUDIO_INPUT_DEVICE_ID", f,
                        list_microphone_choices(), width=32)
        self._combo_row(card, "Speaker / Loopback", "AUDIO_OUTPUT_DEVICE_ID", f,
                        list_speaker_choices(), width=32)
        self._hint(card, "Leave empty for system default")

    def _build_stt_panel(self):
        p = self._make_panel("stt")
        f = (_FONT, 11)

        self._panel_header(p, "Speech-to-Text", "Transcription engine and language settings")

        card = self._card(p, "Engine")
        self._combo_row(card, "STT Provider", "STT_PROVIDER", f,
                        [("Auto (best available)", "auto"), ("Local Whisper", "local"), ("xAI API", "xai")], width=22)

        card = self._card(p, "xAI API")
        self._text_row(card, "xAI API Key", "XAI_API_KEY", f, show="•")
        self._combo_row(
            card, "xAI STT Language", "XAI_STT_LANGUAGE", f,
            [("English", "en"), ("Portuguese", "pt"), ("Spanish", "es"),
             ("French", "fr"), ("German", "de"), ("Japanese", "ja"),
             ("Chinese", "zh"), ("Korean", "ko")],
            width=22,
        )
        self._combo_row(card, "Format Text", "XAI_STT_FORMAT_TEXT", f,
                        [("Yes", True), ("No", False)], width=20)
        self._spin_row(card, "Timeout (s)", "XAI_STT_TIMEOUT_SECONDS", f, 5, 120)
        self._hint(card, "Only needed when STT Provider is set to xAI")

        card = self._card(p, "Language")
        self._combo_row(
            card, "Language", "STT_LANGUAGE", f,
            [
                ("Auto-detect", ""),
                ("English", "en"),
                ("Portuguese", "pt"),
                ("Spanish", "es"),
                ("French", "fr"),
                ("German", "de"),
                ("Italian", "it"),
                ("Japanese", "ja"),
                ("Chinese (Simplified)", "zh"),
                ("Korean", "ko"),
                ("Arabic", "ar"),
                ("Russian", "ru"),
                ("Hindi", "hi"),
            ],
            width=22,
        )

        card = self._card(p, "Local Whisper")
        self._combo_row(card, "Model", "LOCAL_WHISPER_MODEL", f,
                        [("Large V3 Turbo (best)", "large-v3-turbo"),
                         ("Medium English", "medium.en"),
                         ("Small English", "small.en"),
                         ("Base English", "base.en"),
                         ("Tiny English (fastest)", "tiny.en"),
                         ("Large V3", "large-v3"),
                         ("Medium", "medium"),
                         ("Small", "small"),
                         ("Base", "base"),
                         ("Tiny", "tiny")],
                        width=22)
        self._combo_row(card, "Device", "LOCAL_WHISPER_DEVICE", f,
                        [("Auto (GPU if available)", "auto"), ("CPU", "cpu"), ("CUDA GPU", "cuda")], width=22)

    def _build_hotkeys_panel(self):
        p = self._make_panel("hotkeys")
        f = (_FONT, 11)

        self._panel_header(p, "Keyboard Shortcuts", "Click a field and press your desired shortcut")

        card = self._card(p, "Actions")
        self._hotkey_row(card, "Analyze Conversation", "HOTKEY_AUDIO_ANALYSIS", f)
        self._hotkey_row(card, "Screenshot Analysis", "HOTKEY_SCREENSHOT_FEEDBACK", f)
        self._hotkey_row(card, "Quick Text Input", "HOTKEY_QUICK_INPUT", f)
        self._hotkey_row(card, "Show / Hide Overlay", "HOTKEY_SHOW_CONVERSATION", f)

    def _build_appearance_panel(self):
        p = self._make_panel("appearance")
        f = (_FONT, 11)

        self._panel_header(p, "Appearance", "Visual tweaks for the overlay")

        card = self._card(p, "Overlay")
        self._slider_row(card, "Opacity", "INSIGHT_OVERLAY_OPACITY", f, 0.1, 1.0)

        card = self._card(p, "Stealth")
        self._combo_row(card, "Stealth Mode", "STEALTH_MODE", f,
                        [("Enabled — hidden from capture", True),
                         ("Disabled — visible in shares", False)], width=30)

        card = self._card(p, "Features")
        self._combo_row(card, "Screenshot Analysis", "SCREENSHOT_FEEDBACK_ENABLED", f,
                        [("Enabled", True), ("Disabled", False)], width=20)

    # ── Ollama setup ───────────────────────────────────────────────────

    def _setup_ollama(self):
        """Install Ollama, pull the selected model, and start the server."""
        import os, subprocess, shutil, threading, time

        widget = self._entries.get("OLLAMA_MODEL")
        model = widget.get().strip() if isinstance(widget, tk.Entry) else "qwen3:14b"
        if not model:
            model = "qwen3:14b"

        # ── Progress dialog ────────────────────────────────────────────
        prog = tk.Toplevel(self.root)
        prog.overrideredirect(True)
        prog.attributes("-topmost", True)
        prog.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                       highlightthickness=1)
        pw, ph = 480, 320
        px = self.root.winfo_x() + (self.root.winfo_width() - pw) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        prog.geometry(f"{pw}x{ph}+{px}+{py}")

        # Header
        hdr = tk.Frame(prog, bg=_CRUST)
        hdr.pack(fill=tk.X, padx=16, pady=(14, 0))
        tk.Label(hdr, text="⚡  Ollama Setup", bg=_CRUST, fg=_ACCENT,
                 font=(_FONT, 12, "bold")).pack(side=tk.LEFT)

        # Loading dots (animated)
        dot_var = tk.StringVar(value="●○○○○")
        dot_lbl = tk.Label(hdr, textvariable=dot_var, bg=_CRUST, fg=_ACCENT,
                           font=(_FONT, 9))
        dot_lbl.pack(side=tk.RIGHT)
        _DOT_FRAMES = ("●○○○○", "○●○○○", "○○●○○", "○○○●○", "○○○○●")
        _dot_idx = [0]
        _anim_id = [None]

        def _animate():
            _dot_idx[0] = (_dot_idx[0] + 1) % len(_DOT_FRAMES)
            try:
                dot_var.set(_DOT_FRAMES[_dot_idx[0]])
                _anim_id[0] = prog.after(200, _animate)
            except Exception:
                pass

        _anim_id[0] = prog.after(200, _animate)

        # Status line
        status_var = tk.StringVar(value="Checking installation…")
        tk.Label(prog, textvariable=status_var, bg=_CRUST, fg=_TEXT,
                 font=(_FONT, 10), anchor="w").pack(fill=tk.X, padx=16, pady=(10, 4))

        # Log area
        log_frame = tk.Frame(prog, bg=_SURFACE0, highlightbackground=_SURFACE1,
                             highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        log_text = tk.Text(
            log_frame, bg=_SURFACE0, fg=_SUBTEXT,
            font=(_FONT, 8), wrap=tk.WORD,
            relief=tk.FLAT, bd=0, padx=8, pady=6,
            insertbackground=_SUBTEXT, state=tk.DISABLED,
            highlightthickness=0,
        )
        log_text.pack(fill=tk.BOTH, expand=True)

        # Bottom button area (initially empty)
        btn_frame = tk.Frame(prog, bg=_CRUST)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 12))

        def _log(line: str):
            """Append a line to the log area (thread-safe)."""
            def _do():
                try:
                    log_text.config(state=tk.NORMAL)
                    log_text.insert(tk.END, line + "\n")
                    log_text.see(tk.END)
                    log_text.config(state=tk.DISABLED)
                except Exception:
                    pass
            try:
                prog.after(0, _do)
            except Exception:
                pass

        def _status(msg: str):
            try:
                prog.after(0, lambda: status_var.set(msg))
            except Exception:
                pass

        def _stop_anim():
            try:
                if _anim_id[0]:
                    prog.after_cancel(_anim_id[0])
                    _anim_id[0] = None
                prog.after(0, lambda: dot_var.set(""))
            except Exception:
                pass

        def _add_close():
            _stop_anim()
            try:
                btn = tk.Label(btn_frame, text="  OK  ", bg=_ACCENT, fg=_CRUST,
                               font=(_FONT, 9, "bold"), cursor="hand2",
                               pady=4, padx=12)
                btn.pack(side=tk.RIGHT)
                btn.bind("<Button-1>", lambda _: prog.destroy())
                btn.bind("<Enter>", lambda e: btn.config(bg=_MAUVE))
                btn.bind("<Leave>", lambda e: btn.config(bg=_ACCENT))
            except Exception:
                pass

        def _stream_cmd(cmd, label, timeout_s=3600):
            """Run a command and stream its stdout/stderr to the log."""
            CREATE_NO_WINDOW = 0x08000000
            _log(f"$ {' '.join(cmd)}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW,
                )
                deadline = time.monotonic() + timeout_s
                for line in proc.stdout:
                    stripped = line.rstrip()
                    if stripped:
                        _log(stripped)
                    if time.monotonic() > deadline:
                        proc.kill()
                        _log(f"⚠ {label} timed out")
                        return False
                proc.wait(timeout=30)
                if proc.returncode == 0:
                    _log(f"✓ {label} completed")
                    return True
                else:
                    _log(f"✗ {label} failed (exit code {proc.returncode})")
                    return False
            except FileNotFoundError:
                _log(f"✗ Command not found: {cmd[0]}")
                return False
            except Exception as e:
                _log(f"✗ {label} error: {e}")
                return False

        def _run():
            CREATE_NO_WINDOW = 0x08000000
            ollama_dir = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Programs", "Ollama",
            )
            if os.path.isdir(ollama_dir):
                os.environ["PATH"] = (
                    ollama_dir + os.pathsep + os.environ.get("PATH", "")
                )

            # 1. Check / install ─────────────────────────────────────
            if not shutil.which("ollama"):
                _status("Installing Ollama…")
                _log("Ollama not found on PATH — installing via winget…")
                ok = _stream_cmd(
                    ["winget", "install", "-e", "--id",
                     "Ollama.Ollama",
                     "--accept-package-agreements",
                     "--accept-source-agreements"],
                    "Ollama install", timeout_s=600,
                )
                if ok and os.path.isdir(ollama_dir):
                    os.environ["PATH"] = (
                        ollama_dir + os.pathsep
                        + os.environ.get("PATH", "")
                    )
                if not shutil.which("ollama"):
                    _status("❌  Installation failed")
                    _log("ollama binary still not found after install.")
                    _log("Install manually from https://ollama.com")
                    prog.after(0, _add_close)
                    return
                _log("")
            else:
                _log("✓ Ollama is already installed")

            # 2. Start server ────────────────────────────────────────
            _status("Starting Ollama server…")
            _log("Starting ollama serve…")
            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                _log("Server process launched (waiting 3s for startup)…")
            except Exception:
                _log("(server may already be running)")
            time.sleep(3)
            _log("")

            # 3. Pull model ──────────────────────────────────────────
            _status(f"Pulling model '{model}'…")
            _log(f"Downloading model: {model}")
            _log("This can take several minutes for large models.\n")
            ok = _stream_cmd(
                ["ollama", "pull", model],
                "Model pull", timeout_s=3600,
            )

            _log("")
            if ok:
                _status("✓  Ready!")
                _log(f"Model '{model}' is ready — select Ollama as provider and launch!")
                # Update the status label in the settings panel
                try:
                    prog.after(0, lambda: self._ollama_status_lbl.config(
                        text="  ✓  Ollama is installed  ", fg=_GREEN))
                except Exception:
                    pass
            else:
                _status("❌  Setup had errors — check log above")

            prog.after(0, _add_close)

        threading.Thread(target=_run, daemon=True).start()

    # ── UI building blocks ─────────────────────────────────────────────

    def _panel_header(self, parent: tk.Widget, title: str, subtitle: str):
        tk.Label(
            parent, text=title,
            bg=_BASE, fg=_TEXT,
            font=(_FONT, 14, "bold"), anchor="w",
        ).pack(fill=tk.X, pady=(0, 0))
        tk.Label(
            parent, text=subtitle,
            bg=_BASE, fg=_OVERLAY0,
            font=(_FONT, 9), anchor="w",
        ).pack(fill=tk.X, pady=(0, 10))

    def _card(self, parent: tk.Widget, title: str) -> tk.Frame:
        wrapper = tk.Frame(parent, bg=_CARD, highlightbackground=_SURFACE1,
                           highlightthickness=1)
        wrapper.pack(fill=tk.X, pady=(0, 10))
        # Card header
        hdr = tk.Frame(wrapper, bg=_CARD)
        hdr.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            hdr, text=title,
            bg=_CARD, fg=_ACCENT,
            font=(_FONT, 9, "bold"), anchor="w",
        ).pack(side=tk.LEFT)
        # Card body
        body = tk.Frame(wrapper, bg=_CARD)
        body.pack(fill=tk.X, padx=12, pady=(0, 10))
        return body

    def _hint(self, parent: tk.Widget, text: str):
        tk.Label(
            parent, text=text,
            bg=_CARD, fg=_OVERLAY0,
            font=(_FONT, 8), anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

    def _hotkey_row(self, parent: tk.Widget, label: str, key: str, font):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)
        entry = HotkeyEntry(
            row, bg=_SURFACE0, fg=_TEXT,
            insertbackground=_TEXT,
            font=font, relief=tk.FLAT, width=20,
            highlightthickness=1, highlightcolor=_PINK,
            highlightbackground=_SURFACE1,
        )
        entry.insert(0, self.data.get(key, ""))
        entry.pack(side=tk.LEFT, padx=(4, 0), ipady=3)
        self._entries[key] = entry

    def _text_row(self, parent: tk.Widget, label: str, key: str, font, show=None):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)
        entry = tk.Entry(
            row, bg=_SURFACE0, fg=_TEXT,
            insertbackground=_TEXT,
            font=font, relief=tk.FLAT, width=24,
            show=show,
            highlightthickness=1, highlightcolor=_ACCENT,
            highlightbackground=_SURFACE1,
        )
        entry.insert(0, self.data.get(key, ""))
        entry.pack(side=tk.LEFT, padx=(4, 0), ipady=3)
        self._entries[key] = entry

    def _slider_row(self, parent: tk.Widget, label: str, key: str, font, lo: float, hi: float):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)
        var = tk.DoubleVar(value=self.data.get(key, lo))
        scale = tk.Scale(
            row, from_=lo, to=hi, resolution=0.05,
            orient=tk.HORIZONTAL, variable=var,
            bg=_CARD, fg=_TEXT,
            troughcolor=_SURFACE0, highlightthickness=0,
            font=(_FONT, 7), length=180,
            activebackground=_ACCENT, sliderrelief=tk.FLAT,
        )
        scale.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var

    def _spin_row(self, parent: tk.Widget, label: str, key: str, font, lo: int, hi: int):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)
        var = tk.IntVar(value=self.data.get(key, lo))
        spin = tk.Spinbox(
            row, from_=lo, to=hi, textvariable=var, width=6,
            bg=_SURFACE0, fg=_TEXT,
            font=font, relief=tk.FLAT, buttonbackground=_SURFACE1,
        )
        spin.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        self._entries[key] = var

    def _combo_row(self, parent: tk.Widget, label: str, key: str, font, options, width: int = 14):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)

        if options and isinstance(options[0], tuple):
            label_to_value = {lbl: val for lbl, val in options}
            value_to_label = {val: lbl for lbl, val in options}
            current_value = self.data.get(key, options[0][1])
            var = tk.StringVar(value=value_to_label.get(current_value, options[0][0]))
            values = [lbl for lbl, _ in options]
            self._choice_maps[key] = label_to_value
        else:
            var = tk.StringVar(value=self.data.get(key, options[0] if options else ""))
            values = options

        combo = ttk.Combobox(
            row, textvariable=var, values=values, state="readonly",
            width=width, font=font,
        )
        combo.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var

    # ── Actions ────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        result = dict(self.data)
        for key, widget in self._entries.items():
            if isinstance(widget, (tk.DoubleVar, tk.IntVar, tk.StringVar)):
                if key in self._choice_maps:
                    result[key] = self._choice_maps[key].get(widget.get(), "")
                else:
                    result[key] = widget.get()
            elif isinstance(widget, tk.Entry):
                result[key] = widget.get().strip()
        return result

    def _save(self):
        data = self._collect()
        store.save(data)
        messagebox.showinfo("Settings", "Settings saved.", parent=self.root)

    def _save_and_launch(self):
        data = self._collect()
        store.save(data)
        self.root.destroy()
        if self.on_save_and_launch:
            self.on_save_and_launch()

    def run(self):
        try:
            from visibility import exclude_from_taskbar
            self.root.after(100, lambda: exclude_from_taskbar(int(self.root.wm_frame(), 16)))
        except Exception:
            pass
        self.root.mainloop()
