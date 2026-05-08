"""
Overlay UI module.

Multi-window layout:
  1. **Control Bar** — slim, modern strip at the bottom of the screen.
  2. **Conversation Panel** — live transcript with context key toggles.
  3. **Insight Panel** — LLM analysis results (auto-expands).
  4. **Settings Panel** — integrated settings (replaces separate window).

All windows are excluded from screen-capture APIs (WDA_EXCLUDEFROMCAPTURE).
"""

import logging
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import scrolledtext

from config import (
    APP_NAME,
    APP_VERSION,
    INSIGHT_OVERLAY_OPACITY,
    OVERLAY_ACCENT_COLOR,
    OVERLAY_BG_COLOR,
    OVERLAY_FG_COLOR,
    OVERLAY_FONT_FAMILY,
    OVERLAY_FONT_SIZE,
    OVERLAY_HEIGHT,
    OVERLAY_PADDING,
    OVERLAY_WIDTH,
    STEALTH_MODE,
)
from visibility import exclude_from_capture, include_in_capture

logger = logging.getLogger(__name__)

# ── Theme constants ─────────────────────────────────────────────────────────
_SURFACE0 = "#313244"
_SURFACE1 = "#45475a"
_SURFACE2 = "#585b70"
_OVERLAY0 = "#6c7086"
_SUBTEXT = "#a6adc8"
_TEXT = OVERLAY_FG_COLOR        # #cdd6f4
_BASE = OVERLAY_BG_COLOR        # #1e1e2e
_MANTLE = "#181825"
_CRUST  = "#11111b"
_ACCENT = OVERLAY_ACCENT_COLOR  # #89b4fa
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_PEACH = "#fab387"
_PINK = "#f5c2e7"
_MAUVE = "#cba6f7"
_TEAL = "#94e2d5"
_YELLOW = "#f9e2af"

_BTN_STYLE = dict(
    bg=_SURFACE0,
    fg=_TEXT,
    activebackground=_SURFACE1,
    activeforeground=_TEXT,
    font=(OVERLAY_FONT_FAMILY, 9, "bold"),
    relief=tk.FLAT,
    cursor="hand2",
    padx=8,
    pady=2,
    bd=0,
)


@dataclass(frozen=True)
class InsightContent:
    insights: str
    code: str

    @property
    def has_code(self) -> bool:
        return bool(self.code.strip())


_FENCED_CODE_RE = re.compile(r"```[^\n`]*\n?(.*?)(?:```|$)", re.DOTALL)


def split_insight_content(text: str) -> InsightContent:
    """Split fenced code blocks from explanatory insight text."""
    code_blocks: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1).strip())
        return "\n\n"

    insights = _FENCED_CODE_RE.sub(_replace, text)
    insights = re.sub(r"\n{3,}", "\n\n", insights).strip()
    code = "\n\n".join(block for block in code_blocks if block)
    return InsightContent(insights=insights, code=code)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_draggable(window: tk.Tk | tk.Toplevel, *handles: tk.Widget) -> None:
    """Make *window* draggable by any of *handles*."""
    state = {"x": 0, "y": 0}

    def on_press(e):
        state["x"] = e.x
        state["y"] = e.y

    def on_drag(e):
        x = window.winfo_x() + (e.x - state["x"])
        y = window.winfo_y() + (e.y - state["y"])
        window.geometry(f"+{x}+{y}")

    for w in handles:
        w.bind("<ButtonPress-1>", on_press)
        w.bind("<B1-Motion>", on_drag)


# ── Stealth state (module-level, toggled at runtime) ───────────────────────
_stealth_enabled: bool = STEALTH_MODE
_tracked_windows: list = []  # all tk windows that should be stealth-managed


def _apply_exclusion(window: tk.Tk | tk.Toplevel) -> None:
    """Conditionally exclude a tkinter window from screen capture.

    When stealth is on, applies WDA_EXCLUDEFROMCAPTURE.
    Always tracks the window so stealth can be toggled later.
    """
    if window not in _tracked_windows:
        _tracked_windows.append(window)
    if not _stealth_enabled:
        return
    try:
        window.update_idletasks()
        hwnd = int(window.wm_frame(), 16)
        exclude_from_capture(hwnd)
    except Exception:
        logger.exception("Could not apply capture exclusion.")


def _set_stealth_all(enabled: bool) -> None:
    """Apply or remove capture exclusion on every tracked window."""
    global _stealth_enabled
    _stealth_enabled = enabled
    for win in list(_tracked_windows):
        try:
            if not win.winfo_exists():
                _tracked_windows.remove(win)
                continue
            win.update_idletasks()
            hwnd = int(win.wm_frame(), 16)
            if enabled:
                exclude_from_capture(hwnd)
            else:
                include_in_capture(hwnd)
        except Exception:
            logger.debug("Stealth toggle failed for a window.", exc_info=True)


def _add_tooltip(widget: tk.Widget, text: str) -> None:
    """Add a hover tooltip to a widget."""
    tip = {"win": None}

    def _enter(e):
        if tip["win"]:
            return
        tw = tk.Toplevel(widget)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        x = widget.winfo_rootx() + widget.winfo_width() // 2 - 40
        y = widget.winfo_rooty() - 30
        tw.geometry(f"+{x}+{y}")
        tw.configure(bg=_SURFACE1)
        tk.Label(
            tw, text=text, bg=_SURFACE0, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 7), padx=8, pady=3,
        ).pack(padx=1, pady=1)
        tip["win"] = tw

    def _leave(e):
        if tip["win"]:
            tip["win"].destroy()
            tip["win"] = None

    widget.bind("<Enter>", _enter)
    widget.bind("<Leave>", _leave)


# ═══════════════════════════════════════════════════════════════════════════
#  ClosingSplash
# ═══════════════════════════════════════════════════════════════════════════


class ClosingSplash:
    """Small overlay shown while the app is shutting down."""

    def __init__(self, parent: "tk.Tk | None" = None) -> None:
        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                            highlightthickness=1)

        w, h = 300, 90
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        # Top accent line
        tk.Frame(self.root, bg=_RED, height=2).pack(fill=tk.X, side=tk.TOP)

        inner = tk.Frame(self.root, bg=_CRUST)
        inner.pack(fill=tk.BOTH, expand=True, padx=24, pady=14)

        tk.Label(
            inner,
            text="Closing HelpAI\u2026",
            bg=_CRUST,
            fg=_TEXT,
            font=(OVERLAY_FONT_FAMILY, 12, "bold"),
        ).pack(anchor="w")

        tk.Label(
            inner,
            text="Releasing resources",
            bg=_CRUST,
            fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 9),
        ).pack(anchor="w", pady=(4, 0))

        # Animated progress bar
        bar_frame = tk.Frame(inner, bg=_SURFACE0, height=3)
        bar_frame.pack(fill=tk.X, pady=(8, 0))
        bar_frame.pack_propagate(False)
        self._bar = tk.Frame(bar_frame, bg=_RED, width=0)
        self._bar.pack(side=tk.LEFT, fill=tk.Y)

        self._frame = 0
        self._after_id: str | None = None
        _apply_exclusion(self.root)
        self._animate()

    def _animate(self) -> None:
        self._frame = (self._frame + 1) % 40
        try:
            bar_w = self._bar.master.winfo_width()
            if bar_w > 1:
                pos = abs((self._frame % 40) - 20) / 20.0
                w = max(20, int(bar_w * 0.35))
                x = int((bar_w - w) * pos)
                self._bar.place(x=x, y=0, width=w, relheight=1.0)
        except Exception:
            pass
        self._after_id = self.root.after(50, self._animate)

    def run(self) -> None:
        try:
            self.root.mainloop()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  LoadingSplash
