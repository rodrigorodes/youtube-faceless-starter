import asyncio
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

app = FastAPI(title="Faceless Renderer MVP", version="0.1.0")
OUTPUT = Path(os.getenv("OUTPUT_DIR", "/data/output"))
JOBS = Path(os.getenv("JOB_DIR", "/data/jobs"))
OUTPUT.mkdir(parents=True, exist_ok=True)
JOBS.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

class VideoRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    format: str = Field(default="short", pattern="^(short)$")
    duration_seconds: int = Field(default=30, ge=10, le=60)
    style: str = Field(default="documentary", max_length=80)


def wrap(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines

DEMO_SLIDES = ["{topic}", "Uma pergunta interessante para explorar.", "Entenda os pontos principais e descubra novas perspectivas.", "Qual é a sua opinião? Compartilhe nos comentários."]
_vertex_credentials = None


def build_prompt(topic, style):
    return ("Escreva exatamente 4 frases curtas em português do Brasil para slides de um Short informativo. "
            "Sem alegações factuais não verificadas. Responda APENAS JSON array de 4 strings. "
            f"Tema: {topic}. Estilo: {style}.")


def resolve_provider():
    """AI_PROVIDER: auto (padrão: gemini se houver GEMINI_API_KEY, senão demo), demo, gemini, vertex ou opencode."""
    provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if provider == "auto":
        return "gemini" if os.getenv("GEMINI_API_KEY", "").strip() else "demo"
    if provider not in ("demo", "gemini", "vertex", "opencode"):
        raise HTTPException(status_code=500, detail="Invalid AI_PROVIDER; use auto, demo, gemini, vertex or opencode")
    return provider


def vertex_endpoint(project, location, model):
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"


def vertex_access_token():
    """Token OAuth via Application Default Credentials (bloqueante; chamar em thread)."""
    global _vertex_credentials
    import google.auth
    from google.auth.transport.requests import Request
    if _vertex_credentials is None:
        _vertex_credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _vertex_credentials.valid:
        _vertex_credentials.refresh(Request())
    return _vertex_credentials.token


async def post_json(url, headers, payload, timeout=40):
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    return response.json()


def parse_slides(data):
    return parse_slides_text(data["candidates"][0]["content"]["parts"][0]["text"])


def parse_slides_text(raw):
    raw = raw.strip()
    if raw.startswith("```"):  # modelos sem modo JSON costumam envolver em ```json
        raw = raw.strip("`").removeprefix("json").strip()
    slides = json.loads(raw)
    if not isinstance(slides, list) or len(slides) != 4 or not all(isinstance(s, str) for s in slides):
        raise ValueError("Model returned an invalid slide list")
    return [s[:260] for s in slides]


async def generate_with_opencode(prompt):
    """Chama o bridge local (scripts/opencode-bridge.py), que usa o login OAuth do OpenCode."""
    token = os.getenv("OPENCODE_BRIDGE_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="AI_PROVIDER=opencode requires OPENCODE_BRIDGE_TOKEN")
    base = os.getenv("OPENCODE_BRIDGE_URL", "http://host.docker.internal:8787").rstrip("/")
    try:
        data = await post_json(f"{base}/generate", {"Authorization": f"Bearer {token}"}, {"prompt": prompt}, timeout=100)
        return parse_slides_text(data["text"])
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
        raise HTTPException(status_code=502, detail=f"OpenCode bridge failed: {type(exc).__name__}{status}; is scripts/opencode-bridge.py running?") from exc


async def generate_script(topic, style):
    provider = resolve_provider()
    if provider == "demo":
        return [text.format(topic=topic) if "{topic}" in text else text for text in DEMO_SLIDES]
    if provider == "opencode":
        return await generate_with_opencode(build_prompt(topic, style))
    payload = {"contents": [{"role": "user", "parts": [{"text": build_prompt(topic, style)}]}], "generationConfig": {"responseMimeType": "application/json"}}
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=gemini requires GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": key}
        label = "Gemini"
    else:
        project = os.getenv("VERTEX_PROJECT", "").strip()
        if not project:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=vertex requires VERTEX_PROJECT")
        location = os.getenv("VERTEX_LOCATION", "global").strip() or "global"
        model = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
        url = vertex_endpoint(project, location, model)
        label = "Vertex"
        try:
            token = await asyncio.to_thread(vertex_access_token)
        except Exception as exc:  # google.auth.exceptions.* (DefaultCredentials, Refresh)
            raise HTTPException(status_code=502, detail=f"Vertex auth failed: {type(exc).__name__}; check Application Default Credentials") from exc
        headers = {"Authorization": f"Bearer {token}"}
    try:
        return parse_slides(await post_json(url, headers, payload))
    except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
        raise HTTPException(status_code=502, detail=f"{label} failed: {type(exc).__name__}{status}; check credentials, project, model and quota") from exc


def make_slide(text, path, index):
    width, height = 720, 1280
    img = Image.new("RGB", (width, height), (10, 20 + index * 7, 42 + index * 8))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 44)
    small = ImageFont.truetype(FONT, 25)
    draw.rounded_rectangle((38, 150, 682, 1120), radius=32, outline=(55, 140, 220), width=4)
    draw.text((66, 205), f"CENA {index + 1:02d}", font=small, fill=(115, 205, 255))
    lines = wrap(draw, text, font, 575)
    y = 490 - (len(lines) - 1) * 30
    for line in lines:
        draw.text((70, y), line, font=font, fill="white")
        y += 65
    draw.text((66, 1050), "YOUTUBE FACELESS • DEMO", font=small, fill=(145, 165, 185))
    img.save(path)


@app.get("/health")
def health():
    return {"status": "ok", "ffmpeg": True}


@app.post("/videos")
async def create_video(request: VideoRequest):
    job_id = uuid.uuid4().hex
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    script = await generate_script(request.topic, request.style)
    duration = request.duration_seconds
    per_scene = duration / len(script)
    parts = []
    for i, text in enumerate(script):
        png = job_dir / f"scene_{i:02d}.png"
        mp4 = job_dir / f"scene_{i:02d}.mp4"
        make_slide(text, png, i)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "25", "-i", str(png), "-t", str(per_scene), "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(mp4)]
        subprocess.run(cmd, check=True, timeout=150)
        parts.append(mp4)
    concat = job_dir / "concat.txt"
    concat.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    output = OUTPUT / f"{job_id}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)], check=True, timeout=150)
    manifest = {"id": job_id, "topic": request.topic, "status": "AWAITING_APPROVAL", "script": script, "duration_seconds": duration, "video_url": f"http://localhost:8000/videos/{job_id}/file", "note": "Demo silent slideshow; not yet voice/image generation or YouTube upload"}
    (job_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


@app.get("/videos/{job_id}")
def get_video(job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(400, "Invalid ID")
    path = JOBS / job_id / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/videos/{job_id}/file")
def get_file(job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(400, "Invalid ID")
    path = OUTPUT / f"{job_id}.mp4"
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")
