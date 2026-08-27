"""
Tkinter Overlay for Ally Coach Feedback
=======================================
Always-on-top overlay window that displays:
1. Primary coaching feedback, appended as a scrollable history (live)
2. Last prompt to Ally (collapsible)
3. ETA countdown for response
4. Token usage / estimated limit
5. Connection status
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import time
import threading
from typing import Optional, Literal
import cv2
import numpy as np
from PIL import Image, ImageTk

from gui.models import OverlayConfig, FeedbackData, resolve_font_family, DEFAULT_DRAWER_OPEN
from gui.chat_drawer import ChatDrawerMixin
from gui.overlay_api import OverlayApiMixin
from logger import log


class DraggableFrame(tk.Frame):
    dragging: bool = False
    drag_start_y: int = 0
    line_height: int = 16
    accum_dy: int = 0


class AllyOverlay(tk.Tk, OverlayApiMixin, ChatDrawerMixin):
    """Main overlay window that stays always-on-top."""

    def __init__(self, config: Optional[OverlayConfig] = None, on_close=None,
                 on_send_message=None, core=None):
        super().__init__()

        self.config_data = config or OverlayConfig()
        self.config_data.font_family = resolve_font_family(self.config_data.font_family)
        self._on_close_callback = on_close
        self._on_send_message = on_send_message
        if core is not None:
            if self._on_send_message is None:
                self._on_send_message = core.send_message
            core.gui_app = self
            core.on_pipeline_image = self.update_pipeline_image
            core.on_debug_overlay = self.update_debug_image
            core.on_status_update = lambda screen, event: (self.update_debug_info(screen, event), self.start_eta_countdown(15))
            core.on_state_summary = self.update_state_summary
            core.on_prompt_update = self.update_prompt
            core.on_feedback = self.update_feedback
            core.on_chat_message = self.append_chat_message
            core.on_eta_ready = self.set_eta_ready
            core.on_connection_status = self.set_connection_status
            core.on_medium_term = self.update_medium_term_summary
            core.on_personality_state = self.update_personality_state
            core.on_strategic_memory = self.update_strategic_memory

        self._drawer_open = DEFAULT_DRAWER_OPEN
        self._prompt_collapsed = True
        self._summary_collapsed = False
        self._strategic_collapsed = True

        self._setup_window()
        self._setup_fonts()
        self._setup_styles()
        self._create_drawer_widgets()
        self._create_widgets()
        self._create_layout()

        # Data state
        self._feedback_data = FeedbackData()
        self._eta_start_time: Optional[float] = None
        self._eta_thread: Optional[threading.Thread] = None
        self._running = True
        self._feedback_entry_count = 0
        self._resize_job = None
        self._debug_image_raw: Optional[Image.Image] = None
        self._debug_photo_image: Optional[ImageTk.PhotoImage] = None
        self.bind("<Configure>", self._on_window_configure)

        # Thread-safe UI dispatch
        self._init_dispatch_queue()

        # Position window on screen
        self._position_window()

    def _setup_window(self):
        """Configure the main window properties."""
        cfg = self.config_data
        self.title("Ally Coach Overlay")
        self.configure(bg=cfg.bg_color)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', cfg.opacity)

        debug_w = 340
        initial_width = cfg.width + debug_w + (cfg.drawer_width if self._drawer_open else 0)
        self.geometry(f"{initial_width}x{cfg.height}")
        
        min_w = cfg.min_width + debug_w + (cfg.drawer_width if self._drawer_open else 0)
        self.minsize(min_w, cfg.min_height)
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_fonts(self):
        """Initialize font objects."""
        cfg = self.config_data
        self.title_font = tkfont.Font(family=cfg.font_family, size=cfg.title_font_size, weight='bold')
        self.label_font = tkfont.Font(family=cfg.font_family, size=cfg.font_size, weight='bold')
        self.text_font = tkfont.Font(family=cfg.font_family, size=cfg.font_size)
        self.small_font = tkfont.Font(family=cfg.font_family, size=9)
        self.mini_font = tkfont.Font(family=cfg.font_family, size=8)

    def _setup_styles(self):
        """Configure ttk styles."""
        cfg = self.config_data
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure('TFrame', background=cfg.bg_color)
        style.configure('TLabeledScale', background=cfg.bg_color)

    def _make_scrollable_text(self, parent, height, fg_color, font, wrap: Literal["none", "char", "word"] = "word"):
        """Creates a text area component container without scrollbars."""
        cfg = self.config_data
        container = tk.Frame(parent, bg=cfg.bg_color)
        text_widget = tk.Text(
            container,
            wrap=wrap,
            font=font,
            bg=cfg.bg_color,
            fg=fg_color,
            insertbackground=fg_color,
            relief=tk.FLAT,
            state=tk.DISABLED,
            height=height,
            spacing1=4,
            spacing2=2,
            spacing3=6,
            undo=False,
            highlightthickness=0,
        )
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return container, text_widget

    def _create_widgets(self):
        """Create individual widget components for the main panel."""
        cfg = self.config_data
        
        # ── Debug Image Panel (Left) - Scrollable Pipeline View ──
        self.debug_panel_frame = tk.Frame(self, bg=cfg.bg_color, width=340)
        self.debug_panel_frame.pack_propagate(False)

        self._pipeline_canvas = tk.Canvas(self.debug_panel_frame, bg=cfg.bg_color, highlightthickness=0)
        self._pipeline_scrollbar = ttk.Scrollbar(self.debug_panel_frame, orient="vertical", command=self._pipeline_canvas.yview)
        self._pipeline_content = tk.Frame(self._pipeline_canvas, bg=cfg.bg_color)

        self._pipeline_content.bind(
            "<Configure>",
            lambda e: self._pipeline_canvas.configure(scrollregion=self._pipeline_canvas.bbox("all"))
        )
        self._pipeline_canvas.create_window((0, 0), window=self._pipeline_content, anchor="nw")
        self._pipeline_canvas.configure(yscrollcommand=self._pipeline_scrollbar.set)

        self._pipeline_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._pipeline_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            try:
                self._pipeline_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _bound_to_mousewheel(event):
            self.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbound_from_mousewheel(event):
            self.unbind_all("<MouseWheel>")

        self.debug_panel_frame.bind("<Enter>", _bound_to_mousewheel)
        self.debug_panel_frame.bind("<Leave>", _unbound_from_mousewheel)

        self._pipeline_slots = {}
        pipeline_defs = [
            ("observation", "RGB PIL Image Observation"),
            ("grayscale", "Grayscale Frame"),
            ("masked_grayscale", "ROI-Masked Grayscale Frame"),
            ("normalized_grayscale", "Luminance-Normalized Grayscale"),
            ("diff", "Absolute Difference Image"),
            ("thresh", "Thresholded Binary Change Map"),
            ("classifier_gray", "Classifier Grayscale Frame"),
            ("classifier_crop", "Anchor Crop / Draft Frame"),
            ("debug_overlay", "Annotated Debug Overlay Frame"),
        ]

        for key, default_title in pipeline_defs:
            card = tk.Frame(self._pipeline_content, bg=cfg.bg_color, pady=4)
            card.pack(fill=tk.X, padx=4)

            title_lbl = tk.Label(
                card, text=default_title, font=self.mini_font,
                fg=cfg.accent_color, bg=cfg.bg_color, anchor="w"
            )
            title_lbl.pack(fill=tk.X, padx=2)

            img_lbl = tk.Label(card, bg=cfg.border_color, bd=1, relief=tk.SOLID)
            img_lbl.pack(fill=tk.X, padx=2, pady=(2, 0))

            self._pipeline_slots[key] = {
                "title_label": title_lbl,
                "image_label": img_lbl,
                "raw_image": None,
                "photo_image": None,
                "title": default_title,
            }

        self.main_frame = tk.Frame(self, bg=cfg.bg_color)

        # ── Title bar section ──
        self.title_bar = tk.Frame(self.main_frame, bg=cfg.border_color, height=22, cursor="fleur")
        self.title_bar.pack_propagate(False)

        self.status_dot = tk.Canvas(
            self.title_bar, width=10, height=10,
            bg=cfg.border_color, highlightthickness=0, cursor="fleur",
        )
        self._status_dot_id = self.status_dot.create_oval(1, 1, 9, 9, fill=cfg.dim_color, outline="")
        self.status_dot.pack(side=tk.LEFT, padx=(6, 4))

        self.title_label = tk.Label(
            self.title_bar,
            text="Ally",
            font=self.title_font,
            fg=cfg.accent_color,
            bg=cfg.border_color,
            cursor="fleur",
        )
        self.title_label.pack(side=tk.LEFT)
        
        self.close_button = tk.Button(
            self.title_bar,
            text="×",
            width=3,
            font=self.label_font,
            fg="#ff6b6b",
            bg=cfg.border_color,
            activebackground=cfg.error_color,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=self._on_close,
        )
        self.close_button.pack(side=tk.RIGHT, padx=2)
        self.close_button.bind("<Enter>", lambda e: self.close_button.config(bg=cfg.error_color, fg="#ffffff"))
        self.close_button.bind("<Leave>", lambda e: self.close_button.config(bg=cfg.border_color, fg=cfg.error_color))

        self.drawer_toggle_button = tk.Button(
            self.title_bar,
            text="Chat «" if self._drawer_open else "Chat »",
            font=self.mini_font,
            fg=cfg.accent_color,
            bg=cfg.border_color,
            activebackground=cfg.dim_color,
            activeforeground=cfg.fg_color,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._toggle_drawer,
        )
        self.drawer_toggle_button.pack(side=tk.RIGHT, padx=(0, 2))

        self.settings_button = tk.Button(
            self.title_bar,
            text="⚙ Settings",
            font=self.mini_font,
            fg=cfg.accent_color,
            bg=cfg.border_color,
            activebackground=cfg.dim_color,
            activeforeground=cfg.fg_color,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._open_settings,
        )
        self.settings_button.pack(side=tk.RIGHT, padx=(0, 2))

        for widget in (self.title_bar, self.title_label, self.status_dot):
            widget.bind('<ButtonPress-1>', self._start_move)
            widget.bind('<B1-Motion>', self._do_move)
        
        self.title_bar.pack(fill=tk.X, side=tk.TOP)

        # ── Debug line ──
        debug_frame = tk.Frame(self.main_frame, bg=cfg.bg_color)
        debug_frame.pack(fill=tk.X, padx=10, pady=(4, 0))
        self.debug_label = tk.Label(
            debug_frame, text="screen: -  |  event: -", font=self.mini_font,
            fg=cfg.dim_color, bg=cfg.bg_color, anchor='w',
        )
        self.debug_label.pack(fill=tk.X)

        # ── State of the Game Section ──
        summary_outer_container = tk.Frame(self.main_frame, bg=cfg.bg_color)
        summary_outer_container.pack(fill=tk.X, padx=10, pady=4)

        summary_header_row = tk.Frame(summary_outer_container, bg=cfg.bg_color)
        summary_header_row.pack(fill=tk.X, pady=(0, 3))

        self.summary_toggle_btn = tk.Button(
            summary_header_row, text="▼ COMPANION STATE", font=self.label_font,
            fg=cfg.summary_color, bg=cfg.bg_color,
            activebackground=cfg.bg_color, activeforeground=cfg.accent_color,
            relief=tk.FLAT, bd=0, cursor="hand2", anchor="w",
            command=self._toggle_summary_section
        )
        self.summary_toggle_btn.pack(side=tk.LEFT, fill=tk.X)

        self.summary_content_frame = tk.Frame(summary_outer_container, bg=cfg.bg_color)
        summary_box, self.summary_text = self._make_scrollable_text(
            self.summary_content_frame, height=4,
            fg_color=cfg.summary_color, font=self.small_font,
        )
        summary_box.pack(fill=tk.X)
        self.summary_content_frame.pack(fill=tk.X, pady=(0, 3))

        self._add_draggable_divider(lambda: self.summary_text, lambda: self.feedback_text)

        # ── Coaching Feedback Section ──
        feedback_container = tk.Frame(self.main_frame, bg=cfg.bg_color)
        feedback_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))

        feedback_header_row = tk.Frame(feedback_container, bg=cfg.bg_color)
        feedback_header_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            feedback_header_row, text="ALLY FEEDBACK", font=self.label_font,
            fg=cfg.feedback_color, bg=cfg.bg_color,
        ).pack(side=tk.LEFT)
        self.clear_button = tk.Button(
            feedback_header_row, text="Clear", font=self.mini_font,
            fg=cfg.dim_color, bg=cfg.bg_color,
            activebackground=cfg.border_color,
            activeforeground=cfg.fg_color,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.clear_feedback_history,
        )
        self.clear_button.pack(side=tk.RIGHT)

        feedback_box, self.feedback_text = self._make_scrollable_text(
            feedback_container, height=10,
            fg_color=cfg.feedback_color, font=self.text_font,
        )
        feedback_box.pack(fill=tk.BOTH, expand=True)
        self.feedback_text.tag_configure('timestamp', foreground=cfg.dim_color, font=self.mini_font)
        self.feedback_text.tag_configure('body', foreground=cfg.feedback_color, font=self.text_font)
        self.feedback_text.tag_configure('medium', foreground='#ffb74d', font=self.text_font)

        self._add_draggable_divider(lambda: self.feedback_text, lambda: self.prompt_text)

        # ── Prompt Section ──
        prompt_outer_container = tk.Frame(self.main_frame, bg=cfg.bg_color)
        prompt_outer_container.pack(fill=tk.X, padx=10, pady=4)

        prompt_header_row = tk.Frame(prompt_outer_container, bg=cfg.bg_color)
        prompt_header_row.pack(fill=tk.X, pady=(0, 3))
        
        self.prompt_toggle_btn = tk.Button(
            prompt_header_row, text="▶ LAST PROMPT", font=self.label_font,
            fg=cfg.prompt_color, bg=cfg.bg_color,
            activebackground=cfg.bg_color, activeforeground=cfg.accent_color,
            relief=tk.FLAT, bd=0, cursor="hand2", anchor="w",
            command=self._toggle_prompt_section
        )
        self.prompt_toggle_btn.pack(side=tk.LEFT, fill=tk.X)

        self.prompt_content_frame = tk.Frame(prompt_outer_container, bg=cfg.bg_color)
        prompt_box, self.prompt_text = self._make_scrollable_text(
            self.prompt_content_frame, height=4,
            fg_color=cfg.prompt_color, font=self.small_font,
        )
        prompt_box.pack(fill=tk.X)
        self.prompt_content_frame.pack_forget()

        # ── Strategic Memory Section ──
        strategic_outer_container = tk.Frame(self.main_frame, bg=cfg.bg_color)
        strategic_outer_container.pack(fill=tk.X, padx=10, pady=4)

        strategic_header_row = tk.Frame(strategic_outer_container, bg=cfg.bg_color)
        strategic_header_row.pack(fill=tk.X, pady=(0, 3))

        self.strategic_toggle_btn = tk.Button(
            strategic_header_row, text="▶ STRATEGIC MEMORY", font=self.label_font,
            fg=cfg.accent_color, bg=cfg.bg_color,
            activebackground=cfg.bg_color, activeforeground=cfg.accent_color,
            relief=tk.FLAT, bd=0, cursor="hand2", anchor="w",
            command=self._toggle_strategic_section
        )
        self.strategic_toggle_btn.pack(side=tk.LEFT, fill=tk.X)

        self.strategic_content_frame = tk.Frame(strategic_outer_container, bg=cfg.bg_color)
        strategic_box, self.strategic_text = self._make_scrollable_text(
            self.strategic_content_frame, height=4,
            fg_color=cfg.accent_color, font=self.small_font,
        )
        strategic_box.pack(fill=tk.X)
        self.strategic_content_frame.pack_forget()

        self._add_divider()

        # ── Bottom bar: ETA + Tokens ──
        bottom_row = tk.Frame(self.main_frame, bg=cfg.bg_color)
        bottom_row.pack(fill=tk.X, padx=10, pady=(4, 2))

        self.eta_frame = tk.Frame(bottom_row, bg=cfg.bg_color)
        self.eta_frame.pack(side=tk.LEFT)

        tk.Label(self.eta_frame, text="ETA", font=self.small_font, fg=cfg.dim_color, bg=cfg.bg_color).pack(anchor=tk.W)
        self.eta_label = tk.Label(self.eta_frame, text="--:--", font=self.label_font, fg=cfg.eta_color, bg=cfg.bg_color, width=8)
        self.eta_label.pack(anchor=tk.W)

        self.eta_bar = tk.Canvas(self.eta_frame, width=100, height=8, bg=cfg.bg_color, highlightthickness=0)
        self.eta_bar.pack(anchor=tk.W, pady=(2, 0))
        self.eta_bar_bg = self.eta_bar.create_rectangle(0, 0, 100, 8, fill="#2a2a2a", outline="")
        self.eta_bar_progress = self.eta_bar.create_rectangle(0, 0, 0, 8, fill=cfg.eta_color, outline="")

        self.token_frame = tk.Frame(bottom_row, bg=cfg.bg_color)
        self.token_frame.pack(side=tk.RIGHT)

        tk.Label(self.token_frame, text="TPM", font=self.small_font, fg=cfg.dim_color, bg=cfg.bg_color).pack(anchor=tk.E)
        self.token_label = tk.Label(self.token_frame, text="0 / 200k", font=self.label_font, fg=cfg.token_color, bg=cfg.bg_color)
        self.token_label.pack(anchor=tk.E)

        self.token_bar = tk.Canvas(self.token_frame, width=90, height=8, bg=cfg.bg_color, highlightthickness=0)
        self.token_bar.pack(anchor=tk.E, pady=(2, 0))
        self.token_bar_bg = self.token_bar.create_rectangle(0, 0, 90, 8, fill="#2a2a2a", outline="")

        # Status bar
        self.status_frame = tk.Frame(self.main_frame, bg=cfg.border_color)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = tk.Label(
            self.status_frame, text="Ready", font=self.small_font,
            fg=cfg.accent_color, bg=cfg.border_color,
            anchor='e', padx=8, pady=2,
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 20))

        # Resize grip
        self.resize_grip = tk.Canvas(self, width=14, height=14, bg=cfg.border_color, highlightthickness=0, cursor="sizing")
        for i in range(3):
            offset = i * 4
            self.resize_grip.create_line(2 + offset, 12, 12, 2 + offset, fill=cfg.dim_color, width=1)
        self.resize_grip.place(relx=1.0, rely=1.0, anchor='se')
        self.resize_grip.bind('<ButtonPress-1>', self._start_resize)
        self.resize_grip.bind('<B1-Motion>', self._do_resize)
        self.resize_grip.bind('<ButtonRelease-1>', self._stop_resize)

        self._add_borders(cfg)

    def _toggle_summary_section(self):
        summary_height = self.summary_text.cget('height')
        feedback_height = self.feedback_text.cget('height')

        if self._summary_collapsed:
            needed = summary_height
            if feedback_height - needed >= 2:
                self.feedback_text.config(height=feedback_height - needed)
            self.summary_content_frame.pack(fill=tk.X, pady=(0, 3))
            self.summary_toggle_btn.config(text="▼ COMPANION STATE")
            self._summary_collapsed = False
        else:
            gained = summary_height
            self.summary_content_frame.pack_forget()
            self.summary_toggle_btn.config(text="▶ COMPANION STATE")
            self._summary_collapsed = True
            self.feedback_text.config(height=feedback_height + gained)

    def _toggle_prompt_section(self):
        prompt_height = self.prompt_text.cget('height')
        feedback_height = self.feedback_text.cget('height')

        if self._prompt_collapsed:
            needed = prompt_height
            if feedback_height - needed >= 2:
                self.feedback_text.config(height=feedback_height - needed)
            self.prompt_content_frame.pack(fill=tk.X, pady=(0, 3))
            self.prompt_toggle_btn.config(text="▼ LAST PROMPT")
            self._prompt_collapsed = False
        else:
            gained = prompt_height
            self.prompt_content_frame.pack_forget()
            self.prompt_toggle_btn.config(text="▶ LAST PROMPT")
            self._prompt_collapsed = True
            self.feedback_text.config(height=feedback_height + gained)

    def _toggle_strategic_section(self):
        strategic_height = self.strategic_text.cget('height')
        feedback_height = self.feedback_text.cget('height')

        if self._strategic_collapsed:
            needed = strategic_height
            if feedback_height - needed >= 2:
                self.feedback_text.config(height=feedback_height - needed)
            self.strategic_content_frame.pack(fill=tk.X, pady=(0, 3))
            self.strategic_toggle_btn.config(text="▼ STRATEGIC MEMORY")
            self._strategic_collapsed = False
        else:
            gained = strategic_height
            self.strategic_content_frame.pack_forget()
            self.strategic_toggle_btn.config(text="▶ STRATEGIC MEMORY")
            self._strategic_collapsed = True
            self.feedback_text.config(height=feedback_height + gained)

    def _add_divider(self):
        return tk.Frame(self.main_frame, bg=self.config_data.border_color, height=1).pack(fill=tk.X, padx=10, pady=(4, 4))

    def _add_draggable_divider(self, get_above=None, get_below=None):
        container = DraggableFrame(self.main_frame, bg=self.config_data.bg_color, height=9, cursor="sb_v_double_arrow")
        container.pack_propagate(False)
        container.pack(fill=tk.X, padx=10, pady=(1, 1))

        line = tk.Frame(container, bg=self.config_data.border_color, height=1)
        line.pack(fill=tk.X, pady=4)

        if get_above is not None and get_below is not None:
            def start_drag(event):
                text_widget_above = get_above()
                text_widget_below = get_below()
                if text_widget_above is getattr(self, 'summary_text', None) and self._summary_collapsed:
                    container.dragging = False
                    return
                if text_widget_above is getattr(self, 'prompt_text', None) and self._prompt_collapsed:
                    container.dragging = False
                    return
                container.dragging = True
                container.drag_start_y = event.y_root
                try:
                    font_obj = tkfont.Font(font=text_widget_above.cget('font'))
                    container.line_height = font_obj.metrics('linespace')
                except Exception:
                    container.line_height = 16

            def do_drag(event):
                if not container.dragging:
                    return
                dy = event.y_root - container.drag_start_y
                line_h = container.line_height
                delta_lines = round(dy / line_h)
                if delta_lines != 0:
                    text_widget_above = get_above()
                    text_widget_below = get_below()
                    curr_above = text_widget_above.cget('height')
                    curr_below = text_widget_below.cget('height')
                    target_above = max(2, curr_above + delta_lines)
                    actual_delta = target_above - curr_above
                    if actual_delta != 0:
                        text_widget_above.config(height=target_above)
                        text_widget_below.config(height=max(2, curr_below - actual_delta))
                        container.drag_start_y = event.y_root

            for w in (container, line):
                w.bind('<ButtonPress-1>', start_drag)
                w.bind('<B1-Motion>', do_drag)
        return container

    def _create_layout(self):
        if self._drawer_open:
            self.drawer_outer_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.debug_panel_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _on_window_configure(self, event):
        if event.widget is self:
            w, h = self.winfo_width(), self.winfo_height()
            if getattr(self, '_last_configure_width', None) == w and getattr(self, '_last_configure_height', None) == h:
                return  # Position-only change (e.g. dragging the window), skip heavy image re-rendering!
            self._last_configure_width = w
            self._last_configure_height = h

            if hasattr(self, '_resize_job') and self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(100, self._refresh_debug_image)

    def update_pipeline_image(self, key: str, image, title: Optional[str] = None):
        """Update a specific pipeline image slot asynchronously as soon as processed."""
        if image is None:
            return
        if isinstance(image, np.ndarray):
            if len(image.shape) == 3 and image.shape[2] == 3:
                rgb_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            elif len(image.shape) == 2:
                rgb_img = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            else:
                rgb_img = image
            pil_img = Image.fromarray(rgb_img)
        elif isinstance(image, Image.Image):
            pil_img = image.convert("RGB")
        else:
            return

        def _update():
            if key not in self._pipeline_slots:
                card = tk.Frame(self._pipeline_content, bg=self.config_data.bg_color, pady=4)
                card.pack(fill=tk.X, padx=4)
                t = title or key
                title_lbl = tk.Label(
                    card, text=t, font=self.mini_font,
                    fg=self.config_data.accent_color, bg=self.config_data.bg_color, anchor="w"
                )
                title_lbl.pack(fill=tk.X, padx=2)
                img_lbl = tk.Label(card, bg=self.config_data.border_color, bd=1, relief=tk.SOLID)
                img_lbl.pack(fill=tk.X, padx=2, pady=(2, 0))
                self._pipeline_slots[key] = {
                    "title_label": title_lbl,
                    "image_label": img_lbl,
                    "raw_image": None,
                    "photo_image": None,
                    "title": t,
                }
            
            slot = self._pipeline_slots[key]
            if title:
                slot["title"] = title
                slot["title_label"].config(text=title)
            slot["raw_image"] = pil_img
            self._refresh_pipeline_slot(key)

        self._dispatch(_update)

    def update_debug_image(self, image):
        """Backwards compatibility wrapper for debug overlay image."""
        self.update_pipeline_image("debug_overlay", image, "Annotated Debug Overlay Frame")

    def _refresh_pipeline_slot(self, key: str):
        slot = self._pipeline_slots.get(key)
        if not slot or slot["raw_image"] is None:
            return
        try:
            orig_w, orig_h = slot["raw_image"].size
            aspect_ratio = (orig_w / orig_h) if orig_h > 0 else 1.333
            
            target_w = 320
            target_h = int(target_w / aspect_ratio)
            if target_h > 240:
                target_h = 240
                target_w = int(target_h * aspect_ratio)

            resized = slot["raw_image"].resize((target_w, target_h), Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(resized)
            slot["photo_image"] = photo
            slot["image_label"].config(image=photo)
        except Exception:
            pass

    def _refresh_debug_image(self):
        """Refresh all pipeline slots on window configure/resize."""
        for key in self._pipeline_slots:
            self._refresh_pipeline_slot(key)

    def _add_borders(self, cfg):
        left_border = tk.Frame(self, bg=cfg.window_border_color, width=1)
        left_border.place(x=0, y=0, relheight=1.0)
        right_border = tk.Frame(self, bg=cfg.window_border_color, width=1)
        right_border.place(relx=1.0, x=-1, y=0, relheight=1.0)
        bottom_border = tk.Frame(self, bg=cfg.window_border_color, height=1)
        bottom_border.place(x=0, rely=1.0, y=-1, relwidth=1.0)

    def _position_window(self):
        cfg = self.config_data
        debug_w = 340
        initial_width = cfg.width + debug_w + (cfg.drawer_width if self._drawer_open else 0)
        initial_height = cfg.height

        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        x = (screen_width - initial_width) // 2
        y = (screen_height - initial_height) // 2

        self.geometry(f"{initial_width}x{initial_height}+{x}+{y}")

    def _start_move(self, event):
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _do_move(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.geometry(f"+{x}+{y}")

    def _start_resize(self, event):
        self._resize_start_x_root = event.x_root
        self._resize_start_y_root = event.y_root
        self._resize_start_width = self.winfo_width()
        self._resize_start_height = self.winfo_height()
        self._current_new_w = self._resize_start_width
        self._current_new_h = self._resize_start_height

        cfg = self.config_data
        self._resize_outline_win = tk.Toplevel(self)
        self._resize_outline_win.overrideredirect(True)
        self._resize_outline_win.attributes('-topmost', True)
        self._resize_outline_win.attributes('-alpha', 0.35)
        self._resize_outline_win.configure(bg=cfg.success_color)

        outline_frame = tk.Frame(self._resize_outline_win, bg=cfg.bg_color, bd=2, relief=tk.SOLID)
        outline_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        x = self.winfo_x()
        y = self.winfo_y()
        self._resize_outline_win.geometry(f"{self._resize_start_width}x{self._resize_start_height}+{x}+{y}")

    def _do_resize(self, event):
        cfg = self.config_data
        dx = event.x_root - self._resize_start_x_root
        dy = event.y_root - self._resize_start_y_root
        win_min_w = cfg.min_width + (cfg.drawer_width if self._drawer_open else 0)
        self._current_new_w = max(win_min_w, self._resize_start_width + dx)
        self._current_new_h = max(cfg.min_height, self._resize_start_height + dy)

        if hasattr(self, '_resize_outline_win') and self._resize_outline_win:
            x = self.winfo_x()
            y = self.winfo_y()
            self._resize_outline_win.geometry(f"{self._current_new_w}x{self._current_new_h}+{x}+{y}")

    def _stop_resize(self, event):
        if hasattr(self, '_resize_outline_win') and self._resize_outline_win:
            try:
                self._resize_outline_win.destroy()
            except Exception:
                pass
            self._resize_outline_win = None

        if hasattr(self, '_current_new_w') and hasattr(self, '_current_new_h'):
            self.geometry(f"{self._current_new_w}x{self._current_new_h}")

    def _on_close(self):
        if self._on_close_callback:
            self._on_close_callback()
        self._running = False
        self.destroy()

    def _open_settings(self):
        from gui.settings_window import SettingsWindow
        SettingsWindow(self)

    def _toggle_drawer(self):
        self._set_drawer_visible(not self._drawer_open)

    def _set_drawer_visible(self, visible: bool):
        if visible == self._drawer_open:
            return

        current_x = self.winfo_x()
        current_y = self.winfo_y()
        current_width = self.winfo_width()
        current_height = self.winfo_height()
        delta = self.config_data.drawer_width

        if visible:
            new_width = current_width + delta
            self.geometry(f"{new_width}x{current_height}+{current_x}+{current_y}")
            self.update_idletasks()
            self.drawer_outer_frame.pack(side=tk.RIGHT, fill=tk.Y, before=self.main_frame)
        else:
            self.drawer_outer_frame.pack_forget()
            self.update_idletasks()
            new_width = current_width - delta
            self.geometry(f"{new_width}x{current_height}+{current_x}+{current_y}")

        self._drawer_open = visible
        self.drawer_toggle_button.config(text="Chat «" if visible else "Chat »")
        self.update_idletasks()


if __name__ == "__main__":
    app = AllyOverlay()
    app.set_connection_status(True)

    def demo_updates():
        import random
        demo_feedbacks = [
            "Excellent positioning! Maintaining control of the mid lane.\n\n"
            "Your last-hitting is 85% efficient - focus on the mage creep at 7:35.",
            "Watch out for enemy rotations in the river area.\n\n"
            "Enemy jungler spotted near dragon. Be cautious of steals.",
            "Consider backing now - you have enough gold for a significant purchase.",
        ]
        idx = 0
        while app._running and idx < len(demo_feedbacks):
            app.update_feedback(demo_feedbacks[idx])
            app.update_state_summary("Sample game state context...")
            app.update_prompt("Sample prompt sent to Gemini...")
            app.start_eta_countdown(10)
            idx += 1
            time.sleep(12)

    threading.Thread(target=demo_updates, daemon=True).start()
    app.mainloop()