# ═══════════════════════════════════════════════════════════════════════════


class LoadingSplash:
    """Splash/loading window shown during app initialization."""

    _DOT_FRAMES = ("●○○○○", "○●○○○", "○○●○○", "○○○●○", "○○○○●")

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                            highlightthickness=1)

        w, h = 380, 160
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        # Top accent line
        tk.Frame(self.root, bg=_ACCENT, height=2).pack(fill=tk.X, side=tk.TOP)

        inner = tk.Frame(self.root, bg=_CRUST)
        inner.pack(fill=tk.BOTH, expand=True, padx=28, pady=18)

        # App name + version row
        hdr = tk.Frame(inner, bg=_CRUST)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text=APP_NAME,
            bg=_CRUST,
            fg=_TEXT,
            font=(OVERLAY_FONT_FAMILY, 14, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            hdr,
            text=f"  v{APP_VERSION}",
            bg=_CRUST,
            fg=_OVERLAY0,
            font=(OVERLAY_FONT_FAMILY, 9),
        ).pack(side=tk.LEFT, pady=(3, 0))

        # Status line
        self._status_var = tk.StringVar(value="Starting\u2026")
        tk.Label(
            inner,
            textvariable=self._status_var,
            bg=_CRUST,
            fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 9),
            wraplength=320,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(10, 0))

        # Progress bar
        bar_frame = tk.Frame(inner, bg=_SURFACE0, height=4)
        bar_frame.pack(fill=tk.X, pady=(12, 0))
        bar_frame.pack_propagate(False)
        self._progress_bar = tk.Frame(bar_frame, bg=_ACCENT, width=0)
        self._progress_bar.pack(side=tk.LEFT, fill=tk.Y)

        self._dot_frame = 0
        self._after_id: str | None = None
        self._animate()
        _apply_exclusion(self.root)

    def _animate(self) -> None:
        self._dot_frame = (self._dot_frame + 1) % 60
        # Animate the progress bar back and forth
        try:
            bar_w = self._progress_bar.master.winfo_width()
            if bar_w > 1:
                pos = abs((self._dot_frame % 40) - 20) / 20.0
                w = max(20, int(bar_w * 0.3))
                x = int((bar_w - w) * pos)
                self._progress_bar.place(x=x, y=0, width=w, relheight=1.0)
        except Exception:
            pass
        self._after_id = self.root.after(50, self._animate)

    def set_status(self, text: str) -> None:
        """Thread-safe status line update."""
        try:
            self.root.after(0, self._status_var.set, text)
        except Exception:
            pass

    def close(self) -> None:
        """Thread-safe close — cancels animation then destroys the splash window."""
        def _destroy():
            if self._after_id:
                try:
                    self.root.after_cancel(self._after_id)
                except Exception:
                    pass
            self.root.destroy()
        try:
            self.root.after(0, _destroy)
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════
#  OverlayApp
# ═══════════════════════════════════════════════════════════════════════════


