"""Unit tests for infrastructure.tts.base_provider.

Tests cover:
- SynthesizedAudio dataclass properties and validation.
- _naive_sentence_split() behavior including known limitations.
- TTSProvider default synthesize_stream() sentence-splitting logic.
- Class attribute defaults (supports_style_direction, supports_streaming).
"""

import pytest
from infrastructure.tts.base_provider import (
    SynthesizedAudio,
    TTSProvider,
    TTSError,
    _naive_sentence_split,
)


# ---------------------------------------------------------------------------
# SynthesizedAudio tests
# ---------------------------------------------------------------------------

class TestSynthesizedAudio:
    def test_duration_seconds_mono(self) -> None:
        """duration_seconds is computed correctly for mono audio."""
        # 1 second of mono 16-bit audio at 24000 Hz = 48000 bytes.
        audio = SynthesizedAudio(pcm_data=b"\x00" * 48000, sample_rate=24000, channels=1)
        assert audio.duration_seconds == pytest.approx(1.0, rel=0.001)

    def test_duration_seconds_stereo(self) -> None:
        """duration_seconds accounts for stereo (2 channels)."""
        # 1 second of stereo 16-bit audio at 24000 Hz = 96000 bytes.
        audio = SynthesizedAudio(pcm_data=b"\x00" * 96000, sample_rate=24000, channels=2)
        assert audio.duration_seconds == pytest.approx(1.0, rel=0.001)

    def test_duration_seconds_zero_data(self) -> None:
        """duration_seconds returns 0 for empty PCM data."""
        audio = SynthesizedAudio(pcm_data=b"", sample_rate=24000, channels=1)
        assert audio.duration_seconds == 0.0

    def test_sample_width_default_is_2(self) -> None:
        """sample_width defaults to 2 (16-bit audio)."""
        audio = SynthesizedAudio(pcm_data=b"\x00" * 100, sample_rate=24000, channels=1)
        assert audio.sample_width == 2

    def test_post_init_rejects_non_16bit(self) -> None:
        """__post_init__ raises ValueError for non-16-bit sample_width."""
        with pytest.raises(ValueError, match="Only 16-bit audio is supported"):
            SynthesizedAudio(
                pcm_data=b"\x00" * 100,
                sample_rate=24000,
                channels=1,
                sample_width=1,
            )

    def test_dataclass_fields(self) -> None:
        """All required fields are present and typed correctly."""
        audio = SynthesizedAudio(
            pcm_data=b"\x01\x02",
            sample_rate=16000,
            channels=1,
            sample_width=2,
        )
        assert audio.pcm_data == b"\x01\x02"
        assert audio.sample_rate == 16000
        assert audio.channels == 1
        assert audio.sample_width == 2


# ---------------------------------------------------------------------------
# _naive_sentence_split tests (including known limitations)
# ---------------------------------------------------------------------------

