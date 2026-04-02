# LLM_DJ_BOT
THE AI-DJ

CS398 Week 3 Project 3b

A simple command-line music recommender that demonstrates the LLM Sandwich architecture:

    *    Input Validation — reject bad input before calling the model
    
    *    Prompt Construction — structured instructions to the LLM
    
    *    LLM Call — request recommendations
    
    *    Output Parsing — safely extract JSON

    *    Business Validation — verify recommendations are reasonable

The system asks for genres + mood and returns 3–5 music recommendations with explanations, OR allows the user to skip the genre/mood selection and get something random! 


Setup/Requirements:

Python 3.10+
running local llama.cpp server
Python packages:
    * openai


1. install the python dependency 

pip install openai

2. start local llm server

for example:
llama-server -m your_model.gguf --port 8080

3. run the recommender 
python3 recommender.py

And then you're ready to go! 


How this works:

The program:

* asks for genres (up to 3)
* asks for a mood
* validates input
* queries the LLM
* parses structured JSON
* verifies the output
* prints formatted recommendations

If anything fails, it shows a helpful error instead of crashing.

Example run:

Time to tune-in to your AI DJ Assistant!

Genres (choose up to 3, comma-separated OR type 'surprise' for something RANDOM!)
['pop', 'rock', 'hip-hop', 'r&b', 'rap', 'electronic', 'indie', 'jazz', 'classical']
> pop, rap
Mood ['happy', 'sad', 'excited', 'relaxed', 'focused', 'nostalgic', 'angry']: happy

Great choices! Here are my recommendations:

1. Good 4 U — Olivia Rodrigo (2019)
   Here's Why: Upbeat pop-rap energy with a catchy, joyful chorus that perfectly fits a happy pop-rap vibe

2. Levitating — Dua Lipa (2020)
   Here's Why: Danceable pop with a vibrant, upbeat rhythm that blends pop and rap influences, guaranteed to lift your mood

3. HUMBLE. — Drake ft. 21 Savage (2018)
   Here's Why: Confident and energetic rap with a catchy, upbeat flow that brings a happy, motivational pop-rap edge

Would you like more recommendations? (yes/no) >




# Telekinesis Therapy Game - NeuroHack 2025 Project Redo

Browser-based telekinesis training game prototype using MediaPipe hand tracking, a live corner camera preview, attention monitoring, and a TouchDesigner/VCV Rack bridge path.

The interaction is ADHD therapeutic-style focused and coordination exercise, not a medical product or validated treatment.

## What It Does

- tracks one hand in real time with MediaPipe
- lets the player hover objects to reveal labels
- uses pinch to lift and carry objects
- places objects into a single target on the right side of the playfield
- advances through levels with denser maze obstacles
- adds hazard zones on higher levels that restart the current level
- monitors whether the player is looking down too long and warns visually
- keeps a live mirrored camera/tracking preview visible in the corner
- can publish interaction data through a local WebSocket-to-OSC relay for TouchDesigner and VCV Rack

## Setup

Requirements:

- Node.js 20+ recommended
- npm
- a webcam for MediaPipe hand tracking and attention monitoring

Install:

```bash
npm install
```

Run the game:

```bash
npm run dev
```

Then open the local Vite URL in a browser and allow camera access.

Build a production bundle:

```bash
npm run build
```

Preview the production build:

```bash
npm run preview
```

## Controls

- move your hand to hover an object and reveal its label
- pinch to lift the hovered object
- move the lifted object through the maze toward the target
- open your hand to release it into the target

Fallback mode:

- if camera or model setup fails, the app falls back to pointer control
- click and hold to simulate pinch

## Live Preview

The game keeps a live camera preview in the corner of the screen. When MediaPipe is active, the preview shows:

- mirrored camera feed
- tracked hand landmarks
- hand control ring
- eye-attention indicator

This preview is intentionally kept visible during gameplay.

## Attention Model

The current attention rule is lightweight and practical:

- focus is treated as keeping eyes on the screen rather than looking down
- if eyes are down for more than 3 seconds, the game panel flashes red
- the warning clears when focus is regained

This is a prototype interaction heuristic, not a diagnostic signal.

## Level Structure

