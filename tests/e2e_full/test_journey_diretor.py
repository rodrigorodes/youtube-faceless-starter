"""Jornada completa em Modo Diretor: o usuário monta o storyboard cena a cena e só então manda produzir.

Cobre: criar vídeo (roteiro colado vira cenas) → incluir, editar, reordenar e excluir cena (persistência) →
desfazer → a citação das fontes acompanha o texto editado (o fact-check da produção passa) → produzir →
aprovar → pendente de publicar.
"""
from __future__ import annotations

import re
import uuid

from playwright.sync_api import expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids

from .conftest import Journey
from .test_journey_piloto import (approve_from_quality, assert_pending_publication, continue_run_until_approval,
                                  create_channel, create_video, wait_for_scenes)


def scene_texts(j: Journey) -> list[str]:
    return [t.input_value() for t in j.page.locator("textarea[data-a=text]").all()]


def script_scenes(j: Journey, video_id: str) -> list[dict]:
    return j.api(f"/studio/videos/{video_id}/script")[1]["scenes"]


def test_diretor_storyboard_editing_then_production_and_approval(journey: Journey) -> None:
    j, page = journey, journey.page
    suffix = uuid.uuid4().hex[:6]

    create_channel(j, f"Canal Diretor {suffix}")
    video_id = create_video(j, f"Queda de Constantinopla D{suffix}", mode="diretor")
    wait_for_scenes(j, 3)
    initial = scene_texts(j)
    assert page.locator("textarea[data-a=text][readonly]").count() == 0
    expect(page.get_by_text("Criado no piloto automático", exact=False)).to_have_count(0)  # é Diretor
    assert_no_duplicate_ids(page, context_desc="Storyboard (Diretor)")

    # Incluir cena: grava uma nova versão e persiste
    with page.expect_response(lambda r: r.url.endswith("/script/scenes") and r.request.method == "POST") as added:
        page.click("#btn-nova-cena")
    assert added.value.status == 200
    page.reload()
    assert len(scene_texts(j)) == len(initial) + 1

    # Excluir a cena incluída
    with page.expect_response(lambda r: "/script/scenes/" in r.url and r.request.method == "DELETE") as removed:
        page.locator("button", has_text="Excluir").last.click()
        confirm = page.locator("dialog[open] button.primary, dialog[open] button.bad")
        if confirm.count():
            confirm.first.click()
    assert removed.value.status == 200
    page.reload()
    assert scene_texts(j) == initial

    # Editar o texto para OUTRO fato das fontes: a citação acompanha (senão o fact-check reprova)
    before_claims = [s["claim_ids"] for s in script_scenes(j, video_id)]
    new_text = "O sultão Mehmed II comandava cerca de 80 mil soldados otomanos."
    page.locator("textarea[data-a=text]").nth(0).fill(new_text)
    with page.expect_response(lambda r: re.search(r"/script/scenes/0$", r.url) and r.request.method == "POST") as saved:
        page.locator("textarea[data-a=text]").nth(1).click()
    assert saved.value.status == 200
    after_claims = [s["claim_ids"] for s in script_scenes(j, video_id)]
    assert after_claims[0] != before_claims[0], "a citação da cena 1 deveria ter acompanhado o texto novo"
    assert after_claims[1:] == before_claims[1:]

    # Reordenar e desfazer (o histórico de "Desfazer" vive na sessão da página: sem recarregar entre os dois)
    with page.expect_response(lambda r: r.url.endswith("/script/scenes/reorder") and r.request.method == "POST") as moved:
        page.locator('[data-a="mv"][data-d="1"]').first.click()
    assert moved.value.status == 200
    j.wait_for(lambda: scene_texts(j)[1] == new_text, timeout=15, what="cena movida para a posição 2")
    assert [s["narration"] for s in script_scenes(j, video_id)][1] == new_text
    expect(page.locator("#btn-undo-cenas")).to_be_enabled()
    with page.expect_response(lambda r: r.request.method == "POST" and "/script/" in r.url) as undone:
        page.click("#btn-undo-cenas")
    assert undone.value.status == 200
    j.wait_for(lambda: scene_texts(j)[0] == new_text, timeout=15, what="ordem restaurada pelo Desfazer")
    assert [s["narration"] for s in script_scenes(j, video_id)][0] == new_text  # o servidor também voltou

    # Produzir: Diretor também passa pela execução e pelo fact-check
    page.click("#btn-gerar-faltante")
    expect(page.locator("dialog#dlg-impacto[open]")).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith("/production-runs") and r.request.method == "POST") as started:
        page.click("#btn-confirmar-render")
    assert started.value.status == 202
    continue_run_until_approval(j, video_id)  # falha aqui se o fact-check reprovar a cena editada

    approve_from_quality(j, video_id)
    assert_pending_publication(j, video_id)
    j.assert_clean()
