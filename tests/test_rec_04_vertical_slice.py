"""REC-04.01 (R11) — Vertical Slice Real de 60–90s pelo Caminho Canônico do Studio.

Executa um vídeo horizontal 1080p real (60–90s) integralmente pelas rotas HTTP do Studio
(FastAPI TestClient + Postgres descartável + ProductionCoordinator + PlanFfmpegRenderer +
Piper pt_BR-faber-medium + FfmpegQualityEvaluator/FfmpegQa), SEM adaptador isolado,
SEM API paga ($0.00) e com kill switch de publicação estritamente BLOCKED:

1. CreativeBrief via PUT /studio/videos/{id}/direction (propagado ao RenderPlan).
2. Fontes + Roteiro de 5 cenas editadas via POST /studio/videos/{id}/script/scenes/{idx}
   com narrações PT-BR autênticas (~70–80s totais medidos via Piper real).
3. Importação real de PNG e MP4 via POST /studio/videos/{id}/scenes/{sid}/media/import
   (REC-02.03/04: probe/decode real, licença allowlist CC0-1.0, CAS) + MIME coerente no preview.
4. Overlays / PiP via POST /studio/videos/{id}/scenes/{sid}/assets (PNG gráfico na cena 0 +
   MP4 PiP vídeo na cena 1), compostos pelo PlanFfmpegRenderer e verificados pelo FfmpegOverlayVerifier.
5. Execução Run #1 via ProductionCoordinator (POST /studio/videos/{id}/production-runs):
   script -> factcheck -> storyboard -> assets -> render -> qa -> approval (pausa em WAITING_HUMAN;
   NUNCA autoaprova via POST /approve).
6. Legendas exportadas do RenderPlan via rotas HTTP (/subtitles, /subtitles.vtt, /subtitles.ass)
   e sync áudio/legenda medido (render.caption_sync).
7. Edição de UMA cena (cena 3) + regeneração seletiva Run #2 via ProductionCoordinator (REC-03.03):
   comprova preservação de cache (fingerprint, artifact_sha256, artifact_uri, mtime_ns) de vídeo
   e narração das 4 cenas intocadas, invalidando apenas a cena 3.
8. QA real (ffprobe + ebur128 LUFS/dBTP + blackdetect + freezedetect + silencedetect + pixels
   de movimento Ken Burns, vídeo MP4, overlay PNG e PiP MP4 + dinâmica de áudio/ducking).
9. Kill switch BLOCKED comprovado (STUDIO_PUBLICATION_ENABLED=0) e ledger $0.00.
10. Quando REC04_SLICE_OUT_DIR está definido (ex.: scripts/run-rec04-slice.sh), preserva o MP4
    final, legendas, frames-chave de amostra e manifest.json com SHA-256 e métricas observadas.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import resource
import shutil
import struct
import subprocess
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.api.routes import make_router
from app.studio.application.production import ProductionMode
from app.studio.composition import Settings, Studio
from app.studio.domain.quality import CHECK_CAPTION_SYNC, CHECK_OVERLAY
from app.studio.domain.render_cache import NodeId
from conftest import verified_test_connect

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
needs_piper = pytest.mark.skipif(
    not Path("/opt/voices/pt_BR-faber-medium.onnx").is_file() or shutil.which("piper") is None,
    reason="piper pt_BR-faber-medium not installed",
)

SOURCE_URL = "https://pt.wikipedia.org/wiki/Historia_da_computacao"
SOURCE_TEXT = (
    "A história da computação começou muito antes da eletricidade, com instrumentos mecânicos de cálculo, "
    "como o ábaco na antiguidade e a Pascalina criada por Blaise Pascal no século dezessete para automatizar "
    "somas e subtrações.\n"
    "No século dezenove, Charles Babbage projetou a Máquina Analítica com memória e unidade aritmética, "
    "enquanto Ada Lovelace escreveu o primeiro algoritmo publicado da história destinado a uma máquina "
    "programável de propósito geral.\n"
    "Em 1950, Alan Turing e John von Neumann consolidaram os fundamentos da arquitetura de programa "
    "armazenado, permitindo que computadores eletrônicos mantivessem instruções e dados juntos na mesma "
    "memória principal.\n"
    "Em 1971, a invenção do microprocessador integrou milhares de transistores em um único chip de silício, "
    "viabilizando a chegada dos computadores pessoais e impulsionando a revolução digital em escritórios e "
    "residências.\n"
    "Nas últimas décadas, a expansão da internet e dos sistemas distribuídos conectou bilhões de dispositivos "
    "ao redor do planeta, impulsionando a ciência de dados e consolidando a computação moderna em escala global.\n"
    "O avanço da microeletrônica a partir de 1971 integrou milhares de transistores em silício, reduziu "
    "drasticamente o custo e o consumo de energia, e abriu caminho para computadores pessoais, servidores "
    "modernos e dispositivos portáteis.\n"
)

SCENES_V1 = [
    {
        "narration": (
            "A história da computação começou muito antes da eletricidade, com instrumentos mecânicos de cálculo "
            "como o ábaco na antiguidade e a Pascalina de Blaise Pascal, criada no século dezessete para automatizar "
            "somas e subtrações."
        ),
        "caption": "Do ábaco à Pascalina de Blaise Pascal",
        "image_prompt": "Ilustração técnica de instrumentos mecânicos históricos de cálculo em mesa escura",
    },
    {
        "narration": (
            "No século dezenove, Charles Babbage projetou a Máquina Analítica com memória e unidade aritmética, "
            "enquanto Ada Lovelace escreveu o primeiro algoritmo publicado da história para uma máquina programável "
            "de propósito geral."
        ),
        "caption": "Máquina Analítica e o algoritmo pioneiro",
        "image_prompt": "Diagrama de engrenagens e cartões perfurados da Máquina Analítica em estilo documental",
    },
    {
        "narration": (
            "Em 1950, Alan Turing e John von Neumann consolidaram os fundamentos da arquitetura de programa "
            "armazenado, permitindo que computadores eletrônicos mantivessem instruções e dados juntos na mesma "
            "memória principal."
        ),
        "caption": "1950: arquitetura de programa armazenado",
        "image_prompt": "Visualização de circuitos lógicos e memória principal dos primeiros computadores eletrônicos",
    },
    {
        "narration": (
            "Em 1971, a invenção do microprocessador integrou milhares de transistores em um único chip de silício, "
            "viabilizando a chegada dos computadores pessoais e impulsionando a revolução digital em escritórios e "
            "residências."
        ),
        "caption": "1971: a chegada do microprocessador",
        "image_prompt": "Macro de chip de silício com trilhas geométricas iluminadas em tom esmeralda",
    },
    {
        "narration": (
            "Nas últimas décadas, a expansão da internet e dos sistemas distribuídos conectou bilhões de dispositivos "
            "ao redor do planeta, impulsionando a ciência de dados e consolidando a computação moderna em escala global."
        ),
        "caption": "Sistemas distribuídos e computação global",
        "image_prompt": "Mapa de rede global com conexões luminosas representando sistemas distribuídos",
    },
]

SCENE_3_V2 = {
    "narration": (
        "O avanço da microeletrônica a partir de 1971 integrou milhares de transistores em silício, reduziu "
        "drasticamente o custo e o consumo de energia, e abriu caminho para computadores pessoais, servidores "
        "modernos e dispositivos portáteis."
    ),
    "caption": "1971: microeletrônica, servidores e portáteis",
    "image_prompt": "Arquitetura moderna de microeletrônica e circuitos de silício com acentos dourados",
}


class SyncExecutor:
    """Executa tarefas do Studio sincronamente para determinismo total do teste."""

    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        pass


@pytest.fixture
def dsn():
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c = verified_test_connect(dsn, proof)
    try:
        c.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        c.commit()
        yield c
    finally:
        c.close()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_rich_png(
    size: tuple[int, int],
    bg: tuple[int, int, int],
    grid_color: tuple[int, int, int],
    accent: tuple[int, int, int],
    shape: str = "circles",
) -> bytes:
    """Gera PNG 1920x1080 determinístico com geometria nítida (evita quadro uniforme/congelado)."""
    w, h = size
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    for x in range(0, w, 120):
        draw.line([(x, 0), (x, h)], fill=grid_color, width=2)
    for y in range(0, h, 120):
        draw.line([(0, y), (w, y)], fill=grid_color, width=2)
    if shape == "circles":
        for r in (140, 260, 380):
            draw.ellipse((w // 2 - r, h // 2 - r, w // 2 + r, h // 2 + r), outline=accent, width=6)
        draw.rectangle((140, h - 280, 620, h - 180), fill=accent)
    elif shape == "bars":
        for i in range(6):
            x0 = 180 + i * 260
            y0 = 260 + (i % 3) * 140
            draw.rectangle((x0, y0, x0 + 160, h - 220), outline=accent, width=6)
            draw.rectangle((x0 + 24, y0 + 24, x0 + 136, y0 + 96), fill=accent)
    elif shape == "badge":
        draw.rounded_rectangle((16, 16, w - 16, h - 16), radius=28, fill=bg, outline=accent, width=12)
        draw.rectangle((64, 72, w - 64, 152), fill=accent)
        draw.rectangle((64, 192, w - 140, 248), fill=grid_color)
        draw.rectangle((64, 272, w - 220, 312), fill=grid_color)
    else:  # circuit
        for i in range(5):
            y = 180 + i * 165
            draw.line([(160, y), (w - 160, y)], fill=accent, width=5)
            cx = 360 + i * 280
            draw.ellipse((cx - 32, y - 32, cx + 32, y + 32), fill=accent)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_real_mp4(path: Path, *, width: int, height: int, duration_s: float, kind: str = "base") -> bytes:
    """Gera MP4 H.264 real reproduzível com movimento contínuo via FFmpeg."""
    if kind == "base":
        vf = f"testsrc2=size={width}x{height}:rate=25:duration={duration_s:.1f},hue=h=t*45"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
    else:
        # PiP vídeo de alto contraste alternando cores a cada 1.0s (ciano -> magenta -> amarelo -> verde -> laranja)
        # para provar movimento real de vídeo MP4 dentro da janela do PiP (0.7s..3.1s -> clip 0.0s..2.4s).
        seg = max(0.5, duration_s / 5.0)
        colors = ("0x00E5FF", "0xFF2A85", "0xFFE600", "0x00E676", "0xFF6D00")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for c in colors:
            cmd += ["-f", "lavfi", "-i", f"color=c={c}:s={width}x{height}:r=25:d={seg:.2f}"]
        concat_in = "".join(f"[{i}:v]" for i in range(len(colors)))
        cmd += [
            "-filter_complex",
            f"{concat_in}concat=n={len(colors)}:v=1:a=0,drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white:t=10,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
    subprocess.run(cmd, check=True, timeout=60)
    return path.read_bytes()


def _extract_frame(mp4: Path, time_s: float, out_png: Path, *, scale_w: int | None = None) -> Image.Image:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, time_s):.3f}", "-i", str(mp4),
        "-frames:v", "1",
    ]
    if scale_w is not None:
        cmd += ["-vf", f"scale={scale_w}:-2"]
    cmd.append(str(out_png))
    subprocess.run(cmd, check=True, timeout=30)
    with Image.open(out_png) as img:
        return img.convert("RGB")


def _image_stats(img: Image.Image) -> dict[str, float]:
    small = img.resize((160, 90))
    pixels = list(small.getdata())
    n = len(pixels)
    mean_r = sum(p[0] for p in pixels) / n
    mean_g = sum(p[1] for p in pixels) / n
    mean_b = sum(p[2] for p in pixels) / n
    lumas = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in pixels]
    mean_l = sum(lumas) / n
    var_l = sum((v - mean_l) ** 2 for v in lumas) / n
    return {
        "mean_r": round(mean_r, 2),
        "mean_g": round(mean_g, 2),
        "mean_b": round(mean_b, 2),
        "mean_luma": round(mean_l, 2),
        "std_luma": round(math.sqrt(var_l), 2),
    }


def _mean_abs_diff(img_a: Image.Image, img_b: Image.Image, box: tuple[int, int, int, int] | None = None) -> float:
    a = img_a.crop(box) if box else img_a
    b = img_b.crop(box) if box else img_b
    a = a.resize((160, 90))
    b = b.resize((160, 90))
    pa = list(a.getdata())
    pb = list(b.getdata())
    total = sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2]) for x, y in zip(pa, pb))
    return total / (len(pa) * 3)


def _wav_rms_and_duration(wav_bytes: bytes) -> tuple[float, float, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
    assert width == 2, f"expected 16-bit PCM WAV, got sample width {width}"
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    rms = math.sqrt(sum(s * s for s in samples) / max(1, len(samples)))
    peak = max((abs(s) for s in samples), default=0)
    dur = nframes / rate if rate else 0.0
    return dur, rms, peak


def _audio_window_rms(mp4: Path, start_s: float, duration_s: float, tmp_wav: Path) -> float:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, start_s):.3f}", "-t", f"{duration_s:.3f}",
            "-i", str(mp4), "-vn", "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(tmp_wav),
        ],
        check=True,
        timeout=30,
    )
    _, rms, _ = _wav_rms_and_duration(tmp_wav.read_bytes())
    return rms


def _probe_full(mp4: Path) -> dict:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(mp4)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(res.stdout)


def _tool_version(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (res.stdout or res.stderr or "").strip().splitlines()
        return out[0] if out else "unknown"
    except Exception:
        return "unavailable"


def _git_info() -> dict[str, str]:
    info = {"sha": "unknown", "branch": "unknown"}
    try:
        info["sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=10).strip()
        info["branch"] = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, timeout=10).strip()
    except Exception:
        pass
    return info


@pytest.mark.rec04_slice
@needs_ffmpeg
@needs_piper
def test_rec_04_01_real_vertical_slice_60_90s_via_studio(conn, dsn, tmp_path: Path):
    """Vertical slice real 60–90s pelo caminho canônico HTTP do Studio + ProductionCoordinator."""
    t_total_start = time.monotonic()
    stage_timings: dict[str, float] = {}
    migrate(conn)

    storage_root = tmp_path / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # Zero chaves pagas; ElevenLabs desabilitado; Piper local oficial; publicação estritamente BLOCKED.
    environ = {
        "STUDIO_TEXT": "demo:v4",
        "STUDIO_IMAGE": "placeholder:v4",
        "STUDIO_VOICE": "piper:pt_BR-faber-medium",
        "STUDIO_RENDERER": "ffmpeg",
        "STUDIO_PUBLICATION_ENABLED": "0",
        "STUDIO_AUTO_RESEARCH": "0",
        "STUDIO_BUDGET_GUARD": "1",
        "MAX_COST_USD_PER_VIDEO": "0",
        "MAX_COST_USD_PER_MONTH": "0",
    }

    settings = Settings(
        database_url=dsn,
        storage_root=storage_root,
        source_allowlist=("pt.wikipedia.org",),
        auto_research=False,
        render_plan_enabled=True,
        budget_guard=True,
        max_cost_video=0.00,
        max_cost_month=0.00,
        publication_enabled=False,
        production_mode=ProductionMode.BUDGET_GUARDED,
    )

    studio = Studio(settings, environ=environ, executor=SyncExecutor())
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, base_url="http://testserver", headers={"Authorization": "Bearer test-worker-token"})

    try:
        # 0. Verificar provedor ElevenLabs desabilitado no catálogo real
        prov_resp = client.get("/studio/providers")
        if prov_resp.status_code == 200:
            prov_text = prov_resp.text.lower()
            assert "elevenlabs" not in prov_text or '"validated":false' in prov_text.replace(" ", "")

        # 1. Projeto, Vídeo 1080p (long, target 75s) e Direção Criativa (CreativeBrief -> RenderPlan)
        t0 = time.monotonic()
        proj_resp = client.post(
            "/studio/projects",
            json={"name": "Canal Vertical Slice REC-04.01", "niche": "tecnologia", "language": "pt-BR"},
        )
        assert proj_resp.status_code == 201, proj_resp.text
        project_id = proj_resp.json()["id"]

        vid_resp = client.post(
            "/studio/videos",
            json={
                "project_id": project_id,
                "topic": "História da Computação: Do Ábaco aos Sistemas Distribuídos",
                "format": "long",
                "target_duration_s": 75,
            },
        )
        assert vid_resp.status_code == 201, vid_resp.text
        video_id = vid_resp.json()["id"]

        dir_resp = client.put(
            f"/studio/videos/{video_id}/direction",
            json={
                "brief": {
                    "schema_version": 1,
                    "topic": "História da Computação: Do Ábaco aos Sistemas Distribuídos",
                    "narrative_goal": "Explicar os marcos históricos da computação com clareza documental",
                    "hook": "Como instrumentos mecânicos deram origem à computação moderna em escala global?",
                    "content_structure": [
                        "Instrumentos mecânicos: ábaco e Pascalina",
                        "Máquina Analítica e Ada Lovelace",
                        "Arquitetura de programa armazenado (1950)",
                        "Microprocessador (1971)",
                        "Sistemas distribuídos globais",
                    ],
                    "tone": "informativo",
                    "pacing": "cinematic",
                    "visual_direction": "documentário tecnológico cinematográfico",
                    "recommended_media_types": ["image", "video"],
                    "caption_strategy": "Palavra ativa com realce",
                    "audio_guidance": "Trilha sonora ambiente com ducking equilibrado",
                    "max_budget_usd": 0.0,
                    "quality_criteria": ["Boa resolução", "Sem repetição de mídia"],
                }
            },
        )
        assert dir_resp.status_code == 200, dir_resp.text

        # 2. Fonte e Roteiro (5 cenas) editado pelas rotas canônicas do Studio
        src_resp = client.post(
            f"/studio/videos/{video_id}/sources",
            json={"url": SOURCE_URL, "text": SOURCE_TEXT},
        )
        assert src_resp.status_code == 201, src_resp.text

        script_resp = client.post(f"/studio/videos/{video_id}/script", json={"scene_count": 5})
        assert script_resp.status_code == 201, script_resp.text
        script_version = script_resp.json()["script"]["version"]

        for idx, spec in enumerate(SCENES_V1):
            edit_resp = client.post(
                f"/studio/videos/{video_id}/script/scenes/{idx}",
                headers={"Idempotency-Key": f"rec04-init-scene-{idx}"},
                json={
                    "expected_version": script_version,
                    "narration": spec["narration"],
                    "caption": spec["caption"],
                    "image_prompt": spec["image_prompt"],
                    "claim_ids": [],
                },
            )
            assert edit_resp.status_code == 200, edit_resp.text
            script_version = edit_resp.json()["script"]["version"]
            scenes_data = edit_resp.json()["scenes"]

        assert len(scenes_data) == 5
        scene_ids = [s["id"] for s in scenes_data]
        stage_timings["setup_and_script_s"] = round(time.monotonic() - t0, 3)

        # 3. Gerar fixtures reais determinísticos (PNGs 1080p + MP4 1080p + PNG badge + MP4 PiP) e importar via rota HTTP
        t0 = time.monotonic()
        scene0_png = _make_rich_png((1920, 1080), (18, 26, 46), (48, 72, 118), (245, 184, 46), shape="circles")
        scene1_png = _make_rich_png((1920, 1080), (16, 36, 43), (44, 92, 104), (80, 220, 200), shape="bars")
        scene2_mp4 = _make_real_mp4(fixtures_dir / "scene2_base.mp4", width=1920, height=1080, duration_s=24.0, kind="base")
        scene3_png_v1 = _make_rich_png((1920, 1080), (15, 43, 36), (42, 106, 88), (110, 240, 160), shape="circuit")
        scene3_png_v2 = _make_rich_png((1920, 1080), (43, 20, 40), (110, 56, 98), (255, 200, 70), shape="circuit")
        overlay_badge_png = _make_rich_png((640, 360), (245, 184, 46), (255, 250, 230), (24, 32, 56), shape="badge")
        overlay_pip_mp4 = _make_real_mp4(fixtures_dir / "overlay_pip.mp4", width=640, height=360, duration_s=5.0, kind="pip")

        # 3a. Cena 0: importar overlay PNG gráfico -> trocar base para scene0_png com CAS -> anexar overlay PNG
        r_badge = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[0]}/media/import",
            data={"license": "CC0-1.0", "attribution": "Estúdio REC-04.01 Badge"},
            files={"file": ("overlay_badge.png", overlay_badge_png, "image/png")},
        )
        assert r_badge.status_code == 200, r_badge.text
        badge_asset_id = r_badge.json()["asset"]["id"]

        r_s0 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[0]}/media/import",
            data={
                "license": "CC0-1.0",
                "attribution": "Estúdio REC-04.01 Cena 0",
                "expected_asset_id": badge_asset_id,
            },
            files={"file": ("scene0_base.png", scene0_png, "image/png")},
        )
        assert r_s0.status_code == 200, r_s0.text
        prev_s0 = client.get(f"/studio/videos/{video_id}/scenes/{scene_ids[0]}/asset")
        assert prev_s0.status_code == 200 and prev_s0.headers["content-type"].startswith("image/png")

        ov0_resp = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[0]}/assets",
            json={
                "asset_id": badge_asset_id,
                "position": 1,
                "start_s": 0.7,
                "end_s": 3.1,
                "role": "overlay",
            },
        )
        assert ov0_resp.status_code == 201, ov0_resp.text

        # 3b. Cena 1: importar MP4 PiP -> trocar base para scene1_png com CAS -> anexar PiP MP4 como overlay
        r_pip = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[1]}/media/import",
            data={"license": "CC0-1.0", "attribution": "Estúdio REC-04.01 PiP MP4"},
            files={"file": ("overlay_pip.mp4", overlay_pip_mp4, "video/mp4")},
        )
        assert r_pip.status_code == 200, r_pip.text
        pip_asset_id = r_pip.json()["asset"]["id"]

        r_s1 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[1]}/media/import",
            data={
                "license": "CC0-1.0",
                "attribution": "Estúdio REC-04.01 Cena 1",
                "expected_asset_id": pip_asset_id,
            },
            files={"file": ("scene1_base.png", scene1_png, "image/png")},
        )
        assert r_s1.status_code == 200, r_s1.text

        ov1_resp = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[1]}/assets",
            json={
                "asset_id": pip_asset_id,
                "position": 2,
                "start_s": 0.7,
                "end_s": 3.1,
                "role": "overlay",
            },
        )
        assert ov1_resp.status_code == 201, ov1_resp.text

        # 3c. Cena 2: importar MP4 real 1080p como mídia base da cena
        r_s2 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[2]}/media/import",
            data={"license": "CC0-1.0", "attribution": "Estúdio REC-04.01 MP4 Base"},
            files={"file": ("scene2_base.mp4", scene2_mp4, "video/mp4")},
        )
        assert r_s2.status_code == 200, r_s2.text
        prev_s2 = client.get(f"/studio/videos/{video_id}/scenes/{scene_ids[2]}/asset")
        assert prev_s2.status_code == 200 and prev_s2.headers["content-type"].startswith("video/mp4")

        # 3d. Cena 3: importar PNG real v1; Cena 4 fica sem mídia importada para o AssetsHandler gerar localmente
        r_s3 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[3]}/media/import",
            data={"license": "CC0-1.0", "attribution": "Estúdio REC-04.01 Cena 3 v1"},
            files={"file": ("scene3_v1.png", scene3_png_v1, "image/png")},
        )
        assert r_s3.status_code == 200, r_s3.text
        stage_timings["media_import_and_overlays_s"] = round(time.monotonic() - t0, 3)

        # 4. Run #1 via ProductionCoordinator (rota HTTP real /production-runs)
        t_run1 = time.monotonic()
        run1_resp = client.post(
            f"/studio/videos/{video_id}/production-runs",
            headers={"Idempotency-Key": "rec04-slice-run-1"},
            json={"stages": ["script", "factcheck", "storyboard", "assets", "render", "qa", "approval"]},
        )
        run1_wall_s = time.monotonic() - t_run1
        assert run1_resp.status_code == 202, run1_resp.text
        run1_id = run1_resp.json()["run_id"]
        stage_timings["run1_production_coordinator_s"] = round(run1_wall_s, 3)

        run1_view = client.get(f"/studio/videos/{video_id}/production-runs/{run1_id}")
        assert run1_view.status_code == 200, run1_view.text
        run1_data = run1_view.json()
        run1_states = {st["stage"]: st["state"] for st in run1_data["stages"]}
        for st_name in ("script", "factcheck", "storyboard", "assets", "render", "qa"):
            assert run1_states.get(st_name) == "SUCCEEDED", f"Run #1 stage {st_name} failed: {run1_data}"
        assert run1_data["state"] == "WAITING_HUMAN", f"Run #1 deveria pausar em WAITING_HUMAN, obteve {run1_data}"

        v1_info = client.get(f"/studio/videos/{video_id}").json()
        assert v1_info["status"] == "AWAITING_APPROVAL"

        # Snapshot do cache do RenderPlan no Postgres antes da edição seletiva
        plan_repo = PostgresRenderPlanRepository(lambda: psycopg.connect(dsn))
        plan_id = f"plan:{video_id}"
        plan_v1 = plan_repo.latest_plan(plan_id)
        assert plan_v1 is not None and plan_v1.revision == 1
        entries_v1 = plan_repo.entries(plan_id)
        assert len(entries_v1) > 0

        # Mapear nós visuais e de narração por cena antes da edição (com mtime_ns físico)
        shot_ids_by_scene_v1: dict[str, list[str]] = {
            sc.scene_id: [sh.shot_id for sh in sc.base_shots]
            for sc in plan_v1.timeline.scenes
        }
        v1_visual_meta: dict[str, tuple[str, str, str, int]] = {}
        for sid, sh_ids in shot_ids_by_scene_v1.items():
            for sh_id in sh_ids:
                ent = entries_v1[NodeId("visual", sh_id)]
                v1_visual_meta[sh_id] = (
                    ent.fingerprint,
                    ent.artifact_sha256,
                    ent.artifact_uri,
                    Path(ent.artifact_uri).stat().st_mtime_ns,
                )
        v1_narration_meta: dict[str, tuple[str, str, str, int]] = {}
        for sid in scene_ids:
            ent = entries_v1[NodeId("narration", sid)]
            v1_narration_meta[sid] = (
                ent.fingerprint,
                ent.artifact_sha256,
                ent.artifact_uri,
                Path(ent.artifact_uri).stat().st_mtime_ns,
            )

        # 5. Exportação de legendas do RenderPlan via rotas HTTP (SRT, VTT, ASS)
        t0 = time.monotonic()
        srt_v1 = client.get(f"/studio/videos/{video_id}/subtitles")
        vtt_v1 = client.get(f"/studio/videos/{video_id}/subtitles.vtt")
        ass_v1 = client.get(f"/studio/videos/{video_id}/subtitles.ass")
        assert srt_v1.status_code == 200 and "-->" in srt_v1.text
        assert vtt_v1.status_code == 200 and vtt_v1.text.startswith("WEBVTT")
        assert ass_v1.status_code == 200 and "[Script Info]" in ass_v1.text and "Dialogue:" in ass_v1.text
        stage_timings["subtitles_export_v1_s"] = round(time.monotonic() - t0, 3)

        # 6. Edição de UMA cena (Cena 3) + Regeneração Seletiva Run #2 (REC-03.03)
        t0 = time.monotonic()
        tr_resp = client.post(
            f"/studio/videos/{video_id}/transition",
            json={"expected": "AWAITING_APPROVAL", "new": "SCRIPTED"},
        )
        assert tr_resp.status_code == 200, tr_resp.text

        edit3_resp = client.post(
            f"/studio/videos/{video_id}/script/scenes/3",
            headers={"Idempotency-Key": "rec04-edit-scene-3"},
            json={
                "expected_version": script_version,
                "narration": SCENE_3_V2["narration"],
                "caption": SCENE_3_V2["caption"],
                "image_prompt": SCENE_3_V2["image_prompt"],
                "claim_ids": [],
            },
        )
        assert edit3_resp.status_code == 200, edit3_resp.text
        scenes_v2 = edit3_resp.json()["scenes"]
        assert [s["id"] for s in scenes_v2] == scene_ids, "Edição de cena não deve recriar IDs das cenas existentes"

        # Importar nova imagem real v2 apenas para a Cena 3 (cenas 0, 1, 2, 4 intocadas)
        r_s3_v2 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[3]}/media/import",
            data={"license": "CC0-1.0", "attribution": "Estúdio REC-04.01 Cena 3 v2"},
            files={"file": ("scene3_v2.png", scene3_png_v2, "image/png")},
        )
        assert r_s3_v2.status_code == 200, r_s3_v2.text
        stage_timings["edit_scene3_s"] = round(time.monotonic() - t0, 3)

        t_run2 = time.monotonic()
        run2_resp = client.post(
            f"/studio/videos/{video_id}/production-runs",
            headers={"Idempotency-Key": "rec04-slice-run-2"},
            json={"stages": ["script", "factcheck", "storyboard", "assets", "render", "qa", "approval"]},
        )
        run2_wall_s = time.monotonic() - t_run2
        assert run2_resp.status_code == 202, run2_resp.text
        run2_id = run2_resp.json()["run_id"]
        stage_timings["run2_selective_regen_s"] = round(run2_wall_s, 3)

        run2_view = client.get(f"/studio/videos/{video_id}/production-runs/{run2_id}")
        assert run2_view.status_code == 200, run2_view.text
        run2_data = run2_view.json()
        run2_states = {st["stage"]: st["state"] for st in run2_data["stages"]}
        for st_name in ("script", "factcheck", "storyboard", "assets", "render", "qa"):
            assert run2_states.get(st_name) == "SUCCEEDED", f"Run #2 stage {st_name} failed: {run2_data}"
        assert run2_data["state"] == "WAITING_HUMAN"

        # Verificar preservação real de cache (vídeo + narração/TTS) das 4 cenas intocadas (0, 1, 2, 4)
        plan_v2 = plan_repo.latest_plan(plan_id)
        assert plan_v2 is not None and plan_v2.revision == 2
        entries_v2 = plan_repo.entries(plan_id)

        untouched_scene_ids = [scene_ids[0], scene_ids[1], scene_ids[2], scene_ids[4]]
        reused_visual_nodes = 0
        reused_narration_nodes = 0
        for sid in untouched_scene_ids:
            # Narração/TTS preservada intacta
            e2_nar = entries_v2[NodeId("narration", sid)]
            nar_v2_tuple = (
                e2_nar.fingerprint,
                e2_nar.artifact_sha256,
                e2_nar.artifact_uri,
                Path(e2_nar.artifact_uri).stat().st_mtime_ns,
            )
            assert nar_v2_tuple == v1_narration_meta[sid], (
                f"Narração da cena intocada {sid} não reutilizou cache: {nar_v2_tuple} != {v1_narration_meta[sid]}"
            )
            reused_narration_nodes += 1
            # Segmentos de vídeo preservados intactos
            for sh_id in shot_ids_by_scene_v1[sid]:
                e2_vis = entries_v2[NodeId("visual", sh_id)]
                vis_v2_tuple = (
                    e2_vis.fingerprint,
                    e2_vis.artifact_sha256,
                    e2_vis.artifact_uri,
                    Path(e2_vis.artifact_uri).stat().st_mtime_ns,
                )
                assert vis_v2_tuple == v1_visual_meta[sh_id], (
                    f"Shot visual intocado {sh_id} não reutilizou cache: {vis_v2_tuple} != {v1_visual_meta[sh_id]}"
                )
                reused_visual_nodes += 1

        # Cena 3 editada DEVE ter fingerprint e artifact_sha256 novos (narração e vídeo)
        e2_s3_nar = entries_v2[NodeId("narration", scene_ids[3])]
        assert e2_s3_nar.fingerprint != v1_narration_meta[scene_ids[3]][0]
        assert e2_s3_nar.artifact_sha256 != v1_narration_meta[scene_ids[3]][1]
        s3_shots_v2 = [sh.shot_id for sc in plan_v2.timeline.scenes if sc.scene_id == scene_ids[3] for sh in sc.base_shots]
        assert any(
            entries_v2[NodeId("visual", sh_id)].artifact_sha256 != v1_visual_meta.get(sh_id, ("", "", "", 0))[1]
            for sh_id in s3_shots_v2
        ), "Cena 3 editada deveria ter gerado novos artefatos visuais"

        # 7. Legendas finais via HTTP após Run #2 (contém o texto editado da cena 3)
        srt_final = client.get(f"/studio/videos/{video_id}/subtitles")
        vtt_final = client.get(f"/studio/videos/{video_id}/subtitles.vtt")
        ass_final = client.get(f"/studio/videos/{video_id}/subtitles.ass")
        assert srt_final.status_code == 200 and "microeletrônica" in srt_final.text.lower()
        assert vtt_final.status_code == 200 and vtt_final.text.startswith("WEBVTT")
        assert ass_final.status_code == 200 and "Dialogue:" in ass_final.text

        # 8. Verificar QA persistido no Postgres (FfmpegQualityEvaluator)
        v_repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
        video_entity = v_repo.get_video(video_id)
        assert video_entity is not None
        assert video_entity.status.value == "AWAITING_APPROVAL"
        qa_report = video_entity.qa_report
        assert qa_report is not None
        assert qa_report.coverage.status == "verified", f"QA coverage não verificada: {qa_report.coverage}"
        assert len(qa_report.blocking_findings) == 0, f"Achados bloqueantes no QA: {qa_report.blocking_findings}"
        assert qa_report.is_publishable is True
        assert CHECK_OVERLAY in qa_report.checks_run, f"FfmpegOverlayVerifier não executou: {qa_report.checks_run}"
        assert CHECK_CAPTION_SYNC in qa_report.checks_run, f"caption_sync não executou: {qa_report.checks_run}"

        # 9. Custo $0.00 (ledger + endpoint HTTP) e Kill Switch estritamente BLOCKED (SEM POST /approve!)
        u_repo = PostgresUsageRepository(lambda: psycopg.connect(dsn))
        spent_usd = u_repo.spent_video(video_id)
        assert spent_usd == 0.0, f"Gasto indevido detectado no ledger: ${spent_usd:.4f}"

        cost_resp = client.get(f"/studio/videos/{video_id}/cost-breakdown")
        assert cost_resp.status_code == 200, cost_resp.text
        assert cost_resp.json()["total_usd"] == 0.0

        pub_resp = client.post(f"/studio/videos/{video_id}/publication/publish")
        assert pub_resp.status_code == 200, pub_resp.text
        pub_data = pub_resp.json()
        assert pub_data["result"] == "BLOCKED", f"Kill switch falhou: {pub_data}"
        assert pub_data.get("youtube_video_id") is None
        assert "disabled by configuration" in (pub_data.get("detail") or "")

        # Confirmar que vídeo continua em AWAITING_APPROVAL (sem autoaprovação!)
        assert client.get(f"/studio/videos/{video_id}").json()["status"] == "AWAITING_APPROVAL"

        # 10. Baixar o MP4 final via rota HTTP do Studio e verificar CONTEÚDO físico (não só metadados!)
        t0 = time.monotonic()
        file_resp = client.get(f"/studio/videos/{video_id}/file")
        assert file_resp.status_code == 200, file_resp.text
        final_mp4 = tmp_path / "rec04_01_vertical_slice.mp4"
        final_mp4.write_bytes(file_resp.content)
        mp4_sha256 = _sha256_file(final_mp4)
        mp4_bytes = final_mp4.stat().st_size
        assert mp4_bytes > 500_000, f"MP4 suspeitamente pequeno: {mp4_bytes} bytes"

        # 10a. ffprobe + FfmpegQa (ebur128 real LUFS & dBTP, blackdetect, freezedetect, silencedetect)
        probe_data = _probe_full(final_mp4)
        qa_metrics = FfmpegQa().analyze(final_mp4)
        duration_s = float(qa_metrics["duration_s"])
        assert 60.0 <= duration_s <= 90.0, f"Duração fora da janela 60-90s: {duration_s:.3f}s"
        assert qa_metrics["width"] == 1920 and qa_metrics["height"] == 1080
        assert qa_metrics["has_audio"] is True
        assert qa_metrics["video_codec"] in ("h264", "avc1")
        assert qa_metrics["audio_codec"] == "aac"
        assert qa_metrics["integrated_lufs"] is not None and -20.0 <= qa_metrics["integrated_lufs"] <= -12.0, (
            f"LUFS fora da faixa esperada [-20, -12]: {qa_metrics['integrated_lufs']}"
        )
        assert qa_metrics["true_peak_dbtp"] is not None and qa_metrics["true_peak_dbtp"] <= -1.0, (
            f"True Peak acima de -1.0 dBTP: {qa_metrics['true_peak_dbtp']}"
        )
        assert qa_metrics["black_ratio"] < 0.05, f"Fração de quadros pretos alta: {qa_metrics['black_ratio']}"
        assert qa_metrics["frozen_ratio"] < 0.20, f"Fração de quadros congelados alta: {qa_metrics['frozen_ratio']}"
        assert qa_metrics["silence_ratio"] < 0.25, f"Fração de silêncio alta: {qa_metrics['silence_ratio']}"

        # 10b. Verificar WAVs reais de narração Piper de todas as 5 cenas via rota HTTP
        narration_stats: list[dict] = []
        for idx, sid in enumerate(scene_ids):
            w_resp = client.get(f"/studio/videos/{video_id}/scenes/{sid}/narration.wav")
            assert w_resp.status_code == 200, w_resp.text
            w_dur, w_rms, w_peak = _wav_rms_and_duration(w_resp.content)
            assert w_dur >= 7.0, f"Cena {idx} com narração Piper curta demais: {w_dur:.2f}s"
            assert w_rms >= 500.0, f"Cena {idx} com áudio Piper silencioso/muito baixo: RMS={w_rms:.1f}"
            narration_stats.append({
                "scene_idx": idx,
                "scene_id": sid,
                "duration_s": round(w_dur, 3),
                "rms_pcm16": round(w_rms, 1),
                "peak_pcm16": w_peak,
            })

        # 10c. Verificar pixels reais: cenas não pretas, movimento Ken Burns, vídeo MP4, PNG overlay e MP4 PiP
        tps = plan_v2.timeline.ticks_per_second
        scene_starts = [sc.start_tick / tps for sc in plan_v2.timeline.scenes]
        scene_durs = [sc.duration_ticks / tps for sc in plan_v2.timeline.scenes]
        frames_dir = tmp_path / "frames"

        # Cena 0: antes do overlay PNG (0.3s), durante overlay PNG (1.8s), depois do overlay (3.8s), e movimento Ken Burns
        f_s0_before = _extract_frame(final_mp4, scene_starts[0] + 0.30, frames_dir / "s0_before_overlay.png")
        f_s0_overlay = _extract_frame(final_mp4, scene_starts[0] + 1.80, frames_dir / "s0_png_overlay.png")
        f_s0_after = _extract_frame(final_mp4, scene_starts[0] + 3.70, frames_dir / "s0_after_overlay.png")
        f_s0_motion_a = _extract_frame(final_mp4, scene_starts[0] + 5.20, frames_dir / "s0_motion_a.png")
        f_s0_motion_b = _extract_frame(final_mp4, scene_starts[0] + 8.00, frames_dir / "s0_motion_b.png")

        # Região superior direita (position_x=0.94, position_y=0.14, scale=0.45) onde entra o overlay PNG (position=1)
        box_right_top = (1000, 60, 1880, 620)
        diff_png_ov_in = _mean_abs_diff(f_s0_before, f_s0_overlay, box=box_right_top)
        diff_png_ov_out = _mean_abs_diff(f_s0_overlay, f_s0_after, box=box_right_top)
        assert diff_png_ov_in > 12.0, f"Overlay PNG não detectável na entrada (Cena 0): diff={diff_png_ov_in:.2f}"
        assert diff_png_ov_out > 12.0, f"Overlay PNG não detectável na saída (Cena 0): diff={diff_png_ov_out:.2f}"

        diff_ken_burns = _mean_abs_diff(f_s0_motion_a, f_s0_motion_b)
        assert diff_ken_burns > 0.8, f"Movimento Ken Burns não observável na Cena 0: diff={diff_ken_burns:.2f}"

        # Cena 1: antes do PiP MP4 (0.3s), durante PiP MP4 ciano (1.2s, clip 0.5s) e magenta (2.3s, clip 1.6s), depois (3.7s)
        f_s1_before = _extract_frame(final_mp4, scene_starts[1] + 0.30, frames_dir / "s1_before_pip.png")
        f_s1_pip_a = _extract_frame(final_mp4, scene_starts[1] + 1.20, frames_dir / "s1_mp4_pip_a.png")
        f_s1_pip_b = _extract_frame(final_mp4, scene_starts[1] + 2.30, frames_dir / "s1_mp4_pip_b.png")
        f_s1_after = _extract_frame(final_mp4, scene_starts[1] + 3.70, frames_dir / "s1_after_pip.png")

        # Região superior esquerda (position_x=0.06, position_y=0.14, scale=0.45) onde entra o PiP MP4 (position=2)
        box_left_top = (40, 60, 920, 620)
        diff_pip_in = _mean_abs_diff(f_s1_before, f_s1_pip_a, box=box_left_top)
        diff_pip_motion = _mean_abs_diff(f_s1_pip_a, f_s1_pip_b, box=box_left_top)
        diff_pip_out = _mean_abs_diff(f_s1_pip_b, f_s1_after, box=box_left_top)
        assert diff_pip_in > 12.0, f"PiP MP4 não detectável na entrada (Cena 1): diff={diff_pip_in:.2f}"
        assert diff_pip_motion > 10.0, f"PiP MP4 congelado entre 1.4s e 2.75s: diff={diff_pip_motion:.2f}"
        assert diff_pip_out > 12.0, f"PiP MP4 não detectável na saída (Cena 1): diff={diff_pip_out:.2f}"

        # Cena 2: MP4 base importado em movimento real
        f_s2_a = _extract_frame(final_mp4, scene_starts[2] + 2.0, frames_dir / "s2_imported_mp4_a.png")
        f_s2_b = _extract_frame(final_mp4, scene_starts[2] + 6.0, frames_dir / "s2_imported_mp4_b.png")
        diff_s2_mp4 = _mean_abs_diff(f_s2_a, f_s2_b)
        assert diff_s2_mp4 > 5.0, f"MP4 base importado (Cena 2) sem movimento observável: diff={diff_s2_mp4:.2f}"

        # Cena 3 (editada com PNG v2) e Cena 4 (gerada pelo AssetsHandler)
        f_s3 = _extract_frame(final_mp4, scene_starts[3] + 3.0, frames_dir / "s3_edited_v2.png")
        f_s4 = _extract_frame(final_mp4, scene_starts[4] + 3.0, frames_dir / "s4_generated.png")

        # Verificar que nenhum frame-chave é preto ou uniforme
        key_frames_info = [
            ("scene0_png_overlay", scene_starts[0] + 1.80, f_s0_overlay, "Cena 0 com overlay PNG gráfico"),
            ("scene1_mp4_pip", scene_starts[1] + 1.40, f_s1_pip_a, "Cena 1 com PiP vídeo MP4"),
            ("scene2_imported_mp4", scene_starts[2] + 2.00, f_s2_a, "Cena 2 com MP4 base importado"),
            ("scene3_edited_v2", scene_starts[3] + 3.00, f_s3, "Cena 3 após edição e regeneração seletiva"),
            ("scene4_studio_generated", scene_starts[4] + 3.00, f_s4, "Cena 4 gerada localmente pelo AssetsHandler"),
        ]
        for label, _, im, _ in key_frames_info:
            st = _image_stats(im)
            assert st["mean_luma"] > 15.0, f"Frame {label} excessivamente escuro: {st}"
            assert st["std_luma"] > 8.0, f"Frame {label} uniforme/sem detalhe: {st}"

        # 10d. Verificar áudio durante fala e durante pausa entre cenas (trilha musical + ducking real)
        speech_rms = _audio_window_rms(final_mp4, scene_starts[0] + 2.0, 3.0, tmp_path / "win_speech.wav")
        tail_rms = _audio_window_rms(
            final_mp4,
            max(0.0, scene_starts[0] + scene_durs[0] - 0.45),
            0.40,
            tmp_path / "win_tail.wav",
        )
        assert speech_rms > 800.0, f"Energia de áudio muito baixa durante fala: {speech_rms:.1f}"
        assert tail_rms > 50.0, f"Trilha musical ausente na pausa entre cenas (ducking/bed): {tail_rms:.1f}"

        stage_timings["content_verification_s"] = round(time.monotonic() - t0, 3)
        stage_timings["total_wall_s"] = round(time.monotonic() - t_total_start, 3)

        # 11. Exportação opcional de artefatos e manifesto para diretório exclusivo fora do container
        out_dir_env = os.environ.get("REC04_SLICE_OUT_DIR", "").strip()
        if out_dir_env:
            out_dir = Path(out_dir_env)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_mp4 = out_dir / "rec04_01_vertical_slice.mp4"
            shutil.copyfile(final_mp4, out_mp4)

            sub_dir = out_dir / "subtitles"
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "subtitles.srt").write_text(srt_final.text, encoding="utf-8")
            (sub_dir / "subtitles.vtt").write_text(vtt_final.text, encoding="utf-8")
            (sub_dir / "subtitles.ass").write_text(ass_final.text, encoding="utf-8")

            sample_frames_dir = out_dir / "frames"
            sample_frames_dir.mkdir(parents=True, exist_ok=True)
            sampled_frames_manifest = []
            for label, ts, _, desc in key_frames_info:
                dst_png = sample_frames_dir / f"{label}.png"
                small_img = _extract_frame(final_mp4, ts, dst_png, scale_w=640)
                sampled_frames_manifest.append({
                    "label": label,
                    "timestamp_s": round(ts, 3),
                    "description": desc,
                    "file": f"frames/{label}.png",
                    "bytes": dst_png.stat().st_size,
                    "sha256": _sha256_file(dst_png),
                    "stats": _image_stats(small_img),
                })

            ru_self = resource.getrusage(resource.RUSAGE_SELF)
            ru_child = resource.getrusage(resource.RUSAGE_CHILDREN)
            git_info = _git_info()
            run_id_label = os.environ.get("REC04_SLICE_RUN_ID", out_dir.name)

            video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
            audio_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "audio")

            manifest = {
                "schema_version": "rec04-01-manifest/1",
                "task_id": "REC-04.01",
                "requirement_id": "R11",
                "run_id": run_id_label,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "git": git_info,
                "versions": {
                    "ffmpeg": _tool_version(["ffmpeg", "-version"]),
                    "ffprobe": _tool_version(["ffprobe", "-version"]),
                    "piper": _tool_version(["piper", "--version"]),
                    "piper_voice_model": "/opt/voices/pt_BR-faber-medium.onnx",
                },
                "governance": {
                    "studio_publication_enabled": False,
                    "kill_switch_result": pub_data["result"],
                    "kill_switch_detail": pub_data.get("detail"),
                    "youtube_video_id": pub_data.get("youtube_video_id"),
                    "budget_guard_enabled": True,
                    "max_cost_usd_per_video": 0.0,
                    "max_cost_usd_per_month": 0.0,
                    "observed_api_cost_usd": spent_usd,
                    "video_final_status": video_entity.status.value,
                    "human_review_status": "AWAITING_HUMAN_REVIEW",
                    "auto_approved_in_test": False,
                },
                "artifact": {
                    "mp4_relative_path": f"storage/output/runs/{run_id_label}/rec04_01_vertical_slice.mp4",
                    "mp4_sha256": mp4_sha256,
                    "mp4_bytes": mp4_bytes,
                    "subtitles": {
                        "srt_sha256": _sha256_file(sub_dir / "subtitles.srt"),
                        "vtt_sha256": _sha256_file(sub_dir / "subtitles.vtt"),
                        "ass_sha256": _sha256_file(sub_dir / "subtitles.ass"),
                        "plan_subtitle_cues": len(plan_v2.timeline.subtitles),
                    },
                },
                "ffprobe": {
                    "duration_s": round(float(probe_data["format"]["duration"]), 3),
                    "bit_rate_bps": int(probe_data["format"].get("bit_rate", 0)),
                    "video": {
                        "codec_name": video_stream.get("codec_name"),
                        "width": int(video_stream["width"]),
                        "height": int(video_stream["height"]),
                        "r_frame_rate": video_stream.get("r_frame_rate"),
                        "pix_fmt": video_stream.get("pix_fmt"),
                    },
                    "audio": {
                        "codec_name": audio_stream.get("codec_name"),
                        "sample_rate": int(audio_stream.get("sample_rate", 0)),
                        "channels": int(audio_stream.get("channels", 0)),
                        "bit_rate_bps": int(audio_stream.get("bit_rate", 0)),
                    },
                },
                "qa_measured": {
                    "ffmpeg_qa": qa_metrics,
                    "studio_qa_report": {
                        "coverage_status": qa_report.coverage.status,
                        "is_publishable": qa_report.is_publishable,
                        "checks_run": list(qa_report.checks_run),
                        "blocking_findings_count": len(qa_report.blocking_findings),
                        "findings": [
                            {
                                "finding_id": f.finding_id,
                                "check_id": f.check_id,
                                "category": f.category,
                                "severity": f.severity,
                                "evidence": f.evidence,
                            }
                            for f in qa_report.findings
                        ],
                    },
                    "content_pixel_checks": {
                        "scene0_png_overlay_enter_diff": round(diff_png_ov_in, 2),
                        "scene0_png_overlay_exit_diff": round(diff_png_ov_out, 2),
                        "scene0_ken_burns_motion_diff": round(diff_ken_burns, 2),
                        "scene1_mp4_pip_enter_diff": round(diff_pip_in, 2),
                        "scene1_mp4_pip_motion_diff": round(diff_pip_motion, 2),
                        "scene1_mp4_pip_exit_diff": round(diff_pip_out, 2),
                        "scene2_imported_mp4_motion_diff": round(diff_s2_mp4, 2),
                    },
                    "audio_dynamics": {
                        "speech_window_rms_pcm16": round(speech_rms, 1),
                        "inter_scene_tail_bed_rms_pcm16": round(tail_rms, 1),
                        "narration_scenes": narration_stats,
                    },
                },
                "selective_regeneration": {
                    "plan_revision_before": plan_v1.revision,
                    "plan_revision_after": plan_v2.revision,
                    "edited_scene_idx": 3,
                    "edited_scene_id": scene_ids[3],
                    "untouched_scenes_count": len(untouched_scene_ids),
                    "reused_narration_nodes": reused_narration_nodes,
                    "reused_visual_nodes": reused_visual_nodes,
                    "run1_wall_s": round(run1_wall_s, 3),
                    "run2_wall_s": round(run2_wall_s, 3),
                    "time_saved_s": round(run1_wall_s - run2_wall_s, 3),
                },
                "stage_timings_s": stage_timings,
                "resource_usage": {
                    "note": "Linux container getrusage: ru_maxrss in KiB (peak RSS of process / largest child)",
                    "self_utime_s": round(ru_self.ru_utime, 3),
                    "self_stime_s": round(ru_self.ru_stime, 3),
                    "self_maxrss_kib": int(ru_self.ru_maxrss),
                    "children_utime_s": round(ru_child.ru_utime, 3),
                    "children_stime_s": round(ru_child.ru_stime, 3),
                    "children_maxrss_kib": int(ru_child.ru_maxrss),
                },
                "sampled_frames": sampled_frames_manifest,
                "honest_limitations": [
                    "Multitrack 2 faixas (voz Piper + trilha musical sintetizada com sidechaincompress ducking e loudnorm) é real no caminho HTTP do Studio; faixas extras de ambiência/SFX via MultitrackAudioPlan/AudioCatalog ainda não têm rota HTTP/tabela no Studio (verificado no PlanFfmpegRenderer em REC-02.02).",
                    "Transições inter-shot xfade (crossfade/slide/wipe) ainda não são expostas em visual_style.TRANSITION_KINDS (atualmente aceita apenas none/fade); verificadas no PlanFfmpegRenderer em REC-02.01.",
                    "Avaliação semântica/estética multimodal permanece not_verified sem API paga; homologação audiovisual depende de revisão humana real do MP4.",
                ],
                "commands": {
                    "generate_slice": "./scripts/run-rec04-slice.sh",
                    "pytest_container": "./scripts/test-container.sh tests/test_rec_04_vertical_slice.py -ra",
                    "watch_macos": f"open storage/output/runs/{run_id_label}/rec04_01_vertical_slice.mp4",
                },
            }
            (out_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    finally:
        studio.shutdown()
