"""
Settings UI — lets users configure hotkeys and preferences via a GUI.

Each hotkey field captures the actual key combination when the user
clicks it and presses the desired shortcut.
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

_SURFACE0 = "#313244"
_SURFACE1 = "#45475a"
_SURFACE2 = "#585b70"
_SUBTEXT = "#a6adc8"
_TEXT = OVERLAY_FG_COLOR
_BASE = OVERLAY_BG_COLOR
_MANTLE = "#181825"
_ACCENT = OVERLAY_ACCENT_COLOR
_PEACH = "#fab387"
_PINK = "#f5c2e7"


def _make_draggable(window: tk.Tk | tk.Toplevel, *handles: tk.Widget) -> None:
    """Make *window* draggable by any of *handles*."""
    state = {"x": 0, "y": 0}

    def on_press(event):
        state["x"] = event.x
        state["y"] = event.y

    def on_drag(event):
        x = window.winfo_x() + (event.x - state["x"])
        y = window.winfo_y() + (event.y - state["y"])
        window.geometry(f"+{x}+{y}")

    for handle in handles:
        handle.bind("<ButtonPress-1>", on_press)
        handle.bind("<B1-Motion>", on_drag)


class HotkeyEntry(tk.Entry):
    """An Entry widget that captures a keyboard shortcut on focus."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._hook = None
        self.bind("<FocusIn>", self._start_capture)
        self.bind("<FocusOut>", self._stop_capture)

    def _start_capture(self, _event=None):
        self.config(bg="#45475a", fg="#f5c2e7")
        self.delete(0, tk.END)
        self.insert(0, "Press shortcut…")
        self._hook = kb.hook(self._on_key, suppress=False)

    def _stop_capture(self, _event=None):
        if self._hook is not None:
            kb.unhook(self._hook)
            self._hook = None
        self.config(bg="#313244", fg=OVERLAY_FG_COLOR)
        if self.get() == "Press shortcut…":
            self.delete(0, tk.END)

    def _on_key(self, event: kb.KeyboardEvent):
        if event.event_type != kb.KEY_DOWN:
            return
        parts = []
        mods = kb.get_hotkey_name().split("+")
        # Filter to produce a clean combo like "ctrl+shift+d"
        combo = "+".join(m for m in mods if m)
        if combo:
            self.delete(0, tk.END)
            self.insert(0, combo)
            # Stop capture after a valid combo (one that has a non-modifier)
            non_mod = {"ctrl", "shift", "alt", "windows", "right ctrl",
                       "right shift", "right alt", "left ctrl", "left shift", "left alt"}
            if any(p not in non_mod for p in combo.lower().split("+")):
                self.after(150, lambda: self.master.focus_set())


