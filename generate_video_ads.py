#!/usr/bin/env python3
"""
Video ad pipeline:
1. Claude writes 3 video concepts based on winning patterns
2. fal.ai (Kling) generates a real 5-second vertical video per concept
3. YouTube Data API v3 uploads each video as a YouTube Short
4. Video IDs saved to youtube_log.json for engagement tracking
"""

import json
import os
import time
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import fal_client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CONFIG_FILE = Path("config.json")
PERF_FILE = Path("performance.json")
YOUTUBE_LOG = Path("youtube_log.json")
ADS_DIR = Path("ads")

# These hashtags are added to EVERY video description.
# #Shorts is mandatory -- YouTube uses it to classify and surface videos in the Shorts feed.
# The others target the exact audience (people who love going out, 18-35).
BASE_HASHTAGS = "#Shorts #EzCalendar #AICalendar #NeverMissOut #CityLife #WeekendVibes #EventPlanning #LifeHack #ProductivityTok"

SCENE_TEMPLATES = """
PROVEN SCENE TEMPLATES FOR EZCALENDAR ADS (pick the best fit per concept):

1. THE SNAP MOMENT — Close-up on hands holding phone at golden hour, raising it toward a colorful
   street flyer on a brick wall. Macro lens, shallow depth of field, warm orange tones, slow-motion
   snap, camera pushes into phone screen as calendar animates filling in. Satisfying and tactile.

2. THE FOMO RESCUE — Wide shot of a vibrant crowded event (concert, market, rooftop party) at night,
   neon and string lights, joyful crowd. Handheld energy. Quick cut to close-up of phone showing the
   event on a calendar. The person looks up and smiles — they made it. Emotional payoff.

3. THE LINK PASTE — POV shot looking down at phone in a cozy cafe. Social feed scrolling, an event
   post appears. Thumb taps, copies link, pastes into app. Screen blooms as event details fill
   themselves in with a clean animation. Coffee cup visible, morning light, calm and satisfying.

4. THE BEFORE/AFTER — Split screen or whip-pan: LEFT side cold blue light, frustrated person
   manually typing event details, typos, stress. RIGHT side warm golden light, same person
   effortlessly snapping a flyer, calendar fills instantly, she laughs with relief. High contrast
   tones, snappy transition.

5. THE LIFESTYLE MONTAGE — Fast-cut vertical montage: rooftop sunset, live music crowd, art gallery
   opening, food market, friends laughing. Each scene 1-2 seconds, kinetic energy, vibrant colors.
   Ends on close-up of phone with a full exciting calendar. The message: life is full of things to do.

KLING AI PROMPT RULES (always follow these for best results):
- Always specify: camera angle, lighting type, motion style, color palette, mood
- Use cinematic language: "shallow depth of field", "smooth dolly push", "handheld", "slow motion"
- Specify lighting: "golden hour", "neon glow", "soft window light", "blue hour", "warm bokeh"
- Keep prompts under 200 words — Kling performs worse with very long prompts
- NEVER mention text, words, logos, or UI overlays — Kling cannot render readable text
- Focus on EMOTION and MOTION — what does the person FEEL, how does the camera MOVE
- Use "vertical 9:16 framing" explicitly in every prompt
- End every prompt with the quality keywords: "cinematic, 4K, smooth motion, photorealistic"
"""

YOUTUBE_SEO_RULES = """
YOUTUBE SHORTS SEO RULES (critical for discoverability):
- Title must front-load the most searchable keyword in the FIRST 3 words
- Title should feel like something someone would actually search or say out loud
- Title max 70 chars so it never gets cut off in the feed
- Description line 1 = the hook (shown as preview text before someone taps) — make it irresistible
- Description line 2 = the value prop in one sentence
- Description line 3 = CTA with the URL
- Use power words that trigger curiosity: "this app", "why didn't I know about this", "changed my life"
- Tags should mix broad terms (calendar, productivity) with niche terms (event planning app, ai calendar)
- Avoid clickbait that doesn't deliver — YouTube punishes high click-through with low watch time
"""


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def extract_winning_patterns(performance: dict) -> str:
    winners = [e for e in performance.get("ads", []) if e.get("score", 0) >= 7]
    if not winners:
        return "No winners yet — generate a diverse mix using all 5 scene templates above."
    lines = [f"Score {w['score']}/10 | hook={w.get('hook_type','?')} | template={w.get('scene_template','?')} | {w.get('notes', '')}" for w in winners]
    return "WINNING AD PATTERNS — generate more like these:\n" + "\n".join(lines)


