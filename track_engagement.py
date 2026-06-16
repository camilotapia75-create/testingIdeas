#!/usr/bin/env python3
"""
Runs 48 hours after a video is posted.
Fetches real YouTube view/like/comment counts and auto-scores each video 0-10.
Updates performance.json so the agent learns which ad styles win.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

YOUTUBE_LOG = Path("youtube_log.json")
PERF_FILE = Path("performance.json")


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    return build("youtube", "v3", credentials=creds)


def fetch_metrics(youtube, video_id: str) -> dict:
    resp = youtube.videos().list(
        part="statistics",
        id=video_id,
    ).execute()
    if not resp.get("items"):
        return {}
    stats = resp["items"][0]["statistics"]
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


def score_video(metrics: dict) -> float:
    """Score 0-10: views weighted most, then likes, then comments."""
    views = metrics.get("views", 0)
    likes = metrics.get("likes", 0)
    comments = metrics.get("comments", 0)

    # Tier thresholds for a new channel Shorts
    view_score = min(views / 1000, 1.0) * 6   # up to 6pts for 1k+ views
    like_score = min(likes / 50, 1.0) * 3     # up to 3pts for 50+ likes
    comment_score = min(comments / 10, 1.0)   # up to 1pt for 10+ comments
    return round(view_score + like_score + comment_score, 2)


def main():
    youtube_log = load_json(YOUTUBE_LOG)
    performance = load_json(PERF_FILE)
    if "ads" not in performance:
        performance["ads"] = []

    unchecked = [
        v for v in youtube_log.get("videos", [])
        if not v.get("metrics_checked") and v.get("youtube_id")
    ]

    if not unchecked:
        print("No new videos to score.")
        return

    youtube = get_youtube_client()
    print(f"Scoring {len(unchecked)} video(s)...")

    for entry in unchecked:
        video_id = entry["youtube_id"]
        print(f"  Fetching metrics for {video_id}...")
        metrics = fetch_metrics(youtube, video_id)
        if not metrics:
            print(f"  No data yet for {video_id}, skipping.")
            continue

        score = score_video(metrics)
        print(f"  Views={metrics['views']} Likes={metrics['likes']} Comments={metrics['comments']} -> Score {score}/10")

        performance["ads"].append({
            "id": entry["id"],
            "youtube_id": video_id,
            "date": entry["date"],
            "hook_type": entry.get("hook_type"),
            "scene_template": entry.get("scene_template"),
            "title": entry.get("title"),
            "score": score,
            "metrics": metrics,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "notes": "",
        })
        entry["metrics_checked"] = True
        entry["score"] = score
        entry["metrics"] = metrics

    YOUTUBE_LOG.write_text(json.dumps(youtube_log, indent=2))
    PERF_FILE.write_text(json.dumps(performance, indent=2))
    print("Done. performance.json updated.")


if __name__ == "__main__":
    main()
