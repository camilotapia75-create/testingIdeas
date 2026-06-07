#!/usr/bin/env python3
"""
Autonomous ad generation agent.
Runs nightly, reads performance history, generates social media ad copy
biased toward winning patterns.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ADS_DIR = Path("ads")
CONFIG_FILE = Path("config.json")
PERF_FILE = Path("performance.json")


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def extract_winning_patterns(performance: dict, ads_dir: Path) -> str:
    """Find ads scored >= 7 and return them as context for the model."""
    scored = {entry["id"]: entry for entry in performance.get("ads", []) if entry.get("score", 0) >= 7}
    if not scored:
        return "No high-scoring ads yet — generate a diverse mix to learn from."

    winners = []
    for ads_file in sorted(ads_dir.glob("*.json")):
        day_ads = json.loads(ads_file.read_text()).get("ads", [])
        for ad in day_ads:
            if ad["id"] in scored:
                entry = scored[ad["id"]]
                winners.append(
                    f"[Score {entry['score']}/10] {ad['platform'].upper()} — {ad['copy']}"
                    + (f"\n  Notes: {entry['notes']}" if entry.get("notes") else "")
                )

    if not winners:
        return "Scores recorded but no matching ad copy found — generate a diverse mix."

    return "HIGH-PERFORMING ADS TO LEARN FROM:\n" + "\n\n".join(winners)


def build_prompt(config: dict, winning_context: str, today: str) -> str:
    websites = config.get("websites", [])
    platforms = config.get("platforms", ["twitter", "instagram", "linkedin"])
    count = config.get("ads_per_run", 10)
    tone_prefs = ", ".join(config.get("tone_preferences", ["conversational"]))
    brand_voice = config.get("brand_voice", "friendly and helpful")

    website_context = ""
    for site in websites:
        website_context += (
            f"- Website: {site['name']} ({site['url']})\n"
            f"  Product/service: {site['description']}\n"
            f"  Target audience: {site['target_audience']}\n"
            f"  Unique value: {site['unique_value']}\n"
            f"  Goal: get people to {site['cta_goal']}\n"
        )

    return f"""You are an expert performance marketing copywriter. Generate {count} high-converting social media ads.

DATE: {today}

WEBSITES/PRODUCTS TO PROMOTE:
{website_context}
BRAND VOICE: {brand_voice}
TONE PREFERENCES: {tone_prefs}
PLATFORMS: {', '.join(platforms)}

{winning_context}

INSTRUCTIONS:
- Study the high-performing ads above carefully. Identify what made them work: the hook style, emotional trigger, CTA phrasing, length, structure.
- Generate {count} new ads that are inspired by those winning patterns but are fresh and original (not copies).
- If there are no winners yet, generate a diverse set testing different hooks (curiosity, pain point, social proof, bold claim, question).
- Each ad must be platform-appropriate:
  * twitter: max 280 chars, punchy, with 1-2 relevant hashtags
  * instagram: 1-3 sentences + emojis + 3-5 hashtags
  * linkedin: professional tone, 2-4 sentences, no hashtags or 1 max
- Always include a clear CTA that drives to the website URL.
- Spread ads across all platforms evenly.

Return ONLY valid JSON in this exact format, no other text:
{{
  "date": "{today}",
  "ads": [
    {{
      "id": "{today}-001",
      "platform": "twitter",
      "website": "site name",
      "hook_type": "curiosity|pain_point|social_proof|bold_claim|question",
      "copy": "the full ad copy here",
      "notes": "brief note on the strategy used"
    }}
  ]
}}"""


def generate_ads(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ADS_DIR.mkdir(exist_ok=True)

    config = load_json(CONFIG_FILE)
    performance = load_json(PERF_FILE)

    if not config.get("websites"):
        print("ERROR: config.json has no websites configured. Edit config.json first.")
        return

    winning_context = extract_winning_patterns(performance, ADS_DIR)
    print(f"Winning context:\n{winning_context[:500]}...\n")

    prompt = build_prompt(config, winning_context, today)
    print("Generating ads with Claude...")

    result = generate_ads(prompt)

    output_path = ADS_DIR / f"{today}.json"
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Saved {len(result.get('ads', []))} ads to {output_path}")

    # Print a preview
    for ad in result.get("ads", [])[:3]:
        print(f"\n[{ad['platform'].upper()}] {ad['hook_type']}")
        print(ad["copy"])


if __name__ == "__main__":
    main()
