"""Quick smoke test to verify imports work."""
import sys
sys.path.insert(0, ".")

try:
    from infrastructure.stt.assembler import UtteranceAssembler
    print("OK: infrastructure.stt.assembler")
except Exception as e:
    print(f"FAIL: infrastructure.stt.assembler: {e}")

try:
    from infrastructure.stt.recognizer import SpeechRecognizer
    print("OK: infrastructure.stt.recognizer")
except Exception as e:
    print(f"FAIL: infrastructure.stt.recognizer: {e}")

try:
    from gui_qt.prod.voice_input_controller import VoiceInputController
    print("OK: gui_qt.prod.voice_input_controller")
except Exception as e:
    print(f"FAIL: gui_qt.prod.voice_input_controller: {e}")

print("Done.")
