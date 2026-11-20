"""Adaptador para coleta de tendências na YouTube Data API v3."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from ..application.categories import YouTubeApiError
from ..domain.trends import Evidence, TrendItem


def fetch_youtube_trends(yt_key: str, queries: list[str], max_videos: int = 4) -> list[TrendItem]:
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    items: list[TrendItem] = []
    for q in queries:
        params = urllib.parse.urlencode({
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "publishedAfter": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxResults": max_videos,
            "q": q,
            "key": yt_key,
        })
        url = f"https://www.googleapis.com/youtube/v3/search?{params}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise YouTubeApiError(f"YouTube search error ({e.code}): {e.reason}") from e
        except Exception as e:
            raise YouTubeApiError(f"YouTube search request failed: {e}") from e

        raw_items = data.get("items", [])
        vids = [it["id"]["videoId"] for it in raw_items if it.get("id", {}).get("videoId")]
        if not vids:
            continue

        evidence: list[Evidence] = []
        total_views = 0
        p2 = urllib.parse.urlencode({
            "part": "statistics,snippet",
            "id": ",".join(vids),
            "key": yt_key,
        })
        u2 = f"https://www.googleapis.com/youtube/v3/videos?{p2}"
        try:
            req2 = urllib.request.Request(u2)
            with urllib.request.urlopen(req2, timeout=15) as r2:
                d2 = json.loads(r2.read().decode())
                for v in d2.get("items", []):
                    snip = v.get("snippet", {})
                    stats = v.get("statistics", {})
                    vc = int(stats.get("viewCount") or 0)
                    total_views += vc
                    published_str = snip.get("publishedAt")
                    published_at = None
                    if published_str:
                        try:
                            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    evidence.append(
                        Evidence(
                            title=snip.get("title", "Vídeo")[:200],
                            url=f"https://youtube.com/watch?v={v.get('id')}",
                            channel=snip.get("channelTitle", "")[:100],
                            views=vc,
                            published_at=published_at,
                        )
                    )
        except urllib.error.HTTPError as e:
            raise YouTubeApiError(f"YouTube video statistics error ({e.code}): {e.reason}") from e
        except Exception as e:
            raise YouTubeApiError(f"YouTube video statistics request failed: {e}") from e

        if evidence:
            items.append(
                TrendItem(
                    topic=q,
                    source_name="YouTube Data API",
                    source_url="https://www.googleapis.com/youtube/v3/search",
                    observed_at=now,
                    window_start=past,
                    window_end=now,
                    metric_name="views",
                    metric_value=float(total_views),
                    evidence=evidence[:5],
                )
            )
    return items


def fetch_popular_trends(yt_key: str, region_code: str, max_results: int = 10) -> list[TrendItem]:
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    params = urllib.parse.urlencode({
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": max_results,
        "key": yt_key,
    })
    url = f"https://www.googleapis.com/youtube/v3/videos?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise YouTubeApiError(f"YouTube popular trends error ({e.code}): {e.reason}") from e
    except Exception as e:
        raise YouTubeApiError(f"YouTube popular trends request failed: {e}") from e

    region = region_code.upper()
    region_name = {"BR": "Brasil", "US": "EUA"}.get(region, region)
    source_name = f"YouTube {region_name} (Em Alta)"
    source_url = "https://www.youtube.com/feed/trending"

    items: list[TrendItem] = []
    for v in data.get("items", []):
        vid = v.get("id")
        if not vid:
            continue
        snip = v.get("snippet", {})
        stats = v.get("statistics", {})
        vc = int(stats.get("viewCount") or 0)

        published_str = snip.get("publishedAt")
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        raw_title = (snip.get("title") or "").strip() or "Vídeo em alta"
        topic = raw_title[:300] if len(raw_title) >= 3 else (raw_title + "   ")[:300]
        evidence_title = ((snip.get("title") or "").strip() or "Vídeo")[:200]
        channel = ((snip.get("channelTitle") or "").strip())[:100]

        ev = Evidence(
            title=evidence_title,
            url=f"https://youtube.com/watch?v={vid}",
            channel=channel,
            views=vc,
            published_at=published_at,
        )

        items.append(
            TrendItem(
                topic=topic,
                source_name=source_name,
                source_url=source_url,
                observed_at=now,
                window_start=past,
                window_end=now,
                metric_name="views",
                metric_value=float(vc),
                evidence=[ev],
            )
        )

    return items