class SettingsWindow:
    """Standalone settings window.  Can be launched before or instead of main."""

    def __init__(self, on_save_and_launch=None):
        self.on_save_and_launch = on_save_and_launch
        self.data = store.load()
        self._choice_maps: dict[str, dict[str, str]] = {}

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Settings")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=_BASE)
        self.root.resizable(False, False)

        w, h = 520, 740
        sx = (self.root.winfo_screenwidth() - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")

        self._entries: dict[str, tk.Widget] = {}
        self._build()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build(self):
        font = (OVERLAY_FONT_FAMILY, 11)
        font_bold = (OVERLAY_FONT_FAMILY, 10, "bold")

        title_frame = tk.Frame(self.root, bg=_PEACH, height=28)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        title_label = tk.Label(
            title_frame, text="  ⚙  Settings",
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
        close_w.bind("<Button-1>", lambda _: self.root.destroy())

        _make_draggable(self.root, title_frame, title_label)
        tk.Frame(self.root, bg=_SURFACE1, height=1).pack(fill=tk.X)

        _scroll_canvas = tk.Canvas(self.root, bg=_BASE, highlightthickness=0, bd=0)
        _scrollbar = tk.Scrollbar(
            self.root, orient=tk.VERTICAL, command=_scroll_canvas.yview,
        )
        _scroll_canvas.configure(yscrollcommand=_scrollbar.set)
        _scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        _scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content = tk.Frame(_scroll_canvas, bg=_BASE)
        _cw = _scroll_canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_resize(e):
            _scroll_canvas.configure(scrollregion=_scroll_canvas.bbox("all"))

        def _on_canvas_resize(e):
            _scroll_canvas.itemconfig(_cw, width=e.width)

        def _on_wheel(e):
            _scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        content.bind("<Configure>", _on_content_resize)
        _scroll_canvas.bind("<Configure>", _on_canvas_resize)
        _scroll_canvas.bind("<Enter>", lambda e: _scroll_canvas.bind_all("<MouseWheel>", _on_wheel))
        _scroll_canvas.bind("<Leave>", lambda e: _scroll_canvas.unbind_all("<MouseWheel>"))

        self._section(content, "Hotkeys", "⌨")
        self._hotkey_row(content, "Audio Analysis", "HOTKEY_AUDIO_ANALYSIS", font)
        self._hotkey_row(content, "Screenshot", "HOTKEY_SCREENSHOT_FEEDBACK", font)
        self._hotkey_row(content, "Quick Input", "HOTKEY_QUICK_INPUT", font)

        self._section(content, "OpenAI API", "🔑")
        self._text_row(content, "API Key", "OPENAI_API_KEY", font, show="•")
        self._text_row(content, "Model", "OPENAI_MODEL", font)

        self._section(content, "Audio", "🎙")
        self._spin_row(content, "Recording Duration (s)", "AUDIO_CHUNK_DURATION", font, 5, 120)
        self._combo_row(content, "Audio Source", "AUDIO_SOURCE", font, ["other", "me", "both"])
        self._combo_row(content, "Microphone Device", "AUDIO_INPUT_DEVICE_ID", font, list_microphone_choices(), width=28)
        self._combo_row(content, "Loopback Output", "AUDIO_OUTPUT_DEVICE_ID", font, list_speaker_choices(), width=28)

        self._section(content, "Speech-to-Text", "🎤")
        self._combo_row(content, "Provider", "STT_PROVIDER", font, ["auto", "local", "xai"])
        self._combo_row(
            content, "Language", "STT_LANGUAGE", font,
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

        self._section(content, "Appearance", "🎨")
        self._slider_row(content, "Overlay Opacity", "INSIGHT_OVERLAY_OPACITY", font, 0.1, 1.0)

        tk.Frame(content, bg=_BASE, height=8).pack(fill=tk.X)
        tk.Frame(content, bg=_SURFACE1, height=1).pack(fill=tk.X, padx=14)

        btn_frame = tk.Frame(content, bg=_BASE)
        btn_frame.pack(fill=tk.X, padx=14, pady=(10, 14))

        tk.Button(
            btn_frame, text="Save & Launch", width=16,
            bg=_ACCENT, fg=_MANTLE,
            font=font_bold,
            activebackground="#b4befe", activeforeground=_MANTLE,
            relief=tk.FLAT, cursor="hand2",
            command=self._save_and_launch,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            btn_frame, text="Save", width=10,
            bg=_SURFACE1, fg=_TEXT,
            font=font, relief=tk.FLAT, cursor="hand2",
            activebackground=_SURFACE2, activeforeground=_TEXT,
            command=self._save,
        ).pack(side=tk.RIGHT)

        tk.Label(
            btn_frame, text=f"v{APP_VERSION}",
            bg=_BASE, fg=_SURFACE2,
            font=(OVERLAY_FONT_FAMILY, 8),
        ).pack(side=tk.LEFT)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _section(self, parent: tk.Widget, label: str, icon: str = ""):
        tk.Label(
            parent, text=f"{icon}  {label}" if icon else label,
            bg=_BASE, fg=_ACCENT,
            font=(OVERLAY_FONT_FAMILY, 9, "bold"), anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(14, 2))
        tk.Frame(parent, bg=_SURFACE1, height=1).pack(fill=tk.X, padx=14)

    def _hotkey_row(self, parent: tk.Widget, label: str, key: str, font):
        row = tk.Frame(parent, bg=_BASE)
        row.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                 font=font, width=20, anchor="w").pack(side=tk.LEFT)
        entry = HotkeyEntry(
            row, bg=_SURFACE0, fg=_TEXT,
            insertbackground=_TEXT,
            font=font, relief=tk.FLAT, width=22,
            highlightthickness=1, highlightcolor=_PINK,
            highlightbackground=_SURFACE1,
        )
        entry.insert(0, self.data.get(key, ""))
        entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        self._entries[key] = entry

    def _text_row(self, parent: tk.Widget, label: str, key: str, font, show=None):
        row = tk.Frame(parent, bg=_BASE)
        row.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                 font=font, width=20, anchor="w").pack(side=tk.LEFT)
        entry = tk.Entry(
            row, bg=_SURFACE0, fg=_TEXT,
            insertbackground=_TEXT,
            font=font, relief=tk.FLAT, width=22,
            show=show,
            highlightthickness=1, highlightcolor=_ACCENT,
            highlightbackground=_SURFACE1,
        )
        entry.insert(0, self.data.get(key, ""))
        entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        self._entries[key] = entry

    def _slider_row(self, parent: tk.Widget, label: str, key: str, font, lo: float, hi: float):
        row = tk.Frame(parent, bg=_BASE)
        row.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                 font=font, width=20, anchor="w").pack(side=tk.LEFT)
        var = tk.DoubleVar(value=self.data.get(key, lo))
        scale = tk.Scale(
            row, from_=lo, to=hi, resolution=0.05,
            orient=tk.HORIZONTAL, variable=var,
            bg=_BASE, fg=_TEXT,
            troughcolor=_SURFACE0, highlightthickness=0,
            font=(OVERLAY_FONT_FAMILY, 7), length=160,
            activebackground=_ACCENT, sliderrelief=tk.FLAT,
        )
        scale.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var

    def _spin_row(self, parent: tk.Widget, label: str, key: str, font, lo: int, hi: int):
        row = tk.Frame(parent, bg=_BASE)
        row.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                 font=font, width=20, anchor="w").pack(side=tk.LEFT)
        var = tk.IntVar(value=self.data.get(key, lo))
        spin = tk.Spinbox(
            row, from_=lo, to=hi, textvariable=var, width=6,
            bg=_SURFACE0, fg=_TEXT,
            font=font, relief=tk.FLAT, buttonbackground=_SURFACE1,
        )
        spin.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var

    def _combo_row(self, parent: tk.Widget, label: str, key: str, font, options, width: int = 14):
        row = tk.Frame(parent, bg=_BASE)
        row.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(row, text=label, bg=_BASE, fg=_TEXT,
                 font=font, width=20, anchor="w").pack(side=tk.LEFT)

        if options and isinstance(options[0], tuple):
            label_to_value = {label: value for label, value in options}
            value_to_label = {value: label for label, value in options}
            current_value = self.data.get(key, options[0][1])
            var = tk.StringVar(value=value_to_label.get(current_value, options[0][0]))
            values = [label for label, _ in options]
            self._choice_maps[key] = label_to_value
        else:
            var = tk.StringVar(value=self.data.get(key, options[0]))
            values = options

        combo = ttk.Combobox(
            row, textvariable=var, values=values, state="readonly",
            width=width, font=font,
        )
        combo.pack(side=tk.LEFT, padx=(4, 0))
        self._entries[key] = var

    # ── Actions ─────────────────────────────────────────────────────────

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
        self.root.mainloop()
