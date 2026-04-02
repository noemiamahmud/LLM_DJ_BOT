You are a senior engineer helping me build a voice-controlled AI DJ system in three phases.

My existing experience:
- A terminal-based LLM music recommender using the 5-layer pipeline 
  (input validation → prompt construction → LLM call → output parsing → business validation)
- A MediaPipe hand/eye tracker that moves objects on screen

My confirmed credentials and tools:
- STT: openai/whisper-large-v3 via HuggingFace Transformers (local inference, NOT the OpenAI API)
- LLM: Claude claude-sonnet-4-20250514 via Anthropic SDK (ANTHROPIC_API_KEY in env)
- Music: Spotify Web API — app registered, Client ID + Secret ready, 
         redirect URI set to http://localhost:8888/callback
- Gesture: MediaPipe Hands (Python)

══════════════════════════════════════════
PHASE 1 — The Voice Brain (MVP)
══════════════════════════════════════════

Goal: Voice in → Claude interprets vibe → Spotify tracks queued and playing.

STT setup (whisper-large-v3, local):
  - Record mic input with sounddevice or pyaudio (16kHz, mono)
  - Transcribe with HuggingFace Transformers pipeline:

    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
    import torch

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model_id = "openai/whisper-large-v3"

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
    ).to(device)
    processor = AutoProcessor.from_pretrained(model_id)

    whisper_pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
        generate_kwargs={"language": "english"}
    )

  - Pass raw numpy audio array directly to whisper_pipe — no temp file needed
  - Reject transcripts under 3 words before hitting Claude (input validation layer)

Claude's role (Anthropic SDK, claude-sonnet-4-20250514):
  System prompt should instruct Claude to:
    1. Parse spoken vibe ("something lo-fi, melancholy, late night")
    2. Extract structured intent as JSON: 
       {genres[], mood, energy_level (1-10), era_hint, tempo_hint}
    3. Build 1-2 Spotify search query strings from that intent
    4. Return 3-5 track recommendations with confidence reasoning

  Response must always be a JSON object with this exact shape:
  {
    "tracks": [
      {"search_query": "...", "title_hint": "...", "artist_hint": "...", "reason": "..."}
    ],
    "spoken_summary": "Here's what I'm queuing for you...",
    "intent": {genres[], mood, energy_level, era_hint}
  }

Spotify flow:
  - Use spotipy library with SpotifyOAuth (scope: "user-modify-playback-state user-read-playback-state")
  - For each track: call sp.search(q=search_query, type="track", limit=3), take top result
  - Validate each found track: reject if duration_ms < 90000 or already queued this session
  - Call sp.add_to_queue(uri) for each valid track
  - Print: "Now playing: {title} by {artist} — {Claude's reason}"

5-layer pipeline (carry over exactly from my recommender):
  Layer 1 - Input validation: reject empty transcript, < 3 words, or > 200 chars
  Layer 2 - Prompt construction: format transcript into Claude system+user messages
  Layer 3 - LLM call: Claude API with structured JSON response
  Layer 4 - Output parsing: extract JSON, handle missing fields gracefully
  Layer 5 - Business validation: confirm track URIs exist, no duplicates, duration check

Deliverable: A single Python script (dj_phase1.py) that loops:
  press ENTER to record → transcribe → Claude → Spotify queue → print confirmation
  CTRL+C to exit cleanly

Do NOT proceed to Phase 2 until Phase 1 plays music end-to-end.

══════════════════════════════════════════
PHASE 2 — The Playback Engine
══════════════════════════════════════════

Goal: Add real DJ controls — BPM awareness, crossfade, EQ, visual feedback.

Add to Phase 1:
  - Fetch Spotify Audio Features for each queued track:
    sp.audio_features(track_id) → returns tempo (BPM), key, energy, valence
  - Pre-load next track 15s before current track ends (poll sp.current_playback())
  - Crossfade logic: calculate fade duration based on BPM delta between tracks
    (large BPM delta = longer fade to avoid jarring transitions)

Claude's updated response shape — add these fields to the existing JSON:
  {
    ...existing fields...,
    "suggested_crossfade_ms": 8000,
    "energy_trajectory": "build" | "sustain" | "wind_down",
    "key_compatibility_note": "..."
  }

Add a simple browser UI (single HTML file, vanilla JS + Web Audio API):
  - Canvas waveform visualizer for currently playing track
  - BPM display (pulled from Spotify Audio Features)
  - Three EQ sliders: bass (80Hz), mid (1kHz), high (8kHz) — using BiquadFilterNode
  - "Now Playing" card with track info and Claude's reason

TTS feedback (pyttsx3):
  - Speak spoken_summary from Claude's JSON response after each new queue
  - Speak crossfade warning 5s before transition: "Crossfading in 5..."

Deliverable: dj_phase2.py + dj_ui.html running together, Flask serving the UI,
WebSocket (flask-socketio) pushing track state updates to the browser.

══════════════════════════════════════════
PHASE 3 — The Hand Turntable
══════════════════════════════════════════

Goal: MediaPipe Hands becomes the physical DJ controller.

Gesture map — implement in this exact order, one at a time:
  1. Left hand Y-position  → master volume (hand at top = 100%, bottom = 0%)
  2. Right hand X-position → crossfade between current and next track
  3. Pinch gesture         → skip to next track
     (thumb tip + index tip distance < 30px in camera space)
  4. Closed fist           → pause / play toggle
     (all fingertips below MCP joints)
  5. Two-hand spread       → low-pass filter cutoff sweep (scratch effect)
     (distance between left and right wrist landmarks, mapped to 200Hz–8kHz)

Implementation rules:
  - Use mediapipe.solutions.hands with max_num_hands=2
  - Run in OpenCV window alongside the Flask UI (separate thread)
  - Debounce all gestures: 300ms minimum between triggers — use time.monotonic()
  - If MediaPipe loses tracking, freeze the last known gesture values (do not snap to zero)
  - Draw hand skeleton on the OpenCV canvas
  - Highlight the active gesture label in the corner (e.g. "VOLUME: 73%")

Each gesture maps to either:
  - A Web Audio API parameter change (volume, EQ, filter) via WebSocket message to the browser
  - A Spotify API call (skip, pause/play) via spotipy

Claude's optional role in Phase 3:
  - When a skip gesture is detected, Claude picks the next track based on 
    the current session's intent history (pass last 3 intents as context)
  - Speak the transition via pyttsx3: "Crossfading now — dropping into [track name]"

Deliverable: All three phases running simultaneously:
  dj_phase3.py — orchestrator that imports Phase 1 + 2 logic and adds gesture control
  Single command to start everything: python dj_phase3.py

══════════════════════════════════════════
GLOBAL CONSTRAINTS
══════════════════════════════════════════

- Preserve the 5-layer pipeline in every Claude interaction
- All Claude JSON responses must include spoken_summary (used for pyttsx3 TTS)
- All env vars in a .env file loaded with python-dotenv:
    ANTHROPIC_API_KEY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
- If Spotify auth fails or no active device found: print track recommendations 
  only, do not crash
- If Whisper model isn't cached yet, download it on first run with a progress message
- If MediaPipe loses hands: freeze last gesture, show "TRACKING LOST" overlay
- Comments explain WHY decisions were made, not WHAT the code does
- One requirements.txt covering all three phases

Start with Phase 1. Make reasonable default choices without asking — 
state your choices clearly at the top of your response.