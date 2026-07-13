import json
import time
import sys
from channels import CHANNELS
import yt_dlp

OUT_PATH = "data/raw_data.json"
PER_CHANNEL_LIMIT = 350

def fetch_channel(handle, category, channel_id=None):
    url = (f"https://www.youtube.com/channel/{channel_id}/videos" if channel_id
           else f"https://www.youtube.com/@{handle}/videos")
    opts = {
        "extract_flat": True,
        "playlistend": PER_CHANNEL_LIMIT,
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    channel_name = info.get("channel") or info.get("uploader") or handle
    subs = info.get("channel_follower_count")
    videos = []
    for e in info.get("entries") or []:
        if not e:
            continue
        vid = e.get("id")
        title = e.get("title")
        views = e.get("view_count")
        duration = e.get("duration")
        if not vid or not title or views is None:
            continue
        videos.append({
            "video_id": vid,
            "title": title,
            "view_count": views,
            "duration": duration,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return {
        "handle": handle,
        "channel_name": channel_name,
        "category": category,
        "subscriber_count": subs,
        "videos": videos,
    }

def main():
    results = []
    for c in CHANNELS:
        handle = c["handle"]
        print(f"Fetching {handle} ...", file=sys.stderr)
        for attempt in range(3):
            try:
                data = fetch_channel(handle, c["category"], channel_id=c.get("channel_id"))
                print(f"  -> {data['channel_name']}: {len(data['videos'])} videos, subs={data['subscriber_count']}", file=sys.stderr)
                results.append(data)
                break
            except Exception as ex:
                print(f"  attempt {attempt+1} failed: {ex}", file=sys.stderr)
                time.sleep(3)
        else:
            print(f"  FAILED permanently: {handle}", file=sys.stderr)

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} channels to {OUT_PATH}", file=sys.stderr)

if __name__ == "__main__":
    main()
