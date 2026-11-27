"""Jornada completa pela interface, em Piloto Automático, até "aprovado, pendente de publicar".

Cada passo usa só a tela (o que o usuário clica), e confere o estado real pela API do Studio.
Cobre: criar canal → criar vídeo com roteiro colado → storyboard → produção (roteiro, fact-check, cenas, voz,
imagens, render, QA) → prévia → aprovar → pendente de publicar (YouTube não conectado, falha fechada) →
pedir ajustes → editar texto/ordem → recusa de texto sem lastro → regerar → aprovar de novo.
"""
from __future__ import annotations

import re
import uuid

from playwright.sync_api import expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow

from .conftest import SOURCE_LINK, SOURCE_TEXT, Journey

APPROVAL_TIMEOUT = 150  # Piper + ffmpeg em CPU; o render do Short de 6 cenas leva ~25 s


def create_channel(j: Journey, name: str) -> None:
    page = j.page
    page.goto(f"{j.base}/studio/canais/novo")
    page.fill("#novo-canal-nome", name)
    page.fill("#novo-canal-nicho", "História")
    page.click("#btn-criar-canal")
    page.wait_for_url(re.compile(r".*/studio/panel\?project_id=[0-9a-f]{32}"))


def create_video(j: Journey, topic: str, *, mode: str) -> str:
    page = j.page
    page.goto(f"{j.base}/studio/panel/novo-video")
    page.fill("#tema-novo", topic)
    page.locator(f"#card-modo-{mode}").click()
    expect(page.locator(f'input[name="modo-producao"][value="{"piloto" if mode == "piloto" else "diretor"}"]')).to_be_checked()
    page.locator("label.tog:has(#usar-roteiro)").click()
    page.fill("#roteiro-pronto", SOURCE_TEXT)
    page.fill("#roteiro-url", SOURCE_LINK)
    page.click("#btn-criar-abrir")
    page.wait_for_url(re.compile(r".*/studio/panel/videos/[0-9a-f]{32}/cenas"), timeout=30000)
    return j.video_id()


def wait_for_scenes(j: Journey, minimum: int = 3) -> None:
    j.wait_for(lambda: j.page.locator("textarea[data-a=text]").count() >= minimum, timeout=60, reload=True,
               what=f"{minimum}+ cenas no storyboard")


def continue_run_until_approval(j: Journey, video_id: str) -> None:
    """Pausa humana é projeto: o roteiro pronto aguarda "Continuar" na execução; o resto corre sozinho."""
    page = j.page
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/producao")
    page.get_by_role("link", name="Abrir execução").click()
    page.wait_for_url(re.compile(r".*/production-runs/[0-9a-f]{32}"))
    page.locator("button[data-run-action=resume]").first.click()
    j.wait_for(lambda: j.video_status(video_id) == "AWAITING_APPROVAL", timeout=APPROVAL_TIMEOUT,
               what="vídeo renderizado aguardando aprovação")


def approve_from_quality(j: Journey, video_id: str) -> None:
    page = j.page
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/qualidade")
    assert_no_duplicate_ids(page, context_desc="Qualidade com prévia")
    expect(page.locator("#conteudo video")).to_be_visible()  # prévia do render real
    expect(page.get_by_text("Elegível para aprovação")).to_be_visible()
    approve = page.locator("#btn-approve-video")
    expect(approve).to_be_enabled()
    approve.click()
    page.wait_for_url(re.compile(r".*/publicacao$"))
    j.wait_for(lambda: j.video_status(video_id) == "APPROVED", timeout=20, what="status APPROVED")


def assert_pending_publication(j: Journey, video_id: str) -> None:
    """Aprovado e pendente de publicar: a publicação é um passo separado e falha fechada sem YouTube."""
    page = j.page
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/publicacao")
    expect(page.locator(".pill", has_text="Aprovado").first).to_be_visible()
    expect(page.get_by_text("Decisão: aprovado")).to_be_visible()
    expect(page.get_by_role("button", name="Publicar agora")).to_be_visible()
    expect(page.get_by_text("Sem destino YouTube conectado")).to_be_visible()
    expect(page.get_by_text("Nenhuma publicação registrada")).to_be_visible()
    status, publication = j.api(f"/studio/videos/{video_id}/publication")
    assert status == 200 and publication is None, "nada pode ter sido publicado ou enfileirado"
    assert_no_duplicate_ids(page, context_desc="Publicação pendente")


