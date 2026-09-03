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
        if core is not None:
            self.set_core(core)

    def set_core(self, core: AllyCore) -> None:
        core.on_pipeline_image.connect(lambda k, img, t: self.pipeline_image_ready.emit(k, img, t or ""))
        core.on_debug_overlay.connect(lambda img: self.debug_overlay_ready.emit(img))
        core.on_ocr_result.connect(lambda payload: self.ocr_result_ready.emit(payload))
        core.on_scribe_output.connect(lambda payload: self.scribe_output_ready.emit(payload))
        core.on_ally_output.connect(lambda payload: self.ally_output_ready.emit(payload))
        core.on_status_update.connect(lambda s, t: self.status_update_ready.emit(s, t))
        core.on_state_summary.connect(lambda summary: self.state_summary_ready.emit(summary))
        core.on_prompt_update.connect(lambda prompt: self.prompt_update_ready.emit(prompt))
        core.on_feedback.connect(lambda feedback: self.feedback_ready.emit(feedback))
        core.on_chat_message.connect(lambda sender, msg: self.chat_message_ready.emit(sender, msg))
        core.on_connection_status.connect(lambda stat: self.connection_status_ready.emit(stat))
        core.on_medium_term.connect(lambda mem: self.medium_term_ready.emit(mem))
        core.on_personality_state.connect(lambda state: self.personality_state_ready.emit(state))
        core.on_strategic_memory.connect(lambda mem: self.strategic_memory_ready.emit(mem))
        core.on_analysis_stream_begin.connect(lambda: self.analysis_stream_begin.emit())
        core.on_analysis_stream_chunk.connect(lambda chunk: self.analysis_stream_chunk.emit(chunk))
        core.on_analysis_stream_reset.connect(lambda: self.analysis_stream_reset.emit())
        core.on_analysis_stream_finalize.connect(lambda analysis: self.analysis_stream_finalize.emit(analysis))
        core.on_chat_stream_begin.connect(lambda: self.chat_stream_begin.emit())
        core.on_chat_stream_chunk.connect(lambda chunk: self.chat_stream_chunk.emit(chunk))
        core.on_chat_stream_reset.connect(lambda: self.chat_stream_reset.emit())
        core.on_chat_stream_finalize.connect(lambda resp: self.chat_stream_finalize.emit(resp))
        core.on_thinking_stream_begin.connect(lambda: self.thinking_stream_begin.emit())
        core.on_thinking_stream_chunk.connect(lambda chunk: self.thinking_stream_chunk.emit(chunk))
        core.on_thinking_stream_reset.connect(lambda: self.thinking_stream_reset.emit())
        core.on_thinking_stream_finalize.connect(lambda: self.thinking_stream_finalize.emit())
