"""
Settings UI — multi-panel settings window with sidebar navigation.

Catppuccin Mocha themed.  Each section lives in its own panel,
toggled by icon buttons on the left rail.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import webbrowser

import keyboard as kb

from audio_capture import list_microphone_choices, list_speaker_choices
import settings as store
from codex_client import CodexClient, find_codex_executable
from config import (
    APP_NAME,
    APP_VERSION,
    OLLAMA_BASE_URL,
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

# ── Ollama model catalogue with vision capability tags ──────────────────────
# (display_label, model_id, supports_vision)
_OLLAMA_MODELS = [
    ("Qwen3 8B  •  fast, top code/math",       "qwen3:8b",          False),
    ("Qwen3 14B  •  best quality, slower",      "qwen3:14b",         False),
    ("DeepSeek-R1 7B  •  strong reasoning",     "deepseek-r1:7b",    False),
    ("DeepSeek-R1 14B  •  top reasoning",       "deepseek-r1:14b",   False),
    ("Phi-4 Mini 3.8B  •  ultrafast math",      "phi4-mini",         False),
    ("Phi-4 14B  •  math/reasoning",            "phi4:14b",          False),
    ("Gemma 3 12B  •  multimodal, 128K",        "gemma3:12b",        True),
    ("Gemma 4 E2B  •  tiny, phone-ready, 7GB",  "gemma4:e2b",        True),
    ("Gemma 4 E4B  •  small edge, multimodal",  "gemma4:e4b",        True),
    ("Gemma 4 26B MoE  •  frontier, 256K",      "gemma4:26b",        True),
    ("Gemma 4 31B  •  best Gemma, 256K",        "gemma4:31b",        True),
    ("Mistral Nemo 12B  •  fast multilingual",  "mistral-nemo:12b",  False),
    ("GLM-4 9B  •  beats Llama on code",        "glm4:9b",           False),
    ("Llama 4 Scout 17B  •  multimodal",        "llama4:scout",      True),
]

_OLLAMA_ALL_MODELS   = [(lbl, val) for lbl, val, _   in _OLLAMA_MODELS]
_OLLAMA_VISION_MODELS = [(lbl, val) for lbl, val, vis in _OLLAMA_MODELS if vis]

_OPENAI_TEXT_MODELS = [
    ("GPT-5.5  - newest GPT-5 option", "gpt-5.5"),
    ("GPT-5.2  - strong coding/reasoning", "gpt-5.2"),
    ("GPT-5.2 Chat  - ChatGPT-style", "gpt-5.2-chat-latest"),
    ("GPT-5.1  - coding/reasoning", "gpt-5.1"),
    ("GPT-5  - previous GPT-5", "gpt-5"),
    ("GPT-5 mini  - faster, lower cost", "gpt-5-mini"),
    ("GPT-5 nano  - fastest, lowest cost", "gpt-5-nano"),
    ("GPT-4.1  - non-reasoning", "gpt-4.1"),
    ("GPT-4.1 mini  - faster non-reasoning", "gpt-4.1-mini"),
    ("GPT-4o  - legacy multimodal", "gpt-4o"),
    ("GPT-4o mini  - cheap legacy multimodal", "gpt-4o-mini"),
    ("o3  - reasoning", "o3"),
    ("o4-mini  - fast reasoning", "o4-mini"),
    ("o3-mini  - older small reasoning", "o3-mini"),
]

_OPENAI_IMAGE_MODELS = [
    ("GPT-5.5  - newest GPT-5 option", "gpt-5.5"),
    ("GPT-5.2  - strong vision reasoning", "gpt-5.2"),
    ("GPT-5.2 Chat  - ChatGPT-style vision", "gpt-5.2-chat-latest"),
    ("GPT-5.1  - vision capable", "gpt-5.1"),
    ("GPT-5  - vision capable", "gpt-5"),
    ("GPT-5 mini  - faster vision", "gpt-5-mini"),
    ("GPT-5 nano  - fastest vision", "gpt-5-nano"),
    ("GPT-4.1  - vision capable", "gpt-4.1"),
    ("GPT-4.1 mini  - faster vision", "gpt-4.1-mini"),
    ("GPT-4o  - legacy multimodal", "gpt-4o"),
    ("GPT-4o mini  - cheap legacy multimodal", "gpt-4o-mini"),
]


def _query_ollama_models() -> set[str]:
    """Return the set of model ids currently pulled in Ollama (best-effort)."""
    try:
        import json, urllib.request
        req = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        data = json.loads(req.read())
        req.close()
        names: set[str] = set()
        for m in data.get("models", []):
            n = m.get("name", "")
            names.add(n)
            # Also add base name without tag variant (e.g. "qwen3:8b" from "qwen3:8b-q4_0")
            if "-" in n.split(":")[-1]:
                names.add(n.rsplit("-", 1)[0])
        return names
    except Exception:
        return set()


class _Tooltip:
    """Hover tooltip for any tkinter widget — Catppuccin styled."""

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def update_text(self, text: str):
        self._text = text
        if self._tip:
            for child in self._tip.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(text=text)

    def _show(self, _event=None):
        if self._tip or not self._text:
            return
        x = self._widget.winfo_rootx()
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        lbl = tk.Label(
            tw, text=self._text, justify=tk.LEFT,
            bg=_CRUST, fg=_TEXT,
            font=(_FONT, 10), padx=10, pady=6,
            relief=tk.SOLID, borderwidth=1,
            highlightbackground=_SURFACE1, highlightthickness=1,
            wraplength=500,
        )
        lbl.pack()
        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


class _DropdownItemTooltip:
    """Shows a tooltip for individual items inside an open ttk.Combobox dropdown."""

    def __init__(self, combo: ttk.Combobox):
        self._combo = combo
        self._tip: tk.Toplevel | None = None
        self._last_index: int = -1
        self._bound = False
        # Hook into the dropdown open/close events
        combo.bind("<ButtonPress-1>", self._on_open, add="+")
        combo.bind("<<ComboboxSelected>>", self._dismiss, add="+")

    def _on_open(self, _event=None):
        """After the dropdown popdown appears, find its Listbox and bind Motion."""
        self._combo.after(50, self._attach_listbox)

    def _attach_listbox(self):
        """Locate the internal Tk popdown listbox and bind hover events."""
        try:
            # Tk stores the popdown path in the combobox's popdown widget
            popdown = self._combo.tk.call("ttk::combobox::PopdownWindow", self._combo)
            lb = self._combo.nametowidget(f"{popdown}.f.l")
            if not self._bound:
                lb.bind("<Motion>", self._on_motion)
                lb.bind("<Leave>", self._dismiss)
                self._bound = True
        except Exception:
            pass

    def _on_motion(self, event):
        """Show tooltip for the item under the cursor."""
        try:
            lb = event.widget
            index = lb.nearest(event.y)
            if index == self._last_index and self._tip:
                return
            self._last_index = index
            text = lb.get(index)
            self._dismiss()
            if not text:
                return
            # Position the tooltip to the right of the dropdown listbox
            x = lb.winfo_rootx() + lb.winfo_width() + 4
            y = lb.winfo_rooty() + event.y - 10
            self._tip = tw = tk.Toplevel(lb)
            tw.wm_overrideredirect(True)
            tw.wm_attributes("-topmost", True)
            lbl = tk.Label(
                tw, text=text, justify=tk.LEFT,
                bg=_CRUST, fg=_TEXT,
                font=(_FONT, 10), padx=10, pady=6,
                relief=tk.SOLID, borderwidth=1,
                highlightbackground=_SURFACE1, highlightthickness=1,
                wraplength=500,
            )
            lbl.pack()
            tw.wm_geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _dismiss(self, _event=None):
        self._last_index = -1
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


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
        ("codex",      "CX", "Codex"),
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
        self._ensure_combo_widget_registry()
        self._nav_buttons: dict[str, tk.Label] = {}
        self._panels: dict[str, tk.Frame] = {}
        self._active_section: str = "llm"
        self._ollama_pulled: set[str] = set()
        self._codex_account: dict | None = None
        self._codex_available = False
        self._codex_error = ""
        self._mic_choices: list = []
        self._spk_choices: list = []

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

    def _ensure_combo_widget_registry(self) -> dict[str, ttk.Combobox]:
        if not hasattr(self, "_combo_widgets"):
            self._combo_widgets: dict[str, ttk.Combobox] = {}
        return self._combo_widgets

    # ── Layout skeleton ────────────────────────────────────────────────

    @staticmethod
    def _init_ollama_pulled() -> set[str]:
        """Query Ollama for pulled models (callable without an instance)."""
        return _query_ollama_models()

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

        # Show loading screen while fetching data in background
        self._show_loading()
        import threading
        threading.Thread(target=self._load_data_async, daemon=True).start()

    # ── Async data loading ─────────────────────────────────────────────

    def _show_loading(self):
        """Display a loading overlay while background data is fetched."""
        self._loading_frame = tk.Frame(self._main, bg=_BASE)
        self._loading_frame.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(self._loading_frame, bg=_BASE)
        inner.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(
            inner, text="⚙", bg=_BASE, fg=_ACCENT,
            font=(_FONT, 28),
        ).pack()

        self._loading_dots_var = tk.StringVar(value="Loading settings")
        tk.Label(
            inner, textvariable=self._loading_dots_var,
            bg=_BASE, fg=_SUBTEXT, font=(_FONT, 11),
        ).pack(pady=(10, 0))

        tk.Label(
            inner, text="Detecting devices & models…",
            bg=_BASE, fg=_OVERLAY0, font=(_FONT, 9),
        ).pack(pady=(4, 0))

        self._loading_dot_idx = 0
        self._loading_anim_id = None
        self._animate_loading()

    def _animate_loading(self):
        dots = "." * (self._loading_dot_idx % 4)
        try:
            self._loading_dots_var.set(f"Loading settings{dots}")
            self._loading_dot_idx += 1
            self._loading_anim_id = self.root.after(400, self._animate_loading)
        except Exception:
            pass

    def _load_data_async(self):
        """Fetch slow data (Ollama models, audio devices) in a background thread."""
        uses_ollama = "ollama" in (
            self.data.get("LLM_TEXT_PROVIDER", ""),
            self.data.get("LLM_IMAGE_PROVIDER", ""),
        )
        self._ollama_pulled = _query_ollama_models() if uses_ollama else set()
        self._load_codex_status()
        self._mic_choices = list_microphone_choices()
        self._spk_choices = list_speaker_choices()
        try:
            self.root.after(0, self._finish_build)
        except Exception:
            pass

    def _load_codex_status(self):
        """Best-effort Codex CLI/OAuth detection for the settings UI."""
        self._codex_available = find_codex_executable() is not None
        self._codex_account = None
        self._codex_error = ""
        if not self._codex_available:
            self._codex_error = "Codex CLI not found"
            return

        client = CodexClient()
        try:
            account = client.get_account(refresh_token=True).get("account")
            if account and account.get("type") == "chatgpt":
                self._codex_account = account
        except Exception as exc:
            self._codex_error = str(exc)
        finally:
            client.close()

    def _finish_build(self):
        """Build all setting panels after background data is ready."""
        if self._loading_anim_id:
            self.root.after_cancel(self._loading_anim_id)
            self._loading_anim_id = None
        self._loading_frame.destroy()

        self._build_llm_panel()
        self._build_codex_panel()
        self._build_audio_panel()
        self._build_stt_panel()
        self._build_hotkeys_panel()
        self._build_appearance_panel()
        self._switch_section("llm")

    # ── Section switching ──────────────────────────────────────────────

    def _switch_section(self, key: str):
        if key not in self._panels:
            return  # panels not built yet (still loading)
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

    def _llm_provider_options(self):
        options = [("OpenAI API", "openai"), ("Ollama (Local)", "ollama")]
        selected = {
            self.data.get("LLM_TEXT_PROVIDER", ""),
            self.data.get("LLM_IMAGE_PROVIDER", ""),
        }
        if self._codex_account or "codex" in selected:
            options.append(("Codex OAuth", "codex"))
        return options

    def _build_llm_panel(self):
        p = self._make_panel("llm")
        f = (_FONT, 11)

        self._panel_header(p, "AI Model Configuration", "Choose between cloud API or fully local inference")

        # Response Profile card (hot-reloaded — no restart needed)
        card = self._card(p, "Response Profile")
        self._combo_row(card, "AI Persona", "RESPONSE_PROFILE", f,
                        [("Software Engineer", "software_engineer"),
                         ("Tech Lead", "tech_lead"),
                         ("Sales Professional", "seller"),
                         ("HR Professional", "hr"),
                         ("Trainer / Coach", "trainer")], width=22)
        self._hint(card, "Changes apply instantly — no restart required")

        # Provider card
        card = self._card(p, "Provider")
        self._combo_row(card, "Text Provider", "LLM_TEXT_PROVIDER", f,
                        self._llm_provider_options(), width=20)
        self._combo_row(card, "Image Provider", "LLM_IMAGE_PROVIDER", f,
                        self._llm_provider_options(), width=20)
        self._hint(card, "You can mix providers — e.g. Ollama for text, OpenAI for images")

        # OpenAI card
        card = self._card(p, "OpenAI")
        self._text_row(card, "API Key", "OPENAI_API_KEY", f, show="•")
        self._combo_row(card, "Text Model", "OPENAI_TEXT_MODEL", f,
                        _OPENAI_TEXT_MODELS, width=34, editable=True)
        self._hint(card, "Editable dropdown - select a listed model or type another OpenAI text model id")
        self._combo_row(card, "Image Model", "OPENAI_IMAGE_MODEL", f,
                        _OPENAI_IMAGE_MODELS, width=34, editable=True)
        self._hint(card, "Editable dropdown - use a model that supports image input for screenshots")

        # Ollama card
        card = self._card(p, "Ollama (Local)")
        self._text_row(card, "Server URL", "OLLAMA_BASE_URL", f)
        self._combo_row(card, "Text Model", "OLLAMA_TEXT_MODEL", f,
                        _OLLAMA_ALL_MODELS, width=30)
        self._hint(card, "Used for conversation / transcript analysis")
        self._combo_row(card, "Image Model", "OLLAMA_IMAGE_MODEL", f,
                        _OLLAMA_VISION_MODELS, width=30)
        self._hint(card, "Used for screenshot analysis — only vision-capable models shown")
        self._combo_row(card, "Close Ollama on Exit", "KILL_OLLAMA_ON_EXIT", f,
                        [("Disabled — keep Ollama running", False),
                         ("Enabled — kill Ollama process", True)], width=30)
        self._hint(card, "Models are always unloaded from GPU on exit")

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

    def _build_codex_panel(self):
        p = self._make_panel("codex")
        f = (_FONT, 11)

        self._panel_header(p, "Codex OAuth", "Use your local Codex login instead of an OpenAI API key")

        card = self._card(p, "Status")
        self._codex_status_lbl = tk.Label(
            card,
            text=self._codex_status_text(),
            bg=_CARD,
            fg=self._codex_status_color(),
            font=(_FONT, 10),
            anchor="w",
            justify=tk.LEFT,
            wraplength=470,
        )
        self._codex_status_lbl.pack(fill=tk.X, pady=(0, 8))

        button_row = tk.Frame(card, bg=_CARD)
        button_row.pack(fill=tk.X)
        self._action_button(button_row, "Sign In", lambda: self._start_codex_login(False), side=tk.LEFT)
        self._action_button(button_row, "Device Code", lambda: self._start_codex_login(True), side=tk.LEFT)
        self._action_button(button_row, "Refresh", self._refresh_codex_status, side=tk.LEFT)
        self._hint(card, "HelpAI talks to codex app-server and never reads ~/.codex/auth.json")

        card = self._card(p, "Model")
        self._text_row(card, "Model Override", "CODEX_MODEL", f)
        self._hint(card, "Leave empty to use the default model from your Codex configuration")

    def _codex_status_text(self) -> str:
        if not self._codex_available:
            return "Codex CLI is not installed. Install with: npm install -g @openai/codex"
        if self._codex_account:
            email = self._codex_account.get("email", "signed in")
            plan = self._codex_account.get("planType", "unknown")
            return f"Signed in as {email} ({plan}). Codex is available in provider selectors."
        if self._codex_error:
            return f"Codex CLI found, but OAuth is not ready: {self._codex_error}"
        return "Codex CLI found, but no ChatGPT OAuth account is signed in."

    def _codex_status_color(self) -> str:
        if self._codex_account:
            return _GREEN
        if self._codex_available:
            return _YELLOW
        return _RED

    def _action_button(self, parent: tk.Widget, text: str, command, side=tk.RIGHT):
        btn = tk.Label(
            parent,
            text=f"  {text}  ",
            bg=_ACCENT,
            fg=_CRUST,
            font=(_FONT, 9, "bold"),
            cursor="hand2",
            pady=4,
            padx=6,
        )
        btn.pack(side=side, padx=(0, 8))
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda e: btn.config(bg=_MAUVE))
        btn.bind("<Leave>", lambda e: btn.config(bg=_ACCENT))
        return btn

    def _start_codex_login(self, device_code: bool):
        def worker():
            client = CodexClient()
            try:
                login = client.start_login(device_code=device_code)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Codex", str(exc), parent=self.root))
                return
            finally:
                client.close()

            def show_login():
                if login.get("authUrl"):
                    webbrowser.open(login["authUrl"])
                    messagebox.showinfo(
                        "Codex",
                        "Browser login opened. Finish signing in, then click Refresh.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        "Codex Device Code",
                        f"Open {login.get('verificationUrl')}\n\nCode: {login.get('userCode')}",
                        parent=self.root,
                    )

            self.root.after(0, show_login)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_codex_status(self):
        def worker():
            self._load_codex_status()
            self.root.after(0, self._apply_codex_status)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_codex_status(self):
        if hasattr(self, "_codex_status_lbl"):
            self._codex_status_lbl.config(
                text=self._codex_status_text(),
                fg=self._codex_status_color(),
            )
        self._refresh_provider_combos()

    def _refresh_provider_combos(self):
        options = self._llm_provider_options()
        for key in ("LLM_TEXT_PROVIDER", "LLM_IMAGE_PROVIDER"):
            combo = self._ensure_combo_widget_registry().get(key)
            var = self._entries.get(key)
            if combo is None or not isinstance(var, tk.StringVar):
                continue
            current_value = self._choice_maps.get(key, {}).get(var.get(), self.data.get(key, "openai"))
            label_to_value = {label: value for label, value in options}
            value_to_label = {value: label for label, value in options}
            self._choice_maps[key] = label_to_value
            combo.configure(values=[label for label, _value in options])
            var.set(value_to_label.get(current_value, options[0][0]))

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
                        self._mic_choices, width=32)
        self._combo_row(card, "Speaker / Loopback", "AUDIO_OUTPUT_DEVICE_ID", f,
                        self._spk_choices, width=32)
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
        self._hotkey_row(card, "Save Screenshot", "HOTKEY_SCREENSHOT_FEEDBACK", f)
        self._hotkey_row(card, "Analyze Saved Screenshots", "HOTKEY_ANALYZE_SCREENSHOTS", f)
        self._hotkey_row(card, "Quick Text Input", "HOTKEY_QUICK_INPUT", f)
        self._hotkey_row(card, "Show / Hide Overlay", "HOTKEY_SHOW_CONVERSATION", f)
        self._hotkey_row(card, "Clear Context", "HOTKEY_CLEAR_CONTEXT", f)

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
        """Install Ollama, pull the selected models, and start the server."""
        import os, subprocess, shutil, threading, time

        # Read the currently selected text and image models
        def _resolve_model(settings_key, fallback):
            widget = self._entries.get(settings_key)
            if widget is not None:
                display_val = widget.get() if isinstance(widget, tk.StringVar) else (
                    widget.get().strip() if isinstance(widget, tk.Entry) else ""
                )
                if display_val:
                    choice_map = self._choice_maps.get(settings_key, {})
                    return choice_map.get(display_val, display_val)
            return fallback

        text_model = _resolve_model("OLLAMA_TEXT_MODEL", "qwen3:8b")
        image_model = _resolve_model("OLLAMA_IMAGE_MODEL", "gemma3:12b")
        models_to_pull = list(dict.fromkeys([text_model, image_model]))  # dedupe, keep order

        # ── Progress dialog ────────────────────────────────────────────
        prog = tk.Toplevel(self.root)
        prog.overrideredirect(True)
        prog.attributes("-topmost", True)
        prog.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                       highlightthickness=1)
        pw, ph = 560, 420
        px = self.root.winfo_x() + (self.root.winfo_width() - pw) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        prog.geometry(f"{pw}x{ph}+{px}+{py}")

        # Header
        hdr = tk.Frame(prog, bg=_CRUST)
        hdr.pack(fill=tk.X, padx=20, pady=(16, 0))
        tk.Label(hdr, text="⚡  Ollama Setup", bg=_CRUST, fg=_ACCENT,
                 font=(_FONT, 13, "bold")).pack(side=tk.LEFT)

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

        # Model badge
        model_row = tk.Frame(prog, bg=_CRUST)
        model_row.pack(fill=tk.X, padx=20, pady=(6, 0))
        tk.Label(model_row, text="Models:", bg=_CRUST, fg=_OVERLAY0,
                 font=(_FONT, 9)).pack(side=tk.LEFT)
        for m in models_to_pull:
            tk.Label(model_row, text=f"  {m}  ", bg=_SURFACE0, fg=_GREEN,
                     font=(_FONT, 10, "bold")).pack(side=tk.LEFT, padx=(6, 0))

        # Status line
        status_var = tk.StringVar(value="Checking installation…")
        tk.Label(prog, textvariable=status_var, bg=_CRUST, fg=_TEXT,
                 font=(_FONT, 10), anchor="w").pack(fill=tk.X, padx=20, pady=(10, 2))

        # Progress bar
        progress_var = tk.DoubleVar(value=0)
        progress_frame = tk.Frame(prog, bg=_SURFACE0, height=6)
        progress_frame.pack(fill=tk.X, padx=20, pady=(0, 8))
        progress_frame.pack_propagate(False)
        progress_bar = tk.Frame(progress_frame, bg=_ACCENT, height=6, width=0)
        progress_bar.place(x=0, y=0, relheight=1.0, relwidth=0.0)

        def _set_progress(pct: float):
            """Set progress bar 0.0–1.0 (thread-safe)."""
            try:
                prog.after(0, lambda: progress_bar.place_configure(relwidth=max(0.0, min(1.0, pct))))
            except Exception:
                pass

        # Log area with scrollbar
        log_frame = tk.Frame(prog, bg=_SURFACE0, highlightbackground=_SURFACE1,
                             highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 8))

        log_scroll = tk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                  bg=_SURFACE0, troughcolor=_MANTLE,
                                  activebackground=_SURFACE1, width=10,
                                  relief=tk.FLAT, borderwidth=0)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        log_text = tk.Text(
            log_frame, bg=_SURFACE0, fg=_SUBTEXT,
            font=(_FONT, 9), wrap=tk.WORD,
            relief=tk.FLAT, bd=0, padx=10, pady=8,
            insertbackground=_SUBTEXT, state=tk.DISABLED,
            highlightthickness=0,
            yscrollcommand=log_scroll.set,
        )
        log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll.config(command=log_text.yview)

        # Bottom button area (initially empty)
        btn_frame = tk.Frame(prog, bg=_CRUST)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 14))

        def _log(line: str, replace_last: bool = False):
            """Append a line to the log area (thread-safe).
            If replace_last=True, overwrite the last line instead."""
            def _do():
                try:
                    log_text.config(state=tk.NORMAL)
                    if replace_last:
                        # Delete the last line and replace it
                        log_text.delete("end-2l linestart", "end-1c")
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
            """Run a command and stream its stdout/stderr to the log.
            Strips ANSI escape codes and handles \\r progress updates."""
            import re as _re
            _ansi_re = _re.compile(r'\x1b\[[^a-zA-Z]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]')
            _pct_re = _re.compile(r'(\d+)%')
            CREATE_NO_WINDOW = 0x08000000
            _log(f"$ {' '.join(cmd)}")
            _is_progress = [False]  # tracks if last line was a progress line
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=CREATE_NO_WINDOW,
                )
                deadline = time.monotonic() + timeout_s
                buf = ""
                while True:
                    chunk = proc.stdout.read(512)
                    if not chunk:
                        break
                    buf += chunk
                    # Split on \r or \n (ollama uses \r for progress)
                    parts = _re.split(r'[\r\n]+', buf)
                    buf = parts[-1]  # keep incomplete tail
                    for part in parts[:-1]:
                        clean = _ansi_re.sub('', part).strip()
                        if not clean:
                            continue
                        m = _pct_re.search(clean)
                        if m:
                            pct = int(m.group(1)) / 100.0
                            _set_progress(pct)
                            # Format a nice progress line for display
                            _log(clean, replace_last=_is_progress[0])
                            _is_progress[0] = True
                        else:
                            _log(clean)
                            _is_progress[0] = False
                    if time.monotonic() > deadline:
                        proc.kill()
                        _log(f"⚠ {label} timed out")
                        return False
                # Flush remaining buffer
                if buf:
                    clean = _ansi_re.sub('', buf).strip()
                    if clean:
                        _log(clean)
                proc.wait(timeout=30)
                if proc.returncode == 0:
                    _set_progress(1.0)
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

            # 3. Pull models ─────────────────────────────────────────
            all_ok = True
            for idx, model in enumerate(models_to_pull, 1):
                _status(f"Pulling model '{model}' ({idx}/{len(models_to_pull)})…")
                _log(f"Downloading model: {model}")
                _log("This can take several minutes for large models.\n")
                ok = _stream_cmd(
                    ["ollama", "pull", model],
                    f"Model pull ({model})", timeout_s=3600,
                )
                if not ok:
                    all_ok = False
                _log("")

            if all_ok:
                _status("✓  Ready!")
                _log("All models are ready — select Ollama as provider and launch!")
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

    def _combo_row(
        self,
        parent: tk.Widget,
        label: str,
        key: str,
        font,
        options,
        width: int = 14,
        editable: bool = False,
    ):
        row = tk.Frame(parent, bg=_CARD)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, bg=_CARD, fg=_TEXT,
                 font=font, width=22, anchor="w").pack(side=tk.LEFT)

        if options and isinstance(options[0], tuple):
            label_to_value = {lbl: val for lbl, val in options}
            value_to_label = {val: lbl for lbl, val in options}
            current_value = self.data.get(key, options[0][1])
            var = tk.StringVar(value=value_to_label.get(current_value, current_value))
            values = [lbl for lbl, _ in options]
            self._choice_maps[key] = label_to_value
        else:
            var = tk.StringVar(value=self.data.get(key, options[0] if options else ""))
            values = options

        combo = ttk.Combobox(
            row, textvariable=var, values=values, state="normal" if editable else "readonly",
            width=width, font=font,
        )
        combo.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var
        self._ensure_combo_widget_registry()[key] = combo

        # Attach per-item dropdown tooltip for combos with long labels
        has_tuple_options = options and isinstance(options[0], tuple)
        if has_tuple_options:
            _DropdownItemTooltip(combo)

        # Add tooltip + download badge for Ollama model dropdowns
        is_ollama_model = key in ("OLLAMA_TEXT_MODEL", "OLLAMA_IMAGE_MODEL")
        if is_ollama_model:
            badge = tk.Label(row, text="", bg=_CARD, font=(_FONT, 9))
            badge.pack(side=tk.LEFT, padx=(6, 0))
            tip = _Tooltip(combo, var.get())

            def _on_select(_e=None, _var=var, _tip=tip, _badge=badge,
                           _l2v=label_to_value if options and isinstance(options[0], tuple) else None,
                           _pulled=self._ollama_pulled):
                display = _var.get()
                model_id = _l2v.get(display, display) if _l2v else display
                _tip.update_text(display)
                # Update download badge
                if model_id in _pulled:
                    _badge.config(text="  ✓ pulled  ", fg=_GREEN)
                else:
                    _badge.config(text="  ↓ not pulled  ", fg=_YELLOW)

            combo.bind("<<ComboboxSelected>>", _on_select)
            # Trigger initial state
            combo.after(100, _on_select)
        elif options and isinstance(options[0], tuple):
            # Generic tooltip for other combos with long labels
            tip = _Tooltip(combo, var.get())
            def _on_select_generic(_e=None, _var=var, _tip=tip):
                _tip.update_text(_var.get())
            combo.bind("<<ComboboxSelected>>", _on_select_generic)

    # ── Actions ────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        result = dict(self.data)
        for key, widget in self._entries.items():
            value = None
            if isinstance(widget, (tk.DoubleVar, tk.IntVar, tk.StringVar)):
                value = widget.get()
            elif isinstance(widget, tk.Entry):
                value = widget.get().strip()
            elif hasattr(widget, "get"):
                value = widget.get()

            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
            if key in self._choice_maps:
                result[key] = self._choice_maps[key].get(value, value)
            else:
                result[key] = value
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
