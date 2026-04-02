"""
Phase 2 — The Playback Engine

Adds to Phase 1: BPM-aware crossfade, audio features, EQ browser UI,
TTS feedback, and a Flask+SocketIO server pushing real-time state.

Run: python dj_phase2.py
Then open http://127.0.0.1:5000 in your browser for the DJ UI.
"""

import os
import sys
import signal
import threading
import time

from dotenv import load_dotenv
load_dotenv()

# ── Import Phase 1 pipeline ───────────────────────────────────────────────

from dj_phase1 import (
    get_whisper_pipe, get_spotify, record_audio, transcribe,
    validate_transcript, build_messages, call_claude, parse_response,
    _find_active_device, _queued_uris, claude,
    SAMPLE_RATE,
)

# ── Flask + SocketIO ──────────────────────────────────────────────────────

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

app = Flask(__name__, static_folder=".")
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return send_from_directory(".", "dj_ui.html")


# ── TTS (pyttsx3) — runs in its own thread to avoid blocking ─────────────

import pyttsx3

_tts_lock = threading.Lock()
_tts_engine = None

def _get_tts():
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 170)
    return _tts_engine

def speak(text: str):
    """Speak text aloud in a background thread."""
    def _run():
        with _tts_lock:
            engine = _get_tts()
            engine.say(text)
            engine.runAndWait()
    threading.Thread(target=_run, daemon=True).start()


# ── Phase 2 System Prompt (extends Phase 1 with crossfade/energy fields) ──

PHASE2_SYSTEM_PROMPT = """You are an AI DJ assistant. The user will describe a vibe, mood, or music request via voice.

Your job:
1. Parse the spoken vibe into structured musical intent.
2. Build Spotify search query strings that will find the right tracks.
3. Return 3-5 track recommendations.
4. Suggest crossfade timing and energy trajectory for smooth DJ transitions.

You MUST respond with ONLY a JSON object (no markdown fences, no extra text) in this exact shape:
{
  "tracks": [
    {
      "search_query": "artist name track title",
      "title_hint": "Track Title",
      "artist_hint": "Artist Name",
      "reason": "Why this fits the vibe",
      "estimated_bpm": 120,
      "estimated_energy": 0.7,
      "estimated_valence": 0.6
    }
  ],
  "spoken_summary": "A short sentence to read aloud, e.g. 'Queuing up some late-night lo-fi for you'",
  "intent": {
    "genres": ["genre1"],
    "mood": "the mood",
    "energy_level": 5,
    "era_hint": "2010s or any era",
    "tempo_hint": "slow/medium/fast"
  },
  "suggested_crossfade_ms": 8000,
  "energy_trajectory": "build",
  "key_compatibility_note": "Brief note about key/harmonic flow between tracks"
}

Rules:
- search_query should be "artist title" format for best Spotify search results.
- Recommend REAL songs by REAL artists.
- energy_level is 1-10 (1 = ambient, 10 = mosh pit).
- energy_trajectory must be one of: "build", "sustain", or "wind_down".
- suggested_crossfade_ms: how long the crossfade should be (3000-12000ms).
- estimated_bpm: your best guess of the track's BPM (integer).
- estimated_energy: 0.0-1.0, how intense/energetic the track is.
- estimated_valence: 0.0-1.0, how positive/happy the track sounds.
- Always include spoken_summary — it will be read aloud via TTS.
- Return ONLY the JSON object. No explanation, no markdown."""


# ── Audio Features + Crossfade Logic ──────────────────────────────────────

def features_from_claude(track_data: dict) -> dict:
    """Extract Claude's estimated audio features from the track recommendation."""
    return {
        "bpm": track_data.get("estimated_bpm", 0),
        "key": -1,
        "energy": track_data.get("estimated_energy", 0),
        "valence": track_data.get("estimated_valence", 0),
        "danceability": 0,
    }


def calculate_crossfade_ms(bpm_current: int, bpm_next: int, suggested_ms: int = 8000) -> int:
    """Larger BPM delta → longer crossfade to smooth the transition."""
    bpm_delta = abs(bpm_current - bpm_next)
    calculated = 5000 + (bpm_delta * 100)  # +100ms per BPM difference
    calculated = max(3000, min(calculated, 12000))
    # Blend with Claude's suggestion
    return (calculated + suggested_ms) // 2


