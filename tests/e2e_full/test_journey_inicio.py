"""Início: o atalho "Gerar vídeo completo" (piloto) e "Abrir storyboard" (Diretor) seguem o protótipo v4-v3.

Piloto: cria o vídeo E inicia a produção (`runPipeline` do protótipo) e abre o vídeo. Diretor: o botão diz "Abrir
storyboard", cria o rascunho e abre o storyboard SEM iniciar produção. Na stack isolada não há pesquisa automática
(`STUDIO_AUTO_RESEARCH=0`), então a produção sem fonte para no 1º passo: aqui basta provar que ela FOI iniciada.
"""
from __future__ import annotations

import re
import uuid

from playwright.sync_api import expect

from .conftest import Journey
from .test_journey_piloto import create_channel


def _from_home(j: Journey, mode: str, topic: str):
    page = j.page
    page.goto(f"{j.base}/studio/panel")
    page.fill("#homeTopic", topic)
    page.click(f"#btn-mode-{mode}")
    return page.locator("#btn-create-video")


def test_inicio_piloto_creates_the_video_and_starts_the_production(journey: Journey) -> None:
    j, page = journey, journey.page
    create_channel(j, f"Canal Inicio P {uuid.uuid4().hex[:6]}")
    button = _from_home(j, "piloto", "A queda de Constantinopla")
    expect(button).to_have_text("⚡ Gerar vídeo completo")
    with page.expect_response(lambda r: r.url.endswith("/production-runs") and r.request.method == "POST") as started:
        button.click()
        page.wait_for_url(re.compile(r".*/studio/panel/videos/[0-9a-f]{32}/cenas"))
    assert started.value.status == 202, "o piloto precisa iniciar a produção, não só criar o rascunho"
    video_id = j.video_id()
    j.wait_for(lambda: j.api(f"/studio/videos/{video_id}")[1]["production_mode"] == "piloto", timeout=10, what="vídeo piloto")
    assert re.search(r"/production-runs/[0-9a-f]{32}", started.value.request.url) is None  # POST na coleção
    j.assert_clean()


def test_inicio_diretor_says_open_storyboard_and_does_not_start_production(journey: Journey) -> None:
    j, page = journey, journey.page
    create_channel(j, f"Canal Inicio D {uuid.uuid4().hex[:6]}")
    button = _from_home(j, "diretor", "A queda de Constantinopla")
    expect(button).to_have_text("🎬 Abrir storyboard")
    runs: list[str] = []
    page.on("request", lambda r: runs.append(r.url) if r.url.endswith("/production-runs") and r.method == "POST" else None)
    button.click()
    page.wait_for_url(re.compile(r".*/studio/panel/videos/[0-9a-f]{32}/cenas"))
    assert runs == [], "o Modo Diretor não inicia produção"
    expect(page.get_by_text("Modo Diretor", exact=False).first).to_be_visible()
    # voltar ao piloto no mesmo formulário devolve o rótulo do piloto
    page.goto(f"{j.base}/studio/panel")
    page.click("#btn-mode-diretor")
    page.click("#btn-mode-piloto")
    expect(page.locator("#btn-create-video")).to_have_text("⚡ Gerar vídeo completo")
    j.assert_clean()
