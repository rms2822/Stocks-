import json
import re
import statistics
from collections import defaultdict

STOPWORDS = set("""
a an the of in on to and is are was were for with my this that i we you your our it
its at by from as or but if then so than not no do does did be been being have has
had will would can could should just about into over under out up down off vs
""".split())

WORD_RE = re.compile(r"[a-z0-9$%']+")


def tokenize(title):
    return [w.strip("'") for w in WORD_RE.findall(title.lower()) if w.strip("'")]


def mean(xs):
    return statistics.mean(xs) if xs else 0


def median(xs):
    return statistics.median(xs) if xs else 0


FEATURES = {
    "has_number": lambda t: bool(re.search(r"\d", t)),
    "has_question_mark": lambda t: "?" in t,
    "has_exclamation": lambda t: "!" in t,
    "has_dollar_sign": lambda t: "$" in t,
    "has_brackets": lambda t: bool(re.search(r"[\(\)\[\]]", t)),
    "has_colon": lambda t: ":" in t,
    "starts_with_number": lambda t: bool(re.match(r"^\s*[\d$]", t)),
    "has_all_caps_word": lambda t: any(
        w.isupper() and len(w) >= 3 and w.isalpha() for w in t.split()
    ),
    "has_first_person": lambda t: bool(re.search(r"\b(i|i'm|my|we|our)\b", t.lower())),
    "has_second_person": lambda t: bool(re.search(r"\b(you|your|you're)\b", t.lower())),
    "has_superlative": lambda t: bool(re.search(
        r"\b(best|worst|biggest|smallest|fastest|extreme|insane|craziest|ultimate|"
        r"greatest|never|always|secret|impossible|perfect|first|last|most|least)\b",
        t.lower(),
    )),
    "has_how_to": lambda t: t.lower().startswith("how to") or " how to " in t.lower(),
    "has_wh_word": lambda t: bool(re.match(r"^(why|what|how|when|where|which|who)\b", t.lower())),
}


def word_len_bucket(n):
    if n <= 4:
        return "1-4 words"
    if n <= 7:
        return "5-7 words"
    if n <= 10:
        return "8-10 words"
    return "11+ words"


def char_len_bucket(n):
    if n <= 30:
        return "<=30 chars"
    if n <= 50:
        return "31-50 chars"
    if n <= 70:
        return "51-70 chars"
    return "71+ chars"


def main():
    dataset = json.load(open("data/dataset.json"))
    videos = dataset["videos"]
    views = [v["view_count"] for v in videos]

    overall = {
        "video_count": len(videos),
        "avg_views": mean(views),
        "median_views": median(views),
        "max_views": max(views),
        "min_views": min(views),
    }

    # Feature impact
    feature_impact = []
    for name, fn in FEATURES.items():
        with_v = [v["view_count"] for v in videos if fn(v["title"])]
        without_v = [v["view_count"] for v in videos if not fn(v["title"])]
        avg_with = mean(with_v)
        avg_without = mean(without_v)
        feature_impact.append({
            "feature": name,
            "count_with": len(with_v),
            "count_without": len(without_v),
            "avg_views_with": avg_with,
            "avg_views_without": avg_without,
            "median_views_with": median(with_v),
            "median_views_without": median(without_v),
            "lift": (avg_with / avg_without) if avg_without else None,
        })
    feature_impact.sort(key=lambda f: (f["lift"] or 0), reverse=True)

    # Word frequency + avg views per word
    word_stats = defaultdict(list)
    for v in videos:
        seen = set()
        for w in tokenize(v["title"]):
            if w in STOPWORDS or len(w) < 2:
                continue
            if w in seen:
                continue
            seen.add(w)
            word_stats[w].append(v["view_count"])

    word_frequency = []
    for w, vlist in word_stats.items():
        if len(vlist) < 4:
            continue
        word_frequency.append({
            "word": w,
            "count": len(vlist),
            "avg_views": mean(vlist),
            "median_views": median(vlist),
        })
    word_frequency.sort(key=lambda w: w["count"], reverse=True)
    top_words_by_count = word_frequency[:60]
    top_words_by_avg_views = sorted(
        [w for w in word_frequency if w["count"] >= 5],
        key=lambda w: w["avg_views"], reverse=True
    )[:30]

    # Length buckets
    word_len_stats = defaultdict(list)
    char_len_stats = defaultdict(list)
    for v in videos:
        wl = len(tokenize(v["title"]))
        cl = len(v["title"])
        word_len_stats[word_len_bucket(wl)].append(v["view_count"])
        char_len_stats[char_len_bucket(cl)].append(v["view_count"])

    length_analysis = {
        "by_word_count": [
            {"bucket": b, "count": len(vs), "avg_views": mean(vs), "median_views": median(vs)}
            for b, vs in sorted(word_len_stats.items(), key=lambda kv: ["1-4 words", "5-7 words", "8-10 words", "11+ words"].index(kv[0]))
        ],
        "by_char_count": [
            {"bucket": b, "count": len(vs), "avg_views": mean(vs), "median_views": median(vs)}
            for b, vs in sorted(char_len_stats.items(), key=lambda kv: ["<=30 chars", "31-50 chars", "51-70 chars", "71+ chars"].index(kv[0]))
        ],
    }

    # Category stats
    cat_videos = defaultdict(list)
    for v in videos:
        cat_videos[v["category"]].append(v)

    category_stats = []
    for cat, vids in cat_videos.items():
        vs = [v["view_count"] for v in vids]
        cat_word_counts = defaultdict(int)
        for v in vids:
            for w in set(tokenize(v["title"])):
                if w in STOPWORDS or len(w) < 2:
                    continue
                cat_word_counts[w] += 1
        top_words = sorted(cat_word_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        category_stats.append({
            "category": cat,
            "video_count": len(vids),
            "avg_views": mean(vs),
            "median_views": median(vs),
            "avg_title_len_words": mean([len(tokenize(v["title"])) for v in vids]),
            "top_words": [{"word": w, "count": c} for w, c in top_words],
        })
    category_stats.sort(key=lambda c: c["avg_views"], reverse=True)

    # Channel stats
    channel_videos = defaultdict(list)
    for v in videos:
        channel_videos[v["channel_handle"]].append(v)

    channel_stats = []
    for c in dataset["channels"]:
        vids = channel_videos.get(c["handle"], [])
        vs = [v["view_count"] for v in vids]
        channel_stats.append({
            "handle": c["handle"],
            "channel_name": c["channel_name"],
            "category": c["category"],
            "subscriber_count": c["subscriber_count"],
            "qualifying_video_count": len(vids),
            "avg_views": mean(vs),
            "median_views": median(vs),
            "top_video_title": max(vids, key=lambda v: v["view_count"])["title"] if vids else None,
            "top_video_views": max(vs) if vs else 0,
        })
    channel_stats.sort(key=lambda c: c["avg_views"], reverse=True)

    analysis = {
        "overall": overall,
        "feature_impact": feature_impact,
        "top_words_by_count": top_words_by_count,
        "top_words_by_avg_views": top_words_by_avg_views,
        "length_analysis": length_analysis,
        "category_stats": category_stats,
        "channel_stats": channel_stats,
    }

    with open("data/analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)

    print("Wrote analysis.json")
    print(f"Overall avg views: {overall['avg_views']:,.0f}, median: {overall['median_views']:,.0f}")
    print("\nTop feature lifts:")
    for f in feature_impact[:6]:
        print(f"  {f['feature']:20s} lift={f['lift']:.2f}x  n_with={f['count_with']}")


if __name__ == "__main__":
    main()
