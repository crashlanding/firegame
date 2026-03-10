#!/usr/bin/env python3
"""
Twitter/X Archive to CSV Exporter
-----------------------------------
Parses a Twitter/X data archive (ZIP or extracted folder) and writes every
tweet to a CSV with columns:
  date        – ISO-8601 UTC timestamp
  content     – full tweet text
  type        – "reply" or "original"
  tweet_id    – Twitter's tweet ID (useful for reference)
  reply_to_id – the tweet ID being replied to (blank for originals)

Usage:
  python twitter_archive_to_csv.py <path-to-archive.zip>   # ZIP file
  python twitter_archive_to_csv.py <path-to-archive-dir>   # extracted folder
  python twitter_archive_to_csv.py                          # searches current dir

How to get your archive:
  1. Go to Twitter/X → Settings → Your Account → Download an archive of your data
  2. Request the archive and wait for the email (can take up to 24 hours)
  3. Download and unzip (or just hand the .zip directly to this script)
"""

import csv
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def parse_tweets_js(text: str) -> list[dict]:
    """Strip the JS variable assignment that Twitter wraps around the JSON."""
    # Format: window.YTD.tweets.part0 = [ ... ]
    match = re.search(r'=\s*(\[.*\])\s*$', text, re.DOTALL)
    if not match:
        raise ValueError("Unexpected tweets.js format – could not find JSON array.")
    return json.loads(match.group(1))


def fmt_date(twitter_date: str) -> str:
    """Convert Twitter's date string to ISO-8601 UTC."""
    # Twitter format: "Wed Apr 01 12:34:56 +0000 2020"
    try:
        dt = datetime.strptime(twitter_date, "%a %b %d %H:%M:%S +0000 %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return twitter_date  # return as-is if format is unexpected


def is_reply(tweet: dict) -> bool:
    """Return True if this tweet is a reply to someone else's tweet."""
    reply_to = tweet.get("in_reply_to_status_id_str") or ""
    reply_user = tweet.get("in_reply_to_user_id_str") or ""
    return bool(reply_to.strip() and reply_user.strip())


def clean_text(text: str) -> str:
    """Normalise whitespace / newlines for tidy CSV cells."""
    return " ".join(text.split())


# ── archive loading ───────────────────────────────────────────────────────────

def load_tweet_parts_from_zip(zip_path: Path) -> list[str]:
    """Return the raw text of every tweets*.js file inside the ZIP."""
    parts = []
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist()
                 if re.search(r'data/tweets.*\.js$', n, re.IGNORECASE)]
        if not names:
            raise FileNotFoundError(
                "No tweets*.js files found inside the ZIP. "
                "Make sure you downloaded the full Twitter data archive."
            )
        for name in sorted(names):
            parts.append(zf.read(name).decode("utf-8"))
    return parts


def load_tweet_parts_from_dir(dir_path: Path) -> list[str]:
    """Return the raw text of every tweets*.js file inside an extracted dir."""
    data_dir = dir_path / "data"
    if not data_dir.exists():
        data_dir = dir_path  # some people extract one level deeper
    parts = []
    for p in sorted(data_dir.glob("tweets*.js")):
        parts.append(p.read_text(encoding="utf-8"))
    if not parts:
        raise FileNotFoundError(
            f"No tweets*.js files found in {data_dir}. "
            "Is this the right directory?"
        )
    return parts


def collect_all_tweets(raw_parts: list[str]) -> list[dict]:
    """Parse all tweet parts and return a flat list of tweet dicts."""
    all_tweets = []
    for raw in raw_parts:
        records = parse_tweets_js(raw)
        for record in records:
            # Archive wraps each entry as {"tweet": {...}}
            tweet = record.get("tweet", record)
            all_tweets.append(tweet)
    return all_tweets


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # Determine archive path
    if len(sys.argv) >= 2:
        archive_path = Path(sys.argv[1])
    else:
        # Auto-detect a ZIP or extracted folder in the current directory
        candidates = list(Path(".").glob("twitter-*.zip")) + \
                     list(Path(".").glob("*.zip"))
        if candidates:
            archive_path = candidates[0]
            print(f"Auto-detected archive: {archive_path}")
        elif (Path(".") / "data" / "tweets.js").exists():
            archive_path = Path(".")
        else:
            print(__doc__)
            sys.exit(1)

    # Load raw tweet JS parts
    if archive_path.is_file() and archive_path.suffix.lower() == ".zip":
        print(f"Reading ZIP: {archive_path}")
        raw_parts = load_tweet_parts_from_zip(archive_path)
    elif archive_path.is_dir():
        print(f"Reading directory: {archive_path}")
        raw_parts = load_tweet_parts_from_dir(archive_path)
    else:
        print(f"Error: '{archive_path}' is not a ZIP file or directory.")
        sys.exit(1)

    # Parse
    print(f"Parsing {len(raw_parts)} tweet file(s)…")
    tweets = collect_all_tweets(raw_parts)
    print(f"Found {len(tweets):,} tweets.")

    # Sort chronologically (oldest first)
    tweets.sort(key=lambda t: t.get("created_at", ""))

    # Write CSV
    output_path = Path("my_tweets.csv")
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "type", "content", "tweet_id", "reply_to_id"
        ])
        writer.writeheader()
        for t in tweets:
            writer.writerow({
                "date":        fmt_date(t.get("created_at", "")),
                "type":        "reply" if is_reply(t) else "original",
                "content":     clean_text(t.get("full_text", "")),
                "tweet_id":    t.get("id_str", ""),
                "reply_to_id": t.get("in_reply_to_status_id_str", ""),
            })

    print(f"\nDone! CSV written to: {output_path.resolve()}")
    print(f"  Total tweets : {len(tweets):,}")
    originals = sum(1 for t in tweets if not is_reply(t))
    replies   = len(tweets) - originals
    print(f"  Originals    : {originals:,}")
    print(f"  Replies      : {replies:,}")


if __name__ == "__main__":
    main()
