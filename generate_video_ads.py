#!/usr/bin/env python3
"""
Video ad pipeline:
1. Claude writes 3 video concepts based on winning patterns
2. fal.ai (Kling) generates a real 5-second vertical video per concept
3. YouTube Data API v3 uploads each video as a YouTube Short
4. Maximize-views layer: SEO description, creator comment w/ clickable link,
   add to a playlist, hashtags-above-title ordering
5. Video IDs saved to youtube_log.json for engagement tracking
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

# Broad scope so we can upload AND comment AND manage playlists with one token.
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# Name of the playlist all ads get added to (boosts session watch-time).
PLAYLIST_TITLE = "ezCalendar — Plan Your Life"

# The first 3 hashtags render ABOVE the title in the Shorts player, so put the
# strongest discovery tags first. #Shorts is mandatory to land in the Shorts feed.
LEAD_HASHTAGS = "#Shorts #AICalendar #NeverMissOut"
EXTRA_HASHTAGS = "#EzCalendar #CityLife #WeekendVibes #EventPlanning #LifeHack #ProductivityTok #FOMO"

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
- DESIGN FOR A SEAMLESS LOOP: the last frame should flow naturally into the first frame so the
  Short replays without a visible cut — replays are a top ranking signal on Shorts
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
- pinned_comment = a short, friendly comment WE post as the creator in the first seconds. It must
  ask an engaging question to bait replies (comments are a huge first-hour ranking signal) AND
  include the URL as a tappable link. Max 200 chars.
- Use power words that trigger curiosity: "this app", "why didn't I know about this", "changed my life"
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
- The visual_prompt must follow ALL Kling AI prompt rules above (including the seamless loop)
- Follow ALL YouTube SEO rules for title, description, and pinned_comment
- Spread hook types: curiosity, pain_point, and aspirational across the 3 concepts
- Today's date: {today}

Return ONLY valid JSON, no markdown, no explanation:
{{
  "concepts": [
    {{
      "id": "{today}-v001",
      "scene_template": "THE SNAP MOMENT",
      "visual_prompt": "Vertical 9:16 close-up, golden hour warm light, a stylish woman's hand raises a smartphone toward a vibrant pink concert flyer on a brick wall. Shallow depth of field, city bokeh. Slow-motion snap, smooth push-in on the phone as a calendar animates filling in. The final frame eases back to the opening hand pose for a seamless loop. Warm orange and pink tones. Cinematic, 4K, smooth motion, photorealistic.",
      "title": "This app planned my whole weekend in 2 seconds",
      "description": "I snapped a flyer and AI filled my entire calendar instantly. Zero typing, zero forgetting. Free at ezcalendar.vercel.app/calendar",
      "pinned_comment": "Wait til you see how fast this is 😮 What event would YOU add first? Try it free → ezcalendar.vercel.app/calendar",
      "tags": ["ai calendar", "event planning app", "productivity app", "calendar app", "never miss out", "weekend plans", "city life", "ezcalendar"],
      "hook_type": "curiosity",
      "strategy": "Front-load the payoff in the title to stop the scroll, bait comments with a question in the pinned comment."
    }}
  ]
}}"""

    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2560,
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
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def ensure_playlist(youtube, log: dict) -> str:
    """Return the ad playlist ID, creating it once and caching the id in the log."""
    if log.get("playlist_id"):
        return log["playlist_id"]
    print(f"  Creating playlist '{PLAYLIST_TITLE}'...")
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": PLAYLIST_TITLE, "description": "Plan your life with ezCalendar. ezcalendar.vercel.app/calendar"},
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    log["playlist_id"] = resp["id"]
    return resp["id"]


def add_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        ).execute()
        print("  Added to playlist.")
    except Exception as e:
        print(f"  (playlist add skipped: {e})")


def post_creator_comment(youtube, video_id: str, text: str) -> None:
    """Post a top-level comment as the channel owner to bait first-hour engagement."""
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}},
        ).execute()
        print("  Posted creator comment with link.")
    except Exception as e:
        print(f"  (creator comment skipped: {e})")


def build_description(concept: dict, site: dict) -> str:
    """SEO description: lead hashtags (render above title) + body + URL + extra hashtags."""
    desc = concept["description"].rstrip()
    if site["url"] not in desc:
        desc += f"\n{site['url']}"
    # Lead hashtags at top so the strongest ones surface above the title in the player
    return f"{LEAD_HASHTAGS}\n\n{desc}\n\n{EXTRA_HASHTAGS}"


def post_to_youtube(youtube, concept: dict, site: dict, video_path: str) -> str:
    """Upload video as a YouTube Short, return video ID."""
    description = build_description(concept, site)
    body = {
        "snippet": {
            "title": concept["title"],
            "description": description,
            "tags": concept.get("tags", []) + ["shorts", "short", "ezcalendar", "ai", "calendar", "productivity"],
            "categoryId": "22",  # People & Blogs
            "defaultLanguage": "en",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    print(f"  Uploading: {concept['title']}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
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

    youtube = get_youtube_client()
    playlist_id = ensure_playlist(youtube, youtube_log)

    results = []
    for i, concept in enumerate(concepts, 1):
        print(f"\n[{i}/{len(concepts)}] {concept['hook_type']} — {concept['id']}")
        print(f"  Template: {concept.get('scene_template', '?')}")
        print(f"  Title: {concept['title']}")

        try:
            video_path = generate_video(concept["visual_prompt"])
            video_id = post_to_youtube(youtube, concept, site, video_path)
            # Maximize-views layer
            add_to_playlist(youtube, playlist_id, video_id)
            comment = concept.get("pinned_comment") or f"Try it free → {site['url']}"
            post_creator_comment(youtube, video_id, comment)

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
