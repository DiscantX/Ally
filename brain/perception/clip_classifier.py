"""Local, zero-shot CLIP classifier (ONNX via fastembed, CPU-only, no
torch dependency). Used as a semantic pre-filter ahead of Scribe --
never as a replacement for vision/screen_classifier.py's SSIM-based
matching, which does a structurally different job (exact same-screen
identity for OCR layout routing, not general screen-type recognition).
See ally_decision_log.md for the SSIM-vs-CLIP distinction if this
comment needs more context later.

CLIP's image and text encoders are frozen, pretrained models -- nothing
here trains or fine-tunes anything. "Learning" a new category (see
vision/screen_category_store.py) only ever means "embed a new sentence
once and cache the vector," never updating the model itself.
"""

import numpy as np
from PIL import Image

from cabinet.configs.config_manager import load_user_config
from infrastructure.logger import log, timed

try:
    from fastembed import ImageEmbedding, TextEmbedding
    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False


class ClipClassifier:
    """Thin wrapper pairing fastembed's CLIP image and text towers.
    Construct once (model loading has real cost) and share the instance
    -- see ally/core.py for where this gets constructed and injected."""

    def __init__(self, image_model: str | None = None, text_model: str | None = None) -> None:
        import threading
        log("Initializing ClipClassifier...")
        config = load_user_config()
        self.enabled = config.get("clip_enabled", True) and _FASTEMBED_AVAILABLE
        if not _FASTEMBED_AVAILABLE:
            log(
                "fastembed not installed -- CLIP screen gating "
                "disabled, pipeline behaves as if this feature doesn't exist. "
                "`pip install fastembed` to enable it."
            )
            return
        if not self.enabled:
            return

        image_model_name = image_model or config.get("clip_image_model", "Qdrant/clip-ViT-B-32-vision")
        text_model_name = text_model or config.get("clip_text_model", "Qdrant/clip-ViT-B-32-text")
        
        self._image_model = None
        self._text_model = None
        self._loaded_event = threading.Event()

        def _load_models() -> None:
            try:
                log("Loading CLIP models in background (image: {img}, text: {txt})...", img=image_model_name, txt=text_model_name)
                self._image_model = ImageEmbedding(image_model_name)
                self._text_model = TextEmbedding(text_model_name)
                self._loaded_event.set()
                log("CLIP models loaded successfully in background.")
            except Exception as e:
                log("Failed to load CLIP models: {error} -- disabling CLIP gating.", error=str(e), level="error")
                self.enabled = False
                self._loaded_event.set()

        threading.Thread(target=_load_models, name="ClipModelLoader", daemon=True).start()

    def _wait_for_models(self) -> bool:
        if not self.enabled:
            return False
        if not self._loaded_event.is_set():
            log("Waiting for CLIP models to finish loading in background...")
            self._loaded_event.wait(timeout=30.0)
        return self.enabled and self._image_model is not None and self._text_model is not None

    @timed
    def encode_image(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """BGR numpy frame (as produced by ScreenCollector.capture_bgr())
        -> a single L2-normalized embedding vector, or None if disabled/
        failed. Converts to RGB PIL internally since that's the safe,
        version-stable input shape for fastembed."""
        if not self._wait_for_models():
            return None
        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        try:
            embedding = next(self._image_model.embed([pil_image]))
            return self._normalize(np.asarray(embedding))
        except Exception as e:
            log("Image encode failed: {error}", error=str(e), level="warning")
            return None

    @timed
    def encode_text(self, text: str) -> np.ndarray | None:
        """Single sentence -> a single L2-normalized embedding vector, in
        the same space as encode_image's output."""
        if not self._wait_for_models():
            return None
        try:
            embedding = next(self._text_model.embed([text]))
            return self._normalize(np.asarray(embedding))
        except Exception as e:
            log("Text encode failed: {error}", error=str(e), level="warning")
            return None

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
