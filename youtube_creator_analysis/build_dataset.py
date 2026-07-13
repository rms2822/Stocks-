import json

TOP_N_PER_CHANNEL = 25

def format_duration(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def main():
    raw = json.load(open("data/raw_data.json"))
    channels = []
    all_videos = []

    for c in raw:
        vids_1m = [v for v in c["videos"] if v["view_count"] >= 1_000_000]
        vids_1m.sort(key=lambda v: v["view_count"], reverse=True)
        top_vids = vids_1m[:TOP_N_PER_CHANNEL]

        channel_entry = {
            "handle": c["handle"],
            "channel_name": c["channel_name"],
            "category": c["category"],
            "subscriber_count": c["subscriber_count"],
            "video_count_scanned": len(c["videos"]),
            "video_count_1m_plus": len(vids_1m),
        }
        channels.append(channel_entry)

        for v in top_vids:
            all_videos.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "view_count": v["view_count"],
                "duration_sec": v["duration"],
                "duration": format_duration(v["duration"]),
                "url": v["url"],
                "channel_handle": c["handle"],
                "channel_name": c["channel_name"],
                "category": c["category"],
            })

    all_videos.sort(key=lambda v: v["view_count"], reverse=True)

    dataset = {
        "generated_note": "Scraped directly from YouTube (yt-dlp) — top videos with 1M+ views per channel",
        "channels": channels,
        "videos": all_videos,
    }

    with open("data/dataset.json", "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"{len(channels)} channels, {len(all_videos)} videos (>=1M views, top {TOP_N_PER_CHANNEL}/channel)")

if __name__ == "__main__":
    main()
