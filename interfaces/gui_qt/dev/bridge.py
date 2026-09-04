"""CoreBridge QObject connecting AllyCore EventHooks to Qt Signals for safe cross-thread marshalling.
"""
from typing import Optional, Any
from PySide6.QtCore import QObject, Signal
from brain.reasoning.core import AllyCore


class CoreBridge(QObject):
    """Bridges background thread EventHook emissions from AllyCore into Qt Signals.
    """
    pipeline_image_ready = Signal(str, object, str)
    debug_overlay_ready = Signal(object)
    ocr_result_ready = Signal(object)
    scribe_output_ready = Signal(object)
    ally_output_ready = Signal(object)
    status_update_ready = Signal(str, str)
    state_summary_ready = Signal(str)
    prompt_update_ready = Signal(str)
    feedback_ready = Signal(str)
    chat_message_ready = Signal(str, str)
    connection_status_ready = Signal(str)
    medium_term_ready = Signal(str)
    personality_state_ready = Signal(str)
    strategic_memory_ready = Signal(str)
    analysis_stream_begin = Signal()
    analysis_stream_chunk = Signal(str)
    analysis_stream_reset = Signal()
    analysis_stream_finalize = Signal(str)
    chat_stream_begin = Signal()
    chat_stream_chunk = Signal(str)
    chat_stream_reset = Signal()
    chat_stream_finalize = Signal(str)
    thinking_stream_begin = Signal()
    thinking_stream_chunk = Signal(str)
    thinking_stream_reset = Signal()
    thinking_stream_finalize = Signal()

    def __init__(self, core: Optional[AllyCore] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._wired_core: Optional[AllyCore] = None
        if core is not None:
            self.set_core(core)

    def set_core(self, core: AllyCore) -> None:
        if self._wired_core is core:
            return  # already wired to this exact core instance -- no-op
        self._wired_core = core
        core.on_pipeline_image.connect(self._handle_pipeline_image)
        core.on_debug_overlay.connect(self._handle_debug_overlay)
        core.on_ocr_result.connect(self._handle_ocr_result)
        core.on_scribe_output.connect(self._handle_scribe_output)
        core.on_ally_output.connect(self._handle_ally_output)
        core.on_status_update.connect(self._handle_status_update)
        core.on_state_summary.connect(self._handle_state_summary)
        core.on_prompt_update.connect(self._handle_prompt_update)
        core.on_feedback.connect(self._handle_feedback)
        core.on_chat_message.connect(self._handle_chat_message)
        core.on_connection_status.connect(self._handle_connection_status)
        core.on_medium_term.connect(self._handle_medium_term)
        core.on_personality_state.connect(self._handle_personality_state)
        core.on_strategic_memory.connect(self._handle_strategic_memory)
        core.on_analysis_stream_begin.connect(self._handle_analysis_stream_begin)
        core.on_analysis_stream_chunk.connect(self._handle_analysis_stream_chunk)
        core.on_analysis_stream_reset.connect(self._handle_analysis_stream_reset)
        core.on_analysis_stream_finalize.connect(self._handle_analysis_stream_finalize)
        core.on_chat_stream_begin.connect(self._handle_chat_stream_begin)
        core.on_chat_stream_chunk.connect(self._handle_chat_stream_chunk)
        core.on_chat_stream_reset.connect(self._handle_chat_stream_reset)
        core.on_chat_stream_finalize.connect(self._handle_chat_stream_finalize)
        core.on_thinking_stream_begin.connect(self._handle_thinking_stream_begin)
        core.on_thinking_stream_chunk.connect(self._handle_thinking_stream_chunk)
        core.on_thinking_stream_reset.connect(self._handle_thinking_stream_reset)
        core.on_thinking_stream_finalize.connect(self._handle_thinking_stream_finalize)

    # Handler methods
    def _handle_pipeline_image(self, k: str, img: Any, t: Optional[str]) -> None:
        self.pipeline_image_ready.emit(k, img, t or "")

    def _handle_debug_overlay(self, img: Any) -> None:
        self.debug_overlay_ready.emit(img)

    def _handle_ocr_result(self, payload: Any) -> None:
        self.ocr_result_ready.emit(payload)

    def _handle_scribe_output(self, payload: Any) -> None:
        self.scribe_output_ready.emit(payload)

    def _handle_ally_output(self, payload: Any) -> None:
        self.ally_output_ready.emit(payload)

    def _handle_status_update(self, s: str, t: str) -> None:
        self.status_update_ready.emit(s, t)

    def _handle_state_summary(self, summary: str) -> None:
        self.state_summary_ready.emit(summary)

    def _handle_prompt_update(self, prompt: str) -> None:
        self.prompt_update_ready.emit(prompt)

    def _handle_feedback(self, feedback: str) -> None:
        self.feedback_ready.emit(feedback)

    def _handle_chat_message(self, sender: str, msg: str) -> None:
        self.chat_message_ready.emit(sender, msg)

    def _handle_connection_status(self, stat: str) -> None:
        self.connection_status_ready.emit(stat)

    def _handle_medium_term(self, mem: str) -> None:
        self.medium_term_ready.emit(mem)

    def _handle_personality_state(self, state: str) -> None:
        self.personality_state_ready.emit(state)

    def _handle_strategic_memory(self, mem: str) -> None:
        self.strategic_memory_ready.emit(mem)

    def _handle_analysis_stream_begin(self) -> None:
        self.analysis_stream_begin.emit()

    def _handle_analysis_stream_chunk(self, chunk: str) -> None:
        self.analysis_stream_chunk.emit(chunk)

    def _handle_analysis_stream_reset(self) -> None:
        self.analysis_stream_reset.emit()

    def _handle_analysis_stream_finalize(self, analysis: str) -> None:
        self.analysis_stream_finalize.emit(analysis)

    def _handle_chat_stream_begin(self) -> None:
        self.chat_stream_begin.emit()

    def _handle_chat_stream_chunk(self, chunk: str) -> None:
        self.chat_stream_chunk.emit(chunk)

    def _handle_chat_stream_reset(self) -> None:
        self.chat_stream_reset.emit()

    def _handle_chat_stream_finalize(self, resp: str) -> None:
        self.chat_stream_finalize.emit(resp)

    def _handle_thinking_stream_begin(self) -> None:
        self.thinking_stream_begin.emit()

    def _handle_thinking_stream_chunk(self, chunk: str) -> None:
        self.thinking_stream_chunk.emit(chunk)

    def _handle_thinking_stream_reset(self) -> None:
        self.thinking_stream_reset.emit()

    def _handle_thinking_stream_finalize(self) -> None:
        self.thinking_stream_finalize.emit()
