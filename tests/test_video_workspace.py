"""W1.4 (+ W1.7): as 8 áreas do vídeo como rotas, reusando os blocos existentes.

Sem banco: monta `VideoDetailView`/`VideoStyleView`/`ScriptPageView` na mão e renderiza cada área.
Fidelidade ao protótipo (`VIDEO_TABS`, ~584-621) para a navegação; honestidade para o conteúdo —
o que não é medido aparece como ausência explícita, e as áreas somente leitura não têm controles.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape as e

from app.studio.api.panel_video_workspace import (
    DEFAULT_AREA,
    VIDEO_AREAS,
    _area_narracao,
    _area_visao_geral,
    _composition_plan_card,
    _next_step,
    _progress_card,
    area_href,
    render_video_workspace,
)
from app.studio.application.panel import VideoDetailView
from app.studio.application.composition_view import BuildCompositionView
from app.studio.application.ports import LatestRun, PubInfo, SourceInfo
from app.studio.application.publishing import Preview
from app.studio.application.script_view import ChapterView, ScriptPageView
from app.studio.application.video_style import VideoStyleView
from app.studio.domain.contracts import PublicationStatus, Video, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage
from app.studio.domain.render_plan import AssetReference, StyleSnapshot
from app.studio.domain.render_plan_builder import (
    StoryboardOverlay,
    StoryboardScene,
    build_render_plan,
)
from app.studio.domain.visual_style import VisualStyle
from test_panel import _row

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
VIDEO = "a" * 32
STYLE = VisualStyle(
    id="b" * 32,
    name="Cinemático",
    params={
        "motion": ["zoom_in", "pan_left"],
        "music": {"bpm": 90, "seed": 11},
        "caption": {"font_size": 42, "bottom": 96},
        "palette": {"accent": "#a78bfa"},
        "transition": {"kind": "fade", "duration_ticks": 6},
        "voice": {"model": "piper:pt_BR-jeff-medium"},
    },
)

# Ordem e hrefs exatos da tabela de áreas.
EXPECTED_HREFS = {
    "direcao": f"/studio/panel/videos/{VIDEO}/direcao",
    "cenas": f"/studio/panel/videos/{VIDEO}/cenas",
    "composicao": f"/studio/panel/videos/{VIDEO}/composicao",
    "qualidade": f"/studio/panel/videos/{VIDEO}/qualidade",
    "publicacao": f"/studio/panel/videos/{VIDEO}/publicacao",
    "fontes": f"/studio/panel/videos/{VIDEO}/fontes",
    "producao": f"/studio/panel/videos/{VIDEO}/producao",
}


def _view(*, status=VideoStatus.IDEA, stage=Stage.PENDING, sources=(), latest_run=None,
          publication=None, render_error=None, video=None) -> VideoDetailView:
    return VideoDetailView(
        video=video or _row(VIDEO, "Como funciona a energia solar", status=status),
        stage=stage,
        cost_text="sem registro de uso",
        steps=[],
        usage=[],
        render_error=render_error,
        publication=publication,
        sources=list(sources),
        latest_run=latest_run,
    )


def _style_view(*, inherits: bool = True) -> VideoStyleView:
    return VideoStyleView(
        video_id=VIDEO,
        project_id="p1",
        override_style_id=None if inherits else STYLE.id,
        channel_style_id=STYLE.id,
        inherited_style_name=STYLE.name,
        styles=(STYLE,),
    )


def _script_view(*, has_script: bool = True, approved: bool = False) -> ScriptPageView:
    if not has_script:
        return ScriptPageView(video_id=VIDEO, topic="Como funciona a energia solar", has_script=False)
    return ScriptPageView(
        video_id=VIDEO,
        topic="Como funciona a energia solar",
        has_script=True,
        version=2,
        scene_count=3,
        target_seconds=60,
        chapters=[
            ChapterView(0, "Abertura", "intro", "Introdução", 1, 18.0),
            ChapterView(1, "Desenvolvimento", "body", "Desenvolvimento", 2, 30.0),
        ],
        approved=approved,
    )


def _asset(asset_id: str = "asset-1", sha: str = "a" * 64) -> AssetReference:
    return AssetReference(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/{asset_id}.png",
        content_sha256=sha,
        media_type="image",
        license="Imagem gerada por IA",
    )


def _plan_repo(plan):
    """Repositório em memória: só `latest_plan`, que é o que a leitura de Composição usa."""

    class _Repo:
        def latest_plan(self, plan_id):
            assert plan_id == f"plan:{VIDEO}"
            return plan

    return _Repo()


def _persisted_plan(*, scene_id: str = "cena-1", overlay: bool = True):
    """Plano real de uma cena (base + overlay opcional) com revisão 3, pronto para persistir."""
    overlays = ([StoryboardOverlay(scene_id=scene_id, asset_id="overlay-1", start_s=0.5,
                                   duration_s=1.0, z_index=1, fit="contain")]
                if overlay else [])
    assets = [_asset()]
    if overlay:
        assets.append(_asset("overlay-1", "b" * 64))
    return build_render_plan(
        plan_id=f"plan:{VIDEO}",
        revision=3,
        project_id="p1",
        video_id=VIDEO,
        format=VideoFormat.short,
        scenes=[StoryboardScene(scene_id=scene_id, asset_id="asset-1",
                                narration="Uma cena medida.", speech_seconds=2.0)],
        assets=assets,
        style_snapshot=StyleSnapshot(style_id=STYLE.id, version=1),
        overlays=overlays,
    )


def _composition_view(*, scene_id: str = "cena-1", overlay: bool = True):
    return BuildCompositionView(_plan_repo(_persisted_plan(scene_id=scene_id, overlay=overlay))).execute(VIDEO)


def _render(area, *, view=None, style_view=None, script_view=None, composition_view=None, preview=None) -> str:
    return render_video_workspace(
        view if view is not None else _view(),
        area,
        style_view=style_view,
        script_view=script_view,
        composition_view=composition_view,
        preview=preview,
    )[0]


def _area_nav(html: str) -> str:
    match = re.search(r'<nav class="abas-video" aria-label="Áreas do vídeo">(.*?)</nav>', html, re.S)
    assert match is not None, "navegação de áreas ausente"
    return match.group(1)


def _content(html: str) -> str:
    """Fragmento do conteúdo da tela, sem casca lateral/topbar/diálogo nem scripts/estilos."""
    start = html.index('id="conteudo"')
    end = html.index("</main>", start)
    fragment = html[start:end]
    return re.sub(r"<(style|script)\b.*?</\1>", "", fragment, flags=re.S | re.I)


def _active_label(nav_block: str) -> str:
    match = re.search(r'<a[^>]*aria-current="page"[^>]*>([^<]+)</a>', nav_block)
    assert match is not None, "nenhuma área ativa na navegação"
    return match.group(1)


# --------------------------------------------------------------------------- 1) navegação

def test_six_areas_are_links_with_expected_labels_and_hrefs():
    nav = _area_nav(_render(DEFAULT_AREA))

    assert len(VIDEO_AREAS) == 6
    assert [area for area, _ in VIDEO_AREAS] == ["direcao", "cenas", "composicao", "qualidade", "publicacao", "fontes"]
    for area, label in VIDEO_AREAS:
        href = EXPECTED_HREFS[area]
        assert f'href="{href}"' in nav, (area, href)
        assert re.search(rf'<a[^>]*href="{re.escape(href)}"[^>]*>{re.escape(e(label))}</a>', nav), area
    # links de servidor, não abas: sem role/JS de aba.
    assert 'role="tab"' not in nav
    assert "data-tab" not in nav


def test_only_the_active_area_has_aria_current_page():
    for area in ("direcao", "cenas", "composicao", "qualidade", "publicacao", "fontes"):
        nav = _area_nav(_render(area))
        assert nav.count('aria-current="page"') == 1, area
        assert _active_label(nav) == e(dict(VIDEO_AREAS)[area])
        active_anchor = re.search(r'<a[^>]*aria-current="page"[^>]*>', nav).group(0)
        assert f'href="{EXPECTED_HREFS[area]}"' in active_anchor


def test_unknown_area_falls_back_to_overview_without_breaking():
    html = _render("nao-existe")
    assert html.count("<h1") == 1
    nav = _area_nav(html)
    assert nav.count('aria-current="page"') == 1
    assert _active_label(nav) == e(dict(VIDEO_AREAS)["cenas"])
    # Sem cenas, `tabScenes` do protótipo cai no cabeçalho "Storyboard integrado".
    assert "Storyboard integrado" in html


# --------------------------------------------------------------------------- 2) conteúdo por área

def test_visao_geral_shows_scenes_target_and_unmeasured_duration():
    html = _area_visao_geral(_view(), script_view=_script_view(), video_id=VIDEO)
    assert "Cenas no roteiro" in html
    assert ">3<" in html  # número de cenas veio do roteiro real
    assert "Duração-alvo" in html and "1 min 0 s" in html
    assert "Duração real" in html and "não medida" in html
    assert "Próximo passo" in html
    # atalhos para as outras áreas
    for area in ("composicao", "qualidade", "publicacao", "fontes"):
        assert f'href="{EXPECTED_HREFS[area]}"' in html


def test_visao_geral_next_step_uses_the_real_state():
    # sem fontes: o próximo passo é adicionar fontes (link para a área fontes).
    html = _area_visao_geral(_view(), video_id=VIDEO)
    assert "Adicione fontes" in html
    assert f'href="{EXPECTED_HREFS["fontes"]}"' in html

    # com run vivo: o caminho é a execução.
    html = _area_visao_geral(_view(latest_run=LatestRun("r1", "RUNNING")), video_id=VIDEO)
    assert "Acompanhe a execução" in html
    assert f'href="{EXPECTED_HREFS["producao"]}"' in html

    # aprovado: preparar a publicação.
    html = _area_visao_geral(_view(
        status=VideoStatus.AWAITING_APPROVAL, stage=Stage.APPROVED,
        sources=[SourceInfo("s1", "https://exemplo.test/a", 120)]), video_id=VIDEO)
    assert "Prepare a publicação" in html
    assert f'href="{EXPECTED_HREFS["publicacao"]}"' in html


def test_fontes_reuses_sources_card_and_states_registered_is_not_extracted():
    html = _render("fontes", view=_view(sources=[SourceInfo("s1", "https://exemplo.test/a", 120)]))
    content = _content(html)
    assert 'id="video-fontes"' in content  # cartão real reutilizado
    assert 'id="video-sources-form"' in content
    assert "https://exemplo.test/a" in content
    visible = re.sub(r"<[^>]+>", " ", content)
    assert "registrada" in visible
    assert "extraída" in visible
    assert "verificada" in visible
    # O protótipo não tem ponte para a página antiga de Roteiro: Cenas é o lugar do roteiro.
    assert "/roteiro" not in content and "Abrir roteiro e estrutura" not in content


def test_narracao_is_read_only_and_names_effective_voice():
    content = _area_narracao(_view(), style_view=_style_view(), script_view=_script_view(), video_id=VIDEO)
    assert "piper:pt_BR-jeff-medium" in content
    assert "Cinemático" in content
    assert "Duração-alvo" in content and "1 min 0 s" in content
    assert "Áudio e duração medida indisponíveis" in content
    assert "Abertura" in content and "Desenvolvimento" in content  # trechos do roteiro


def test_cenas_without_scene_read_is_honest_empty_state():
    """Sem cenas lidas, a aba segue o vazio do protótipo e não inventa cena nem ação sobre cena."""
    html = _render("cenas", script_view=_script_view())
    content = _content(html)
    visible = _visible(content)
    assert "Storyboard integrado" in visible
    assert "ainda não tem cenas" in visible  # estado vazio honesto: o roteiro nasce das fontes
    assert 'id="cena-em-foco"' not in content
    assert 'id="btn-excluir-cena"' not in content
    # `addscene` do protótipo: "+ Nova cena" é ação na própria bancada, não link para o roteiro
    assert 'id="btn-nova-cena"' in content and f'href="/studio/videos/{VIDEO}/roteiro"' not in content


def test_composicao_shows_effective_params_and_declares_transition_only():
    html = _render("composicao", style_view=_style_view())
    content = _content(html)
    assert "Estilo efetivo" in content and "Cinemático" in content
    assert "fade · 6 ticks" in content
    assert "bpm 90" in content and "seed 11" in content
    assert "zoom_in, pan_left" in content
    assert "fonte 42" in content and "base 96" in content
    assert "transição é apenas declarada" in content or "transição</strong> é apenas declarada" in content
    assert "não é consumida" in content
    assert "visual_style.py:502-506" in content
    assert "Resolução e FPS são fixos hoje" in content


def test_composicao_without_style_is_honest_about_absence():
    html = _render("composicao")
    assert "Nenhum estilo efetivo resolvido" in html


def test_composicao_without_a_persisted_plan_is_honest_about_absence():
    assert BuildCompositionView(_plan_repo(None)).execute(VIDEO) is None
    content = _content(_render("composicao"))
    assert "Plano de composição" in content
    assert "Sem plano de composição ainda" in content
    # sem plano, nada de tracks ilustrativas do protótipo (B-roll, Título, Imagem base).
    for invented in ("B-roll", "Título", "Imagem base", "Shots"):
        assert invented not in content, invented


def test_composicao_shows_the_persisted_plan_tracks_and_shots_in_read_only():
    view = _composition_view()
    assert view is not None

    content = _content(_render("composicao", composition_view=view))
    assert "Plano de composição" in content
    assert "Revisão <strong>3</strong>" in content
    # tracks do plano: a base e a de overlay (VE-01), mais narração e legenda declaradas.
    for track in ("visual-main", "visual-overlay", "narration-main", "subtitle-main"):
        assert track in content, track
    # shots com cena, papel, z-index e janela reais do plano.
    assert "cena-1" in content
    assert ">base<" in content and ">overlay<" in content
    assert "0.00 s – 2.80 s" in content  # base cobre a cena inteira
    assert "0.50 s – 1.50 s" in content  # overlay na sua própria janela
    assert ">sim<" in content  # ativos: derivado do plano, não um toggle inventado


def test_composicao_is_read_only_with_and_without_a_plan():
    for composition_view in (None, _composition_view()):
        card = _composition_plan_card(composition_view)
        assert "<button" not in card
        assert "<input" not in card
        assert "<form" not in card
        assert "autosave" not in card.lower()


def test_composicao_escapes_the_plan_content_before_rendering():
    payload = '<img src=x onerror=alert(1)>'
    view = _composition_view(scene_id=payload, overlay=False)
    assert view is not None

    content = _content(_render("composicao", composition_view=view))
    assert payload not in content
    assert "&lt;img src=x onerror=alert(1)&gt;" in content


def test_qualidade_states_semantic_not_verified_and_links_preview():
    html = _render("qualidade", view=_view(
        status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL),
        script_view=_script_view(approved=True))
    content = _content(html)
    assert "não verificada" in content
    assert "Avaliação semântica" in content
    assert "Aguardando aprovação" in content
    assert f'href="/studio/videos/{VIDEO}/preview"' in content

    # antes do render, o link de prévia não aparece: a tela explica em vez de linkar para o vazio.
    early = _content(_render("qualidade"))
    assert f'href="/studio/videos/{VIDEO}/preview"' not in early
    assert "após a renderização" in early


def test_qualidade_renders_qa_report_when_the_view_carries_one():
    from types import SimpleNamespace

    class _Coverage:
        status = "verified"

    class _Qa:
        is_publishable = False
        coverage = _Coverage()
        findings = [1, 2]

    video = _row(VIDEO, "Tema")
    fake_video = SimpleNamespace(id=VIDEO, title=video.title, topic=video.topic, qa_report=_Qa())
    html = _render("qualidade", view=_view(video=fake_video))
    content = _content(html)
    assert "Relatório de QA do render" in content
    assert "Publicável" in content and "não" in content
    assert "Achados" in content and ">2<" in content


def test_publicacao_summarizes_publication_and_refuses_without_destination():
    pub = PubInfo(status=PublicationStatus.FAILED, attempt=2, error="upload recusado")
    html = _render("publicacao", view=_view(
        status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL, publication=pub))
    content = _content(html)
    assert "Publicação" in content
    assert "FAILED" in content and "Tentativa" in content
    assert "upload recusado" in content
    assert f'href="/studio/videos/{VIDEO}/preview"' in content
    assert "publicação é recusada" in content
    assert "domain/channel.py" in content


def test_producao_reuses_run_card_and_links_the_execution():
    run = LatestRun("run-123", "FAILED", failed_stage="render", failure_reason="ffmpeg falhou")
    html = _render("producao", view=_view(stage=Stage.FAILED, latest_run=run))
    content = _content(html)
    assert 'id="video-producao"' in content
    assert "Render" in content and "ffmpeg falhou" in content
    assert f'href="/studio/panel/videos/{VIDEO}/production-runs/run-123"' in content


# --------------------------------------------------------------------------- 3) sem controle falso

# --------------------------------------------------------------------------- 5) W1.7 visível

def test_fontes_honesty_is_visible_not_sr_only():
    content = _content(_render("fontes", view=_view(
        sources=[SourceInfo("s1", "https://exemplo.test/a", 120)])))
    # a frase de honestidade existe em markup visível (um `<p class="note">`, como no protótipo), não em `sr-only`.
    match = re.search(r'<p class="(?:aviso|note)"[^>]*id="fontes-honestidade"[^>]*>(.*?)</p>', content, re.S)
    assert match is not None, "texto de honestidade das fontes ausente"
    phrase = match.group(1)
    assert "registrada" in phrase and "extraída" in phrase and "verificada" in phrase
    for sr_only in re.finditer(r'class="[^"]*sr-only[^"]*"[^>]*>(.*?)</(?:span|p|div)>',
                               content, re.S):
        assert "extraída" not in sr_only.group(1)


def test_area_href_helper_matches_the_nav():
    for area in EXPECTED_HREFS:
        assert area_href(VIDEO, area) == EXPECTED_HREFS[area]


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# --------------------------------------------------------------------------- 6) W5.1 (PUB-01)

def _preview(*, status=VideoStatus.AWAITING_APPROVAL, title="Título padrão", tags=("ade",)):
    video = Video(id=VIDEO, project_id="p1", topic="Tema do vídeo", format=VideoFormat.short,
                  status=status, title=title, tags=list(tags))
    return Preview(video=video, scenes=[], qa=None, has_file=False, sources=[], credits=[],
                   default_title=title, default_description="Descrição padrão", approval=None,
                   publication=None, output_asset_id="e" * 32)


def test_publicacao_renders_the_approval_form_reusing_the_preview_block():
    html, headers = render_video_workspace(
        _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL),
        "publicacao", preview=_preview())
    content = _content(html)
    assert 'id="review"' in content and 'id="approve"' in content and 'id="reject"' in content
    for marker in ('for="title"', 'for="description"', 'for="tags"', 'for="publish_at"', 'role="status"'):
        assert marker in content, f"o formulário não contém {marker!r}"
    # o JS do formulário entra no documento sob o nonce da CSP estrita
    csp = headers["Content-Security-Policy"]
    nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">' in html and "getElementById('review')" in html
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert headers["Cache-Control"] == "no-store"


def test_publicacao_form_escapes_the_metadata():
    html, _ = render_video_workspace(
        _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL),
        "publicacao",
        preview=_preview(title='<script>alert(1)</script> & "x"', tags=["a<b"]))
    content = _content(html)
    assert "<script>alert(1)" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content and "a&lt;b" in content


def test_publicacao_without_preview_keeps_the_summary_and_has_no_form():
    html, _ = render_video_workspace(
        _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL), "publicacao")
    content = _content(html)
    assert 'id="review"' not in content and 'id="approve"' not in content
    assert "Nenhuma publicação registrada" in content
    assert f'href="/studio/videos/{VIDEO}/preview"' in content


def test_publicacao_after_the_decision_shows_it_without_the_form():
    html, _ = render_video_workspace(
        _view(status=VideoStatus.APPROVED, stage=Stage.APPROVED),
        "publicacao", preview=_preview(status=VideoStatus.APPROVED))
    content = _content(html)
    assert 'id="approve"' not in content
    assert "não está em revisão" in content


def test_publicacao_declares_the_intent_invalidation_rule():
    html, _ = render_video_workspace(
        _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL), "publicacao")
    assert 'id="publicacao-intencao"' in html and "invalida a intenção anterior" in html


def _com_hash(view, content_hash="c" * 64):
    from dataclasses import replace

    from app.studio.application.script_view import VersionView
    return replace(view, versions=[VersionView(version=view.version, current=True, approved=False, rejected=False,
                                               superseded=False, hash_short=content_hash[:8],
                                               content_hash=content_hash)])


def test_qualidade_does_not_offer_script_approval_for_a_script_without_content_hash():
    """Bug: roteiro curto não tem plano nem hash; o botão enviava hash vazio e a API respondia "Revise os campos: content_hash"."""
    content = _content(_render("qualidade", script_view=_script_view(approved=False)))  # sem hash na versão corrente
    assert 'id="btn-approve-script"' not in content
    assert "não se aplica" in content and "aprovação do vídeo" in content


def test_qualidade_approves_the_script_version_inline_without_leaving_for_the_old_script_page():
    html = _render("qualidade", script_view=_com_hash(_script_view(approved=False)))
    content = _content(html)
    assert 'id="btn-approve-script"' in content and 'data-version="2"' in content
    assert 'data-hash="' + "c" * 64 + '"' in content
    assert "Aprovar versão 2 do roteiro" in content
    assert "/roteiro" not in content
    assert "/script/approve" in html  # o clique chama a API existente
    approved = _content(_render("qualidade", script_view=_script_view(approved=True)))
    assert 'id="btn-approve-script"' not in approved and "aprovada" in approved


def test_fontes_flags_a_source_too_short_to_yield_any_claim():
    html = _render("fontes", view=_view(sources=[SourceInfo("s1", "https://exemplo.test/curta", 4),
                                                    SourceInfo("s2", "https://exemplo.test/longa", 900)]))
    content = _content(html)
    assert content.count("Texto curto demais para o roteiro") == 1
    assert content.index("Texto curto demais") < content.index("exemplo.test/longa")
    assert 'id="source-text-rule"' in content and "40 a 400 caracteres" in content


def test_qualidade_approve_button_sends_the_reviewed_render_revision():
    """Bug (achado no E2E real): o botão enviava `{}` e a API respondia "the reviewed render revision is required"."""
    view = _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL)
    html = _render("qualidade", view=view, preview=_preview())
    button = re.search(r'<button[^>]*id="btn-approve-video"[^>]*>', _content(html)).group(0)
    assert 'data-output-asset-id="' + "e" * 32 + '"' in button and "disabled" not in button
    assert "output_asset_id: approveBtn.getAttribute('data-output-asset-id')" in html  # o corpo do POST leva a revisão


def test_qualidade_approve_button_is_disabled_without_a_known_render_revision():
    view = _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL)
    button = re.search(r'<button[^>]*id="btn-approve-video"[^>]*>', _content(_render("qualidade", view=view))).group(0)
    assert "disabled" in button and "prévia" in button.lower()


def test_approved_video_with_a_run_waiting_for_publication_shows_no_production_in_progress():
    """Achado no E2E: o run só fecha na publicação (WAITING_HUMAN), mas aprovado não é "produção em andamento"."""
    view = _view(status=VideoStatus.APPROVED, stage=Stage.APPROVED, latest_run=LatestRun("r1", "WAITING_HUMAN"))
    assert _progress_card(view) == ""
    assert 'id="btn-render" disabled aria-busy' not in _render("cenas", view=view)
    live = _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL, latest_run=LatestRun("r1", "WAITING_HUMAN"))
    assert _progress_card(live) != ""  # aguardando aprovação continua sendo a execução viva
    title = _next_step(view, VIDEO)[0]
    assert title != "Acompanhe a execução"


def test_publicacao_of_an_approved_video_does_not_say_the_preview_is_pending_render():
    view = _view(status=VideoStatus.APPROVED, stage=Stage.APPROVED)
    content = _content(_render("publicacao", view=view, preview=_preview(status=VideoStatus.APPROVED)))
    assert "A prévia fica disponível após a renderização" not in content
    assert f'href="/studio/videos/{VIDEO}/preview"' in content
