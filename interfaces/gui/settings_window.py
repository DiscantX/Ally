"""Settings Menu Window for Ally Overlay.
Provides a tabbed settings interface (Standard vs Advanced/Dev) with synchronized
sliders and entry boxes, dropdowns, and checkboxes to configure models, thresholds,
and pipeline parameters in a modern, cohesive dark theme matching the main overlay.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from cabinet.configs.config_manager import load_user_config, save_user_config
from brain.reasoning.personalities import PERSONALITIES
from infrastructure.llm.providers.gemini_provider import get_available_models, get_available_thinking_levels


class SettingsWindow(tk.Toplevel):
    """Settings menu dialog window with modern dark theme and grouped controls."""

    def __init__(self, parent: tk.Widget, on_save: Callable[[], None] | None = None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Ally Settings & Configuration")
        self.minsize(550, 500)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.configure(bg="#1a1a1a")
        self.attributes("-topmost", True)

        self.on_save_callback = on_save
        self.config_data = load_user_config()
        self.vars: dict[str, Any] = {}

        self._setup_styles()
        self._create_widgets()

        width, height = 640, 680
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        try:
            if parent and parent.winfo_exists():
                parent_x = parent.winfo_rootx()
                parent_y = parent.winfo_rooty()
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                x = parent_x + (parent_w - width) // 2
                y = parent_y + (parent_h - height) // 2
            else:
                raise Exception()
        except Exception:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.update_idletasks()
        self.focus_set()
        self.deiconify()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')

        # Global dark theme styling
        bg_col = "#1a1a1a"
        fg_col = "#e0e0e0"
        field_col = "#2d2d2d"
        border_col = "#333333"
        accent_col = "#00ffcc"
        disabled_fg = "#666666"

        # Configure dropdown listbox background globally via option_add
        self.option_add('*TCombobox*Listbox.background', field_col)
        self.option_add('*TCombobox*Listbox.foreground', fg_col)
        self.option_add('*TCombobox*Listbox.selectBackground', accent_col)
        self.option_add('*TCombobox*Listbox.selectForeground', bg_col)

        style.configure('.',
                        background=bg_col,
                        foreground=fg_col,
                        fieldbackground=field_col,
                        darkcolor=border_col,
                        lightcolor=border_col,
                        bordercolor=border_col,
                        troughcolor=field_col,
                        selectbackground=accent_col,
                        selectforeground=bg_col)
        
        style.map('.',
                  foreground=[('disabled', disabled_fg)],
                  fieldbackground=[('disabled', field_col)])

        style.configure('TNotebook', background=bg_col, bordercolor=border_col)
        style.configure('TNotebook.Tab', background=field_col, foreground=fg_col, padding=[12, 6], font=('Segoe UI', 9, 'bold'))
        style.map('TNotebook.Tab',
                  background=[('selected', bg_col)],
                  foreground=[('selected', accent_col)])

        style.configure('TFrame', background=bg_col)
        style.configure('TLabel', background=bg_col, foreground=fg_col, font=('Segoe UI', 9))
        style.configure('Heading.TLabel', background=bg_col, foreground=accent_col, font=('Segoe UI', 10, 'bold'))
        style.map('TLabel',
                  foreground=[('disabled', disabled_fg)])
        
        style.configure('TCheckbutton', background=bg_col, foreground=fg_col, font=('Segoe UI', 9), focuscolor=bg_col)
        style.map('TCheckbutton',
                  background=[('active', bg_col)],
                  foreground=[('active', accent_col), ('disabled', disabled_fg)])

        style.configure('TButton', background=field_col, foreground=fg_col, font=('Segoe UI', 9, 'bold'), bordercolor=border_col, relief=tk.FLAT)
        style.map('TButton',
                  background=[('active', border_col), ('disabled', field_col)],
                  foreground=[('active', accent_col), ('disabled', disabled_fg)])

        style.configure('TCombobox', fieldbackground=field_col, background=field_col, foreground=fg_col, selectbackground=accent_col, selectforeground=bg_col)
        style.map('TCombobox',
                  fieldbackground=[('readonly', field_col), ('disabled', field_col)],
                  foreground=[('disabled', disabled_fg)])

        style.configure('TEntry', fieldbackground=field_col, foreground=fg_col, insertcolor=fg_col)
        style.map('TEntry',
                  fieldbackground=[('disabled', field_col)],
                  foreground=[('disabled', disabled_fg)])

        style.configure('TSpinbox', fieldbackground=field_col, foreground=fg_col, insertcolor=fg_col)
        style.map('TSpinbox',
                  fieldbackground=[('disabled', field_col)],
                  foreground=[('disabled', disabled_fg)])

        style.configure('Horizontal.TScale', background=bg_col, troughcolor=field_col, bordercolor=border_col)
        style.map('Horizontal.TScale',
                  background=[('active', '#444444'), ('pressed', '#333333')],
                  troughcolor=[('active', field_col)])

        style.configure('TSeparator', background=border_col)

        style.configure('Vertical.TScrollbar', background=field_col, troughcolor=bg_col, bordercolor=border_col, arrowcolor=fg_col)
        style.map('Vertical.TScrollbar',
                  background=[('active', '#444444'), ('pressed', '#333333')])
        style.configure('Horizontal.TScrollbar', background=field_col, troughcolor=bg_col, bordercolor=border_col, arrowcolor=fg_col)
        style.map('Horizontal.TScrollbar',
                  background=[('active', '#444444'), ('pressed', '#333333')])

    def _create_widgets(self):
        # Notebook for tabs
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Tab 1: Standard Settings
        std_frame = ttk.Frame(notebook)
        notebook.add(std_frame, text="  Standard Settings  ")
        self._build_standard_tab(std_frame)

        # Tab 2: Advanced / Dev Settings
        adv_frame = ttk.Frame(notebook)
        notebook.add(adv_frame, text="  Advanced / Dev Settings  ")
        self._build_advanced_tab(adv_frame)

        # Bottom Button Bar
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        save_btn = ttk.Button(btn_frame, text="Save & Apply", command=self._save_settings, width=15)
        save_btn.pack(side=tk.RIGHT, padx=5)

        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=12)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

    def _build_standard_tab(self, parent: ttk.Frame):
        canvas = tk.Canvas(parent, bg="#1a1a1a", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=15)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        model_choices = get_available_models()
        row = 0

        # Subsection: LLM Model Management
        ttk.Label(scrollable_frame, text="LLM Model Management", style='Heading.TLabel').grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        row += 1

        use_master_var = tk.BooleanVar(value=bool(self.config_data.get("use_master_model", False)))
        self.vars["use_master_model"] = use_master_var
        master_chk = ttk.Checkbutton(scrollable_frame, text="Use Master Model for All Pipelines", variable=use_master_var, command=lambda: self._toggle_master_mode(master_chk))
        master_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(scrollable_frame, text="Master Model Override").grid(row=row, column=0, sticky=tk.W, pady=6, padx=(15, 10))
        master_model_var = tk.StringVar(value=self.config_data.get("master_model", model_choices[0] if model_choices else ""))
        self.vars["master_model"] = master_model_var
        master_combo = ttk.Combobox(scrollable_frame, textvariable=master_model_var, values=model_choices, state="readonly", width=30)
        master_combo.grid(row=row, column=1, sticky=tk.W, pady=6, padx=5)
        row += 1

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky="ew", pady=15)
        row += 1

        # Subsection: Individual LLM Overrides
        ttk.Label(scrollable_frame, text="Individual LLM Overrides", style='Heading.TLabel').grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        row += 1

        models = [
            ("Scribe Model", "scribe_model"),
            ("Ally Model", "ally_model"),
            ("Narrative Model", "narrative_model"),
            ("Personality Model", "personality_model"),
            ("Genealogy Model", "geneology_model"),
        ]

        self.model_combos = []
        for label_text, key in models:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=6, padx=(15, 10))
            var = tk.StringVar(value=self.config_data.get(key, model_choices[0] if model_choices else ""))
            self.vars[key] = var
            combo = ttk.Combobox(scrollable_frame, textvariable=var, values=model_choices, state="readonly", width=30)
            combo.grid(row=row, column=1, sticky=tk.W, pady=6, padx=5)
            self.model_combos.append(combo)
            row += 1

        self._toggle_master_mode(None)  # Initialize state

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky="ew", pady=15)
        row += 1

        # Subsection: Companion Settings
        ttk.Label(scrollable_frame, text="Companion Settings", style='Heading.TLabel').grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        row += 1

        ttk.Label(scrollable_frame, text="Default Personality").grid(row=row, column=0, sticky=tk.W, pady=6, padx=(15, 10))
        personality_choices = list(PERSONALITIES.keys())
        p_var = tk.StringVar(value=self.config_data.get("default_personality", "Scout"))
        self.vars["default_personality"] = p_var
        p_combo = ttk.Combobox(scrollable_frame, textvariable=p_var, values=personality_choices, state="readonly", width=30)
        p_combo.grid(row=row, column=1, sticky=tk.W, pady=6, padx=5)
        row += 1

    def _toggle_master_mode(self, event):
        enabled = self.vars["use_master_model"].get()
        state = "disabled" if enabled else "readonly"
        for combo in self.model_combos:
            combo.configure(state=state)

    def _build_advanced_tab(self, parent: ttk.Frame):
        canvas = tk.Canvas(parent, bg="#1a1a1a", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=15)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        scrollable_frame.columnconfigure(0, weight=0)
        scrollable_frame.columnconfigure(1, weight=0)
        scrollable_frame.columnconfigure(2, weight=1)

        row = 0

        # Helper method to create a slider with entry and optional checkbox grouped right next to it
        def add_slider_row(section_label_text, check_label_key_tuple, slider_key, label_text, min_val, max_val, resolution):
            nonlocal row
            # If section header is provided, create subsection header
            if section_label_text:
                ttk.Label(scrollable_frame, text=section_label_text, style='Heading.TLabel').grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(10, 8))
                row += 1

            # Optional checkbox toggle row
            if check_label_key_tuple:
                chk_text, chk_key = check_label_key_tuple
                c_var = tk.BooleanVar(value=bool(self.config_data.get(chk_key, False)))
                self.vars[chk_key] = c_var
                chk = ttk.Checkbutton(scrollable_frame, text=chk_text, variable=c_var)
                chk.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=4, padx=(15, 0))
                row += 1

            # Slider row
            pad_left = 15
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=(pad_left, 10))

            val = self.config_data.get(slider_key, min_val)
            is_int = isinstance(min_val, int) and isinstance(max_val, int)

            var = tk.IntVar(value=int(val)) if is_int else tk.DoubleVar(value=float(val))
            self.vars[slider_key] = var

            entry = ttk.Entry(scrollable_frame, width=8)
            entry.insert(0, str(val))
            entry.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

            scale = ttk.Scale(scrollable_frame, from_=min_val, to=max_val, orient=tk.HORIZONTAL, variable=var, length=220)
            scale.grid(row=row, column=2, sticky="ew", pady=5, padx=5)

            # Bi-directional sync between scale and entry box
            def make_sync(v, e, integer_mode):
                def on_var_change(*args):
                    try:
                        new_v = v.get()
                        e.delete(0, tk.END)
                        e.insert(0, str(int(new_v) if integer_mode else round(new_v, 2)))
                    except Exception:
                        pass
                return on_var_change

            var.trace_add("write", make_sync(var, entry, is_int))

            def make_entry_sync(v, e, min_v, max_v, integer_mode):
                def on_entry_focus_out(event):
                    try:
                        text_val = e.get()
                        num = int(text_val) if integer_mode else float(text_val)
                        num = max(min_v, min(max_v, num))
                        v.set(num)
                    except Exception:
                        pass
                return on_entry_focus_out

            entry.bind("<FocusOut>", make_entry_sync(var, entry, min_val, max_val, is_int))
            entry.bind("<Return>", make_entry_sync(var, entry, min_val, max_val, is_int))

            row += 1

        # Subsection 1: Cooldown & Timing
        add_slider_row("Cooldown & Timing Controls", ("Enable Cooldown Processing", "enable_cooldown"),
                       "cooldown_seconds", "Cooldown Seconds", 0.1, 10.0, 0.1)

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1

        # Subsection 2: Stability & Change Detection Thresholds
        add_slider_row("Stability & Change Detection", ("Enable Stability Check", "enable_stability_check"),
                       "stability_threshold_percent", "Stability Threshold %", 0.1, 20.0, 0.1)
        
        # Additional sliders under Change Detection subsection
        add_slider_row(None, None, "threshold_percent", "Change Threshold %", 0.1, 50.0, 0.1)
        add_slider_row(None, None, "pixel_diff_threshold", "Pixel Diff Threshold", 1, 255, 1)
        add_slider_row(None, None, "major_change_threshold", "Major Change Threshold %", 1.0, 100.0, 0.5)

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1

        # Subsection 3: Vision Processing & Matching
        add_slider_row("Vision Processing & Matching", ("Use Structural Similarity (SSIM)", "use_ssim"),
                       "match_threshold", "Screen Match Threshold", 0.5, 1.0, 0.01)
        add_slider_row(None, None, "draft_match_threshold", "Draft Match Threshold", 0.5, 1.0, 0.01)

        # Downscaling checkbox + spinbox
        c_downscale = tk.BooleanVar(value=bool(self.config_data.get("enable_downscaling", False)))
        self.vars["enable_downscaling"] = c_downscale
        ttk.Checkbutton(scrollable_frame, text="Enable Frame Downscaling", variable=c_downscale).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(8, 4), padx=(15, 0))
        row += 1

        ttk.Label(scrollable_frame, text="Max Downscale Size").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(15, 10))
        downscale_var = tk.IntVar(value=int(self.config_data.get("downscale_max_size", 300)))
        self.vars["downscale_max_size"] = downscale_var
        ttk.Spinbox(scrollable_frame, from_=300, to=3840, textvariable=downscale_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        row += 1

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1

        # Subsection 4: AI Reasoning & Capacities
        ttk.Label(scrollable_frame, text="AI Reasoning & Buffers", style='Heading.TLabel').grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(5, 8))
        row += 1

        thinking_choices = [lvl.upper() for lvl in get_available_thinking_levels()]

        use_master_t_var = tk.BooleanVar(value=bool(self.config_data.get("use_master_thinking_level", False)))
        self.vars["use_master_thinking_level"] = use_master_t_var
        master_t_chk = ttk.Checkbutton(scrollable_frame, text="Use Master Thinking Level for All Components", variable=use_master_t_var, command=lambda: self._toggle_master_thinking_mode(master_t_chk))
        master_t_chk.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=4, padx=(15, 0))
        row += 1

        ttk.Label(scrollable_frame, text="Master Thinking Level").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(15, 10))
        master_t_var = tk.StringVar(value=str(self.config_data.get("master_thinking_level", "LOW")).upper())
        self.vars["master_thinking_level"] = master_t_var
        master_t_combo = ttk.Combobox(scrollable_frame, textvariable=master_t_var, values=thinking_choices, state="readonly", width=12)
        master_t_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        row += 1

        ttk.Label(scrollable_frame, text="Default Thinking Level").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(15, 10))
        t_var = tk.StringVar(value=str(self.config_data.get("thinking_level", "LOW")).upper())
        self.vars["thinking_level"] = t_var
        ttk.Combobox(scrollable_frame, textvariable=t_var, values=thinking_choices, state="readonly", width=12).grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        row += 1

        comp_thinking = [
            ("Scribe Thinking Level", "scribe_thinking_level"),
            ("Ally Thinking Level", "ally_thinking_level"),
            ("Narrative Thinking Level", "narrative_thinking_level"),
            ("Personality Thinking Level", "personality_thinking_level"),
            ("Genealogy Thinking Level", "geneology_thinking_level"),
        ]

        self.thinking_combos = []
        for label_text, key in comp_thinking:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=(15, 10))
            var = tk.StringVar(value=str(self.config_data.get(key, "LOW")).upper())
            self.vars[key] = var
            combo = ttk.Combobox(scrollable_frame, textvariable=var, values=thinking_choices, state="readonly", width=12)
            combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
            self.thinking_combos.append(combo)
            row += 1

        self._toggle_master_thinking_mode(None)

        spinboxes = [
            ("Unknown Streak Threshold", "unknown_streak_threshold", 1, 10),
            ("Short-Term Buffer Capacity", "short_term_capacity", 2, 30),
        ]

        for label_text, key, min_v, max_v in spinboxes:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=(15, 10))
            var = tk.IntVar(value=int(self.config_data.get(key, min_v)))
            self.vars[key] = var
            ttk.Spinbox(scrollable_frame, from_=min_v, to=max_v, textvariable=var, width=10).grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
            row += 1

    def _toggle_master_thinking_mode(self, event):
        enabled = self.vars["use_master_thinking_level"].get()
        state = "disabled" if enabled else "readonly"
        for combo in getattr(self, "thinking_combos", []):
            combo.configure(state=state)

    def _save_settings(self):
        new_config = self.config_data.copy()
        for key, var in self.vars.items():
            try:
                new_config[key] = var.get()
            except Exception:
                pass
        save_user_config(new_config)
        if self.on_save_callback:
            try:
                self.on_save_callback()
            except Exception:
                pass
        self.destroy()
