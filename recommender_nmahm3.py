"""
CS 398 - Week 3: Music Recommender

1. INPUT VALIDATION - reject bad input before wasting tokens
2. PROMPT CONSTRUCTION - format the request
3. LLM CALL - the black box you don't control
4. OUTPUT PARSING - extract JSON from response
5. BUSINESS VALIDATION - check output makes sense

Your task: Fill in the TODOs.
"""
#necessary imports
from openai import OpenAI
import json
import re

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

#validation phase 

def get_valid_genres(valid_genres, max_genres=3): #this validates the selected genres by the user before calling the LLM
    genres_text = input(
        f"Genres (choose up to {max_genres}, comma-separated OR type 'surprise' for something RANDOM!)\n{valid_genres}\n> "
    ).strip().lower()

    if genres_text == "":
        raise ValueError("Genres cannot be empty.") #making sure that a genre is chosen 
    if len(genres_text) > 100:
        raise ValueError("Genres input is too long.") #making sure the genre makes sense 

    if genres_text == "surprise": # surprise option that is a fun and extra choice insread of genres
        return "surprise"

    parts = [p.strip() for p in genres_text.split(",") if p.strip()]
    if len(parts) == 0:
        raise ValueError("Genres cannot be empty.")
    if len(parts) > max_genres:
        raise ValueError(f"Too many genres. Choose up to {max_genres}.")

    invalid = [g for g in parts if g not in valid_genres]
    if invalid:
        raise ValueError(f"Invalid genre(s): {invalid}. Choose from: {valid_genres}") # validates genres chosen 

    return parts

# validation step for chosen moods for the user 
def get_valid_mood(valid_moods):
    mood = input(f"Mood {valid_moods}: ").strip().lower()

    if mood == "":
        raise ValueError("Mood cannot be empty.") #user must choose a mood (if they didnt choose surpise mode)
    if len(mood) > 30:
        raise ValueError("Mood is too long.")
    if mood not in valid_moods:
        raise ValueError(f"Invalid mood. Choose from: {valid_moods}")

    return mood

#instructions for JSON output 
def build_prompt(genres, mood):
    genres_str = ", ".join(genres)
    return f"""
Recommend 3-5 REAL music picks for someone who likes the genres "{genres_str}" and feels "{mood}".

Return ONLY a JSON array (no markdown, no extra text).
Format exactly like:
[
  {{"title": "Song Title", "artist": "Artist Name", "year": 2020, "reason": "Why it matches"}}
]
""".strip()

#instructions for when the surprise music is chosen 
def build_surprise_prompt():
    return """
Recommend EXACTLY 3 REAL songs (not artists).

Return ONLY valid JSON (no markdown, no extra text).
The JSON must be a single array of 3 objects.
Each object must have: title (string), artist (string), year (int), reason (string).

Example:
[
  {"title": "Song Title", "artist": "Artist Name", "year": 2020, "reason": "One short sentence."},
  {"title": "Song Title", "artist": "Artist Name", "year": 2021, "reason": "One short sentence."},
  {"title": "Song Title", "artist": "Artist Name", "year": 2019, "reason": "One short sentence."}
]
""".strip()

#output parisng layer 
def parse_json_array(raw_output): #had some struggles here but its meant to try different ways to extract valid JSON 
    text = (raw_output or "").strip()

    text_no_fences = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text_no_fences = text_no_fences.replace("```", "").strip()

    try:
        data = json.loads(text_no_fences)
        if isinstance(data, list):
            return data
    except:
        pass

    candidates = re.findall(r"\[[\s\S]*?\]", text_no_fences)
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, list):
                return data
        except:
            continue

    snippet = text_no_fences[:400].replace("\n", "\\n")
    # in the event that it cannot properly format, it can still provide song and artist names as well as descriptions but in a more paragraph format 
    raise ValueError(f"Could not extract a JSON array from LLM output. Snippet: {snippet}") 

#business logic validation layer 
# Ensures the parsed recommendations match the requirements for the recommender
def business_validation(reccomendations, expected_min=3, expected_max=5):
    if not isinstance(reccomendations, list):
        raise ValueError("Output was not a list.")
    if len(reccomendations) < expected_min or len(reccomendations) > expected_max:
        raise ValueError(
            f"Expected {expected_min}-{expected_max} recommendations, got {len(reccomendations)}."
        )

    cleaned = []

    for r in reccomendations: #making sure all the parts of the output make sense before being given to the user 
        if not isinstance(r, dict):
            raise ValueError("Each recommendation must be an object/dict.")

        for key in ["title", "artist", "year", "reason"]:
            if key not in r:
                raise ValueError(f"Missing required field: {key}")

        if not isinstance(r["title"], str) or r["title"].strip() == "":
            raise ValueError("Invalid title.")

        if not isinstance(r["artist"], str) or r["artist"].strip() == "":
            raise ValueError("Invalid artist.")

        if not isinstance(r["reason"], str) or r["reason"].strip() == "":
            raise ValueError("Invalid reason.")

        if not isinstance(r["year"], int):
            raise ValueError("Year must be an integer.")

        if r["year"] < 1900 or r["year"] > 2026:
            raise ValueError(f"Suspicious year: {r['year']}")

        cleaned.append(r)

    return cleaned