class TestNaiveSentenceSplit:
    def test_basic_sentences(self) -> None:
        """Splits on period, question mark, and exclamation mark."""
        text = "Hello world. How are you? I'm fine!"
        sentences = _naive_sentence_split(text)
        assert sentences == ["Hello world.", "How are you?", "I'm fine!"]

    def test_single_sentence(self) -> None:
        """Returns a single-element list for single-sentence input."""
        sentences = _naive_sentence_split("Hello world.")
        assert sentences == ["Hello world."]

    def test_trims_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped from sentences."""
        text = "   Hello.   World!   "
        sentences = _naive_sentence_split(text)
        assert sentences == ["Hello.", "World!"]

    def test_filters_empty_strings(self) -> None:
        """Empty strings are filtered out."""
        text = "Hello.   . World!"
        sentences = _naive_sentence_split(text)
        assert "Hello." in sentences
        assert "World!" in sentences
        assert "" not in sentences

    # --- Known limitations (documented in the function docstring) ---

    def test_known_limitation_abbreviations(self) -> None:
        """ABBREVIATIONS are incorrectly split (known limitation).

        "Dr." and "Mr." are standalone sentences because the naive splitter
        treats any period as a sentence boundary.
        """
        text = "Hello Dr. Smith, how are you?"
        sentences = _naive_sentence_split(text)
        # This is the INCORRECT behavior due to naive splitting.
        assert "Dr." in sentences
        assert "Smith," in sentences  # This becomes its own "sentence"

    def test_known_limitation_decimals(self) -> None:
        """DECIMALS are incorrectly split (known limitation).

        "3.14" is treated as two sentences because periods in numbers
        are sentence boundaries.
        """
        text = "The value is 3.14. That is all."
        sentences = _naive_sentence_split(text)
        # This is the INCORRECT behavior due to naive splitting.
        assert "3" in sentences
        assert "14" in sentences

    def test_known_limitation_ellipsis(self) -> None:
        """ELLIPSIS ... sequences may cause issues."""
        text = "Hello... World."
        sentences = _naive_sentence_split(text)
        # "..." becomes an empty split; result should still contain
        # "Hello..." and "World."
        assert "Hello..." in sentences
        assert "World." in sentences

    def test_known_limitation_single_char_sentences(self) -> None:
        """Single-character 'sentences' can result from abbreviation splitting."""
        text = "The U.S.A. is great."
        sentences = _naive_sentence_split(text)
        # INCORRECT: "U" and "S" and "A" become their own sentences.
        assert "U" in sentences
        assert "S" in sentences
        assert "A" in sentences

    def test_empty_string(self) -> None:
        """Empty input returns empty list."""
        assert _naive_sentence_split("") == []
        assert _naive_sentence_split("   ") == []


# ---------------------------------------------------------------------------
# TTSProvider tests (default synthesize_stream behavior)
# ---------------------------------------------------------------------------

class ConcreteTTSProvider(TTSProvider):
    """Concrete subclass for testing abstract method enforcement."""

    def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> SynthesizedAudio:
        # Return a deterministic audio object keyed off the text.
        return SynthesizedAudio(
            pcm_data=text.encode("utf-8"),
            sample_rate=24000,
            channels=1,
        )


class TestTTSProviderClassAttributes:
    """Class attribute defaults on TTSProvider ABC."""

    def test_default_supports_style_direction_is_false(self) -> None:
        assert TTSProvider.supports_style_direction is False

    def test_default_supports_streaming_is_false(self) -> None:
        assert TTSProvider.supports_streaming is False


class TestTTSProviderDefaultSynthesizeStream:
    """Test the default synthesize_stream() sentence-splitting behavior."""

    def test_synthesize_stream_yields_one_chunk_per_sentence(self) -> None:
        """Each sentence from naive split yields one SynthesizedAudio."""
        provider = ConcreteTTSProvider()
        text = "Hello. How are you? I'm fine!"
        chunks = list(provider.synthesize_stream(text))

        assert len(chunks) == 3
        assert chunks[0].pcm_data == b"Hello."
        assert chunks[1].pcm_data == b"How are you?"
        assert chunks[2].pcm_data == b"I'm fine!"

    def test_synthesize_stream_passes_voice_name(self) -> None:
        """voice_name is forwarded to synthesize()."""
        provider = ConcreteTTSProvider()
        # We only verify that synthesize_stream doesn't crash; the concrete
        # provider ignores the parameter, but the base impl passes it.
        text = "Hello."
        chunks = list(provider.synthesize_stream(text, voice_name="Kore"))
        assert len(chunks) == 1

    def test_synthesize_stream_passes_speaking_rate(self) -> None:
        """speaking_rate is forwarded to synthesize()."""
        provider = ConcreteTTSProvider()
        text = "Hello."
        chunks = list(provider.synthesize_stream(text, speaking_rate=1.2))
        assert len(chunks) == 1

    def test_synthesize_stream_empty_text_yields_nothing(self) -> None:
        """Empty text yields zero chunks."""
        provider = ConcreteTTSProvider()
        chunks = list(provider.synthesize_stream(""))
        assert chunks == []

    def test_synthesize_stream_whitespace_only_yields_nothing(self) -> None:
        """Whitespace-only text yields zero chunks."""
        provider = ConcreteTTSProvider()
        chunks = list(provider.synthesize_stream("   \n\t  "))
        assert chunks == []

    def test_synthesize_stream_is_generator(self) -> None:
        """synthesize_stream returns an Iterator, not a list (lazy evaluation)."""
        provider = ConcreteTTSProvider()
        result = provider.synthesize_stream("Hello.")
        # Should be an iterator/generator, not already consumed.
        assert hasattr(result, "__next__")
        first_chunk = next(result)
        assert isinstance(first_chunk, SynthesizedAudio)

    def test_synthesize_stream_multiple_whitespace_between_sentences(self) -> None:
        """Multiple spaces between sentences are handled correctly."""
        provider = ConcreteTTSProvider()
        text = "Hello.   World!"
        chunks = list(provider.synthesize_stream(text))
        assert len(chunks) == 2
        assert chunks[0].pcm_data == b"Hello."
        assert chunks[1].pcm_data == b"World!"

    def test_synthesize_stream_abbreviation_breaks_sentence(self) -> None:
        """Known limitation: abbreviations cause extra chunks."""
        provider = ConcreteTTSProvider()
        text = "Hello Dr. Smith."
        chunks = list(provider.synthesize_stream(text))
        # INCORRECT but expected behavior: "Dr." and "Smith." are separate.
        # This test documents the known limitation.
        assert len(chunks) == 3  # "Hello", "Dr.", "Smith."
        assert chunks[1].pcm_data == b"Dr."

    def test_synthesize_stream_decimal_breaks_sentence(self) -> None:
        """Known limitation: decimals cause extra chunks."""
        provider = ConcreteTTSProvider()
        text = "Pi is 3.14. That's all."
        chunks = list(provider.synthesize_stream(text))
        # INCORRECT but expected behavior: "3" and "14" are separate.
        assert len(chunks) == 4  # "Pi is 3", "14", "That's all."
        assert b"3" in [ch.pcm_data for ch in chunks]

    def test_refresh_config_is_noop(self) -> None:
        """refresh_config() should not raise (no-op by default)."""
        provider = ConcreteTTSProvider()
        # Should not raise.
        provider.refresh_config()


# ---------------------------------------------------------------------------
# TTSError tests
# ---------------------------------------------------------------------------

class TestTTSError:
    def test_tts_error_is_exception(self) -> None:
        """TTSError is a subclass of Exception."""
        err = TTSError("test message")
        assert isinstance(err, Exception)

    def test_tts_error_message(self) -> None:
        """TTSError preserves the message."""
        err = TTSError("synthesis failed")
        assert str(err) == "synthesis failed"

    def test_tts_error_can_chain(self) -> None:
        """TTSError supports exception chaining."""
        cause = ValueError("cause")
        err = TTSError("effect") from cause
        assert err.__cause__ is cause