class OverlayApp:
    """Multi-window overlay: control bar + conversation + insight + settings panels."""

    def __init__(self) -> None:
        # ── Root = Control Bar ─────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", INSIGHT_OVERLAY_OPACITY)
        self.root.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                            highlightthickness=1)

        bar_w = 620
        bar_h = 40
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        bx = (screen_w - bar_w) // 2
        by = screen_h - bar_h - int(screen_h * 0.05) - 10
        self.root.geometry(f"{bar_w}x{bar_h}+{bx}+{by}")

        self._build_bar()
        _apply_exclusion(self.root)
        _make_draggable(self.root, self._bar_drag, self._status_label)

        # ── Conversation Panel ─────────────────────────────────────────
        self._conv_panel: tk.Toplevel | None = None
        self._conv_visible = False
        self._saved_conv_geo: str | None = None
        self._conv_text: scrolledtext.ScrolledText | None = None
        self._pending_conv: str | None = None  # buffer when panel hidden
        self._conv_meter_frame: tk.Frame | None = None
        self._audio_level_rows: dict[str, dict[str, object]] = {}
        self._conv_user_scrolled = False   # True when user scrolls manually
        self._conv_last_len = 0            # track streaming (content growing)

        # ── Insight Panel ──────────────────────────────────────────────
        self._insight_panel: tk.Toplevel | None = None
        self._insight_visible = False
        self._saved_insight_geo: str | None = None
        self._insight_text: scrolledtext.ScrolledText | None = None
        self._insight_raw_text = ""
        self._insight_size_locked = False  # True after first auto-expand
        self._insight_user_scrolled = False  # True when user scrolls manually
        self._insight_last_len = 0  # track streaming (content growing)

        # ── Code Panel ───────────────────────────────────────────────
        self._code_panel: tk.Toplevel | None = None
        self._code_visible = False
        self._saved_code_geo: str | None = None
        self._code_text: scrolledtext.ScrolledText | None = None
        self._code_user_scrolled = False
        self._code_size_locked = False

        # ── Settings Panel ─────────────────────────────────────────────
        self._settings_panel: tk.Toplevel | None = None
        self._settings_visible = False
        self._saved_settings_geo: str | None = None

        # ── Bar geometry save ──────────────────────────────────────────
        self._saved_bar_geo: str | None = None

        # ── Quick-input window ─────────────────────────────────────────
        self._quick_input_win: tk.Toplevel | None = None
        self._saved_quick_input_geo: str | None = None

        # ── Loading animation state ────────────────────────────────────
        self._loading_active = False
        self._loading_frame = 0
        self._loading_title = ""
        self._loading_after_id = None

        # ── Callbacks (set by main.py) ─────────────────────────────────
        self.on_quick_input_submit: callable = lambda text: None
        self.on_audio: callable = lambda: None
        self.on_screenshot: callable = lambda: None
        self.on_stop: callable = lambda: None
        self.on_quit: callable = lambda: None
        self.on_settings: callable = lambda: None
        self.on_clear_conversation: callable = lambda: None
        self.on_context_key_toggle: callable = lambda key, active: None
        self.on_auto_whisper_toggle: callable = lambda enabled: None

        # Context keys state
        self._context_keys: dict[str, str] = {}
        self._active_keys: set[str] = set()
        self._context_frame: tk.Frame | None = None
        self._context_buttons: dict[str, tk.Button] = {}
        self._auto_whisper_enabled = False
        self._auto_whisper_btn: tk.Label | None = None

    # ═══════════════════════════════════════════════════════════════════
    #  Control Bar
    # ═══════════════════════════════════════════════════════════════════

    def _build_bar(self) -> None:
        f = self.root

        # Left: drag handle — subtle branded grip
        self._bar_drag = tk.Label(
            f, text="  ⬡  ",
            bg=_CRUST, fg=_ACCENT,
            font=(OVERLAY_FONT_FAMILY, 11),
            cursor="fleur",
        )
        self._bar_drag.pack(side=tk.LEFT, fill=tk.Y, padx=(2, 0))

        # ── Right-side buttons (packed first = rightmost) ─────────────

        # Quit — subtle X, red on hover
        quit_btn = tk.Label(
            f, text=" ✕ ",
            bg=_CRUST, fg=_SURFACE2,
            font=(OVERLAY_FONT_FAMILY, 10), cursor="hand2",
        )
        quit_btn.pack(side=tk.RIGHT, padx=(0, 4))
        quit_btn.bind("<Button-1>", lambda _: self._do_quit())
        quit_btn.bind("<Enter>", lambda e: quit_btn.config(fg=_RED))
        quit_btn.bind("<Leave>", lambda e: quit_btn.config(fg=_SURFACE2))
        _add_tooltip(quit_btn, "Quit")

        # Settings — gear
        settings_btn = tk.Label(
            f, text=" ⚙ ",
            bg=_CRUST, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 10), cursor="hand2",
        )
        settings_btn.pack(side=tk.RIGHT, padx=1)
        settings_btn.bind("<Button-1>", lambda _: self._do_settings())
        settings_btn.bind("<Enter>", lambda e: settings_btn.config(fg=_TEXT))
        settings_btn.bind("<Leave>", lambda e: settings_btn.config(fg=_SUBTEXT))
        _add_tooltip(settings_btn, "Settings")

        # Stealth mode toggle — eye icon
        self._stealth_btn = tk.Label(
            f, text=" 👁 " if not _stealth_enabled else " 🔒 ",
            bg=_SURFACE0 if _stealth_enabled else _CRUST,
            fg=_GREEN if _stealth_enabled else _SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 10), cursor="hand2",
        )
        self._stealth_btn.pack(side=tk.RIGHT, padx=1)
        self._stealth_btn.bind("<Button-1>", lambda _: self.toggle_stealth())
        self._stealth_btn.bind("<Enter>", lambda e: self._stealth_btn.config(
            bg=_SURFACE0))
        self._stealth_btn.bind("<Leave>", lambda e: self._stealth_btn.config(
            bg=_SURFACE0 if _stealth_enabled else _CRUST))
        _add_tooltip(self._stealth_btn, "Stealth Mode")

        # Thin separator
        tk.Frame(f, bg=_SURFACE1, width=1).pack(side=tk.RIGHT, fill=tk.Y, pady=8, padx=3)

        # ── Left-side buttons (packed first = leftmost) ───────────────

        # Toggle conversation panel
        self._conv_btn = self._bar_icon_btn(f, "💬", _GREEN, "Chat")
        self._conv_btn.pack(side=tk.LEFT, padx=1)
        self._conv_btn.bind("<Button-1>", lambda _: self.toggle_conversation())

        # Toggle insight panel
        self._insight_btn = self._bar_icon_btn(f, "📋", _ACCENT, "Insight")
        self._insight_btn.pack(side=tk.LEFT, padx=1)
        self._insight_btn.bind("<Button-1>", lambda _: self.toggle_insight())

        # Thin separator
        tk.Frame(f, bg=_SURFACE1, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=8, padx=3)

        # Audio — mic icon
        audio_btn = self._bar_icon_btn(f, "🎙", _SUBTEXT, "Audio Analysis (Ctrl+D)")
        audio_btn.pack(side=tk.LEFT, padx=1)
        audio_btn.bind("<Button-1>", lambda _: self.on_audio())

        # Auto Whisper runtime toggle
        self._auto_whisper_btn = tk.Label(
            f, text=" AW ",
            bg=_CRUST, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 9), cursor="hand2",
        )
        self._auto_whisper_btn.pack(side=tk.LEFT, padx=1)
        self._auto_whisper_btn.bind("<Button-1>", lambda _: self.toggle_auto_whisper())
        self._auto_whisper_btn.bind("<Enter>", lambda _: self._auto_whisper_btn.config(bg=_SURFACE0))
        self._auto_whisper_btn.bind("<Leave>", lambda _: self._refresh_auto_whisper_button())
        _add_tooltip(self._auto_whisper_btn, "Auto Whisper")

        # Screenshot — camera icon
        screen_btn = self._bar_icon_btn(f, "📷", _SUBTEXT, "Screenshot Analysis (Ctrl+E)")
        screen_btn.pack(side=tk.LEFT, padx=1)
        screen_btn.bind("<Button-1>", lambda _: self.on_screenshot())

        # Quick Input — keyboard icon
        input_btn = self._bar_icon_btn(f, "⌨", _SUBTEXT, "Quick Input (Ctrl+Shift+Enter)")
        input_btn.pack(side=tk.LEFT, padx=1)
        input_btn.bind("<Button-1>", lambda _: self.open_quick_input())

        # ── Status label fills remaining center space ─────────────────
        self._status_label = tk.Label(
            f, text=" Ready ",
            bg=_CRUST, fg=_OVERLAY0,
            font=(OVERLAY_FONT_FAMILY, 8),
            anchor=tk.CENTER,
        )
        self._status_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _bar_icon_btn(self, parent, icon: str, fg_color: str, tooltip: str) -> tk.Label:
        """Create a minimal icon button for the control bar."""
        btn = tk.Label(
            parent, text=f" {icon} ",
            bg=_CRUST, fg=fg_color,
            font=(OVERLAY_FONT_FAMILY, 10), cursor="hand2",
        )
        btn.bind("<Enter>", lambda e, b=btn: b.config(fg=_TEXT, bg=_SURFACE0))
        btn.bind("<Leave>", lambda e, b=btn: b.config(fg=fg_color, bg=_CRUST))
        _add_tooltip(btn, tooltip)
        return btn

    # ═══════════════════════════════════════════════════════════════════
    #  Panel Factory
    # ═══════════════════════════════════════════════════════════════════

    def _create_panel(self, title: str, accent: str, pos_x: int, pos_y: int,
                      clear_btn: bool = False) -> tuple:
        """Create a panel Toplevel and return (panel, text_widget, close_w, clear_w)."""
        panel = tk.Toplevel(self.root)
        panel.title(title)
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.attributes("-alpha", INSIGHT_OVERLAY_OPACITY)
        panel.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                        highlightthickness=1)

        self.root.update_idletasks()
        pw = OVERLAY_WIDTH
        ph = OVERLAY_HEIGHT
        panel.geometry(f"{pw}x{ph}+{pos_x}+{pos_y}")
        panel.withdraw()

        # ── Title bar ──────────────────────────────────────────────────
        title_frame = tk.Frame(panel, bg=_CRUST, height=30)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        # Accent pip on the left
        tk.Frame(title_frame, bg=accent, width=3).pack(side=tk.LEFT, fill=tk.Y)

        title_label = tk.Label(
            title_frame, text=f"  {title}",
            bg=_CRUST, fg=_TEXT,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), anchor="w",
        )
        title_label.pack(side=tk.LEFT, padx=2, pady=0)

        close_btn_w = tk.Label(
            title_frame, text=" ✕ ",
            bg=_CRUST, fg=_SURFACE2,
            font=(OVERLAY_FONT_FAMILY, 9), cursor="hand2",
        )
        close_btn_w.pack(side=tk.RIGHT, padx=(0, 4))
        close_btn_w.bind("<Enter>", lambda e: close_btn_w.config(fg=_RED))
        close_btn_w.bind("<Leave>", lambda e: close_btn_w.config(fg=_SURFACE2))

        clear_w = None
        if clear_btn:
            clear_w = tk.Label(
                title_frame, text=" 🗑 ",
                bg=_CRUST, fg=_SURFACE2,
                font=(OVERLAY_FONT_FAMILY, 9), cursor="hand2",
            )
            clear_w.pack(side=tk.RIGHT, padx=(0, 2))
            clear_w.bind("<Enter>", lambda e: clear_w.config(fg=_PEACH))
            clear_w.bind("<Leave>", lambda e: clear_w.config(fg=_SURFACE2))
            _add_tooltip(clear_w, "Clear transcript")

        _make_draggable(panel, title_frame, title_label)

        # ── Subtle divider ─────────────────────────────────────────────
        tk.Frame(panel, bg=_SURFACE1, height=1).pack(fill=tk.X)

        # ── Bottom grip ────────────────────────────────────────────────
        grip = tk.Frame(panel, bg=_CRUST, cursor="sb_v_double_arrow", height=6)
        grip.pack(fill=tk.X, side=tk.BOTTOM)
        grip_label = tk.Label(grip, text="⋯", bg=_CRUST, fg=_SURFACE1,
                              font=(OVERLAY_FONT_FAMILY, 6), cursor="size_nw_se")
        grip_label.pack(side=tk.RIGHT, padx=4)

        # ── Text area ──────────────────────────────────────────────────
        text_w = scrolledtext.ScrolledText(
            panel,
            wrap=tk.WORD,
            bg=_BASE,
            fg=_TEXT,
            selectbackground=_SURFACE2,
            selectforeground="#f5e0dc",
            font=(OVERLAY_FONT_FAMILY, OVERLAY_FONT_SIZE),
            padx=OVERLAY_PADDING + 4,
            pady=OVERLAY_PADDING,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="xterm",
            borderwidth=0,
            highlightthickness=0,
            spacing1=2,   # extra space above each line
            spacing3=2,   # extra space below each line
        )
        text_w.pack(fill=tk.BOTH, expand=True)

        # Style the scrollbar to match the theme
        try:
            text_w.vbar.configure(
                bg=_SURFACE0,
                troughcolor=_MANTLE,
                activebackground=_SURFACE1,
                relief=tk.FLAT,
                borderwidth=0,
                width=12,
                elementborderwidth=0,
            )
        except Exception:
            pass
        text_w.bind("<ButtonPress-1>", lambda e: self._sel_start_on(text_w, e))
        text_w.bind("<B1-Motion>", lambda e: self._sel_move_on(text_w, e))
        text_w.bind("<ButtonRelease-1>", lambda e: self._sel_end_on(text_w))

        self._add_resize_bottom(grip, panel)
        self._add_resize_corner(grip_label, panel)
        self._add_edge_resize(panel)

        return panel, text_w, close_btn_w, clear_w

    # ═══════════════════════════════════════════════════════════════════
    #  Conversation Panel
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_conv_panel(self) -> None:
        if self._conv_panel and self._conv_panel.winfo_exists():
            return
        panel, text_w, close_w, clear_w = self._create_panel(
            "Conversation", _GREEN,
            pos_x=10, pos_y=40, clear_btn=True,
        )
        self._conv_panel = panel
        self._conv_text = text_w
        close_w.bind("<Button-1>", lambda _: self.toggle_conversation())
        if clear_w:
            clear_w.bind("<Button-1>", lambda _: self.clear_conversation())

        # Detect manual scrolling (same approach as insight panel)
        text_w.bind("<MouseWheel>", self._on_conv_scroll)
        text_w.bind("<Button-4>", self._on_conv_scroll)   # Linux scroll up
        text_w.bind("<Button-5>", self._on_conv_scroll)   # Linux scroll down

        self._conv_meter_frame = tk.Frame(panel, bg=_MANTLE)
        self._conv_meter_frame.pack(fill=tk.X, padx=0, before=text_w)
        tk.Frame(self._conv_meter_frame, bg=_SURFACE1, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        self._audio_level_rows = {
            "output": self._build_audio_meter_row(self._conv_meter_frame, "🔊 THEM"),
            "input": self._build_audio_meter_row(self._conv_meter_frame, "🎙 YOU"),
        }

        # Context keys bar
        self._context_frame = tk.Frame(panel, bg=_MANTLE)
        self._context_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self._context_buttons = {}
        self._rebuild_context_keys()

    def toggle_conversation(self) -> None:
        self._ensure_conv_panel()
        if self._conv_visible:
            self._conv_panel.withdraw()
            self._conv_visible = False
            # panel closed — no button state change needed
        else:
            self._conv_panel.deiconify()
            self._conv_panel.lift()
            self._conv_panel.attributes("-topmost", True)
            self._conv_panel.after(50, lambda: _apply_exclusion(self._conv_panel))
            self._conv_visible = True
            # panel opened — no button state change needed
            # Flush buffered conversation text
            if self._pending_conv is not None:
                self._write_conv(self._pending_conv)
                self._pending_conv = None
        self.root.lift()

    def clear_conversation(self) -> None:
        if self._conv_text:
            self._conv_text.config(state=tk.NORMAL)
            self._conv_text.delete("1.0", tk.END)
            self._conv_text.config(state=tk.DISABLED)
        self._pending_conv = None
        self._conv_user_scrolled = False
        self._conv_last_len = 0
        self.on_clear_conversation()

    def _is_conv_near_bottom(self) -> bool:
        """Return True if conversation text is scrolled to (or near) the bottom."""
        try:
            return self._conv_text.yview()[1] >= 0.95
        except Exception:
            return True

    def _on_conv_scroll(self, *_args):
        """Called when user scrolls the conversation panel manually."""
        if not self._is_conv_near_bottom():
            self._conv_user_scrolled = True
        else:
            self._conv_user_scrolled = False

    def _write_conv(self, text: str) -> None:
        """Internal: write text into conversation ScrolledText.

        Uses a diff-based approach: if the new text starts with the same
        content, only the changed tail is appended.  Respects user scroll
        position — only auto-scrolls when the user is near the bottom.
        """
        if self._conv_text is None:
            return

        new_len = len(text)
        is_streaming = new_len > self._conv_last_len and self._conv_last_len > 0
        self._conv_last_len = new_len

        self._conv_text.config(state=tk.NORMAL)
        existing = self._conv_text.get("1.0", "end-1c")

        if is_streaming and text.startswith(existing) and existing:
            # Monotonic growth — just append the tail
            tail = text[len(existing):]
            if tail:
                self._conv_text.insert(tk.END, tail)
        elif existing.startswith(text) and len(existing) > len(text):
            # Text got shorter — full rewrite, preserve scroll
            ypos = self._conv_text.yview()
            self._conv_text.delete("1.0", tk.END)
            self._conv_text.insert(tk.END, text)
            if self._conv_user_scrolled:
                self._conv_text.yview_moveto(ypos[0])
        else:
            ypos = self._conv_text.yview()
            self._conv_text.delete("1.0", tk.END)
            self._conv_text.insert(tk.END, text)
            if self._conv_user_scrolled:
                self._conv_text.yview_moveto(ypos[0])

        self._conv_text.config(state=tk.DISABLED)

        # Only auto-scroll if user hasn't scrolled away
        if not self._conv_user_scrolled:
            self._conv_text.see(tk.END)

    def _build_audio_meter_row(self, parent: tk.Frame, title: str) -> dict[str, object]:
        """Create one conversation-panel audio meter row."""
        row = tk.Frame(parent, bg=_MANTLE)

        header = tk.Frame(row, bg=_MANTLE)
        header.pack(fill=tk.X, padx=10)

        title_label = tk.Label(
            header,
            text=title,
            bg=_MANTLE,
            fg=_TEXT,
            font=(OVERLAY_FONT_FAMILY, 8, "bold"),
            anchor="w",
        )
        title_label.pack(side=tk.LEFT)

        device_label = tk.Label(
            header,
            text="",
            bg=_MANTLE,
            fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 7),
            anchor="e",
        )
        device_label.pack(side=tk.RIGHT)

        meter = tk.Canvas(
            row,
            height=6,
            bg=_SURFACE0,
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        fill_id = meter.create_rectangle(0, 0, 0, 6, fill=_ACCENT, width=0)
        meter.pack(fill=tk.X, pady=(2, 0), padx=10)

        return {
            "frame": row,
            "title": title_label,
            "device": device_label,
            "meter": meter,
            "fill": fill_id,
            "visible": False,
            "pady": None,
            "device_text": None,
            "title_dimmed": None,
            "fill_width": None,
            "fill_color": None,
        }

    def _meter_color(self, level: float, active: bool) -> str:
        if not active and level < 0.04:
            return _SURFACE1
        if level >= 0.85:
            return _RED
        if level >= 0.55:
            return _PEACH
        if level >= 0.22:
            return _GREEN
        return _ACCENT

    def set_audio_levels(self, levels: dict[str, dict[str, object]]) -> None:
        """Update the conversation-panel audio meters for the active devices."""
        self._ensure_conv_panel()
        if not self._conv_meter_frame:
            return

        visible_streams = [key for key in ("output", "input") if levels.get(key)]
        visible_positions = {key: index for index, key in enumerate(visible_streams)}

        for key in ("output", "input"):
            row = self._audio_level_rows.get(key)
            if not row:
                continue

            position = visible_positions.get(key)
            should_show = position is not None
            if not should_show:
                if row["visible"]:
                    row["frame"].pack_forget()
                    row["visible"] = False
                    row["pady"] = None
                continue

            pady = ((10, 0) if position == 0 else (6, 0))
            if not row["visible"]:
                row["frame"].pack(fill=tk.X, pady=pady)
                row["visible"] = True
                row["pady"] = pady
            elif row["pady"] != pady:
                row["frame"].pack_configure(pady=pady)
                row["pady"] = pady

            info = levels[key]
            device_name = str(info.get("device_name") or ("Microphone" if key == "input" else "System Audio"))
            if len(device_name) > 36:
                device_name = f"{device_name[:33]}..."
            if row["device_text"] != device_name:
                row["device"].config(text=device_name)
                row["device_text"] = device_name

            level = max(0.0, min(1.0, float(info.get("level", 0.0))))
            active = bool(info.get("active", False))
            title_dimmed = not (active or level > 0.06)
            if row["title_dimmed"] != title_dimmed:
                row["title"].config(fg=_SUBTEXT if title_dimmed else _TEXT)
                row["title_dimmed"] = title_dimmed

            meter = row["meter"]
            width = meter.winfo_width()
            if width <= 1:
                width = max(1, meter.winfo_reqwidth())
            fill_width = int(width * level)
            if row["fill_width"] != fill_width:
                meter.coords(row["fill"], 0, 0, fill_width, 6)
                row["fill_width"] = fill_width

            fill_color = self._meter_color(level, active)
            if row["fill_color"] != fill_color:
                meter.itemconfig(row["fill"], fill=fill_color)
                row["fill_color"] = fill_color

    # ═══════════════════════════════════════════════════════════════════
    #  Context Keys
    # ═══════════════════════════════════════════════════════════════════

    def set_context_keys(self, keys: dict[str, str], active: set[str]) -> None:
        self._context_keys = keys
        self._active_keys = active
        self._rebuild_context_keys()

    def _rebuild_context_keys(self) -> None:
        if not self._context_frame:
            return
        for w in self._context_frame.winfo_children():
            w.destroy()
        self._context_buttons.clear()

        if not self._context_keys:
            self._context_frame.pack_forget()
            return

        self._context_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Separator line
        tk.Frame(self._context_frame, bg=_SURFACE1, height=1).pack(fill=tk.X)

        row = tk.Frame(self._context_frame, bg=_MANTLE)
        row.pack(fill=tk.X, padx=6, pady=3)

        tk.Label(
            row, text="Context:",
            bg=_MANTLE, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 8, "bold"), anchor="w",
        ).pack(side=tk.LEFT, padx=(0, 4))

        for key, summary in self._context_keys.items():
            is_active = key in self._active_keys
            btn = tk.Button(
                row,
                text=key.replace("_", " "),
                font=(OVERLAY_FONT_FAMILY, 7, "bold"),
                relief=tk.FLAT,
                cursor="hand2",
                padx=5, pady=1, bd=0,
                bg=_GREEN if is_active else _SURFACE1,
                fg=_MANTLE if is_active else _SUBTEXT,
                activebackground="#b5e8b0" if is_active else _SURFACE2,
                activeforeground=_MANTLE if is_active else _TEXT,
            )
            btn.pack(side=tk.LEFT, padx=1)

            def _enter(e, b=btn, s=summary):
                b._tip = tk.Toplevel(b)
                b._tip.overrideredirect(True)
                b._tip.attributes("-topmost", True)
                x = b.winfo_rootx()
                y = b.winfo_rooty() - 30
                b._tip.geometry(f"+{x}+{y}")
                tk.Label(
                    b._tip, text=s[:120],
                    bg=_SURFACE0, fg=_TEXT,
                    font=(OVERLAY_FONT_FAMILY, 8),
                    padx=6, pady=3, wraplength=300,
                ).pack()

            def _leave(e, b=btn):
                if hasattr(b, "_tip") and b._tip:
                    b._tip.destroy()
                    b._tip = None

            btn.bind("<Enter>", _enter)
            btn.bind("<Leave>", _leave)

            def _toggle(k=key, b=btn):
                if k in self._active_keys:
                    self._active_keys.discard(k)
                    b.config(bg=_SURFACE1, fg=_SUBTEXT,
                             activebackground=_SURFACE2, activeforeground=_TEXT)
                else:
                    self._active_keys.add(k)
                    b.config(bg=_GREEN, fg=_MANTLE,
                             activebackground="#b5e8b0", activeforeground=_MANTLE)
                self.on_context_key_toggle(k, k in self._active_keys)

            btn.config(command=_toggle)
            self._context_buttons[key] = btn

    # ═══════════════════════════════════════════════════════════════════
    #  Insight Panel
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_insight_panel(self) -> None:
        if self._insight_panel and self._insight_panel.winfo_exists():
            return
        screen_w = self.root.winfo_screenwidth()
        insight_x = (screen_w - OVERLAY_WIDTH) // 2
        panel, text_w, close_w, _ = self._create_panel(
            "Insight", _ACCENT,
            pos_x=insight_x, pos_y=40, clear_btn=False,
        )
        self._insight_panel = panel
        self._insight_text = text_w
        self._insight_size_locked = False
        self._insight_user_scrolled = False
        self._insight_last_len = 0
        close_w.bind("<Button-1>", lambda _: self.toggle_insight())
        # Detect manual scrolling
        text_w.bind("<MouseWheel>", self._on_insight_scroll)
        text_w.bind("<Button-4>", self._on_insight_scroll)   # Linux scroll up
        text_w.bind("<Button-5>", self._on_insight_scroll)   # Linux scroll down

    def toggle_insight(self) -> None:
        self._ensure_insight_panel()
        if self._insight_visible:
            self._insight_panel.withdraw()
            self._insight_visible = False
            # panel closed — no button state change needed
        else:
            self._insight_panel.deiconify()
            self._insight_panel.lift()
            self._insight_panel.attributes("-topmost", True)
            self._insight_panel.after(50, lambda: _apply_exclusion(self._insight_panel))
            self._insight_visible = True
            # panel opened — no button state change needed
        self.root.lift()

    # ═══════════════════════════════════════════════════════════════════
    #  Settings Panel — delegates to settings_ui.SettingsWindow
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_code_panel(self) -> None:
        if self._code_panel and self._code_panel.winfo_exists():
            return
        screen_w = self.root.winfo_screenwidth()
        insight_x = (screen_w - OVERLAY_WIDTH) // 2
        code_x = min(insight_x + OVERLAY_WIDTH + 12, max(10, screen_w - OVERLAY_WIDTH - 10))
        panel, text_w, close_w, _ = self._create_panel(
            "Code", _TEAL,
            pos_x=code_x, pos_y=40, clear_btn=False,
        )
        text_w.config(wrap=tk.NONE, font=("Consolas", OVERLAY_FONT_SIZE))
        self._code_panel = panel
        self._code_text = text_w
        self._code_visible = False
        self._code_user_scrolled = False
        self._code_size_locked = False
        close_w.bind("<Button-1>", lambda _: self.toggle_code())
        text_w.bind("<MouseWheel>", self._on_code_scroll)
        text_w.bind("<Button-4>", self._on_code_scroll)
        text_w.bind("<Button-5>", self._on_code_scroll)

    def toggle_code(self) -> None:
        self._ensure_code_panel()
        if self._code_visible:
            self._code_panel.withdraw()
            self._code_visible = False
        else:
            self._code_panel.deiconify()
            self._code_panel.lift()
            self._code_panel.attributes("-topmost", True)
            self._code_panel.after(50, lambda: _apply_exclusion(self._code_panel))
            self._code_visible = True
        self.root.lift()

    def _show_code_panel(self) -> None:
        self._ensure_code_panel()
        if not self._code_visible:
            self._code_panel.deiconify()
            self._code_visible = True
        self._code_panel.lift()
        self._code_panel.attributes("-topmost", True)
        self._code_panel.after(50, lambda: _apply_exclusion(self._code_panel))

    def _hide_code_panel(self) -> None:
        if self._panel_alive(self._code_panel) and self._code_visible:
            self._code_panel.withdraw()
            self._code_visible = False

    def _is_code_near_bottom(self) -> bool:
        try:
            return self._code_text.yview()[1] >= 0.95 if self._code_text else True
        except Exception:
            return True

    def _on_code_scroll(self, *_args):
        self._code_user_scrolled = not self._is_code_near_bottom()

    def _set_code(self, code: str, *, is_streaming: bool) -> None:
        if not code.strip():
            self._hide_code_panel()
            return
        self._show_code_panel()
        if self._code_text is None:
            return
        self._write_text_widget(
            self._code_text,
            code,
            user_scrolled=self._code_user_scrolled,
        )
        if not is_streaming:
            self._code_text.see("1.0")
        self._auto_expand_code()

    def _auto_expand_code(self) -> None:
        if self._code_size_locked:
            return
        if not self._code_panel or not self._code_text:
            return
        self._code_panel.update_idletasks()
        line_count = int(self._code_text.index("end-1c").split(".")[0])
        line_px = int(OVERLAY_FONT_SIZE * 1.8)
        needed_h = 40 + OVERLAY_PADDING * 2 + (line_count * line_px)
        screen_h = self._code_panel.winfo_screenheight()
        max_h = int(screen_h * 0.80)
        current_h = self._code_panel.winfo_height()
        new_h = max(current_h, OVERLAY_HEIGHT, min(needed_h, max_h))
        cur_w = self._code_panel.winfo_width()
        cur_x = self._code_panel.winfo_x()
        cur_y = self._code_panel.winfo_y()
        self._code_panel.geometry(f"{cur_w}x{new_h}+{cur_x}+{cur_y}")
        self._code_size_locked = True

    def toggle_settings(self) -> None:
        """Open/close the shared settings window."""
        if self._settings_panel and self._settings_panel.winfo_exists():
            if self._settings_visible:
                self._settings_panel.destroy()
                self._settings_panel = None
                self._settings_visible = False
                return

        self._build_settings_panel()

    def _build_settings_panel(self) -> None:
        """Reuse the SettingsWindow component as a child of the overlay."""
        from settings_ui import SettingsWindow

        def _on_close():
            """Called when SettingsWindow saves — just close it."""
            self._settings_panel = None
            self._settings_visible = False
            self.set_insight("✅ Settings saved. Restart HelpAI to apply changes.")

        win = SettingsWindow.__new__(SettingsWindow)
        win.on_save_and_launch = None
        win.data = __import__("settings").load()
        win._choice_maps = {}
        win._entries = {}
        win._nav_buttons = {}
        win._panels = {}
        win._active_section = "llm"
        win._ollama_pulled = set()
        win._mic_choices = []
        win._spk_choices = []

        # Build as Toplevel under our root
        win.root = tk.Toplevel(self.root)
        win.root.title("Settings")
        win.root.overrideredirect(True)
        win.root.attributes("-topmost", True)
        win.root.configure(bg="#1e1e2e")
        win.root.resizable(False, False)

        w, h = 620, 540
        sx = (win.root.winfo_screenwidth() - w) // 2
        sy = (win.root.winfo_screenheight() - h) // 2
        win.root.geometry(f"{w}x{h}+{sx}+{sy}")

        win._build()

        # Override save to notify overlay
        _orig_save = win._save
        def _save_and_notify():
            _orig_save()
            _on_close()

        _orig_save_launch = win._save_and_launch
        def _save_launch_notify():
            data = win._collect()
            __import__("settings").save(data)
            win.root.destroy()
            _on_close()

        win._save = _save_and_notify
        win._save_and_launch = _save_launch_notify

        win.root.after(50, lambda: _apply_exclusion(win.root))

        self._settings_panel = win.root
        self._settings_visible = True

        self.root.lift()

    # ═══════════════════════════════════════════════════════════════════
    #  Text selection helpers
    # ═══════════════════════════════════════════════════════════════════

    def _sel_start_on(self, text_w, event):
        text_w.config(state=tk.NORMAL)
        text_w.mark_set(tk.INSERT, f"@{event.x},{event.y}")
        text_w.tag_remove(tk.SEL, "1.0", tk.END)
        text_w.config(state=tk.DISABLED)

    def _sel_move_on(self, text_w, event):
        text_w.config(state=tk.NORMAL)
        text_w.mark_set(tk.INSERT, f"@{event.x},{event.y}")
        try:
            text_w.tag_add(tk.SEL, "sel_anchor", tk.INSERT)
        except tk.TclError:
            pass
        text_w.config(state=tk.DISABLED)

    def _sel_end_on(self, text_w):
        text_w.config(state=tk.DISABLED)

    def get_selection(self) -> str | None:
        for tw in (self._insight_text, self._code_text, self._conv_text):
            if tw is None:
                continue
            try:
                return tw.get(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                continue
        return None

    # ═══════════════════════════════════════════════════════════════════
    #  Resize helpers
    # ═══════════════════════════════════════════════════════════════════

    def _add_resize_bottom(self, grip: tk.Widget, window: tk.Toplevel) -> None:
        state: dict = {}

        def on_press(e):
            state["y"] = e.y_root
            state["h"] = window.winfo_height()

        def on_drag(e):
            new_h = max(150, state["h"] + (e.y_root - state["y"]))
            window.geometry(f"{window.winfo_width()}x{new_h}")

        grip.bind("<ButtonPress-1>", on_press)
        grip.bind("<B1-Motion>", on_drag)

    def _add_resize_corner(self, widget: tk.Widget, window: tk.Toplevel) -> None:
        state: dict = {}

        def on_press(e):
            state["x"] = e.x_root
            state["y"] = e.y_root
            state["w"] = window.winfo_width()
            state["h"] = window.winfo_height()

        def on_drag(e):
            new_w = max(300, state["w"] + (e.x_root - state["x"]))
            new_h = max(150, state["h"] + (e.y_root - state["y"]))
            window.geometry(f"{new_w}x{new_h}")

        widget.bind("<ButtonPress-1>", on_press)
        widget.bind("<B1-Motion>", on_drag)

    def _add_edge_resize(self, window: tk.Toplevel) -> None:
        EDGE = 6
        state: dict = {}

        def _hit_zone(e):
            w = window.winfo_width()
            h = window.winfo_height()
            return (e.x <= EDGE, e.x >= w - EDGE, e.y <= EDGE, e.y >= h - EDGE)

        def on_motion(e):
            left, right, top, bottom = _hit_zone(e)
            if (right and bottom) or (left and top):
                window.config(cursor="size_nw_se")
            elif (left and bottom) or (right and top):
                window.config(cursor="size_ne_sw")
            elif right or left:
                window.config(cursor="sb_h_double_arrow")
            elif top or bottom:
                window.config(cursor="sb_v_double_arrow")
            else:
                window.config(cursor="")

        def on_press(e):
            left, right, top, bottom = _hit_zone(e)
            if not (left or right or top or bottom):
                state.clear()
                return
            state.update(x=e.x_root, y=e.y_root, w=window.winfo_width(),
                         h=window.winfo_height(), wx=window.winfo_x(),
                         wy=window.winfo_y(), left=left, right=right,
                         top=top, bottom=bottom)

        def on_drag(e):
            if not state:
                return
            dx = e.x_root - state["x"]
            dy = e.y_root - state["y"]
            x, y = state["wx"], state["wy"]
            w, h = state["w"], state["h"]

            if state.get("right"):
                w = max(300, state["w"] + dx)
            elif state.get("left"):
                new_w = max(300, state["w"] - dx)
                x = state["wx"] + (state["w"] - new_w)
                w = new_w
            if state.get("bottom"):
                h = max(150, state["h"] + dy)
            elif state.get("top"):
                new_h = max(150, state["h"] - dy)
                y = state["wy"] + (state["h"] - new_h)
                h = new_h

            window.geometry(f"{w}x{h}+{x}+{y}")

        def on_leave(_e):
            if not state:
                window.config(cursor="")

        window.bind("<Motion>", on_motion)
        window.bind("<ButtonPress-1>", on_press, add="+")
        window.bind("<B1-Motion>", on_drag, add="+")
        window.bind("<Leave>", on_leave)

    # ═══════════════════════════════════════════════════════════════════
    #  Quick Input Dialog
    # ═══════════════════════════════════════════════════════════════════

    def open_quick_input(self) -> None:
        if self._quick_input_win and self._quick_input_win.winfo_exists():
            self._quick_input_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", INSIGHT_OVERLAY_OPACITY)
        win.configure(bg=_CRUST, highlightbackground=_SURFACE1,
                      highlightthickness=1)

        w, h = 620, 160
        sx = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        sy = self.root.winfo_y() - h - 8
        win.geometry(f"{w}x{h}+{sx}+{sy}")
        _apply_exclusion(win)

        # ── Title bar ─────────────────────────────────────────────────
        tf = tk.Frame(win, bg=_CRUST, height=26)
        tf.pack(fill=tk.X)
        tf.pack_propagate(False)

        # Accent pip
        tk.Frame(tf, bg=_ACCENT, width=3).pack(side=tk.LEFT, fill=tk.Y)

        tl = tk.Label(tf, text="  Ask anything",
                      bg=_CRUST, fg=_TEXT,
                      font=(OVERLAY_FONT_FAMILY, 8, "bold"), anchor="w")
        tl.pack(side=tk.LEFT, padx=2)

        cb = tk.Label(tf, text=" ✕ ", bg=_CRUST, fg=_SURFACE2,
                      font=(OVERLAY_FONT_FAMILY, 9), cursor="hand2")
        cb.pack(side=tk.RIGHT, padx=(0, 4))
        cb.bind("<Button-1>", lambda _: self._close_quick_input(win))
        cb.bind("<Enter>", lambda e: cb.config(fg=_RED))
        cb.bind("<Leave>", lambda e: cb.config(fg=_SURFACE2))
        _make_draggable(win, tf, tl)

        tk.Frame(win, bg=_SURFACE1, height=1).pack(fill=tk.X)

        # ── Input area (multiline Text) ───────────────────────────────
        body = tk.Frame(win, bg=_BASE)
        body.pack(fill=tk.BOTH, expand=True)

        text_input = tk.Text(
            body, bg=_BASE, fg=_TEXT,
            insertbackground=_ACCENT,
            font=(OVERLAY_FONT_FAMILY, OVERLAY_FONT_SIZE),
            relief=tk.FLAT,
            highlightthickness=0,
            borderwidth=0,
            wrap=tk.WORD,
            undo=True,
            spacing1=1, spacing3=1,
        )
        text_input.pack(fill=tk.BOTH, expand=True, padx=14, pady=(10, 4))
        text_input.focus_force()

        # ── Footer row (hint + send button) ───────────────────────────
        footer = tk.Frame(win, bg=_CRUST)
        footer.pack(fill=tk.X)
        tk.Frame(footer, bg=_SURFACE1, height=1).pack(fill=tk.X)

        hint = tk.Label(footer, text="  Ctrl+Enter to send",
                        bg=_CRUST, fg=_OVERLAY0,
                        font=(OVERLAY_FONT_FAMILY, 7))
        hint.pack(side=tk.LEFT, padx=6, pady=4)

        send_btn = tk.Label(
            footer, text=" Send ➜ ",
            bg=_ACCENT, fg=_CRUST,
            font=(OVERLAY_FONT_FAMILY, 8, "bold"),
            cursor="hand2", padx=8, pady=2,
        )
        send_btn.pack(side=tk.RIGHT, padx=6, pady=4)
        send_btn.bind("<Enter>", lambda e: send_btn.config(bg=_MAUVE))
        send_btn.bind("<Leave>", lambda e: send_btn.config(bg=_ACCENT))

        def submit(_e=None):
            text = text_input.get("1.0", tk.END).strip()
            if text:
                self.on_quick_input_submit(text)
            self._close_quick_input(win)
            return "break"

        send_btn.bind("<Button-1>", lambda _: submit())
        text_input.bind("<Control-Return>", submit)
        text_input.bind("<Escape>", lambda _: self._close_quick_input(win))
        self._quick_input_win = win

    def _close_quick_input(self, win):
        win.destroy()
        self._quick_input_win = None

    # ═══════════════════════════════════════════════════════════════════
    #  Action handlers
    # ═══════════════════════════════════════════════════════════════════

    def _do_stop(self) -> None:
        self.on_stop()
        self.set_status("Capture stopped")

    def _do_quit(self) -> None:
        self.on_quit()

    def _do_settings(self) -> None:
        self.toggle_settings()

    # ═══════════════════════════════════════════════════════════════════
    #  Stealth Mode
    # ═══════════════════════════════════════════════════════════════════

    def toggle_stealth(self) -> None:
        """Toggle stealth mode on/off and persist the setting."""
        self.set_stealth(not _stealth_enabled)

    def set_stealth(self, enabled: bool) -> None:
        """Enable or disable stealth mode for all overlay windows."""
        _set_stealth_all(enabled)
        # Update toolbar button appearance
        if enabled:
            self._stealth_btn.config(text=" 🔒 ", fg=_GREEN, bg=_SURFACE0)
            self.set_status("Stealth ON — hidden from capture")
        else:
            self._stealth_btn.config(text=" 👁 ", fg=_SUBTEXT, bg=_CRUST)
            self.set_status("Stealth OFF — visible in capture")
        # Persist to settings
        import settings as _settings_mod
        data = _settings_mod.load()
        data["STEALTH_MODE"] = enabled
        _settings_mod.save(data)
        logger.info("Stealth mode %s.", "enabled" if enabled else "disabled")

    @property
    def stealth_enabled(self) -> bool:
        return _stealth_enabled

    # ═══════════════════════════════════════════════════════════════════
    #  Public API
    # ═══════════════════════════════════════════════════════════════════

    def set_status(self, text: str) -> None:
        self._status_label.config(text=f" {text} ")
        self.root.update_idletasks()

    def _refresh_auto_whisper_button(self) -> None:
        if not self._auto_whisper_btn:
            return
        self._auto_whisper_btn.config(
            bg=_SURFACE0 if self._auto_whisper_enabled else _CRUST,
            fg=_GREEN if self._auto_whisper_enabled else _SUBTEXT,
        )

    def set_auto_whisper_enabled(self, enabled: bool) -> None:
        self._auto_whisper_enabled = enabled
        self._refresh_auto_whisper_button()

    def toggle_auto_whisper(self) -> None:
        self.set_auto_whisper_enabled(not self._auto_whisper_enabled)
        self.on_auto_whisper_toggle(self._auto_whisper_enabled)

    # ── Loading animation ──────────────────────────────────────────────────

    _SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def begin_loading(self, title: str = "Working") -> None:
        """Start a spinner animation in the status bar."""
        self._loading_title = title
        self._loading_frame = 0
        self._loading_active = True
        self._tick_loading()

    def _tick_loading(self) -> None:
        if not getattr(self, "_loading_active", False):
            return
        frame = self._SPINNER_FRAMES[self._loading_frame % len(self._SPINNER_FRAMES)]
        self._status_label.config(text=f" {frame} {self._loading_title}… ")
        self._loading_frame += 1
        self._loading_after_id = self.root.after(80, self._tick_loading)

    def end_loading(self) -> None:
        """Stop the spinner animation."""
        self._loading_active = False
        after_id = getattr(self, "_loading_after_id", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._loading_after_id = None

    def set_conversation(self, text: str) -> None:
        """Replace conversation panel content."""
        self._ensure_conv_panel()
        if not self._conv_visible:
            self._pending_conv = text  # buffer for when panel opens
            return
        self._write_conv(text)

    def append_conversation(self, text: str) -> None:
        self._ensure_conv_panel()
        if not self._conv_visible:
            if self._pending_conv is None:
                self._pending_conv = ""
            self._pending_conv += text
            return
        if self._conv_text is None:
            return
        self._conv_text.config(state=tk.NORMAL)
        self._conv_text.insert(tk.END, text)
        self._conv_text.config(state=tk.DISABLED)
        if not self._conv_user_scrolled:
            self._conv_text.see(tk.END)

    def _is_insight_near_bottom(self) -> bool:
        """Return True if insight text is scrolled to (or near) the bottom."""
        try:
            return self._insight_text.yview()[1] >= 0.95
        except Exception:
            return True

    def _on_insight_scroll(self, *_args):
        """Called when user scrolls the insight panel manually."""
        if not self._is_insight_near_bottom():
            self._insight_user_scrolled = True
        else:
            self._insight_user_scrolled = False

    def set_insight(self, text: str) -> None:
        """Replace insight panel content."""
        self._ensure_insight_panel()
        if not self._insight_visible:
            self.toggle_insight()
        self.root.deiconify()
        if self._insight_text is None:
            return

        self._insight_raw_text = text
        content = split_insight_content(text)
        new_len = len(text)
        is_streaming = new_len > self._insight_last_len and self._insight_last_len > 0
        self._insight_last_len = new_len

        self._write_text_widget(
            self._insight_text,
            content.insights or text,
            user_scrolled=self._insight_user_scrolled,
        )
        self._set_code(content.code, is_streaming=is_streaming)

        if not is_streaming:
            self._insight_text.see("1.0")
            self._insight_last_len = new_len

        self._auto_expand_insight()
        logger.debug("Insight panel updated (%d chars).", len(text))

    def _write_text_widget(
        self,
        widget: scrolledtext.ScrolledText,
        text: str,
        *,
        user_scrolled: bool,
    ) -> None:
        ypos = widget.yview() if user_scrolled else None
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state=tk.DISABLED)
        if ypos is not None:
            widget.yview_moveto(ypos[0])
        elif not user_scrolled:
            widget.see(tk.END)

    def set_content(self, text: str) -> None:
        self.set_insight(text)

    def append_content(self, text: str) -> None:
        current = self._insight_raw_text
        self.set_insight(f"{current}\n{text}" if current else text)

    def _auto_expand_insight(self) -> None:
        """Expand the insight panel height on first show only; never move it after."""
        if self._insight_size_locked:
            return
        if not self._insight_panel or not self._insight_text:
            return
        self._insight_panel.update_idletasks()
        line_count = int(self._insight_text.index("end-1c").split(".")[0])
        line_px = int(OVERLAY_FONT_SIZE * 1.8)
        needed_h = 40 + OVERLAY_PADDING * 2 + (line_count * line_px)

        screen_h = self._insight_panel.winfo_screenheight()
        max_h = int(screen_h * 0.80)
        current_h = self._insight_panel.winfo_height()
        new_h = max(current_h, OVERLAY_HEIGHT, min(needed_h, max_h))
        cur_w = self._insight_panel.winfo_width()
        cur_x = self._insight_panel.winfo_x()
        cur_y = self._insight_panel.winfo_y()
        self._insight_panel.geometry(f"{cur_w}x{new_h}+{cur_x}+{cur_y}")
        self._insight_size_locked = True

    def _panel_alive(self, panel) -> bool:
        """Return True if *panel* is a valid, non-destroyed Toplevel."""
        try:
            return panel is not None and panel.winfo_exists()
        except Exception:
            return False

    def show(self) -> None:
        if self._saved_bar_geo:
            self.root.geometry(self._saved_bar_geo)
        self.root.deiconify()
        for panel, visible, saved_geo in [
            (self._conv_panel, self._conv_visible, self._saved_conv_geo),
            (self._insight_panel, self._insight_visible, self._saved_insight_geo),
            (self._code_panel, self._code_visible, self._saved_code_geo),
            (self._settings_panel, self._settings_visible, self._saved_settings_geo),
        ]:
            if self._panel_alive(panel) and visible:
                if saved_geo:
                    panel.geometry(saved_geo)
                panel.deiconify()
                panel.lift()
                panel.attributes("-topmost", True)
        if self._quick_input_win and self._quick_input_win.winfo_exists():
            if self._saved_quick_input_geo:
                self._quick_input_win.geometry(self._saved_quick_input_geo)
            self._quick_input_win.deiconify()
            self._quick_input_win.lift()
            self._quick_input_win.attributes("-topmost", True)
        self.root.lift()

    def hide(self) -> None:
        try:
            self._saved_bar_geo = self.root.geometry()
        except Exception:
            pass
        if self._panel_alive(self._conv_panel) and self._conv_visible:
            try:
                self._saved_conv_geo = self._conv_panel.geometry()
            except Exception:
                pass
            self._conv_panel.withdraw()
        if self._panel_alive(self._insight_panel) and self._insight_visible:
            try:
                self._saved_insight_geo = self._insight_panel.geometry()
            except Exception:
                pass
            self._insight_panel.withdraw()
        if self._panel_alive(self._code_panel) and self._code_visible:
            try:
                self._saved_code_geo = self._code_panel.geometry()
            except Exception:
                pass
            self._code_panel.withdraw()
        if self._panel_alive(self._settings_panel) and self._settings_visible:
            try:
                self._saved_settings_geo = self._settings_panel.geometry()
            except Exception:
                pass
            self._settings_panel.withdraw()
        if self._panel_alive(self._quick_input_win):
            try:
                self._saved_quick_input_geo = self._quick_input_win.geometry()
            except Exception:
                pass
            self._quick_input_win.withdraw()
        self.root.withdraw()

    def toggle(self) -> None:
        if self.root.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def run(self) -> None:
        self.root.mainloop()

    def schedule(self, func: callable, *args) -> None:
        self.root.after(0, func, *args)
