# Autonomous Video Ad Agent

Runs every night: generates AI video ads, posts them to Twitter/X, tracks engagement, and gets smarter over time.

## How it works

```
2:00am UTC — Nightly Video Ad Generation
  1. Claude writes 3 video concepts based on your winning patterns
  2. fal.ai (Kling AI) generates a real 5-10s vertical video per concept
  3. Each video is auto-posted to your Twitter/X with caption + hashtags
  4. Tweet IDs saved to tweet_log.json

6:00am UTC — Engagement Tracker (runs 28hrs after posting)
  1. Pulls real metrics from Twitter: impressions, likes, retweets, clicks
  2. Auto-scores each ad 0-10 based on engagement rate
  3. Saves scores to performance.json
  4. Next night, the agent reads those scores and generates more ads
     in the style of your winners
```

The loop is fully autonomous. The longer it runs, the smarter it gets.

## Setup

### Step 1 — Anthropic API key
- Get key: https://console.anthropic.com/settings/keys
- Add GitHub secret: `ANTHROPIC_API_KEY`

### Step 2 — fal.ai API key (video generation)
- Sign up: https://fal.ai → Dashboard → API Keys
- Add GitHub secret: `FAL_API_KEY`
- Cost: ~$0.05–0.30 per video (3 videos/night = ~$0.15–0.90/night)

### Step 3 — Twitter/X Developer keys (auto-posting)
- Apply: https://developer.twitter.com/en/portal/dashboard
- Create an app, generate all 4 keys
- Add GitHub secrets:
  - `TWITTER_API_KEY`
  - `TWITTER_API_SECRET`
  - `TWITTER_ACCESS_TOKEN`
  - `TWITTER_ACCESS_SECRET`

### Step 4 — Edit config.json
Fill in your website, product description, target audience, CTA goal.

## File structure

```
generate_video_ads.py       # Main pipeline: concept → video → post
track_engagement.py         # Pulls Twitter metrics, auto-scores ads
config.json                 # Your website/product info
performance.json            # Auto-maintained scores (agent learns from this)
tweet_log.json              # Auto-maintained log of posted tweets
ads/                        # Daily log of generated concepts + status
.github/workflows/
  nightly_ads.yml           # 2am — generate + post
  track_engagement.yml      # 6am — score engagement
  score_ad.yml              # Manual scoring form (optional override)
```

## Costs per night
| Service | Usage | Est. cost |
|---|---|---|
| Claude Opus (concepts) | ~2k tokens | ~$0.03 |
| fal.ai Kling (3 videos) | 3 × 5s clips | ~$0.45 |
| Twitter API | posting + metrics | Free |
| **Total** | | **~$0.50/night** |