# ── Session State ─────────────────────────────────────────────────────────

class DJSession:
    """Holds the current session's playback state, shared across threads."""
    def __init__(self):
        self.current_track = None      # {title, artist, reason, uri, features}
        self.queue = []                 # upcoming tracks with features
        self.history = []               # already-played tracks
        self.crossfade_ms = 8000
        self.energy_trajectory = "sustain"
        self.is_running = True

session = DJSession()


# ── Layer 5 (Phase 2): Validate, Queue, Fetch Features ────────────────────

def validate_and_queue_p2(data: dict, sp) -> list[dict]:
    """Phase 2 version: searches Spotify, validates, queues, and fetches audio features."""
    tracks = data["tracks"]
    if not isinstance(tracks, list) or len(tracks) < 1:
        raise ValueError("Expected at least 1 track recommendation.")
    if len(tracks) > 5:
        tracks = tracks[:5]

    device_id = None
    if sp is not None:
        device_id = _find_active_device(sp)
        if device_id is None:
            print("   ⚠  No active Spotify device — showing recommendations only.")
            print("      Open Spotify and play anything, then try again.\n")
            sp = None

    queued = []
    first_track = True

    for t in tracks:
        search_query = t.get("search_query", "")
        reason = t.get("reason", "")
        title_hint = t.get("title_hint", "Unknown")
        artist_hint = t.get("artist_hint", "Unknown")

        if sp is None:
            queued.append({
                "title": title_hint, "artist": artist_hint,
                "reason": reason, "uri": None, "features": features_from_claude(t),
            })
            continue

        try:
            results = sp.search(q=search_query, type="track", limit=3)
            items = results["tracks"]["items"]
            if not items:
                print(f"   ⚠  No Spotify result for: {search_query}")
                continue

            found = items[0]
            uri = found["uri"]
            track_id = found["id"]
            title = found["name"]
            artist = found["artists"][0]["name"]
            duration_ms = found["duration_ms"]
            album_art = found["album"]["images"][0]["url"] if found["album"]["images"] else None

            if duration_ms < 90_000:
                print(f"   ⚠  Skipping '{title}' — too short ({duration_ms // 1000}s)")
                continue
            if uri in _queued_uris:
                print(f"   ⚠  Skipping '{title}' — already queued this session")
                continue

            features = features_from_claude(t)

            if first_track:
                sp.start_playback(device_id=device_id, uris=[uri])
                first_track = False
            else:
                sp.add_to_queue(uri)

            _queued_uris.add(uri)

            track_info = {
                "title": title, "artist": artist, "reason": reason,
                "uri": uri, "features": features, "duration_ms": duration_ms,
                "album_art": album_art,
            }
            queued.append(track_info)

        except Exception as e:
            print(f"   ⚠  Spotify error for '{search_query}': {e}")

    return queued


# ── Playback Monitor Thread ───────────────────────────────────────────────
# Polls Spotify every 2s, pushes state to the browser, warns before crossfade.

def playback_monitor(sp):
    """Background thread: polls Spotify and pushes updates via SocketIO."""
    warned_crossfade = False

    while session.is_running:
        try:
            if sp is None:
                time.sleep(2)
                continue

            playback = sp.current_playback()
            if playback and playback.get("item"):
                item = playback["item"]
                progress_ms = playback.get("progress_ms", 0)
                duration_ms = item.get("duration_ms", 0)
                remaining_ms = duration_ms - progress_ms

                album_art = item["album"]["images"][0]["url"] if item["album"]["images"] else None

                # Use Claude's estimates from the session if available
                cur = session.current_track or {}
                feat = cur.get("features") or {}

                state = {
                    "title": item["name"],
                    "artist": item["artists"][0]["name"],
                    "album_art": album_art,
                    "progress_ms": progress_ms,
                    "duration_ms": duration_ms,
                    "bpm": feat.get("bpm", 0),
                    "energy": feat.get("energy", 0),
                    "valence": feat.get("valence", 0),
                    "key": feat.get("key", -1),
                    "crossfade_ms": session.crossfade_ms,
                    "energy_trajectory": session.energy_trajectory,
                    "is_playing": playback.get("is_playing", False),
                    "reason": session.current_track.get("reason", "") if session.current_track else "",
                }

                socketio.emit("playback_state", state)

                # Crossfade warning 5s before track ends
                if remaining_ms < (session.crossfade_ms + 5000) and not warned_crossfade:
                    speak("Crossfading in 5...")
                    socketio.emit("crossfade_warning", {"remaining_ms": remaining_ms})
                    warned_crossfade = True

                # Reset warning flag when a new track starts
                if remaining_ms > 30000:
                    warned_crossfade = False

        except Exception as e:
            # Spotify polling can fail transiently
            pass

        time.sleep(2)


