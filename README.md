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

ribed as a medical treatment, diagnosis, or validated therapy system.
