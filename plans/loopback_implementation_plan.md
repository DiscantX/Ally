# Implementation Plan: Game Audio Loopback & Echo Cancellation for Gemini Live Companion

## 1. Objective & System Architecture
The goal of this implementation is to upgrade the current voice-driven game companion from a **Text-In/Audio-Out** system to a fully multimodal **Text+Audio-In/Audio-Out** system. 

### Current State
* **Input:** User voice is processed **locally** via **Vosk STT** to completely bypass Gemini audio input token billing and avoid background noise triggers. Only clean text strings are sent to Gemini.
* **Output:** Gemini returns native audio streams, which are handled via a gapless, callback-driven `AudioPlayer`.

### Proposed Target State
* **The Goal:** Allow the Gemini model to natively hear the game's audio environment, sound effects (SFX), and music to provide context-aware commentary.
* **The Challenge:** Because the game audio must be captured from the system's output mix (Loopback), the stream will naturally capture Gemini's own voice as well. If sent unfiltered, this creates an **acoustic feedback loop**, causing the model to interrupt itself or echo endlessly.
* **The Solution:** Implement a programmatic, **zero-installation software loopback** using `pyaudiowpatch` and pass the stream through an adaptive acoustic echo cancellation (AEC) filter via `pywebrtc-audio` before routing it to the Gemini Live WebSocket.

---

## 2. Technical Stack & Constraints
* **Audio Capture:** `pyaudiowpatch` (A PyAudio fork unlocking native Windows WASAPI / host-level loopback interfaces without requiring external virtual audio cables or admin/root installation).
* **Echo Cancellation Engine:** `pywebrtc-audio` (Uses Google Chrome's native C++ WebRTC Audio Processing Module to dynamically track lag, frame jitter, and cancel reference signals).
* **Data Flow Constraint:** The Gemini Live API accepts only **one** audio input stream per WebSocket connection. The loopback stream must handle game audio streaming, while user commands remain handled by the local Vosk text injection channel.

---

## 3. Vertical Slices Implementation Roadmap

To develop this feature safely without breaking the current snappy framework, implement the changes using the following four vertical slices.

### 🎚️ Slice 4.1: Local System Loopback Pipeline (No Cloud Connection)
* **Objective:** Verify that the system can programmatically hook into the computer's master audio output line without crackling, stuttering, or dropping frames.
* **Tasks:**
  1. Add `pyaudiowpatch` as a project dependency.
  2. Write automated device discovery logic to scan system APIs, locate the default multimedia output device, and isolate its corresponding sub-indexed **Loopback/What U Hear** device interface.
  3. Spin up an independent input stream thread using a callback framework.
  4. Convert the incoming buffers into a structured `numpy` array (`int16` PCM) and write them directly to a local diagnostic `.wav` file.
* **Verification:** Run a game or play music locally for 10 seconds. Check the output `.wav` file; it must contain a flawless, uncorrupted, crystal-clear clone of the desktop audio.

### 🔌 Slice 4.2: The Live Audio Cloud Stream (The "Echo Trap")
* **Objective:** Establish the raw data pipeline to Gemini's WebSocket alongside our current local Vosk processing loop.
* **Tasks:**
  1. Route the raw byte blocks fetched from the `pyaudiowpatch` callback directly up to the active Gemini Live WebSocket connection using `session.send()`.
  2. Set the appropriate audio MIME type configuration (`audio/pcm;rate=16000` or matching system sample rate).
  3. Ensure the local Vosk text-generation listener continues to interleave text payloads seamlessly.
* **Verification:** Trigger loud game audio or music. Gemini should immediately begin dynamically generating voice audio analyzing the gameplay sounds. *Note:* The companion will enter an aggressive acoustic feedback loop at this stage—this confirms the pipeline is successful.

### 🧠 Slice 4.3: Playback Reference Tracking
* **Objective:** Isolate Gemini's own output voice at the exact microsecond of playback so it can be used as a reference mask.
* **Tasks:**
  1. Modify the custom gapless `AudioPlayer` class implementation.
  2. In the `_callback` routine where PCM chunks are sliced out of the `_chunks` deque for hardware output, mirror those exact frames out to a public tracking ring buffer or getter method (e.g., `get_current_playing_block(frame_count)`).
  3. Match and reconcile sample rates. If the game loopback runs at 44.1kHz or 48kHz, but Gemini's output or input layers operate at 24kHz/16kHz, integrate an inline downsampler/resampler.
* **Verification:** Log or print the frame sizes and arrays of the reference channel while Gemini speaks to confirm it mirrors the active audio payload.

### 🧹 Slice 4.4: WebRTC Adaptive Audio Filtering
* **Objective:** Blend the reference and master streams through the WebRTC engine to erase Gemini's voice in real time.
* **Tasks:**
  1. Initialize the `pywebrtc-audio` Audio Processing Module (`APM`) with `enable_aec=True`.
  2. Inside the `pyaudiowpatch` master loopback callback loop, pass Gemini's matching playback reference chunk into `apm.analyze_reverse_stream()`.
  3. Pass the uncleaned master desktop audio chunk directly through `apm.process_stream()`. The underlying C++ layer will automatically calculate variable system lag, align the waveforms, and cancel out Gemini's vocal pattern.
  4. Forward the output `cleaned_audio_bytes` up to the Gemini live session.
* **Verification:** Engage in a conversation with the companion while high-intensity game music is blasting. The model should accurately hear and comment on the player's voice and game audio, but completely ignore its own spoken output—permanently resolving the echo loop without requiring physical device reconfiguration.