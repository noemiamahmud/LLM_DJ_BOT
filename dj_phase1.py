"""
Phase 1 — The Voice Brain (MVP)

Voice in → Claude interprets vibe → Spotify tracks queued and playing.

5-layer pipeline:
  1. Input validation   — reject bad transcripts before hitting Claude
  2. Prompt construction — format transcript into Claude system+user messages
  3. LLM call           — Claude API with structured JSON response
  4. Output parsing      — extract JSON, handle missing fields
  5. Business validation — confirm tracks exist on Spotify, no dupes, duration check
"""

import os
import sys
import json
import signal
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

# ── Lazy-loaded heavy modules ──────────────────────────────────────────────
# Whisper is ~3 GB; defer download/load until first recording so startup is fast
# and so the script can still test Spotify auth without a GPU.

_whisper_pipe = None

def get_whisper_pipe():
    global _whisper_pipe
    if _whisper_pipe is not None:
        return _whisper_pipe

    print("Loading Whisper model (first run downloads ~3 GB)…")
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model_id = "openai/whisper-large-v3"

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
    ).to(device)
    processor = AutoProcessor.from_pretrained(model_id)

    _whisper_pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
        generate_kwargs={"language": "english"},
    )
    print("Whisper ready.\n")
    return _whisper_pipe


# ── Anthropic client ───────────────────────────────────────────────────────

import anthropic

claude = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


# ── Spotify client ─────────────────────────────────────────────────────────

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SPOTIFY_SCOPES = "user-modify-playback-state user-read-playback-state"

def get_spotify():
    """Return an authenticated Spotify client, or None if creds are missing."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("⚠  Spotify credentials not found in .env — running in recommendation-only mode.\n")
        return None
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=SPOTIFY_SCOPES,
        ))
        # Quick check: can we reach the API?
        sp.current_playback()
        return sp
    except Exception as e:
        print(f"⚠  Spotify auth failed ({e}) — running in recommendation-only mode.\n")
        return None


# ── Layer 1: Input Validation ──────────────────────────────────────────────

SAMPLE_RATE = 16_000
RECORD_SECONDS = 5

def record_audio():
    """Record RECORD_SECONDS of 16 kHz mono audio and return a numpy array."""
    print(f"🎙  Recording for {RECORD_SECONDS}s…")
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype="float32")
    sd.wait()
    print("   Done recording.")
    return audio.flatten()


def transcribe(audio: np.ndarray) -> str:
    pipe = get_whisper_pipe()
    result = pipe({"raw": audio, "sampling_rate": SAMPLE_RATE})
    return result["text"].strip()


def validate_transcript(text: str) -> str:
    """Layer 1 — reject garbage before spending Claude tokens."""
    if not text:
        raise ValueError("Empty transcript — try speaking louder.")
    if len(text) > 200:
        raise ValueError("Transcript too long (>200 chars). Keep it short.")
    if len(text.split()) < 2:
        raise ValueError("Too few words — say something like 'chill jazz' or 'upbeat indie'.")
    return text


# ── Layer 2: Prompt Construction ───────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI DJ assistant. The user will describe a vibe, mood, or music request via voice.

Your job:
1. Parse the spoken vibe into structured musical intent.
2. Build Spotify search query strings that will find the right tracks.
3. Return 3-5 track recommendations.

You MUST respond with ONLY a JSON object (no markdown fences, no extra text) in this exact shape:
{
  "tracks": [
    {
      "search_query": "artist name track title",
      "title_hint": "Track Title",
      "artist_hint": "Artist Name",
      "reason": "Why this fits the vibe"
    }
  ],
  "spoken_summary": "A short sentence to read aloud, e.g. 'Queuing up some late-night lo-fi for you'",
  "intent": {
    "genres": ["genre1"],
    "mood": "the mood",
    "energy_level": 5,
    "era_hint": "2010s or any era",
    "tempo_hint": "slow/medium/fast"
  }
}

Rules:
- search_query should be "artist title" format for best Spotify search results.
- Recommend REAL songs by REAL artists.
- energy_level is 1-10 (1 = ambient, 10 = mosh pit).
- Always include spoken_summary — it will be read aloud via TTS later.
- Return ONLY the JSON object. No explanation, no markdown."""


def build_messages(transcript: str) -> list[dict]:
    """Layer 2 — format the transcript into Claude messages."""
    return [
        {"role": "user", "content": f"The listener just said: \"{transcript}\""},
    ]


# ── Layer 3: LLM Call ─────────────────────────────────────────────────────

def call_claude(messages: list[dict], system_prompt: str = None) -> str:
    """Layer 3 — call Claude and return the raw response text."""
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt or SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


# ── Layer 4: Output Parsing ────────────────────────────────────────────────

import re