- one target sits on the far right side at mid-height
- objects begin on the left side
- each level contains 1-2 objects
- level progression increases maze complexity instead of speed
- level 3 and above include red hazard zones that restart the current level

## TouchDesigner / VCV Rack Bridge

Run the local relay:

```bash
npm run bridge
```

Default transport path:

- browser app -> `ws://127.0.0.1:8765`
- relay -> TouchDesigner UDP OSC `127.0.0.1:7000`
- relay -> VCV Rack UDP OSC `127.0.0.1:7001`

Relay environment variables:

- `TELEKINESIS_WS_PORT`
- `TOUCHDESIGNER_HOST`
- `TOUCHDESIGNER_OSC_PORT`
- `VCV_RACK_HOST`
- `VCV_RACK_OSC_PORT`

Browser query parameters:

- `?bridge=websocket`
- `?bridge=console`
- `?bridgeUrl=ws://host:port`

OSC addresses and mapping notes are documented in [docs/osc-schema.md](/Users/noemiamahmud/Motion-Tracker/docs/osc-schema.md).

## Architecture

High-level flow:

`webcam -> MediaPipe hand + face processing -> feature extraction -> smoothing -> gesture/game logic -> rendering`

Parallel bridge flow:

`game metrics + hand metrics -> OSC mapping layer -> WebSocket relay -> TouchDesigner / VCV Rack`

Architecture notes are in [docs/architecture.md](/Users/noemiamahmud/Motion-Tracker/docs/architecture.md).

## Project Layout

```text
Motion-Tracker/
├── CODEX.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── developer-notes.md
│   └── osc-schema.md
├── scripts/
│   └── osc-relay.mjs
└── src/
    ├── app/
    ├── bridge/
    ├── config/
    ├── feedback/
    ├── game/
    ├── render/
    ├── tracking/
    └── types/
```

## Key Tech Responsibilities

- `MediaPipe`
  - hand landmarks
  - face blendshape-based eye/down attention heuristic
- `TouchDesigner`
  - bridge endpoint
  - mapping editor
  - audiovisual routing / performance tooling
- `VCV Rack`
  - downstream synthesis and audio response

## Where To Modify Things

- gesture thresholds and runtime defaults:
  - [src/config/gameConfig.ts](/Users/noemiamahmud/Motion-Tracker/src/config/gameConfig.ts)
- hand feature extraction and normalization:
  - [src/tracking/featureExtraction.ts](/Users/noemiamahmud/Motion-Tracker/src/tracking/featureExtraction.ts)
- tracking adapters:
  - [src/tracking/mediaPipeHandTracker.ts](/Users/noemiamahmud/Motion-Tracker/src/tracking/mediaPipeHandTracker.ts)
  - [src/tracking/pointerHandTracker.ts](/Users/noemiamahmud/Motion-Tracker/src/tracking/pointerHandTracker.ts)
- object spawn layouts, maze walls, and hazards:
  - [src/game/spawn.ts](/Users/noemiamahmud/Motion-Tracker/src/game/spawn.ts)
- telekinesis feel, level logic, collisions, resets:
  - [src/game/telekinesisGame.ts](/Users/noemiamahmud/Motion-Tracker/src/game/telekinesisGame.ts)
- HUD, targets, walls, hazards, warning overlays:
  - [src/render/canvasRenderer.ts](/Users/noemiamahmud/Motion-Tracker/src/render/canvasRenderer.ts)
- live camera preview:
  - [src/render/trackingPreviewRenderer.ts](/Users/noemiamahmud/Motion-Tracker/src/render/trackingPreviewRenderer.ts)
- OSC mapping:
  - [src/bridge/oscMapping.ts](/Users/noemiamahmud/Motion-Tracker/src/bridge/oscMapping.ts)
- relay transport:
  - [scripts/osc-relay.mjs](/Users/noemiamahmud/Motion-Tracker/scripts/osc-relay.mjs)

## Developer Notes

Detailed tuning and extension notes are in [docs/developer-notes.md](/Users/noemiamahmud/Motion-Tracker/docs/developer-notes.md).

## Framing

This codebase is intended as a modular prototype for:

- attention-supportive interaction design
- hand-eye coordination gameplay
- therapeutic-style neurointeractive experiences
- future audiovisual and research-oriented expansion

It should not be described as a medical treatment, diagnosis, or validated therapy system.