def generate_video_concepts(config: dict, winning_context: str, today: str) -> list:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    site = config["websites"][0]

    prompt = f"""You are an expert YouTube Shorts ad director and AI video prompt engineer.
Your job is to write 3 video ad concepts for the product below. Each video is 5 seconds, vertical 9:16.
These will be generated by Kling AI and uploaded as YouTube Shorts.

PRODUCT: {site['name']}
URL: {site['url']}
DESCRIPTION: {site['description']}
AUDIENCE: {site['target_audience']}
UNIQUE VALUE: {site['unique_value']}
CTA: {site['cta_goal']}
BRAND VOICE: {config.get('brand_voice', 'fun and energetic')}

{SCENE_TEMPLATES}

{YOUTUBE_SEO_RULES}

{winning_context}

YOUR TASK:
- Write 3 concepts, each using a DIFFERENT scene template and hook type
- The visual_prompt must follow ALL Kling AI prompt rules above
- Follow ALL YouTube SEO rules for title and description
- Spread hook types: curiosity, pain_point, and aspirational across the 3 concepts
- Today's date: {today}

Return ONLY valid JSON, no markdown, no explanation:
{{
  "concepts": [
    {{
      "id": "{today}-v001",
      "scene_template": "THE SNAP MOMENT",
      "visual_prompt": "Vertical 9:16 close-up, golden hour warm light, a stylish woman's hand raises a smartphone toward a vibrant pink concert flyer stuck to a weathered brick wall. Shallow depth of field, bokeh background of a busy city street. Slow-motion snap, then smooth push-in on the phone screen as a clean calendar interface animates event details filling in automatically. Warm orange and pink tones, tactile and satisfying. Cinematic, 4K, smooth motion, photorealistic.",
      "title": "This app planned my whole weekend in 2 seconds",
      "description": "I snapped a flyer and AI filled my entire calendar instantly. Zero typing, zero forgetting. Free at ezcalendar.vercel.app/calendar",
      "tags": ["ai calendar", "event planning app", "productivity app", "calendar app", "never miss out", "weekend plans", "city life", "ezcalendar"],
      "hook_type": "curiosity",
      "strategy": "Front-load the payoff in the title so it stops the scroll, then description delivers the proof."
    }}
  ]
}}"""

    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)["concepts"]


def generate_video(visual_prompt: str) -> str:
    """Generate video via fal.ai Kling v1.6, return local tmp file path."""
    print(f"  Generating video: {visual_prompt[:100]}...")
    result = fal_client.subscribe(
        "fal-ai/kling-video/v1.6/standard/text-to-video",
        arguments={
            "prompt": visual_prompt,
            "duration": "5",
            "aspect_ratio": "9:16",
        },
    )
    video_url = result["video"]["url"]
    print(f"  Video ready: {video_url[:70]}")

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    urllib.request.urlretrieve(video_url, tmp.name)
    return tmp.name


def get_youtube_client():
    """Build authenticated YouTube API client from stored OAuth credentials."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=creds)


def build_description(concept: dict, site: dict) -> str:
    """Build SEO-optimized description with mandatory #Shorts hashtag."""
    desc = concept["description"].rstrip()
    # Ensure the URL is in the description
    if site["url"] not in desc:
        desc += f"\n{site['url']}"
    # Append hashtags -- #Shorts MUST be here for YouTube to surface in Shorts feed
    desc += f"\n\n{BASE_HASHTAGS}"
    return desc


def post_to_youtube(concept: dict, site: dict, video_path: str) -> str:
    """Upload video as a YouTube Short, return video ID."""
    youtube = get_youtube_client()
    description = build_description(concept, site)

    body = {
        "snippet": {
            "title": concept["title"],
            "description": description,
            # Tags: combine concept-specific tags with always-on discovery tags
            "tags": concept.get("tags", []) + ["shorts", "short", "ezcalendar", "ai", "calendar", "productivity"],
            "categoryId": "22",  # People & Blogs -- best fit for lifestyle/productivity
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    print(f"  Uploading: {concept['title']}")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"  Posted! https://www.youtube.com/shorts/{video_id}")
    return video_id


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ADS_DIR.mkdir(exist_ok=True)

    config = load_json(CONFIG_FILE)
    performance = load_json(PERF_FILE)
    youtube_log = load_json(YOUTUBE_LOG)
    if "videos" not in youtube_log:
        youtube_log["videos"] = []

    site = config["websites"][0]
    winning_context = extract_winning_patterns(performance)
    print(f"Winning context: {winning_context[:100]}...")

    print("\nGenerating video concepts with Claude...")
    concepts = generate_video_concepts(config, winning_context, today)
    print(f"Got {len(concepts)} concepts.")

    results = []
    for i, concept in enumerate(concepts, 1):
        print(f"\n[{i}/{len(concepts)}] {concept['hook_type']} — {concept['id']}")
        print(f"  Template: {concept.get('scene_template', '?')}")
        print(f"  Title: {concept['title']}")

        try:
            video_path = generate_video(concept["visual_prompt"])
            video_id = post_to_youtube(concept, site, video_path)
            concept["youtube_id"] = video_id
            concept["status"] = "posted"
            youtube_log["videos"].append({
                "id": concept["id"],
                "youtube_id": video_id,
                "url": f"https://www.youtube.com/shorts/{video_id}",
                "date": today,
                "hook_type": concept["hook_type"],
                "scene_template": concept.get("scene_template"),
                "title": concept["title"],
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "metrics_checked": False,
            })
        except Exception as e:
            concept["status"] = "failed"
            concept["error"] = str(e)
            print(f"  FAILED: {e}")

        results.append(concept)
        time.sleep(10)

    (ADS_DIR / f"{today}.json").write_text(json.dumps({"date": today, "ads": results}, indent=2))
    YOUTUBE_LOG.write_text(json.dumps(youtube_log, indent=2))

    posted = sum(1 for r in results if r["status"] == "posted")
    print(f"\nDone: {posted}/{len(results)} videos posted to YouTube Shorts.")


if __name__ == "__main__":
    main()