def test_piloto_creation_to_approved_pending_publication_and_adjustments(journey: Journey) -> None:
    j, page = journey, journey.page
    suffix = uuid.uuid4().hex[:6]

    # 1. Canal e vídeo (roteiro colado com link de referência = fonte registrada)
    create_channel(j, f"Canal Ponta a Ponta {suffix}")
    video_id = create_video(j, f"Queda de Constantinopla {suffix}", mode="piloto")

    # 2. Storyboard com cenas reais, todas editáveis (Short sem plano de capítulos)
    wait_for_scenes(j, 3)
    assert page.locator("textarea[data-a=text][readonly]").count() == 0
    assert_no_duplicate_ids(page, context_desc="Storyboard")
    assert_no_horizontal_overflow(page, context_desc="Storyboard")
    expect(page.get_by_text("Gerar roteiro e cenas")).to_have_count(0)

    # 3. Produção: continuar na execução e esperar o render e o QA reais
    continue_run_until_approval(j, video_id)
    status, render = j.api(f"/studio/videos/{video_id}/render")
    assert render["job"]["status"] == "SUCCEEDED" and render["job"]["error"] is None
    qa = render["qa_report"]
    assert qa is not None and qa["coverage"]["status"] == "verified", qa
    assert len(qa["checks_run"]) > 0, qa
    assert [f for f in qa["findings"] if f.get("severity") not in ("warning", "info")] == [], qa["findings"]

    # 4. Aprovar na aba Qualidade (regressão: o botão enviava corpo vazio e a API recusava)
    approve_from_quality(j, video_id)

    # 5. Aprovado e pendente de publicar
    assert_pending_publication(j, video_id)

    # 6. Pedir ajustes: diálogo do tema, reabre a edição e invalida a aprovação
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/qualidade")
    page.locator("[data-reopen]").first.click()
    expect(page.locator("dialog#dlg-reopen[open]")).to_be_visible()
    expect(page.locator("dialog#dlg-reopen")).to_contain_text("aprovação")
    page.click("#btn-confirmar-reopen")
    page.wait_for_url(re.compile(r".*/cenas$"))
    j.wait_for(lambda: j.video_status(video_id) == "SCRIPTED", timeout=20, what="vídeo reaberto (SCRIPTED)")
    wait_for_scenes(j, 3)

    # 7. Editar texto com lastro nas fontes e reordenar; persiste depois de recarregar
    first = page.locator("textarea[data-a=text]").first
    new_text = "O sultão Mehmed II comandava cerca de 80 mil soldados otomanos."
    first.fill(new_text)
    with page.expect_response(lambda r: re.search(r"/script/scenes/0$", r.url) and r.request.method == "POST") as saved:
        page.locator("textarea[data-a=text]").nth(1).click()
    assert saved.value.status == 200
    second_before = page.locator("textarea[data-a=text]").nth(1).input_value()
    with page.expect_response(lambda r: r.url.endswith("/script/scenes/reorder") and r.request.method == "POST") as moved:
        page.locator('[data-a="mv"][data-d="1"]').first.click()
    assert moved.value.status == 200
    page.reload()
    texts = [t.input_value() for t in page.locator("textarea[data-a=text]").all()]
    assert texts[0] == second_before and texts[1] == new_text, texts[:3]

    # 8. Texto sem lastro nas fontes é recusado e nada é gravado
    before = [t.input_value() for t in page.locator("textarea[data-a=text]").all()]
    j.expected_5xx.append("/script/scenes/2")  # a API recusa com 502 o texto que as fontes não sustentam
    page.locator("textarea[data-a=text]").nth(2).fill("O cerco durou 987654 dias e envolveu 31 milhões de soldados.")
    with page.expect_response(lambda r: "/script/scenes/2" in r.url and r.request.method == "POST") as refused:
        page.locator("textarea[data-a=text]").nth(0).click()
    assert refused.value.status in (409, 422, 502), refused.value.status
    page.reload()
    assert [t.input_value() for t in page.locator("textarea[data-a=text]").all()] == before

    # 9. Regerar o que mudou e aprovar de novo
    page.click("#btn-gerar-faltante")
    expect(page.locator("dialog#dlg-impacto[open]")).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith("/production-runs") and r.request.method == "POST") as started:
        page.click("#btn-confirmar-render")
    assert started.value.status == 202
    continue_run_until_approval(j, video_id)
    approve_from_quality(j, video_id)
    assert_pending_publication(j, video_id)

    # 10. Em nenhum passo houve erro de JS, diálogo nativo ou 5xx
    j.assert_clean()