def parse_response(raw: str) -> dict:
    """Layer 4 — extract JSON from Claude's response."""
    text = raw.strip()

    # Strip markdown fences if Claude wrapped the response
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the response
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse JSON from Claude response: {text[:300]}")

    # Ensure required top-level keys exist
    if "tracks" not in data:
        raise ValueError("Claude response missing 'tracks' field.")
    if "spoken_summary" not in data:
        data["spoken_summary"] = "Here are some tracks for you."
    if "intent" not in data:
        data["intent"] = {}

    return data


# ── Layer 5: Business Validation + Spotify Queue ───────────────────────────

# Track URIs queued this session — prevents duplicates across rounds
_queued_uris: set[str] = set()


def _find_active_device(sp):
    """Return the ID of an active Spotify device, or None."""
    try:
        devices = sp.devices().get("devices", [])
        for d in devices:
            if d.get("is_active"):
                return d["id"]
        # No active device — pick the first available one
        if devices:
            return devices[0]["id"]
    except Exception:
        pass
    return None


def validate_and_queue(data: dict, sp) -> list[dict]:
    """Layer 5 — search Spotify for each track, validate, and queue.

    Returns the list of successfully queued tracks (with Spotify metadata).
    If sp is None (no Spotify), returns the raw recommendations instead.
    """
    tracks = data["tracks"]
    if not isinstance(tracks, list) or len(tracks) < 1:
        raise ValueError("Expected at least 1 track recommendation.")
    if len(tracks) > 5:
        tracks = tracks[:5]

    # Check for an active device upfront so we can start playback if needed
    device_id = None
    if sp is not None:
        device_id = _find_active_device(sp)
        if device_id is None:
            print("   ⚠  No active Spotify device found — showing recommendations only.")
            print("      Open Spotify on your phone/desktop/browser and play anything, then try again.\n")
            sp = None  # fall back to recommendation-only for this round

    queued = []
    first_track = True  # first track uses start_playback, rest use add_to_queue

    for t in tracks:
        search_query = t.get("search_query", "")
        reason = t.get("reason", "")
        title_hint = t.get("title_hint", "Unknown")
        artist_hint = t.get("artist_hint", "Unknown")

        if sp is None:
            queued.append({
                "title": title_hint,
                "artist": artist_hint,
                "reason": reason,
                "uri": None,
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
            title = found["name"]
            artist = found["artists"][0]["name"]
            duration_ms = found["duration_ms"]

            if duration_ms < 90_000:
                print(f"   ⚠  Skipping '{title}' — too short ({duration_ms // 1000}s)")
                continue

            if uri in _queued_uris:
                print(f"   ⚠  Skipping '{title}' — already queued this session")
                continue

            if first_track:
                # Start playback on the device — this wakes it up and begins playing
                sp.start_playback(device_id=device_id, uris=[uri])
                first_track = False
            else:
                sp.add_to_queue(uri)

            _queued_uris.add(uri)

            queued.append({
                "title": title,
                "artist": artist,
                "reason": reason,
                "uri": uri,
            })
        except Exception as e:
            print(f"   ⚠  Spotify error for '{search_query}': {e}")

    return queued


# ── Output ─────────────────────────────────────────────────────────────────

def print_results(queued: list[dict], spoken_summary: str, has_spotify: bool):
    if not queued:
        print("\nNo tracks could be queued. Try a different vibe.\n")
        return

    if has_spotify:
        print(f"\n🎧 {spoken_summary}\n")
    else:
        print(f"\n🎵 {spoken_summary} (recommendation-only — no Spotify connected)\n")

    for i, t in enumerate(queued, 1):
        status = "Queued" if t["uri"] else "Recommended"
        print(f"  {i}. {t['title']} — {t['artist']}")
        print(f"     {status}: {t['reason']}\n")


# ── Main Loop ──────────────────────────────────────────────────────────────

def main():
    # Graceful CTRL+C
    signal.signal(signal.SIGINT, lambda *_: (print("\n\nGoodbye!"), sys.exit(0)))

    print("=" * 50)
    print("  AI DJ — Phase 1: The Voice Brain")
    print("=" * 50)
    print()

    sp = get_spotify()

    print("Press ENTER to start recording, CTRL+C to quit.\n")

    while True:
        input("▶  ENTER to record → ")

        try:
            # Layer 1: Record + transcribe + validate
            audio = record_audio()
            transcript = transcribe(audio)
            print(f"   You said: \"{transcript}\"")
            transcript = validate_transcript(transcript)

            # Layer 2: Build prompt
            messages = build_messages(transcript)

            # Layer 3: Call Claude
            print("   Asking Claude for recommendations…")
            raw = call_claude(messages)

            # Layer 4: Parse response
            data = parse_response(raw)

            # Layer 5: Validate + queue on Spotify
            queued = validate_and_queue(data, sp)

            # Output
            print_results(queued, data.get("spoken_summary", ""), sp is not None)

        except ValueError as e:
            print(f"\n   Error: {e}\n")
        except Exception as e:
            print(f"\n   Unexpected error: {e}\n")

        print("-" * 50)


if __name__ == "__main__":
    main()
