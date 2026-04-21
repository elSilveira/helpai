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
import tkinter as tk
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
)
from visibility import exclude_from_capture

logger = logging.getLogger(__name__)

# ── Theme constants ─────────────────────────────────────────────────────────
_SURFACE0 = "#313244"
_SURFACE1 = "#45475a"
_SURFACE2 = "#585b70"
_SUBTEXT = "#a6adc8"
_TEXT = OVERLAY_FG_COLOR        # #cdd6f4
_BASE = OVERLAY_BG_COLOR        # #1e1e2e
_MANTLE = "#181825"
_ACCENT = OVERLAY_ACCENT_COLOR  # #89b4fa
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_PEACH = "#fab387"
_PINK = "#f5c2e7"

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


def _apply_exclusion(window: tk.Tk | tk.Toplevel) -> None:
    """Exclude a tkinter window from screen capture."""
    try:
        window.update_idletasks()
        hwnd = int(window.wm_frame(), 16)
        exclude_from_capture(hwnd)
    except Exception:
        logger.exception("Could not apply capture exclusion.")


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
        y = widget.winfo_rooty() - 28
        tw.geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=text, bg=_SURFACE0, fg=_TEXT,
            font=(OVERLAY_FONT_FAMILY, 8), padx=6, pady=2,
        ).pack()
        tip["win"] = tw

    def _leave(e):
        if tip["win"]:
            tip["win"].destroy()
            tip["win"] = None

    widget.bind("<Enter>", _enter)
    widget.bind("<Leave>", _leave)


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
        self.root.configure(bg=_MANTLE)

        bar_w = 560
        bar_h = 36
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        bx = (screen_w - bar_w) // 2
        by = screen_h - bar_h - 10
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

        # ── Insight Panel ──────────────────────────────────────────────
        self._insight_panel: tk.Toplevel | None = None
        self._insight_visible = False
        self._saved_insight_geo: str | None = None
        self._insight_text: scrolledtext.ScrolledText | None = None

        # ── Settings Panel ─────────────────────────────────────────────
        self._settings_panel: tk.Toplevel | None = None
        self._settings_visible = False
        self._saved_settings_geo: str | None = None

        # ── Bar geometry save ──────────────────────────────────────────
        self._saved_bar_geo: str | None = None

        # ── Quick-input window ─────────────────────────────────────────
        self._quick_input_win: tk.Toplevel | None = None
        self._saved_quick_input_geo: str | None = None

        # ── Callbacks (set by main.py) ─────────────────────────────────
        self.on_quick_input_submit: callable = lambda text: None
        self.on_audio: callable = lambda: None
        self.on_screenshot: callable = lambda: None
        self.on_stop: callable = lambda: None
        self.on_quit: callable = lambda: None
        self.on_settings: callable = lambda: None
        self.on_clear_conversation: callable = lambda: None
        self.on_context_key_toggle: callable = lambda key, active: None

        # Context keys state
        self._context_keys: dict[str, str] = {}
        self._active_keys: set[str] = set()
        self._context_frame: tk.Frame | None = None
        self._context_buttons: dict[str, tk.Button] = {}

    # ═══════════════════════════════════════════════════════════════════
    #  Control Bar
    # ═══════════════════════════════════════════════════════════════════

    def _build_bar(self) -> None:
        f = self.root

        # Left: drag handle with app name
        self._bar_drag = tk.Label(
            f, text=f"  ≡  {APP_NAME}  ",
            bg=_ACCENT, fg=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"),
            cursor="fleur",
        )
        self._bar_drag.pack(side=tk.LEFT, fill=tk.Y)

        # Thin separator
        tk.Frame(f, bg=_SURFACE1, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=0)

        # Status
        self._status_label = tk.Label(
            f, text=" Ready ",
            bg=_MANTLE, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 8),
        )
        self._status_label.pack(side=tk.LEFT, padx=(6, 2))

        # ── Right-side buttons ─────────────────────────────────────────

        # Quit (far right)
        quit_btn = tk.Button(
            f, text="✕", command=self._do_quit,
            bg=_RED, fg=_MANTLE, activebackground="#eba0ac",
            activeforeground=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 10, "bold"),
            relief=tk.FLAT, cursor="hand2", padx=6, pady=0, bd=0,
        )
        quit_btn.pack(side=tk.RIGHT, padx=(1, 3))
        _add_tooltip(quit_btn, "Quit")

        # Settings
        settings_btn = tk.Button(
            f, text="⚙", command=self._do_settings,
            **{**_BTN_STYLE, "padx": 6, "font": (OVERLAY_FONT_FAMILY, 10)},
        )
        settings_btn.pack(side=tk.RIGHT, padx=1)
        _add_tooltip(settings_btn, "Settings")

        # Separator
        tk.Frame(f, bg=_SURFACE2, width=1).pack(side=tk.RIGHT, fill=tk.Y, pady=6, padx=2)

        # Quick Input
        input_btn = tk.Button(f, text="⌨", command=self.open_quick_input,
                              **{**_BTN_STYLE, "padx": 6, "font": (OVERLAY_FONT_FAMILY, 10)})
        input_btn.pack(side=tk.RIGHT, padx=1)
        _add_tooltip(input_btn, "Quick Input (Ctrl+Shift+Enter)")

        # Screenshot
        screen_btn = tk.Button(f, text="📸", command=lambda: self.on_screenshot(),
                               **{**_BTN_STYLE, "padx": 6})
        screen_btn.pack(side=tk.RIGHT, padx=1)
        _add_tooltip(screen_btn, "Screenshot Analysis (Ctrl+E)")

        # Audio analysis
        audio_btn = tk.Button(f, text="🎙", command=lambda: self.on_audio(),
                              **{**_BTN_STYLE, "padx": 6})
        audio_btn.pack(side=tk.RIGHT, padx=1)
        _add_tooltip(audio_btn, "Audio Analysis (Ctrl+D)")

        # Separator
        tk.Frame(f, bg=_SURFACE2, width=1).pack(side=tk.RIGHT, fill=tk.Y, pady=6, padx=2)

        # Toggle insight panel
        self._insight_btn = tk.Button(
            f, text="📋 Insight", command=self.toggle_insight,
            bg=_ACCENT, fg=_MANTLE, activebackground="#b4befe",
            activeforeground=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"),
            relief=tk.FLAT, cursor="hand2", padx=6, pady=2, bd=0,
        )
        self._insight_btn.pack(side=tk.RIGHT, padx=1)

        # Toggle conversation panel
        self._conv_btn = tk.Button(
            f, text="💬 Chat", command=self.toggle_conversation,
            bg=_GREEN, fg=_MANTLE, activebackground="#b5e8b0",
            activeforeground=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"),
            relief=tk.FLAT, cursor="hand2", padx=6, pady=2, bd=0,
        )
        self._conv_btn.pack(side=tk.RIGHT, padx=1)

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
        panel.configure(bg=_BASE)

        self.root.update_idletasks()
        pw = OVERLAY_WIDTH
        ph = OVERLAY_HEIGHT
        panel.geometry(f"{pw}x{ph}+{pos_x}+{pos_y}")
        panel.withdraw()

        # ── Title bar ──────────────────────────────────────────────────
        title_frame = tk.Frame(panel, bg=accent, height=28)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        # Coloured left pip
        tk.Frame(title_frame, bg=accent, width=4).pack(side=tk.LEFT, fill=tk.Y)

        title_label = tk.Label(
            title_frame, text=f"  {title}",
            bg=accent, fg=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), anchor="w",
        )
        title_label.pack(side=tk.LEFT, padx=2, pady=0)

        close_btn_w = tk.Label(
            title_frame, text=" ✕ ",
            bg=accent, fg=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), cursor="hand2",
        )
        close_btn_w.pack(side=tk.RIGHT, padx=(0, 2))

        clear_w = None
        if clear_btn:
            clear_w = tk.Label(
                title_frame, text=" 🗑 ",
                bg=accent, fg=_MANTLE,
                font=(OVERLAY_FONT_FAMILY, 9), cursor="hand2",
            )
            clear_w.pack(side=tk.RIGHT, padx=(0, 2))
            _add_tooltip(clear_w, "Clear transcript")

        _make_draggable(panel, title_frame, title_label)

        # ── Subtle divider ─────────────────────────────────────────────
        tk.Frame(panel, bg=_SURFACE1, height=1).pack(fill=tk.X)

        # ── Bottom grip ────────────────────────────────────────────────
        grip = tk.Frame(panel, bg=_SURFACE1, cursor="sb_v_double_arrow", height=5)
        grip.pack(fill=tk.X, side=tk.BOTTOM)
        grip_label = tk.Label(grip, text="⋯", bg=_SURFACE1, fg=_SURFACE2,
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
            padx=OVERLAY_PADDING,
            pady=OVERLAY_PADDING,
            insertbackground=_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="xterm",
            borderwidth=0,
            highlightthickness=0,
        )
        text_w.pack(fill=tk.BOTH, expand=True)
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
            self._conv_btn.config(text="💬 Chat")
        else:
            self._conv_panel.deiconify()
            self._conv_panel.lift()
            self._conv_panel.attributes("-topmost", True)
            self._conv_panel.after(50, lambda: _apply_exclusion(self._conv_panel))
            self._conv_visible = True
            self._conv_btn.config(text="💬 Hide")
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
        self.on_clear_conversation()

    def _write_conv(self, text: str) -> None:
        """Internal: write text into conversation ScrolledText."""
        if self._conv_text is None:
            return
        self._conv_text.config(state=tk.NORMAL)
        self._conv_text.delete("1.0", tk.END)
        self._conv_text.insert(tk.END, text)
        self._conv_text.config(state=tk.DISABLED)
        self._conv_text.see(tk.END)

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
        close_w.bind("<Button-1>", lambda _: self.toggle_insight())

    def toggle_insight(self) -> None:
        self._ensure_insight_panel()
        if self._insight_visible:
            self._insight_panel.withdraw()
            self._insight_visible = False
            self._insight_btn.config(text="📋 Insight")
        else:
            self._insight_panel.deiconify()
            self._insight_panel.lift()
            self._insight_panel.attributes("-topmost", True)
            self._insight_panel.after(50, lambda: _apply_exclusion(self._insight_panel))
            self._insight_visible = True
            self._insight_btn.config(text="📋 Hide")
        self.root.lift()

    # ═══════════════════════════════════════════════════════════════════
    #  Settings Panel (integrated overlay)
    # ═══════════════════════════════════════════════════════════════════

    def toggle_settings(self) -> None:
        """Toggle the inline settings panel."""
        if self._settings_panel and self._settings_panel.winfo_exists():
            if self._settings_visible:
                self._settings_panel.withdraw()
                self._settings_visible = False
                return
            self._settings_panel.deiconify()
            self._settings_panel.lift()
            self._settings_panel.attributes("-topmost", True)
            self._settings_visible = True
            self.root.lift()
            return

        self._build_settings_panel()

    def _build_settings_panel(self) -> None:
        """Build the settings panel as a Toplevel."""
        import settings as store
        from audio_capture import list_microphone_choices, list_speaker_choices
        from settings_ui import HotkeyEntry

        settings_data = store.load()
        entries: dict[str, tk.Widget] = {}
        choice_maps: dict[str, dict[str, str]] = {}

        panel = tk.Toplevel(self.root)
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.attributes("-alpha", INSIGHT_OVERLAY_OPACITY)
        panel.configure(bg=_BASE)

        pw, ph = 520, 590
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        px = (screen_w - pw) // 2
        py = (screen_h - ph) // 2
        panel.geometry(f"{pw}x{ph}+{px}+{py}")
        panel.after(50, lambda: _apply_exclusion(panel))

        self._settings_panel = panel
        self._settings_visible = True

        font = (OVERLAY_FONT_FAMILY, 10)
        font_bold = (OVERLAY_FONT_FAMILY, 10, "bold")

        # ── Title bar ──────────────────────────────────────────────────
        title_frame = tk.Frame(panel, bg=_PEACH, height=28)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        title_label = tk.Label(
            title_frame, text=f"  ⚙  Settings",
            bg=_PEACH, fg=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), anchor="w",
        )
        title_label.pack(side=tk.LEFT, padx=2)

        close_w = tk.Label(
            title_frame, text=" ✕ ",
            bg=_PEACH, fg=_MANTLE,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), cursor="hand2",
        )
        close_w.pack(side=tk.RIGHT, padx=(0, 2))
        close_w.bind("<Button-1>", lambda _: self.toggle_settings())

        _make_draggable(panel, title_frame, title_label)
        tk.Frame(panel, bg=_SURFACE1, height=1).pack(fill=tk.X)

        # ── Scrollable content ─────────────────────────────────────────
        canvas = tk.Canvas(panel, bg=_BASE, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(panel, orient=tk.VERTICAL, command=canvas.yview)
        content = tk.Frame(canvas, bg=_BASE)

        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=pw - 14)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)

        # Mouse wheel scroll
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Section helpers ────────────────────────────────────────────
        def _section(label: str, icon: str = ""):
            frm = tk.Frame(content, bg=_BASE)
            frm.pack(fill=tk.X, padx=14, pady=(14, 0))
            tk.Label(
                frm, text=f"{icon}  {label}" if icon else label,
                bg=_BASE, fg=_ACCENT,
                font=(OVERLAY_FONT_FAMILY, 9, "bold"), anchor="w",
            ).pack(side=tk.LEFT)
            tk.Frame(content, bg=_SURFACE1, height=1).pack(fill=tk.X, padx=14, pady=(3, 0))

        def _text_row(label: str, key: str, show: str | None = None):
            row = tk.Frame(content, bg=_BASE)
            row.pack(fill=tk.X, padx=14, pady=2)
            tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                     font=font, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(row, bg=_SURFACE0, fg=_TEXT,
                             insertbackground=_TEXT,
                             font=font, relief=tk.FLAT, width=22, show=show,
                             highlightthickness=1, highlightcolor=_ACCENT,
                             highlightbackground=_SURFACE1)
            entry.insert(0, settings_data.get(key, ""))
            entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
            entries[key] = entry

        def _hotkey_row(label: str, key: str):
            row = tk.Frame(content, bg=_BASE)
            row.pack(fill=tk.X, padx=14, pady=2)
            tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                     font=font, width=20, anchor="w").pack(side=tk.LEFT)
            entry = HotkeyEntry(row, bg=_SURFACE0, fg=_TEXT,
                                insertbackground=_TEXT,
                                font=font, relief=tk.FLAT, width=22,
                                highlightthickness=1, highlightcolor=_PINK,
                                highlightbackground=_SURFACE1)
            entry.insert(0, settings_data.get(key, ""))
            entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
            entries[key] = entry

        def _slider_row(label: str, key: str, lo: float, hi: float):
            row = tk.Frame(content, bg=_BASE)
            row.pack(fill=tk.X, padx=14, pady=2)
            tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                     font=font, width=20, anchor="w").pack(side=tk.LEFT)
            var = tk.DoubleVar(value=settings_data.get(key, lo))
            tk.Scale(row, from_=lo, to=hi, resolution=0.05, orient=tk.HORIZONTAL,
                     variable=var, bg=_BASE, fg=_TEXT,
                     troughcolor=_SURFACE0, highlightthickness=0,
                     font=(OVERLAY_FONT_FAMILY, 7), length=160,
                     activebackground=_ACCENT, sliderrelief=tk.FLAT,
                     ).pack(side=tk.LEFT, padx=(4, 0))
            entries[key] = var

        def _combo_row(label: str, key: str, options, width: int = 18):
            row = tk.Frame(content, bg=_BASE)
            row.pack(fill=tk.X, padx=14, pady=2)
            tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                     font=font, width=20, anchor="w").pack(side=tk.LEFT)
            from tkinter import ttk
            if options and isinstance(options[0], tuple):
                label_to_value = {label: value for label, value in options}
                value_to_label = {value: label for label, value in options}
                current_value = settings_data.get(key, options[0][1])
                var = tk.StringVar(value=value_to_label.get(current_value, options[0][0]))
                values = [label for label, _ in options]
                choice_maps[key] = label_to_value
            else:
                var = tk.StringVar(value=settings_data.get(key, options[0]))
                values = options
            combo = ttk.Combobox(row, textvariable=var, values=options,
                                 state="readonly", width=width, font=font)
            combo.configure(values=values)
            combo.pack(side=tk.LEFT, padx=(4, 0))
            entries[key] = var

        # ── Rows ───────────────────────────────────────────────────────
        _section("Hotkeys", "⌨")
        _hotkey_row("Audio Analysis", "HOTKEY_AUDIO_ANALYSIS")
        _hotkey_row("Screenshot", "HOTKEY_SCREENSHOT_FEEDBACK")
        _hotkey_row("Quick Input", "HOTKEY_QUICK_INPUT")

        _section("OpenAI API", "🔑")
        _text_row("API Key", "OPENAI_API_KEY", show="•")
        _text_row("Model", "OPENAI_MODEL")

        _section("Audio", "🎙")
        _combo_row("Audio Source", "AUDIO_SOURCE", ["other", "me", "both"])
        _combo_row("Microphone Device", "AUDIO_INPUT_DEVICE_ID", list_microphone_choices(), width=28)
        _combo_row("Loopback Output", "AUDIO_OUTPUT_DEVICE_ID", list_speaker_choices(), width=28)

        _section("Appearance", "🎨")
        _slider_row("Overlay Opacity", "INSIGHT_OVERLAY_OPACITY", 0.1, 1.0)

        # ── Buttons ────────────────────────────────────────────────────
        tk.Frame(content, bg=_BASE, height=8).pack(fill=tk.X)
        tk.Frame(content, bg=_SURFACE1, height=1).pack(fill=tk.X, padx=14)

        btn_frame = tk.Frame(content, bg=_BASE)
        btn_frame.pack(fill=tk.X, padx=14, pady=(10, 14))

        def _save():
            result = dict(settings_data)
            for k, widget in entries.items():
                if isinstance(widget, (tk.DoubleVar, tk.IntVar, tk.StringVar)):
                    if k in choice_maps:
                        result[k] = choice_maps[k].get(widget.get(), "")
                    else:
                        result[k] = widget.get()
                elif isinstance(widget, tk.Entry):
                    result[k] = widget.get().strip()
            store.save(result)
            self.set_insight("✅ Settings saved. Restart HelpAI to apply changes.")
            self.toggle_settings()

        tk.Button(
            btn_frame, text="💾  Save & Close", width=16,
            bg=_ACCENT, fg=_MANTLE,
            font=font_bold,
            activebackground="#b4befe", activeforeground=_MANTLE,
            relief=tk.FLAT, cursor="hand2", command=_save,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_frame, text="Cancel", width=10,
            bg=_SURFACE1, fg=_TEXT,
            font=font,
            activebackground=_SURFACE2, activeforeground=_TEXT,
            relief=tk.FLAT, cursor="hand2",
            command=self.toggle_settings,
        ).pack(side=tk.RIGHT)

        # Version info
        tk.Label(
            btn_frame, text=f"v{APP_VERSION}",
            bg=_BASE, fg=_SURFACE2,
            font=(OVERLAY_FONT_FAMILY, 8),
        ).pack(side=tk.LEFT)

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
        for tw in (self._insight_text, self._conv_text):
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
        win.configure(bg=_BASE)

        w, h = 460, 110
        sx = self.root.winfo_x()
        sy = self.root.winfo_y() - h - 6
        win.geometry(f"{w}x{h}+{sx}+{sy}")
        _apply_exclusion(win)

        # Title bar
        tf = tk.Frame(win, bg=_ACCENT, height=24)
        tf.pack(fill=tk.X)
        tf.pack_propagate(False)
        tl = tk.Label(tf, text="  ⌨  Ask anything…",
                      bg=_ACCENT, fg=_MANTLE,
                      font=(OVERLAY_FONT_FAMILY, 8, "bold"), anchor="w")
        tl.pack(side=tk.LEFT, padx=2)
        cb = tk.Label(tf, text=" ✕ ", bg=_ACCENT, fg=_MANTLE,
                      font=(OVERLAY_FONT_FAMILY, 9, "bold"), cursor="hand2")
        cb.pack(side=tk.RIGHT)
        cb.bind("<Button-1>", lambda _: self._close_quick_input(win))
        _make_draggable(win, tf, tl)

        tk.Frame(win, bg=_SURFACE1, height=1).pack(fill=tk.X)

        tk.Label(
            win, text="Type your question, then press Enter:",
            bg=_BASE, fg=_SUBTEXT,
            font=(OVERLAY_FONT_FAMILY, 8),
        ).pack(padx=10, pady=(6, 2), anchor="w")

        entry = tk.Entry(
            win, bg=_SURFACE0, fg=_TEXT,
            insertbackground=_TEXT,
            font=(OVERLAY_FONT_FAMILY, OVERLAY_FONT_SIZE),
            relief=tk.FLAT,
            highlightthickness=1, highlightcolor=_ACCENT,
            highlightbackground=_SURFACE1,
        )
        entry.pack(fill=tk.X, padx=10, pady=(2, 8), ipady=3)
        entry.focus_force()

        def submit(_e=None):
            text = entry.get().strip()
            if text:
                self.on_quick_input_submit(text)
            self._close_quick_input(win)

        entry.bind("<Return>", submit)
        entry.bind("<Escape>", lambda _: self._close_quick_input(win))
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
    #  Public API
    # ═══════════════════════════════════════════════════════════════════

    def set_status(self, text: str) -> None:
        self._status_label.config(text=f" {text} ")
        self.root.update_idletasks()

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
        self._conv_text.see(tk.END)

    def set_insight(self, text: str) -> None:
        """Replace insight panel content."""
        self._ensure_insight_panel()
        if not self._insight_visible:
            self.toggle_insight()
        self.root.deiconify()
        if self._insight_text is None:
            return
        self._insight_text.config(state=tk.NORMAL)
        self._insight_text.delete("1.0", tk.END)
        self._insight_text.insert(tk.END, text)
        self._insight_text.config(state=tk.DISABLED)
        self._insight_text.see("1.0")
        self._auto_expand_insight()
        logger.debug("Insight panel updated (%d chars).", len(text))

    def set_content(self, text: str) -> None:
        self.set_insight(text)

    def append_content(self, text: str) -> None:
        self._ensure_insight_panel()
        if not self._insight_visible:
            self.toggle_insight()
        self._insight_text.config(state=tk.NORMAL)
        self._insight_text.insert(tk.END, "\n" + text)
        self._insight_text.config(state=tk.DISABLED)
        self._insight_text.see("1.0")

    def _auto_expand_insight(self) -> None:
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

    def show(self) -> None:
        if self._saved_bar_geo:
            self.root.geometry(self._saved_bar_geo)
        self.root.deiconify()
        for panel, visible, saved_geo in [
            (self._conv_panel, self._conv_visible, self._saved_conv_geo),
            (self._insight_panel, self._insight_visible, self._saved_insight_geo),
            (self._settings_panel, self._settings_visible, self._saved_settings_geo),
        ]:
            if panel and visible:
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
        if self._conv_panel and self._conv_visible:
            try:
                self._saved_conv_geo = self._conv_panel.geometry()
            except Exception:
                pass
            self._conv_panel.withdraw()
        if self._insight_panel and self._insight_visible:
            try:
                self._saved_insight_geo = self._insight_panel.geometry()
            except Exception:
                pass
            self._insight_panel.withdraw()
        if self._settings_panel and self._settings_visible:
            try:
                self._saved_settings_geo = self._settings_panel.geometry()
            except Exception:
                pass
            self._settings_panel.withdraw()
        if self._quick_input_win and self._quick_input_win.winfo_exists():
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
