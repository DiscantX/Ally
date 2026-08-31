# Modular Game Audio Loopback & Acoustic Echo Cancellation (AEC) Plugin

This directory contains a standalone, third-party-ready plugin package (`gemini_speech/plugins/loopback/`) designed to capture system master audio via Windows WASAPI loopback, eliminate speaker feedback using Acoustic Echo Cancellation (AEC), and stream clean PCM audio blocks into a Gemini Live multimodal session.

## Architecture & Components

1. [`loopback.py`](loopback.py):
   - Uses `pyaudiowpatch` to scan and bind to the system's default multimedia output loopback device without requiring virtual audio cables or administrator/root privileges.
   - Runs a non-blocking background stream callback pushing int16 PCM blocks into a thread-safe queue.

2. [`filter.py`](filter.py):
   - Integrates `pyaec` (Rust-backed WebRTC Audio Processing Module) to dynamically align far-end reference audio (AI voice output) against near-end capture audio (gameplay sounds/music) and strip out speaker echo in real time.

3. [`plugin.py`](plugin.py):
   - Implements `LoopbackPluginManager` to encapsulate lifecycle management, sample rate resampling via `scipy.signal.resample`, downmixing, and 20ms micro-burst WebSocket transmission.

## Third-Party Portability

All modules are heavily docstringed with explicit type hints and zero hardcoded ties to internal game state, making them trivially portable to any Python-based audio assistant or voice pipeline.
