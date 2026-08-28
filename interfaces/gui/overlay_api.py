"""
Public API update methods and background ETA worker for the Ally Coach Overlay.
"""

import time
import threading
import queue
from datetime import datetime
import tkinter as tk
from typing import Optional
from interfaces.gui.models import OverlayConfig, FeedbackData


class OverlayApiMixin:
    feedback_text: tk.Text
    summary_text: tk.Text
    prompt_text: tk.Text
    status_label: tk.Label
    eta_label: tk.Label
    eta_bar: tk.Canvas
    eta_bar_progress: int
    token_label: tk.Label
    token_bar: tk.Canvas
    debug_label: tk.Label
    status_dot: tk.Canvas
    _status_dot_id: int
    config_data: OverlayConfig
    _running: bool
    _feedback_entry_count: int
    _feedback_data: FeedbackData
    _ui_queue: queue.Queue
    _eta_generation: int
    _eta_start_time: Optional[float]
    _eta_thread: Optional[threading.Thread]

    def _init_dispatch_queue(self):
        """Call once from the main thread, after self._running is set."""
        self._ui_queue = queue.Queue()
        self._eta_generation = 0
        self._poll_ui_queue()

    def _poll_ui_queue(self):
        """MAIN THREAD ONLY. Drains everything queued so far."""
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                callback()
        except queue.Empty:
            pass
        if self._running:
            self.after(15, self._poll_ui_queue)

    def _dispatch(self, callback):
        """Thread-safe replacement for dispatching UI updates."""
        self._ui_queue.put(callback)

    def after(self, ms: int, func=None, *args):
        raise NotImplementedError

    @staticmethod
    def _is_scrolled_to_bottom(text_widget: tk.Text, threshold: float = 0.98) -> bool:
        """Whether the visible viewport already reaches (or is very near) the end of the text."""
        try:
            _, bottom = text_widget.yview()
        except tk.TclError:
            return True
        return bottom >= threshold

    def update_feedback(self, feedback: str):
        """Append a new coaching-feedback entry, with a timestamp header, to the scrollable history."""
        def _update():
            text = self.feedback_text
            was_at_bottom = self._is_scrolled_to_bottom(text)
            timestamp = datetime.now().strftime('%H:%M:%S')

            text.config(state=tk.NORMAL)
            if self._feedback_entry_count > 0:
                text.insert(tk.END, "\n\n")
            text.insert(tk.END, f"── {timestamp} ──\n", 'timestamp')
            text.insert(tk.END, feedback, 'body')
            text.config(state=tk.DISABLED)
            self._feedback_entry_count += 1

            if was_at_bottom:
                text.see(tk.END)

            self._feedback_data.feedback = feedback
            self._feedback_data.last_update = time.time()
            self.status_label.config(text=f"Updated: {timestamp}")
        self._dispatch(_update)

    def clear_feedback_history(self):
        """Wipe the feedback history."""
        self.feedback_text.config(state=tk.NORMAL)
        self.feedback_text.delete('1.0', tk.END)
        self.feedback_text.config(state=tk.DISABLED)
        self._feedback_entry_count = 0

    def update_prompt(self, prompt: str):
        """Update the last-prompt display."""
        def _update():
            self._feedback_data.last_prompt = prompt
            self.prompt_text.config(state=tk.NORMAL)
            self.prompt_text.delete('1.0', tk.END)
            self.prompt_text.insert(tk.END, prompt)
            self.prompt_text.config(state=tk.DISABLED)
            self.prompt_text.see('1.0')
        self._dispatch(_update)

    def update_state_summary(self, summary: str):
        """Update the State of the Game display."""
        def _update():
            self.summary_text.config(state=tk.NORMAL)
            self.summary_text.delete('1.0', tk.END)
            self.summary_text.insert(tk.END, summary)
            self.summary_text.config(state=tk.DISABLED)
            self.summary_text.see('1.0')
        self._dispatch(_update)

    def update_personality_state(self, state_text: str):
        """Update the Companion State display."""
        def _update():
            self.summary_text.config(state=tk.NORMAL)
            self.summary_text.delete('1.0', tk.END)
            self.summary_text.insert(tk.END, state_text)
            self.summary_text.config(state=tk.DISABLED)
            self.summary_text.see('1.0')
        self._dispatch(_update)

    def update_medium_term_summary(self, summary: str):
        """Append a medium-term situational summary to the coaching history with amber coloring."""
        def _update():
            text = self.feedback_text
            was_at_bottom = self._is_scrolled_to_bottom(text)
            timestamp = datetime.now().strftime('%H:%M:%S')

            text.config(state=tk.NORMAL)
            if self._feedback_entry_count > 0:
                text.insert(tk.END, "\n\n")
            text.insert(tk.END, f"── {timestamp} [MEDIUM-TERM THOUGHT] ──\n", 'timestamp')
            text.insert(tk.END, summary, 'medium')
            text.config(state=tk.DISABLED)
            self._feedback_entry_count += 1

            if was_at_bottom:
                text.see(tk.END)
        self._dispatch(_update)

    def update_strategic_memory(self, memory_text: str):
        """Update the Strategic & Long-Term Memory display."""
        def _update():
            if hasattr(self, 'strategic_text'):
                self.strategic_text.config(state=tk.NORMAL)
                self.strategic_text.delete('1.0', tk.END)
                self.strategic_text.insert(tk.END, memory_text)
                self.strategic_text.config(state=tk.DISABLED)
                self.strategic_text.see('1.0')
        self._dispatch(_update)

    def start_eta_countdown(self, seconds: int):
        """Start the ETA countdown timer."""
        self._feedback_data.eta_seconds = seconds
        self._feedback_data.is_loading = True

        self._eta_generation += 1
        my_generation = self._eta_generation

        self._eta_start_time = time.time()
        self._eta_thread = threading.Thread(
            target=self._eta_worker, args=(seconds, my_generation), daemon=True,
        )
        self._eta_thread.start()

        def _update():
            self.eta_label.config(text="0:00")
            self.eta_bar.coords(self.eta_bar_progress, 0, 0, 0, 8)
        self._dispatch(_update)

    def _eta_worker(self, total_seconds: int, generation: int):
        total = total_seconds

        for remaining in range(total, -1, -1):
            if not self._running or generation != self._eta_generation:
                return

            elapsed = total - remaining
            progress_width = int((elapsed / total) * 100) if total > 0 else 0
            mins = remaining // 60
            secs = remaining % 60
            time_str = f"{mins}:{secs:02d}"

            def _update_eta_display(remaining=remaining, progress_width=progress_width,
                                    time_str=time_str, generation=generation):
                if generation != self._eta_generation:
                    return
                self.eta_label.config(text=time_str)
                self.eta_bar.coords(
                    self.eta_bar_progress, 0, 0,
                    max(progress_width, 1) if remaining > 0 else 100, 8,
                )
                if remaining > 0:
                    self.status_label.config(text="Awaiting response...")

            self._dispatch(_update_eta_display)

            if remaining > 0:
                time.sleep(1)

        if generation != self._eta_generation:
            return

        def _finish_countdown(generation=generation):
            if generation != self._eta_generation:
                return
            self._feedback_data.is_loading = False
            self.eta_label.config(text="Ready!")
            self.status_label.config(text="Response ready!")
            self.eta_bar.coords(self.eta_bar_progress, 0, 0, 100, 8)
            self.after(3000, lambda: self.eta_label.config(text="--:--"))
            self.after(3000, lambda: self.eta_bar.coords(self.eta_bar_progress, 0, 0, 0, 8))

        self._dispatch(_finish_countdown)

    def update_tokens(self, used: int, limit: int = 200000):
        """Update token usage display."""
        self._feedback_data.tokens_used = used
        self._feedback_data.token_limit = limit

        def _update_token_display():
            percentage = (used / limit * 100) if limit > 0 else 0

            used_str = f"{used/1000:.1f}k" if used >= 1000 else str(used)
            limit_str = f"{limit/1000:.0f}k" if limit >= 1000 else str(limit)

            if percentage < 75:
                bar_color = self.config_data.success_color
            elif percentage < 90:
                bar_color = self.config_data.eta_color
            else:
                bar_color = self.config_data.error_color

            self.token_label.config(text=f"{used_str} / {limit_str}", fg=bar_color)

            bar_width = int((percentage / 100) * 90)
            self.token_bar.delete("progress")
            self.token_bar.create_rectangle(
                0, 0, max(bar_width, 1), 8, fill=bar_color, outline="", tags="progress",
            )

        self._dispatch(_update_token_display)

    def update_debug_info(self, screen_type: str, event_kind: str):
        """Update debug panel info."""
        def _update():
            self.debug_label.config(text=f"screen: {screen_type or '-'}  |  event: {event_kind or '-'}")
        self._dispatch(_update)

    def feedback_status(self, message: str):
        """Thread-safe: update status label message."""
        def _update():
            self.status_label.config(text=message)
        self._dispatch(_update)

    def set_connection_status(self, connected: bool):
        """Thread-safe: update title-bar connection status dot."""
        color = self.config_data.success_color if connected else self.config_data.error_color

        def _update():
            self.status_dot.itemconfig(self._status_dot_id, fill=color)
        self._dispatch(_update)

    def set_eta_ready(self):
        """Thread-safe: mark ETA display as complete."""
        self._eta_generation += 1
        def _update():
            self._feedback_data.is_loading = False
            self.eta_label.config(text="Ready!")
            self.eta_bar.coords(self.eta_bar_progress, 0, 0, 100, 8)
        self._dispatch(_update)

    def set_eta_error(self):
        """Thread-safe: mark ETA display as errored out."""
        self._eta_generation += 1
        def _update():
            self._feedback_data.is_loading = False
            self.eta_label.config(text="Error!")
        self._dispatch(_update)

    def is_loading(self) -> bool:
        """Check if feedback is currently loading."""
        return self._feedback_data.is_loading
