#!/usr/bin/env python3
"""
Pulls engagement metrics for yesterday's tweets.
Auto-scores them 0-10 and writes results to performance.json.
The nightly agent reads performance.json to learn winning patterns.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import tweepy

TWEET_LOG = Path("tweet_log.json")
PERF_FILE = Path("performance.json")


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def score_from_metrics(metrics: dict) -> int:
    """Score 0-10 based on engagement rate. Clicks weighted highest."""
    impressions = metrics.get("impression_count", 0)
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    clicks = metrics.get("url_link_clicks", 0)

    if impressions == 0:
        return 0

    # Clicks = 3pts, retweets = 2pts, likes = 1pt
    weighted = (clicks * 3 + retweets * 2 + likes) / impressions * 100

    if weighted >= 5:   return 10
    if weighted >= 3:   return 8
    if weighted >= 1.5: return 6
    if weighted >= 0.5: return 4
    return 2


def main():
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    tweet_log = load_json(TWEET_LOG)
    performance = load_json(PERF_FILE)
    if "ads" not in performance:
        performance["ads"] = []

    existing_ids = {e["id"] for e in performance["ads"]}
    updated = 0

    for tweet in tweet_log.get("tweets", []):
        if tweet.get("metrics_checked"):
            continue

        posted_at = datetime.fromisoformat(tweet["posted_at"])
        if datetime.now(timezone.utc) - posted_at < timedelta(hours=23):
            print(f"  Skipping {tweet['id']} — not 24hrs old yet")
            continue

        try:
            response = client.get_tweet(
                tweet["tweet_id"],
                tweet_fields=["public_metrics", "non_public_metrics"],
                user_auth=True,
            )
            metrics = {}
            if response.data.public_metrics:
                metrics.update(response.data.public_metrics)
            if hasattr(response.data, "non_public_metrics") and response.data.non_public_metrics:
                metrics.update(response.data.non_public_metrics)

            score = score_from_metrics(metrics)
            notes = (
                f"impressions={metrics.get('impression_count', 0)} "
                f"likes={metrics.get('like_count', 0)} "
                f"retweets={metrics.get('retweet_count', 0)} "
                f"clicks={metrics.get('url_link_clicks', 0)}"
            )

            if tweet["id"] not in existing_ids:
                performance["ads"].append({
                    "id": tweet["id"],
                    "tweet_id": tweet["tweet_id"],
                    "score": score,
                    "notes": notes,
                    "hook_type": tweet.get("hook_type"),
                    "auto_scored": True,
                })
                existing_ids.add(tweet["id"])
                updated += 1
                print(f"  Scored {tweet['id']}: {score}/10 — {notes}")

            tweet["metrics_checked"] = True

        except Exception as e:
            print(f"  Could not fetch metrics for {tweet['tweet_id']}: {e}")

    PERF_FILE.write_text(json.dumps(performance, indent=2))
    TWEET_LOG.write_text(json.dumps(tweet_log, indent=2))
    print(f"\nEngagement tracking done. {updated} new scores saved.")


if __name__ == "__main__":
    main()
