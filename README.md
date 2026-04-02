# AI DJ Bot

A voice-controlled, gesture-driven DJ system that turns spoken vibes into Spotify playback — controlled by your hands through a webcam.

Say something like *"play me something chill and jazzy"* and the AI DJ queues real tracks on Spotify. Then use hand gestures to control volume, crossfade, skip tracks, and sweep a filter — all by interacting with a virtual ball on your camera feed.

## Architecture

Built on a **5-layer LLM Sandwich pipeline** that runs on every voice request:

1. **Input Validation** — reject empty/short transcripts before spending API tokens
2. **Prompt Construction** — format the transcript into Claude system + user messages
3. **LLM Call** — Claude Sonnet interprets the vibe, returns structured JSON with track recommendations
4. **Output Parsing** — extract and validate JSON from Claude's response
5. **Business Validation** — search Spotify, reject short tracks and duplicates, queue valid tracks

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Speech-to-Text | openai/whisper-large-v3 via HuggingFace Transformers (local) |
| LLM | Claude Sonnet via Anthropic SDK |
| Music | Spotify Web API via spotipy |
| Hand Tracking | MediaPipe Hands (Python) |
| UI | Flask + SocketIO + vanilla JS + Web Audio API |
| TTS | pyttsx3 |

## Phases

### Phase 1 — The Voice Brain (`dj_phase1.py`)

The MVP: voice in → Claude interprets vibe → Spotify tracks queued and playing.

- Records 5s of mic audio at 16kHz mono via `sounddevice`
- Transcribes locally with Whisper large-v3 (downloads ~3GB on first run)
- Claude parses the vibe and returns Spotify search queries + track recommendations
- Searches Spotify, validates tracks, and queues them (first track uses `start_playback`, rest use `add_to_queue`)
- Falls back to recommendation-only mode if Spotify credentials are missing or no active device is found

### Phase 2 — The Playback Engine (`dj_phase2.py` + `dj_ui.html`)

Adds a browser-based DJ dashboard and real-time playback monitoring.

- Flask + SocketIO server pushes playback state to the browser every 2s
- Claude estimates BPM, energy, and valence for each recommended track
- Crossfade logic: base 5s + 100ms per BPM difference between tracks (capped 3–12s)
- Browser UI: now playing card with spinning vinyl, BPM/energy/vibe stats, animated waveform, EQ sliders, upcoming queue
- TTS via pyttsx3 speaks Claude's summary after each queue and warns before crossfades

### Phase 3 — The Hand Turntable (`dj_phase3.py`)

MediaPipe Hands becomes the physical DJ controller via an interactive ball in the camera view.

- Python runs hand detection and sends raw landmarks to the browser via SocketIO
- Browser renders a glowing ball on the webcam canvas overlay
- All gesture detection happens client-side in JavaScript
- Browser sends commands back to Python, which executes Spotify API calls
- Values freeze at their last state when hands leave the frame (no snapping to zero)

**Gesture controls (interact with the ball):**

| Gesture | Action |
|---------|--------|
| Grab + drag ball up/down | Volume |
| Grab + drag ball left/right | Crossfade |
| Two hands stretch apart (near ball) | Open filter (200→8000 Hz) |
| Two hands squeeze together | Close filter |
| Pinch (thumb + index) near ball | Skip track |
| Closed fist near ball | Pause / Play |

## Setup

### Prerequisites

- Python 3.10+
- A Spotify Premium account with an active device (phone, desktop, or web player)
- A registered Spotify app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
  - Redirect URI set to `http://127.0.0.1:8888/callback`
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
- A webcam (for Phase 3 hand tracking)

### Install

```bash
pip install -r requirements.txt
```

### Configure

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=your-key-here
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret
```

### Run

**Phase 1 only** (voice → Spotify, no UI):
```bash
python3 dj_phase1.py
```

**Phase 2** (voice → Spotify + browser DJ dashboard):
```bash
python3 dj_phase2.py
# Open http://127.0.0.1:5000
```

**Phase 3 — full experience** (voice + hands + browser):
```bash
python3 dj_phase3.py
# Open http://127.0.0.1:5000
# Webcam window opens for hand tracking
# Press ENTER in terminal to record voice
# ESC in webcam window or CTRL+C to quit
```

The first run will:
- Open your browser for Spotify OAuth login
- Download the Whisper model (~3GB)
- Download the MediaPipe hand landmarker model (~10MB)

After the first run, everything is cached locally.

## File Structure

```
dj_phase1.py          — Voice brain: STT → Claude → Spotify (5-layer pipeline)
dj_phase2.py          — Playback engine: Flask server, TTS, playback monitor
dj_phase3.py          — Hand turntable: MediaPipe + SocketIO gesture bridge
dj_ui.html            — Browser DJ UI: ball interaction, skeleton overlay, controls
recommender_nmahm3.py — Original terminal recommender (CS398 Week 3)
requirements.txt      — All Python dependencies
.env.example          — Template for API credentials
```

## Origin

Started as a terminal-based music recommender for CS398 Applied LLMs (`recommender_nmahm3.py`), using a local llama.cpp server. Evolved into a full voice + gesture DJ system powered by Claude and Spotify.