# ── Output ────────────────────────────────────────────────────────────────

def print_and_announce(queued: list[dict], data: dict, has_spotify: bool):
    """Print results and speak the summary via TTS."""
    spoken_summary = data.get("spoken_summary", "Here are your tracks.")

    if not queued:
        print("\nNo tracks could be queued. Try a different vibe.\n")
        return

    if has_spotify:
        print(f"\n🎧 {spoken_summary}\n")
    else:
        print(f"\n🎵 {spoken_summary} (recommendation-only)\n")

    for i, t in enumerate(queued, 1):
        status = "Now playing" if i == 1 and t["uri"] else ("Queued" if t["uri"] else "Recommended")
        bpm_str = f" [{t['features']['bpm']} BPM]" if t.get("features") and t["features"]["bpm"] else ""
        print(f"  {i}. {t['title']} — {t['artist']}{bpm_str}")
        print(f"     {status}: {t['reason']}\n")

    # Update session state
    if queued:
        session.current_track = queued[0]
        session.queue = queued[1:]
        session.crossfade_ms = data.get("suggested_crossfade_ms", 8000)
        session.energy_trajectory = data.get("energy_trajectory", "sustain")

        # Push the full queue to the browser
        socketio.emit("queue_update", {
            "current": queued[0],
            "upcoming": queued[1:],
            "crossfade_ms": session.crossfade_ms,
            "energy_trajectory": session.energy_trajectory,
        })

    # TTS
    speak(spoken_summary)


# ── Voice Input Loop (runs in its own thread) ─────────────────────────────

def voice_loop(sp):
    """ENTER-to-record loop — same as Phase 1 but uses Phase 2 pipeline."""
    print("Press ENTER to start recording, CTRL+C to quit.\n")

    while session.is_running:
        try:
            input("▶  ENTER to record → ")
        except EOFError:
            break

        try:
            audio = record_audio()
            transcript = transcribe(audio)
            print(f"   You said: \"{transcript}\"")
            transcript = validate_transcript(transcript)

            messages = build_messages(transcript)

            print("   Asking Claude for recommendations…")
            raw = call_claude(messages, system_prompt=PHASE2_SYSTEM_PROMPT)

            data = parse_response(raw)

            queued = validate_and_queue_p2(data, sp)

            print_and_announce(queued, data, sp is not None)

        except ValueError as e:
            print(f"\n   Error: {e}\n")
        except Exception as e:
            print(f"\n   Unexpected error: {e}\n")

        print("-" * 50)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, lambda *_: (
        setattr(session, 'is_running', False),
        print("\n\nGoodbye!"),
        sys.exit(0),
    ))

    print("=" * 50)
    print("  AI DJ — Phase 2: The Playback Engine")
    print("  Open http://127.0.0.1:5000 for the DJ UI")
    print("=" * 50)
    print()

    sp = get_spotify()

    # Start playback monitor in background
    monitor_thread = threading.Thread(target=playback_monitor, args=(sp,), daemon=True)
    monitor_thread.start()

    # Start voice input loop in background thread
    voice_thread = threading.Thread(target=voice_loop, args=(sp,), daemon=True)
    voice_thread.start()

    # Run Flask+SocketIO on main thread
    socketio.run(app, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
