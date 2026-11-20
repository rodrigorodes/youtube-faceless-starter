"""Coleta tendências da YouTube Data API v3 e envia para o Studio.

Uso:
  python scripts/fetch_trends.py [--project-id <id>] [--queries "termo1,termo2"]

Lê a chave da YouTube Data API de credentials/token.env (YOUTUBE_API_KEY)
e o token de worker de .env (STUDIO_WORKER_TOKEN).
Nunca imprime tokens nem segredos.
"""
import argparse
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    res = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        res[k.strip()] = v.strip().strip("'\"")
    return res


def fetch_trends_for_queries(yt_key: str, queries: list[str], max_videos: int = 4) -> list[dict]:
    now = datetime.datetime.now(datetime.timezone.utc)
    past = now - datetime.timedelta(days=7)
    now_str = now.isoformat()
    past_str = past.isoformat()

    items = []
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
        except Exception as e:
            print(f"Aviso: falha ao buscar '{q}': {e}", file=sys.stderr)
            continue

        raw_items = data.get("items", [])
        vids = [it["id"]["videoId"] for it in raw_items if it.get("id", {}).get("videoId")]
        if not vids:
            continue

        evidence = []
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
                    vc = int(stats.get("viewCount", 0))
                    total_views += vc
                    evidence.append({
                        "title": snip.get("title", "Vídeo")[:200],
                        "url": f"https://youtube.com/watch?v={v.get('id')}",
                        "channel": snip.get("channelTitle", "")[:100],
                        "views": vc,
                        "published_at": snip.get("publishedAt"),
                    })
        except Exception as e:
            print(f"Aviso: falha ao buscar métricas de '{q}': {e}", file=sys.stderr)
            continue

        if evidence:
            items.append({
                "topic": q,
                "source_name": "YouTube Data API",
                "source_url": "https://www.googleapis.com/youtube/v3/search",
                "observed_at": now_str,
                "window_start": past_str,
                "window_end": now_str,
                "metric_name": "views",
                "metric_value": float(total_views),
                "evidence": evidence,
            })
    return items


def main():
    parser = argparse.ArgumentParser(description="Coleta tendências do YouTube para o Studio")
    parser.add_argument("--project-id", default="359e326ae66e46de86d4c560c74779f1", help="UUID do projeto")
    parser.add_argument("--queries", default="Música Eletrônica 2026,Alok 2026,Vintage Culture 2026,ADE 2026", help="Consultas separadas por vírgula")
    parser.add_argument("--api-url", default="http://localhost:8000/studio/trends", help="URL do endpoint de trends")
    args = parser.parse_args()

    token_env = parse_env_file(ROOT / "credentials" / "token.env")
    app_env = parse_env_file(ROOT / ".env")

    yt_key = token_env.get("YOUTUBE_API_KEY")
    if not yt_key:
        print("Erro: YOUTUBE_API_KEY não encontrada em credentials/token.env", file=sys.stderr)
        sys.exit(1)

    worker_token = app_env.get("STUDIO_WORKER_TOKEN")
    if not worker_token:
        print("Erro: STUDIO_WORKER_TOKEN não encontrada em .env", file=sys.stderr)
        sys.exit(1)

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    print(f"Consultando YouTube Data API para {len(queries)} termos...")
    items = fetch_trends_for_queries(yt_key, queries)
    if not items:
        print("Nenhum item retornado pela API do YouTube.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "project_id": args.project_id,
        "items": items,
    }

    req = urllib.request.Request(
        args.api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {worker_token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print(f"Sucesso! {data.get('stored', 0)} tópicos persistidos no Studio.")
    except urllib.error.HTTPError as e:
        print(f"Erro na ingestão ({e.code}): {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
