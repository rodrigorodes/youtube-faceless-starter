import asyncio
import base64
import json
import os
import re
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, HttpUrl

from . import rich
from .studio.api.routes import make_router
from .studio.composition import Settings, Studio

studio = Studio(Settings.from_env())  # estado de domínio (Postgres); opcional: sem banco o modo /videos segue funcionando


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(studio.use_cases)  # migra o schema studio; falha não derruba o app
    yield


app = FastAPI(title="Faceless Renderer MVP", version="0.3.0", lifespan=lifespan)
OUTPUT = Path(os.getenv("OUTPUT_DIR", "/data/output"))
JOBS = Path(os.getenv("JOB_DIR", "/data/jobs"))
OUTPUT.mkdir(parents=True, exist_ok=True)
JOBS.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

class Scene(BaseModel):
    narration: str = Field(min_length=5, max_length=400)
    caption: str = Field(default="", max_length=110)
    image_prompt: str = Field(min_length=10, max_length=500)
    label: str = Field(default="", max_length=32)


class VideoRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    format: str = Field(default="short", pattern="^(short)$")
    duration_seconds: int = Field(default=30, ge=10, le=60)
    style: str = Field(default="documentary", max_length=80)
    context: str = Field(default="", max_length=3000)  # fatos verificados; o modelo só pode usar isto
    sources: list[HttpUrl] = Field(default_factory=list, max_length=5)
    footer: str = Field(default="YOUTUBE FACELESS • DEMO", max_length=40)
    mode: str = Field(default="slides", pattern="^(slides|rich)$")  # rich = imagens + narração + trilha
    scenes: list[Scene] = Field(default_factory=list, max_length=16)  # storyboard explícito (rich)
    scene_count: int = Field(default=10, ge=4, le=14)  # usado quando o storyboard é gerado por IA
    title: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=15)
    music: bool = True


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


def build_prompt(topic, style, context=""):
    rules = ("Responda APENAS um objeto JSON com as chaves: "
             '"slides" (exatamente 4 frases curtas, até 120 caracteres cada), "title" (até 90 caracteres), '
             '"description" (até 600 caracteres, sem hashtags em excesso) e "tags" (até 8 strings curtas). ')
    if context.strip():
        facts = ("Use SOMENTE os fatos do CONTEXTO abaixo. Não invente datas, nomes, números nem alegações; "
                 "o que não estiver no contexto não pode ser afirmado.")
        tail = f" CONTEXTO: {context.strip()}"
    else:
        facts = "Sem alegações factuais não verificadas."
        tail = ""
    return ("Você escreve roteiros curtos em português do Brasil para slides de um YouTube Short informativo. "
            f"{rules}{facts} Tema: {topic}. Estilo: {style}.{tail}")


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
    return parse_content_text(data["candidates"][0]["content"]["parts"][0]["text"])["slides"]


def parse_slides_text(raw):
    return parse_content_text(raw)["slides"]


def parse_content_text(raw):
    """Aceita lista de 4 frases (formato antigo) ou objeto {slides,title,description,tags}."""
    raw = raw.strip()
    if raw.startswith("```"):  # modelos sem modo JSON costumam envolver em ```json
        raw = raw.strip("`").removeprefix("json").strip()
    data = json.loads(raw)
    meta = {}
    if isinstance(data, dict):
        meta, data = data, data.get("slides")
    if not isinstance(data, list) or len(data) != 4 or not all(isinstance(x, str) for x in data):
        raise ValueError("Model returned an invalid slide list")
    title = meta.get("title") if isinstance(meta.get("title"), str) else ""
    description = meta.get("description") if isinstance(meta.get("description"), str) else ""
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    tags = [t.strip()[:30] for t in tags if isinstance(t, str) and t.strip()][:8]
    return {"slides": [x[:260] for x in data], "title": title.strip()[:100], "description": description.strip()[:900], "tags": tags}