#output of recommendations, in a formatted input 
def print_recs(recs):
    print("\nGreat choices! Here are my recommendations:\n")

    for i, r in enumerate(recs, start=1):
        print(f"{i}. {r['title']} — {r['artist']} ({r['year']})")
        print(f"   Here's Why: {r['reason']}\n")


def main():
    print("Time to tune-in to your AI DJ Assistant!\n") #im calling it the AI DJ 

    valid_genres = [ #genre options 
        "pop",
        "rock",
        "hip-hop",
        "r&b",
        "rap",
        "electronic",
        "indie",
        "jazz",
        "classical",
    ]

    valid_moods = [ #possible moods 
        "happy",
        "sad",
        "excited",
        "relaxed",
        "focused",
        "nostalgic",
        "angry",
    ]

    while True:
        try:
            genres = get_valid_genres(valid_genres, max_genres=3)

            if genres == "surprise": # Surprise mode: skip mood input and generate random songs

                prompt = build_surprise_prompt()
                response = client.chat.completions.create(
                    model="local",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=500
                )

                raw_output = response.choices[0].message.content
                recs_raw = parse_json_array(raw_output)
                recs = business_validation(recs_raw, expected_min=3, expected_max=3)
                print_recs(recs)
            else:  # Standard recommendation path using genres + mood

                mood = get_valid_mood(valid_moods)
                prompt = build_prompt(genres, mood)

                response = client.chat.completions.create(
                    model="local",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                )

                raw_output = response.choices[0].message.content

                recs_raw = parse_json_array(raw_output)
                recs = business_validation(recs_raw, expected_min=3, expected_max=5)
                print_recs(recs)
        # exception handling 
        except ValueError as e:
            print("\n Error:", e)

        except Exception as e:
            print("\nUnexpected error:", e)

        again = input(
            "Would you like more recommendations? (yes/no) > "
        ).strip().lower()

        if again not in ["yes", "y"]:
            print("Goodbye!")
            break

        print("-" * 50)


if __name__ == "__main__":
    main()



'''
3 Example Runs 


Time to tune-in to your AI DJ Assistant!

Genres (choose up to 3, comma-separated OR type 'surprise' for something RANDOM!)
['pop', 'rock', 'hip-hop', 'r&b', 'rap', 'electronic', 'indie', 'jazz', 'classical']
> indie
Mood ['happy', 'sad', 'excited', 'relaxed', 'focused', 'nostalgic', 'angry']: sad

Great choices! Here are my recommendations:

1. The Night We Met — Lord Huron (2018)
   Here's Why: A melancholic indie folk track with haunting vocals and emotional depth that perfectly captures a sad, reflective mood.

2. Ho Hey — The Lumineers (2012)
   Here's Why: A gentle, bittersweet indie folk song that blends warm instrumentation with a quietly sorrowful tone.

3. Rivers and Roads — Big Thief (2019)
   Here's Why: A raw, tender indie folk piece with poetic lyrics and a slow, mournful melody that resonates with quiet sadness.

4. Skinny Love — Bon Iver (2011)
   Here's Why: An ethereal, deeply emotional indie folk track with a haunting atmosphere that evokes profound melancholy.

5. Sweater Weather — The Neighbourhood (2015)
   Here's Why: A moody indie rock ballad with a melancholic vibe, blending sadness with poetic introspection.

Would you like more recommendations? (yes/no) > yes


--------------------------------------------------
Genres (choose up to 3, comma-separated OR type 'surprise' for something RANDOM!)
['pop', 'rock', 'hip-hop', 'r&b', 'rap', 'electronic', 'indie', 'jazz', 'classical']
> surprise

Great choices! Here are my recommendations:

1. Blinding Lights — The Weeknd (2019)
   Here's Why: A synth-driven pop hit that dominated global charts.

2. Levitating — Dua Lipa (2020)
   Here's Why: A dance-pop anthem with infectious energy and modern production.

3. Drivers License — Olivia Rodrigo (2021)
   Here's Why: A heartfelt ballad that captured widespread emotional resonance.

Would you like more recommendations? (yes/no) > 

--------------------------------------------------
Genres (choose up to 3, comma-separated OR type 'surprise' for something RANDOM!)
['pop', 'rock', 'hip-hop', 'r&b', 'rap', 'electronic', 'indie', 'jazz', 'classical']
> jazz
Mood ['happy', 'sad', 'excited', 'relaxed', 'focused', 'nostalgic', 'angry']: relaxed

Great choices! Here are my recommendations:

1. Take Five — Dave Brubeck Quartet (1959)
   Here's Why: A smooth, melodic jazz classic with a relaxed tempo that encourages calm and reflection.

2. Feeling Good — Nina Simone (1965)
   Here's Why: A soulful, introspective jazz piece with a gentle rhythm perfect for unwinding.

3. Blue in Green — Miles Davis (1964)
   Here's Why: A hauntingly beautiful, atmospheric track that blends jazz with a deeply relaxing mood.

4. Lush Life — Chet Baker (1959)
   Here's Why: A tender, mellow jazz standard with a soft, soothing vocal delivery ideal for relaxation.

5. So What — Miles Davis (1959)
   Here's Why: Cool, understated, and meditative—this jazz icon offers a serene, laid-back listening experience.

Would you like more recommendations? (yes/no) > 
'''