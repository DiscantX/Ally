"""Settings Menu Window for Ally Overlay.
Provides a tabbed settings interface (Standard vs Advanced/Dev) with synchronized
sliders and entry boxes, dropdowns, and checkboxes to configure models, thresholds,
and pipeline parameters.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from configs.config_manager import load_user_config, save_user_config
from ally.personalities import PERSONALITIES


class SettingsWindow(tk.Toplevel):
    """Settings menu dialog window."""

    def __init__(self, parent: tk.Widget, on_save: Callable[[], None] | None = None):
        super().__init__(parent)
        self.title("Ally Settings & Configuration")
        self.geometry("600x550")
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.on_save_callback = on_save
        self.config_data = load_user_config()
        self.vars: dict[str, Any] = {}

        self._setup_styles()
        self._create_widgets()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')

    def _create_widgets(self):
        # Notebook for tabs
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Standard Settings
        std_frame = ttk.Frame(notebook, padding=10)
        notebook.add(std_frame, text="Standard Settings")
        self._build_standard_tab(std_frame)

        # Tab 2: Advanced / Dev Settings
        adv_frame = ttk.Frame(notebook, padding=10)
        notebook.add(adv_frame, text="Advanced / Dev Settings")
        self._build_advanced_tab(adv_frame)

        # Bottom Button Bar
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        save_btn = ttk.Button(btn_frame, text="Save & Apply", command=self._save_settings)
        save_btn.pack(side=tk.RIGHT, padx=5)

        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

    def _build_standard_tab(self, parent: ttk.Frame):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=10)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        model_choices = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]

        row = 0
        ttk.Label(scrollable_frame, text="LLM Model Selections", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1

        models = [
            ("Scribe Model", "scribe_model"),
            ("Ally Model", "ally_model"),
            ("Narrative Model", "narrative_model"),
            ("Personality Model", "personality_model"),
            ("Genealogy Model", "geneology_model"),
        ]

        for label_text, key in models:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=5)
            var = tk.StringVar(value=self.config_data.get(key, model_choices[0]))
            self.vars[key] = var
            combo = ttk.Combobox(scrollable_frame, textvariable=var, values=model_choices, state="readonly", width=25)
            combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
            row += 1

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky="ew", pady=15)
        row += 1

        ttk.Label(scrollable_frame, text="Companion Settings", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1

        ttk.Label(scrollable_frame, text="Default Personality").grid(row=row, column=0, sticky=tk.W, pady=5, padx=5)
        personality_choices = list(PERSONALITIES.keys())
        p_var = tk.StringVar(value=self.config_data.get("default_personality", "Scout"))
        self.vars["default_personality"] = p_var
        p_combo = ttk.Combobox(scrollable_frame, textvariable=p_var, values=personality_choices, state="readonly", width=25)
        p_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        row += 1

    def _build_advanced_tab(self, parent: ttk.Frame):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=10)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        row = 0
        ttk.Label(scrollable_frame, text="Vision & Change Detection Thresholds", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1

        sliders = [
            ("Change Threshold %", "threshold_percent", 0.1, 50.0, 0.1),
            ("Pixel Diff Threshold", "pixel_diff_threshold", 1, 255, 1),
            ("Major Change Threshold %", "major_change_threshold", 1.0, 100.0, 0.5),
            ("Cooldown Seconds", "cooldown_seconds", 0.1, 10.0, 0.1),
            ("Stability Threshold %", "stability_threshold_percent", 0.1, 20.0, 0.1),
            ("Screen Match Threshold", "match_threshold", 0.5, 1.0, 0.01),
            ("Draft Match Threshold", "draft_match_threshold", 0.5, 1.0, 0.01),
        ]

        for label_text, key, min_val, max_val, resolution in sliders:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=5)
            
            val = self.config_data.get(key, min_val)
            is_int = isinstance(min_val, int) and isinstance(max_val, int)
            
            var = tk.IntVar(value=int(val)) if is_int else tk.DoubleVar(value=float(val))
            self.vars[key] = var

            entry = ttk.Entry(scrollable_frame, width=8)
            entry.insert(0, str(val))
            entry.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

            scale = ttk.Scale(scrollable_frame, from_=min_val, to=max_val, orient=tk.HORIZONTAL, variable=var, length=200)
            scale.grid(row=row, column=2, sticky=tk.W, pady=5, padx=5)

            # Bi-directional sync between scale and entry box
            def make_sync(v, e, res, integer_mode):
                def on_var_change(*args):
                    try:
                        new_v = v.get()
                        e.delete(0, tk.END)
                        e.insert(0, str(int(new_v) if integer_mode else round(new_v, 2)))
                    except Exception:
                        pass
                return on_var_change

            var.trace_add("write", make_sync(var, entry, resolution, is_int))

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

        ttk.Separator(scrollable_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky="ew", pady=15)
        row += 1

        ttk.Label(scrollable_frame, text="Feature Toggles & Capacities", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1

        toggles = [
            ("Enable Cooldown", "enable_cooldown"),
            ("Enable Stability Check", "enable_stability_check"),
            ("Use SSIM", "use_ssim"),
        ]

        for label_text, key in toggles:
            var = tk.BooleanVar(value=bool(self.config_data.get(key, False)))
            self.vars[key] = var
            chk = ttk.Checkbutton(scrollable_frame, text=label_text, variable=var)
            chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5, padx=5)
            row += 1

        # Integer spinboxes for capacities
        spinboxes = [
            ("Unknown Streak Threshold", "unknown_streak_threshold", 1, 10),
            ("Short-Term Buffer Capacity", "short_term_capacity", 2, 30),
        ]

        for label_text, key, min_v, max_v in spinboxes:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=5, padx=5)
            var = tk.IntVar(value=int(self.config_data.get(key, min_v)))
            self.vars[key] = var
            spin = ttk.Spinbox(scrollable_frame, from_=min_v, to=max_v, textvariable=var, width=10)
            spin.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
            row += 1

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