async def generate_with_opencode(prompt, parser=None):
    """Chama o bridge local (scripts/opencode-bridge.py), que usa o login OAuth do OpenCode."""
    token = os.getenv("OPENCODE_BRIDGE_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="AI_PROVIDER=opencode requires OPENCODE_BRIDGE_TOKEN")
    base = os.getenv("OPENCODE_BRIDGE_URL", "http://host.docker.internal:8787").rstrip("/")
    try:
        data = await post_json(f"{base}/generate", {"Authorization": f"Bearer {token}"}, {"prompt": prompt}, timeout=100)
        return (parser or parse_content_text)(data["text"])
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
        raise HTTPException(status_code=502, detail=f"OpenCode bridge failed: {type(exc).__name__}{status}; is scripts/opencode-bridge.py running?") from exc


async def generate_script(topic, style):
    """Compatibilidade: só as 4 frases."""
    return (await generate_content(topic, style))["slides"]


async def generate_content(topic, style, context=""):
    """Devolve {slides, title, description, tags} (título/descrição/tags podem vir vazios)."""
    provider = resolve_provider()
    if provider == "demo":
        slides = [text.format(topic=topic) if "{topic}" in text else text for text in DEMO_SLIDES]
        return {"slides": slides, "title": "", "description": "", "tags": []}
    return await call_provider(provider, build_prompt(topic, style, context), parse_content_text)


async def generate_storyboard(topic, style, context, scene_count):
    provider = resolve_provider()
    if provider == "demo":
        raise HTTPException(status_code=422, detail="mode=rich without 'scenes' needs an AI provider (AI_PROVIDER is demo); send 'scenes' or configure a provider")
    return await call_provider(provider, build_storyboard_prompt(topic, style, context, scene_count), lambda raw: parse_storyboard_text(raw, scene_count))


async def call_provider(provider, prompt, parser):
    if provider == "opencode":
        return await generate_with_opencode(prompt, parser)
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
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
        data = await post_json(url, headers, payload)
        return parser(data["candidates"][0]["content"]["parts"][0]["text"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
        raise HTTPException(status_code=502, detail=f"{label} failed: {type(exc).__name__}{status}; check credentials, project, model and quota") from exc


def build_storyboard_prompt(topic, style, context, scene_count):
    rules = ("Você cria o roteiro de um YouTube Short informativo em português do Brasil, narrado e com imagens ilustrativas geradas por IA. "
             "Responda APENAS um objeto JSON com: \"title\" (até 90 caracteres), \"description\" (até 600 caracteres), "
             "\"tags\" (até 8 strings curtas) e \"scenes\": lista de EXATAMENTE " + str(scene_count) + " objetos, cada um com "
             "\"narration\" (1 a 2 frases curtas em português, até 220 caracteres, texto que será falado), "
             "\"caption\" (até 70 caracteres, legenda na tela), \"label\" (selo curto como 'QUA • 21/10', ou vazio) e "
             "\"image_prompt\" (EM INGLÊS, uma cena genérica e ilustrativa; PROIBIDO citar pessoas reais, nomes de artistas, logotipos, marcas ou texto escrito). "
             "Cubra o contexto em ordem cronológica. ")
    facts = ("Use SOMENTE os fatos do CONTEXTO; não invente datas, nomes, números nem alegações."
             if context.strip() else "Sem alegações factuais não verificadas.")
    tail = f" CONTEXTO: {context.strip()}" if context.strip() else ""
    return f"{rules}{facts} Tema: {topic}. Estilo: {style}.{tail}"


def parse_storyboard_text(raw, scene_count):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    data = json.loads(raw)
    scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(scenes, list) or not 4 <= len(scenes) <= 16:
        raise ValueError("Model returned an invalid scene list")
    clean = []
    for sc in scenes:
        if not isinstance(sc, dict) or not isinstance(sc.get("narration"), str) or len(sc["narration"].strip()) < 5:
            raise ValueError("Scene without narration")
        text = lambda k, n: sc[k].strip()[:n] if isinstance(sc.get(k), str) else ""
        clean.append({"narration": text("narration", 400), "caption": text("caption", 110), "label": text("label", 32),
                      "image_prompt": text("image_prompt", 500) or "abstract colorful stage lights, cinematic"})
    meta = parse_content_meta(data)
    return {"scenes": clean, **meta}


def parse_content_meta(data):
    title = data.get("title") if isinstance(data.get("title"), str) else ""
    description = data.get("description") if isinstance(data.get("description"), str) else ""
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags = [t.strip()[:30] for t in tags if isinstance(t, str) and t.strip()][:8]
    return {"title": title.strip()[:100], "description": description.strip()[:900], "tags": tags}


IMAGE_STYLE = ", cinematic photography, vertical 9:16 composition, rich colors, no text, no logos, no recognizable real people"


async def fetch_image(prompt, index, dst):
    """Imagem da cena: bridge (modelo gratuito via OpenCode) ou degradê local (IMAGE_PROVIDER=placeholder)."""
    provider = os.getenv("IMAGE_PROVIDER", "opencode").strip().lower()
    if provider == "placeholder":
        await asyncio.to_thread(rich.placeholder_image, index, dst)
        return
    if provider != "opencode":
        raise HTTPException(status_code=500, detail="Invalid IMAGE_PROVIDER; use opencode or placeholder")
    token = os.getenv("OPENCODE_BRIDGE_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="IMAGE_PROVIDER=opencode requires OPENCODE_BRIDGE_TOKEN")
    base = os.getenv("OPENCODE_BRIDGE_URL", "http://host.docker.internal:8787").rstrip("/")
    last = None
    for attempt in range(2):
        try:
            data = await post_json(f"{base}/image", {"Authorization": f"Bearer {token}"}, {"prompt": prompt + IMAGE_STYLE}, timeout=120)
            await asyncio.to_thread(rich.cover_image, base64.b64decode(data["data"]), dst)
            return
        except (httpx.HTTPError, KeyError, ValueError, OSError) as exc:
            last = exc
    status = f" (HTTP {last.response.status_code})" if isinstance(last, httpx.HTTPStatusError) else ""
    raise HTTPException(status_code=502, detail=f"Image generation failed for scene {index + 1}: {type(last).__name__}{status}; is scripts/opencode-bridge.py running with a :free image model?") from last


def build_rich(job_dir, scenes, music):
    """Parte bloqueante do modo rich: voz, trilha, overlays, cenas e mixagem. Roda em thread."""
    speech = []
    for i, sc in enumerate(scenes):
        wav = job_dir / f"speech_{i:02d}.wav"
        rich.synthesize_speech(sc["narration"], wav)
        speech.append(wav)
    narration = job_dir / "narration.wav"
    lengths = rich.build_narration_track(speech, narration)
    total = sum(lengths)
    if total > 175:
        raise HTTPException(status_code=422, detail=f"Video would be {total:.0f}s; Shorts allow up to 180s. Use fewer or shorter scenes.")
    music_wav = job_dir / "music.wav"
    rich.synth_music(total + 1.0, music_wav)
    if not music:  # mantém o mesmo grafo de mixagem, com a trilha silenciada
        import wave as _w
        with _w.open(str(music_wav), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rich.MUSIC_SR)
            w.writeframes(b"\x00\x00" * int((total + 1.0) * rich.MUSIC_SR))
    mp4s = []
    for i, (sc, seconds) in enumerate(zip(scenes, lengths)):
        overlay = job_dir / f"overlay_{i:02d}.png"
        rich.make_overlay(sc.get("label", ""), sc.get("caption", ""), overlay)
        mp4 = job_dir / f"scene_{i:02d}.mp4"
        rich.render_scene(job_dir / f"image_{i:02d}.png", overlay, seconds, i, mp4)
        mp4s.append(mp4)
    return total, mp4s, narration, music_wav


async def create_rich_video(request, job_id, job_dir):
    meta = {"title": "", "description": "", "tags": []}
    if request.scenes:
        scenes = [sc.model_dump() for sc in request.scenes]
    else:
        storyboard = await generate_storyboard(request.topic, request.style, request.context, request.scene_count)
        scenes, meta = storyboard["scenes"], storyboard
    for i, sc in enumerate(scenes):  # sequencial: o bridge atende uma geração por vez
        await fetch_image(sc["image_prompt"], i, job_dir / f"image_{i:02d}.png")
    output = OUTPUT / f"{job_id}.mp4"
    try:
        total, mp4s, narration, music_wav = await asyncio.to_thread(build_rich, job_dir, scenes, request.music)
        await asyncio.to_thread(rich.assemble, mp4s, narration, music_wav, job_dir / "concat.txt", output)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode("utf-8", "replace")[-300:]
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {tail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="ffmpeg timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:  # voz (Piper), numpy, Pillow
        raise HTTPException(status_code=500, detail=f"Rich render failed: {type(exc).__name__}") from exc
    sources = [str(u) for u in request.sources]
    narrations = [sc["narration"] for sc in scenes]
    title = (request.title or meta["title"] or request.topic)[:100]
    body = request.description or meta["description"] or " ".join(narrations)[:600]
    parts = [body]
    if sources:
        parts.append("Fontes:\n" + "\n".join(sources))
    parts.append("Imagens ilustrativas geradas por IA (não são fotos nem vídeos do evento). Narração sintetizada por IA e trilha original gerada por software.")
    manifest = {"id": job_id, "topic": request.topic, "mode": "rich", "status": "AWAITING_APPROVAL", "script": narrations,
                "scenes": len(scenes), "title": title, "description": "\n\n".join(parts)[:4900],
                "tags": request.tags or meta["tags"], "sources": sources, "duration_seconds": round(total, 1), "has_audio": True,
                "video_url": f"http://localhost:8000/videos/{job_id}/file",
                "note": "AI-generated illustrative images, synthesized narration, original generated music; not real event footage"}
    (job_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def make_slide(text, path, index, footer="YOUTUBE FACELESS • DEMO"):
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
    draw.text((66, 1050), footer, font=small, fill=(145, 165, 185))
    img.save(path)


@app.get("/health")
def health():
    return {"status": "ok", "ffmpeg": True, "studio_db": "ok" if studio.ping() else "unavailable"}


@app.post("/videos")
async def create_video(request: VideoRequest):
    job_id = uuid.uuid4().hex
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    if request.mode == "rich":
        return await create_rich_video(request, job_id, job_dir)
    content = await generate_content(request.topic, request.style, request.context)
    script = content["slides"]
    duration = request.duration_seconds
    per_scene = duration / len(script)
    parts = []
    for i, text in enumerate(script):
        png = job_dir / f"scene_{i:02d}.png"
        mp4 = job_dir / f"scene_{i:02d}.mp4"
        make_slide(text, png, i, request.footer)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "25", "-i", str(png), "-t", str(per_scene), "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(mp4)]
        subprocess.run(cmd, check=True, timeout=150)
        parts.append(mp4)
    concat = job_dir / "concat.txt"
    concat.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    output = OUTPUT / f"{job_id}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)], check=True, timeout=150)
    sources = [str(u) for u in request.sources]
    title = (content["title"] or request.topic)[:100]
    body = content["description"] or " ".join(script)
    parts = [body]
    if sources:
        parts.append("Fontes:\n" + "\n".join(sources))
    parts.append("Roteiro gerado com auxílio de IA e vídeo montado automaticamente.")
    description = "\n\n".join(parts)[:4900]
    manifest = {"id": job_id, "topic": request.topic, "status": "AWAITING_APPROVAL", "script": script, "title": title, "description": description, "tags": content["tags"], "sources": sources, "duration_seconds": duration, "video_url": f"http://localhost:8000/videos/{job_id}/file", "note": "Demo silent slideshow; not yet voice/image generation or YouTube upload"}
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


app.include_router(make_router(lambda: studio.use_cases(), lambda: studio.ping()))
