#!/usr/bin/env python3
"""
Video ad pipeline:
1. Claude writes 3 video concepts based on winning patterns
2. fal.ai (Kling) generates a real 5-10s vertical video per concept
3. Tweepy posts each video to Twitter/X with caption + hashtags
4. Tweet IDs saved to tweet_log.json for engagement tracking
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
import tweepy

CONFIG_FILE = Path("config.json")
PERF_FILE = Path("performance.json")
TWEET_LOG = Path("tweet_log.json")
ADS_DIR = Path("ads")


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def extract_winning_patterns(performance: dict) -> str:
    winners = [e for e in performance.get("ads", []) if e.get("score", 0) >= 7]
    if not winners:
        return "No winners yet — generate a diverse mix of styles to learn from."
    lines = [f"Score {w['score']}/10 | hook={w.get('hook_type','?')} | {w.get('notes', '')}" for w in winners]
    return "WINNING AD PATTERNS TO REPLICATE:\n" + "\n".join(lines)


def generate_video_concepts(config: dict, winning_context: str, today: str) -> list:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    site = config["websites"][0]

    prompt = f"""You are an expert short-form video ad director. Generate 3 video ad concepts.

PRODUCT: {site['name']}
URL: {site['url']}
DESCRIPTION: {site['description']}
AUDIENCE: {site['target_audience']}
UNIQUE VALUE: {site['unique_value']}
CTA: {site['cta_goal']}
BRAND VOICE: {config.get('brand_voice', 'fun and energetic')}

{winning_context}

Each video is 5-10 seconds, vertical (9:16), for Twitter/X. Think cinematic, scroll-stopping visuals.
The visual_prompt goes directly to an AI video model — be specific about motion, lighting, setting.
Do NOT mention text overlays in the visual_prompt — the video is pure visuals only.

Return ONLY valid JSON, no markdown:
{{
  "concepts": [
    {{
      "id": "{today}-v001",
      "visual_prompt": "Cinematic scene: a young woman on a busy city street at golden hour spots a colorful event flyer on a brick wall. She pulls out her phone, opens an app, snaps a photo. The camera pushes in on the phone screen as a calendar fills with event details automatically. She grins and walks away excited. Warm vibrant colors, smooth handheld motion.",
      "caption": "Saw a flyer. Didn't type a thing. It's already on my calendar ✨ Stop missing out → ezcalendar.vercel.app/calendar",
      "hashtags": "#EzCalendar #NeverMissOut #AICalendar",
      "hook_type": "curiosity",
      "strategy": "Show the core magic moment visually — snap to calendar — so the value is felt not just told."
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
    print(f"  Generating video...")
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


def post_to_twitter(caption: str, hashtags: str, video_path: str) -> str:
    """Upload video + post tweet, return tweet ID."""
    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    api = tweepy.API(auth)
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    print("  Uploading video to Twitter...")
    media = api.media_upload(
        filename=video_path,
        media_category="tweet_video",
        chunked=True,
    )

    # Wait for Twitter to process the video
    for _ in range(40):
        status = api.get_media_upload_status(media.media_id)
        state = getattr(getattr(status, "processing_info", None), "state", "succeeded")
        if state == "succeeded":
            break
        if state == "failed":
            raise RuntimeError("Twitter video processing failed")
        pct = getattr(getattr(status, "processing_info", None), "progress_percent", 0)
        print(f"  Twitter processing... {pct}%")
        time.sleep(6)

    tweet_text = f"{caption}\n{hashtags}"
    response = client.create_tweet(text=tweet_text, media_ids=[media.media_id])
    return str(response.data["id"])


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ADS_DIR.mkdir(exist_ok=True)

    config = load_json(CONFIG_FILE)
    performance = load_json(PERF_FILE)
    tweet_log = load_json(TWEET_LOG)
    if "tweets" not in tweet_log:
        tweet_log["tweets"] = []

    winning_context = extract_winning_patterns(performance)
    print(f"Winning context: {winning_context[:100]}...")

    print("\nGenerating video concepts with Claude...")
    concepts = generate_video_concepts(config, winning_context, today)
    print(f"Got {len(concepts)} concepts.")

    results = []
    for i, concept in enumerate(concepts, 1):
        print(f"\n[{i}/{len(concepts)}] {concept['hook_type']} — {concept['id']}")
        print(f"  Strategy: {concept['strategy']}")

        try:
            video_path = generate_video(concept["visual_prompt"])
            tweet_id = post_to_twitter(concept["caption"], concept["hashtags"], video_path)
            concept["tweet_id"] = tweet_id
            concept["status"] = "posted"
            print(f"  Posted! https://twitter.com/i/web/status/{tweet_id}")
            tweet_log["tweets"].append({
                "id": concept["id"],
                "tweet_id": tweet_id,
                "date": today,
                "hook_type": concept["hook_type"],
                "caption": concept["caption"],
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "metrics_checked": False,
            })
        except Exception as e:
            concept["status"] = "failed"
            concept["error"] = str(e)
            print(f"  FAILED: {e}")

        results.append(concept)
        time.sleep(15)  # buffer between posts

    (ADS_DIR / f"{today}.json").write_text(json.dumps({"date": today, "ads": results}, indent=2))
    TWEET_LOG.write_text(json.dumps(tweet_log, indent=2))

    posted = sum(1 for r in results if r["status"] == "posted")
    print(f"\nDone: {posted}/{len(results)} videos posted to Twitter.")


if __name__ == "__main__":
    main()
