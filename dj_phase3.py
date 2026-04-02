"""
Phase 3 — The Hand Turntable

MediaPipe Hands detects hands via webcam, sends landmarks to the browser.
The browser renders an interactive ball on the camera feed — hand interactions
with the ball control the DJ (volume, crossfade, filter, skip, pause).
Browser sends commands back via SocketIO; Python executes Spotify API calls.

Run: python dj_phase3.py
"""

import os
import sys
import signal
import threading
import time
import ssl
import urllib.request
import cv2
import numpy as np

from dotenv import load_dotenv
load_dotenv()

from dj_phase1 import (
    get_spotify, record_audio, transcribe, validate_transcript,
    build_messages, call_claude, parse_response,
    _find_active_device, _queued_uris, claude,
)

from dj_phase2 import (
    app, socketio, session, speak,
    validate_and_queue_p2, print_and_announce, playback_monitor,
    PHASE2_SYSTEM_PROMPT,
)

# ── MediaPipe Tasks API ──────────────────────────────────────────────────

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker, HandLandmarkerOptions, RunningMode,
)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")


def ensure_model():
    if os.path.exists(MODEL_PATH):
        return
    print("Downloading MediaPipe hand landmarker model…")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except urllib.error.URLError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(MODEL_URL)
        with urllib.request.urlopen(req, context=ctx) as resp, open(MODEL_PATH, "wb") as f:
            f.write(resp.read())
    print("Model downloaded.\n")


# ── Spotify Reference (shared with SocketIO handlers) ────────────────────

_sp_ref = None


# ── SocketIO: Browser → Python command handlers ─────────────────────────
# The browser detects gestures from landmarks and sends commands here.
# Python executes the Spotify API calls.

@socketio.on("browser_volume")
def handle_browser_volume(data):
    vol = max(0, min(100, int(data.get("volume", 70))))
    if _sp_ref:
        try:
            _sp_ref.volume(vol)
        except Exception:
            pass


@socketio.on("browser_skip")
def handle_browser_skip(data):
    if _sp_ref:
        try:
            _sp_ref.next_track()
            _request_skip_recommendation(_sp_ref)
        except Exception as e:
            print(f"   ⚠  Skip error: {e}")


@socketio.on("browser_pause_play")
def handle_browser_pause_play(data):
    if _sp_ref:
        try:
            playback = _sp_ref.current_playback()
            if playback and playback.get("is_playing"):
                _sp_ref.pause_playback()
            else:
                _sp_ref.start_playback()
        except Exception as e:
            print(f"   ⚠  Pause/play error: {e}")


# ── Skip Recommendation ──────────────────────────────────────────────────

_recent_intents = []

def _request_skip_recommendation(sp):
    def _run():
        try:
            context = "\n".join(
                f"- Intent {i+1}: {intent}"
                for i, intent in enumerate(_recent_intents[-3:])
            )
            messages = [{"role": "user", "content":
                f"The DJ just skipped a track. Based on the recent session vibes, pick the next track.\n\nRecent intents:\n{context}\n\nPick one great follow-up track."
            }]
            raw = call_claude(messages, system_prompt=PHASE2_SYSTEM_PROMPT)
            data = parse_response(raw)
            queued = validate_and_queue_p2(data, sp)
            if queued:
                track = queued[0]
                speak(f"Dropping into {track['title']} by {track['artist']}")
                print(f"\n   ⏭  Skipped → {track['title']} — {track['artist']}")
                socketio.emit("queue_update", {
                    "current": track,
                    "upcoming": queued[1:],
                    "crossfade_ms": session.crossfade_ms,
                    "energy_trajectory": session.energy_trajectory,
                })
        except Exception as e:
            print(f"   ⚠  Skip recommendation failed: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ── Emit hand landmarks to browser ───────────────────────────────────────

def emit_hand_landmarks(hands_data):
    payload = []
    for side, pts in hands_data:
        landmarks = [[round(pts[i][0], 1), round(pts[i][1], 1)] for i in range(21)]
        payload.append({"side": side, "landmarks": landmarks})
    socketio.emit("hand_landmarks", payload)


def landmarks_to_px(landmarks, frame_w, frame_h):
    return {i: (lm.x * frame_w, lm.y * frame_h) for i, lm in enumerate(landmarks)}


# Hand skeleton connections for OpenCV debug window
HAND_CONNS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17),
]


def draw_hand_skeleton(frame, pts):
    for a, b in HAND_CONNS:
        if a in pts and b in pts:
            cv2.line(frame, (int(pts[a][0]), int(pts[a][1])),
                     (int(pts[b][0]), int(pts[b][1])), (0, 240, 255), 2)
    for idx, (px, py) in pts.items():
        cv2.circle(frame, (int(px), int(py)), 3, (255, 255, 255), -1)


# ── OpenCV Hand Tracking Loop ────────────────────────────────────────────

def hand_tracking_loop(sp):
    ensure_model()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("⚠  Could not open webcam — running without gesture control.")
        while session.is_running:
            time.sleep(1)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = HandLandmarker.create_from_options(options)

    print("Webcam ready — show your hands!\n")

    was_tracking = False

    while session.is_running:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame = cv2.flip(frame, 1)
        frame_h, frame_w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_image)

        if result.hand_landmarks and result.handedness:
            hands_data = []
            for hand_lms, hand_cls in zip(result.hand_landmarks, result.handedness):
                pts = landmarks_to_px(hand_lms, frame_w, frame_h)
                side = hand_cls[0].category_name
                draw_hand_skeleton(frame, pts)
                hands_data.append((side, pts))

            emit_hand_landmarks(hands_data)
            socketio.emit("tracking_status", {"lost": False})
            was_tracking = True
        else:
            # Emit lost only once on transition
            if was_tracking:
                socketio.emit("tracking_status", {"lost": True})
                was_tracking = False

        cv2.imshow("AI DJ — Hand Tracking", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            session.is_running = False
            break

    landmarker.close()
    cap.release()
    cv2.destroyAllWindows()


# ── Voice Input Loop ─────────────────────────────────────────────────────

def voice_loop(sp):
    print("Press ENTER to start recording, ESC in webcam window or CTRL+C to quit.\n")

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

            if "intent" in data:
                _recent_intents.append(str(data["intent"]))
                if len(_recent_intents) > 5:
                    _recent_intents.pop(0)

            queued = validate_and_queue_p2(data, sp)
            print_and_announce(queued, data, sp is not None)

        except ValueError as e:
            print(f"\n   Error: {e}\n")
        except Exception as e:
            print(f"\n   Unexpected error: {e}\n")

        print("-" * 50)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    global _sp_ref

    signal.signal(signal.SIGINT, lambda *_: (
        setattr(session, 'is_running', False),
        print("\n\nGoodbye!"),
        sys.exit(0),
    ))

    print("=" * 50)
    print("  AI DJ — Phase 3: The Hand Turntable")
    print("  Browser: http://127.0.0.1:5000")
    print("  Terminal: voice input via ENTER")
    print("=" * 50)
    print()

    sp = get_spotify()
    _sp_ref = sp

    threading.Thread(target=playback_monitor, args=(sp,), daemon=True).start()
    threading.Thread(target=voice_loop, args=(sp,), daemon=True).start()
    threading.Thread(
        target=lambda: socketio.run(app, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True),
        daemon=True,
    ).start()

    hand_tracking_loop(sp)


if __name__ == "__main__":
    main()
