"""Workspace do vídeo em **8 áreas como rotas** (W1.4 + W1.7).

Fonte de UX: `docs/backlogs/faceless-visual-evolution 2/prototype/index.html` (~583-621),
`VIDEO_TABS` e os painéis. Este módulo segue **estrutura, rótulos, estados e honestidade** do
protótipo, mas a aparência manda é a casca V3 (`shell_v3` + `shell_v3_css`): nada de CSS novo
aqui, nada de JS de abas — cada área é um **link** de servidor com `aria-current="page"` só na
ativa, exatamente como a navegação de Configurações (`.menu-config`, rotas, não abas).

Reuso, não duplicação: os cartões reais já existentes continuam sendo a fonte dos controles que
funcionam (`panel._video_sources_card`, `panel._video_run_card`). O que esta tela acrescenta é a
**navegação por área** e o conteúdo honesto de cada uma: só o que existe vira número/lista; o que
não é medido aparece como ausência explícita, e nunca existe controle que não faz nada.

A página sai por `shell_v3.render_document(...)` (`active="videos"`), como as outras telas.
As rotas antigas (`/studio/panel/videos/{id}`, `/roteiro`, `/preview`, `production-runs`) seguem
existindo e não são tocadas aqui.
"""
from __future__ import annotations

import secrets
from html import escape as e

from ..domain.contracts import VideoStatus
from ..domain.panel import Stage
from . import approval_form
from . import panel as legacy
from . import shell_v3

# Ordem e rótulos do protótipo (`VIDEO_TABS`). O id é o segmento da rota.
VIDEO_AREAS: tuple[tuple[str, str], ...] = (
    ("visao-geral", "Visão geral"),
    ("fontes", "Fontes e roteiro"),
    ("narracao", "Narração"),
    ("cenas", "Cenas e mídias"),
    ("composicao", "Composição"),
    ("qualidade", "Qualidade"),
    ("publicacao", "Publicação"),
    ("producao", "Produção"),
)
AREA_LABELS = dict(VIDEO_AREAS)
AREA_IDS = frozenset(AREA_LABELS)
DEFAULT_AREA = "visao-geral"

# A prévia (e a aprovação) só existe depois que há artefato renderizado — mesma leitura do
# detalhe antigo. Antes disso, esta tela explica em vez de oferecer um link que não levaria a nada.
_PREVIEW_STAGES = (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED)

# Um run vivo é continuado pela execução, não por uma produção nova.
_LIVE_RUN_STATES = ("CREATED", "RUNNING", "WAITING_HUMAN", "PAUSED")


def area_href(video_id: str, area: str) -> str:
    """Rota real da área. O `area` já chega normalizado (ver `_normalize_area`)."""
    return f"/studio/panel/videos/{e(video_id)}/{area}"


def _normalize_area(area: str | None) -> str:
    """Área desconhecida (ou ausente) cai em `visao-geral`.

    Decisão: a rota sempre devolve uma tela válida. O protótipo faz o mesmo
    (`panels[S.videoTab] || overviewPanel`); um segmento desconhecido não é erro do operador,
    é "nenhuma área específica" — e o `aria-current` vai para a Visão geral.
    """
    return area if area in AREA_IDS else DEFAULT_AREA


def _video_area_nav(video_id: str, active: str) -> str:
    """Navegação por área: links de servidor, um único `aria-current="page"` na ativa."""
    items = []
    for area_id, label in VIDEO_AREAS:
        current = ' aria-current="page"' if area_id == active else ""
        cls = "aba ativa" if area_id == active else "aba"
        items.append(
            f'<a class="{cls}" href="{area_href(video_id, area_id)}"{current}>{e(label)}</a>'
        )
    return f'<nav class="abas-video" aria-label="Áreas do vídeo">{"".join(items)}</nav>'


def _kv(label: str, value_html: str) -> str:
    return f'<div class="kv"><span>{e(label)}</span><span>{value_html}</span></div>'


def _effective_style(style_view) -> object | None:
    """O `VisualStyle` efetivo do vídeo (override > canal), ou `None` se não resolvido."""
    if style_view is None:
        return None
    style_id = getattr(style_view, "effective_style_id", None)
    if style_id is None:
        return None
    for style in getattr(style_view, "styles", ()) or ():
        if style.id == style_id:
            return style
    return None


def _group(params: dict, group: str) -> dict:
    value = params.get(group)
    return value if isinstance(value, dict) else {}


def _next_step(view, video_id: str) -> tuple[str, str, str, str]:
    """A próxima ação real, derivada do estado — nunca um botão que não faz nada.

    Ordem de precedência: falha de render > run falho > run vivo > sem fontes > aprovação >
    aprovado > falha > revisão do roteiro. Devolve (título, motivo, href, rótulo do link).
    """
    if view.render_error:
        return ("Reexecute o render",
                "O render falhou. Abra a produção para ver o motivo real antes de tentar de novo.",
                area_href(video_id, "producao"), "Abrir produção")
    run = view.latest_run
    if run is not None and run.state == "FAILED":
        return ("Retome a produção",
                "A execução parou. Abra a produção para ver a etapa e o motivo antes de retomar.",
                area_href(video_id, "producao"), "Abrir produção")
    if run is not None and run.state in _LIVE_RUN_STATES:
        return ("Acompanhe a execução",
                "Há uma execução em andamento; o caminho é continuar por ela.",
                area_href(video_id, "producao"), "Abrir produção")
    if not view.sources:
        return ("Adicione fontes",
                "O roteiro só é escrito a partir de fatos das fontes. Sem fonte aproveitável, "
                "a produção para no primeiro passo.",
                area_href(video_id, "fontes"), "Abrir fontes")
    if view.stage == Stage.AWAITING_APPROVAL:
        return ("Aprove a versão",
                "A prévia e a aprovação desta versão estão na página de prévia.",
                f"/studio/videos/{e(video_id)}/preview", "Abrir prévia")
    if view.stage in (Stage.APPROVED, Stage.COMPLETED):
        return ("Prepare a publicação",
                "A versão está aprovada; revise a intenção de publicação antes de enviar.",
                area_href(video_id, "publicacao"), "Abrir publicação")
    if view.stage == Stage.FAILED:
        return ("Ver e retomar",
                "A produção falhou. Abra a produção para ver o motivo registrado.",
                area_href(video_id, "producao"), "Abrir produção")
    return ("Revise as fontes e o roteiro",
            "Confirme as fontes e o roteiro antes de gerar narração e cenas.",
            area_href(video_id, "fontes"), "Abrir fontes")


def _revision_history_card(script_view, video_id: str) -> str:
    """Histórico honesto: lista revisões com snapshot e só oferece restaurar quando o backend aceita."""
    versions = list(getattr(script_view, "versions", []) or [])
    if not versions:
        return ""
    editable = bool(getattr(script_view, "editable", False))
    current_version = getattr(script_view, "version", None)
    rows = []
    for version in versions:
        state = "atual" if version.current else ("aprovada" if version.approved else "substituída")
        meta = f"v{version.version} · {state} · {version.scene_count} cena(s)"
        if version.media_pending:
            meta += f" · {version.media_pending} mídia(s) pendente(s)"
        if version.superseded and version.restorable and editable and current_version is not None:
            rows.append(
                f'<li><span>{e(meta)}</span>'
                f'<button type="button" class="btn restore-revision" data-video-id="{e(video_id)}" '
                f'data-version="{version.version}" data-expected-version="{e(str(current_version))}">'
                f"Restaurar v{version.version}</button></li>"
            )
        else:
            note = ""
            if version.superseded and not version.restorable:
                note = " · sem snapshot recuperável"
            elif version.superseded and not editable:
                note = " · restaure em IDEA/SCRIPTED"
            rows.append(f"<li><span>{e(meta + note)}</span></li>")
    return (
        '<div class="card"><h3>Histórico de revisões</h3>'
        '<p class="micro">Restaurar cria uma NOVA revisão com o texto, a ordem e a mídia da versão '
        "escolhida. Mídia que não existe mais fica marcada para revisão.</p>"
        f'<ul class="pilha" id="revision-history">{"".join(rows)}</ul>'
        '<div id="revision-feedback" class="form-feedback" role="status"></div>'
        "</div>"
    )


def _area_visao_geral(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    scenes_text = "não disponível"
    target_text = "não registrada"
    if script_view is not None and script_view.has_script:
        scenes_text = str(script_view.scene_count)
        if script_view.target_seconds is not None:
            target_text = legacy._duration_text(script_view.target_seconds) or "não registrada"

    details = (
        '<div class="card"><h3>Este vídeo</h3>'
        + _kv("Cenas no roteiro", e(scenes_text))
        + _kv("Duração-alvo", e(target_text))
        + _kv("Duração real", "não medida")
        + "</div>"
    )

    shortcuts = "".join(
        f'<a class="btn" href="{area_href(video_id, area_id)}">{e(label)}</a>'
        for area_id, label in VIDEO_AREAS
        if area_id != "visao-geral"
    )
    shortcuts_card = (
        '<div class="card"><h3>Ajustes deste vídeo</h3>'
        f'<div class="pilha">{shortcuts}</div></div>'
    )

    title, reason, href, cta = _next_step(view, video_id)
    next_card = (
        '<div class="card"><h2>Próximo passo</h2>'
        f"<p><strong>{e(title)}</strong></p>"
        f"<p>{e(reason)}</p>"
        f'<p><a class="btn btn-primario" href="{href}">{e(cta)}</a></p>'
        "</div>"
    )

    stage_label = legacy.STAGE_LABELS.get(view.stage, view.stage.value)
    run_line = ""
    if view.latest_run is not None:
        run_state = legacy._RUN_STATE_LABELS.get(view.latest_run.state, view.latest_run.state)
        run_line = f'<p class="micro">Execução mais recente: {e(run_state)}.</p>'
    production_card = (
        '<div class="card"><h3>Produção</h3>'
        f"<p>{e(stage_label)}</p>{run_line}"
        f'<p><a class="btn" href="{area_href(video_id, "producao")}">Ver etapas e controles</a></p>'
        "</div>"
    )

    measured_note = (
        '<p class="aviso">A <strong>duração real não é medida</strong>: o Studio mostra a meta do '
        "roteiro, nunca um tempo que não foi medido.</p>"
    )
    history_card = _revision_history_card(script_view, video_id)
    return (
        '<div class="grade-video"><div>'
        + details + measured_note + shortcuts_card + history_card
        + "</div><div>"
        + next_card + production_card
        + "</div></div>"
    )


def _area_fontes(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    # W1.7: a honestidade é texto **visível** (não `sr-only`) e vem antes do cartão reutilizado,
    # para o operador não confundir "registrado" com "extraído" nem com "verificado".
    honesty = (
        '<p class="aviso" id="fontes-honestidade">'
        "<strong>URL registrada não é fonte extraída nem verificada.</strong> "
        "A URL sozinha é só uma referência; o texto só passa a valer quando você cola o conteúdo, "
        "e nada aqui é fact-checkado automaticamente."
        "</p>"
    )
    roteiro_link = (
        f'<p><a class="btn" href="/studio/videos/{e(video_id)}/roteiro">'
        "Abrir roteiro e estrutura</a></p>"
    )
    return honesty + legacy._video_sources_card(view) + roteiro_link


def _area_narracao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    style = _effective_style(style_view)
    voice_model = _group(dict(style.params) if style is not None else {}, "voice").get("model")
    style_name = style.name if style is not None else "nenhum estilo efetivo"

    target_text = "não registrada"
    if script_view is not None and script_view.has_script and script_view.target_seconds is not None:
        target_text = legacy._duration_text(script_view.target_seconds) or "não registrada"

    identidade = (
        '<div class="card"><h3>Narração do vídeo</h3>'
        "<p class=\"muted\">Somente leitura: esta área mostra a voz e o ritmo efetivos sem gerar "
        "áudio.</p>"
        + _kv("Voz efetiva", e(voice_model) if voice_model
              else "não declarada pelo estilo (vale a voz do projeto ou do motor)")
        + _kv("Estilo efetivo", e(style_name))
        + _kv("Provider de voz", "não informado nesta leitura")
        + _kv("Duração-alvo", e(target_text))
        + _kv("Duração medida", "indisponível")
        + "</div>"
    )

    if script_view is not None and script_view.has_script and script_view.chapters:
        items = "".join(
            f'<li><span class="cena-n" aria-hidden="true">{index + 1}</span><div>'
            f"<strong>{e(chapter.title)}</strong>"
            f'<small class="micro">{chapter.scene_count} cena(s) · '
            f'{e(legacy._duration_text(chapter.estimated_seconds) or "sem estimativa")}</small>'
            "</div></li>"
            for index, chapter in enumerate(script_view.chapters)
        )
        trechos = f'<ul class="cenas">{items}</ul>'
    else:
        trechos = '<p class="vazio">Nenhum trecho de roteiro registrado para este vídeo.</p>'
    trechos_card = f'<div class="card"><h3>Trechos por cena</h3>{trechos}</div>'

    honest_wave = (
        '<p class="aviso"><strong>Áudio e duração medida indisponíveis.</strong> Não há player nem '
        "medição nesta tela; nada de onda ou tempo inventados.</p>"
    )
    return identidade + trechos_card + honest_wave


def _area_cenas(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    count_text = "não disponível"
    if script_view is not None and script_view.has_script:
        count_text = str(script_view.scene_count)
    return (
        '<div class="card"><h3>Cenas e mídias</h3>'
        f'<p class="muted">Número de cenas no roteiro: {e(count_text)}.</p>'
        '<p class="vazio">A leitura de cenas por mídia (texto, legenda e asset de cada cena) '
        "ainda não está disponível nesta tela.</p>"
        '<p class="micro">A edição por cena — trocar a mídia, ajustar a legenda — entra na onda 4. '
        "Até lá, o roteiro é a fonte de verdade.</p>"
        f'<p><a class="btn" href="/studio/videos/{e(video_id)}/roteiro">'
        "Abrir roteiro e estrutura</a></p>"
        "</div>"
    )


_TRACK_KIND_LABELS = {"visual": "visual", "narration": "narração", "subtitle": "legenda"}


def _seconds_text(seconds: float) -> str:
    """Segundos legíveis da janela do shot (a fonte é o tick do plano, não um chute)."""
    return f"{seconds:.2f} s"


def _window_text(shot) -> str:
    return f"{_seconds_text(shot.start_seconds)} – {_seconds_text(shot.end_seconds)}"


def _track_content_text(track) -> str:
    """O que a track realmente carrega: shots visuais, cues de narração/legenda, ou nada."""
    if track.shots:
        return f"{len(track.shots)} shot(s)"
    if track.cue_count:
        return f"{track.cue_count} cue(s)"
    return "vazia"


def _composition_plan_card(composition_view) -> str:
    """Leitura do plano persistido (W2.3): revisão, tracks e shots — só o que o plano tem."""
    if composition_view is None:
        return (
            '<div class="card"><h3>Plano de composição</h3>'
            '<p class="vazio">Sem plano de composição ainda. O plano aparece aqui depois que o '
            "render compila a primeira revisão; até lá não há timeline ilustrativa.</p>"
            "</div>"
        )

    track_rows = "".join(
        "<tr>"
        f"<td>{e(track.track_id)}</td>"
        f"<td>{e(_TRACK_KIND_LABELS.get(track.kind, track.kind))}</td>"
        f"<td>{e(track.role)}</td>"
        f"<td>{e(_track_content_text(track))}</td>"
        f"<td>{'sim' if track.active else 'não'}</td>"
        "</tr>"
        for track in composition_view.tracks
    )
    shot_rows = "".join(
        "<tr>"
        f"<td>{e(shot.scene_id)}</td>"
        f"<td>{e(shot.role)}</td>"
        f"<td>{shot.z_index}</td>"
        f"<td>{e(_window_text(shot))}</td>"
        f"<td>{'sim' if shot.active else 'não'}</td>"
        "</tr>"
        for shot in composition_view.shots
    )
    if shot_rows:
        shots_table = (
            '<h3>Shots</h3><table class="tabela-kv">'
            '<caption class="sr-only">Shots do plano</caption>'
            "<thead><tr>"
            '<th scope="col">Cena</th><th scope="col">Papel</th><th scope="col">z-index</th>'
            '<th scope="col">Janela</th><th scope="col">Ativo</th>'
            "</tr></thead>"
            f"<tbody>{shot_rows}</tbody></table>"
        )
    else:
        shots_table = '<p class="vazio">O plano não declara shots visuais.</p>'

    return (
        '<div class="card"><h3>Plano de composição</h3>'
        f'<p class="micro">Revisão <strong>{composition_view.revision}</strong> · '
        f"{len(composition_view.tracks)} track(s) · {len(composition_view.shots)} shot(s) — "
        "o que o plano persistido tem.</p>"
        '<table class="tabela-kv"><caption class="sr-only">Tracks do plano</caption>'
        "<thead><tr>"
        '<th scope="col">Track</th><th scope="col">Tipo</th><th scope="col">Papel</th>'
        '<th scope="col">Conteúdo</th><th scope="col">Ativa</th>'
        "</tr></thead>"
        f"<tbody>{track_rows}</tbody></table>"
        f"{shots_table}"
        '<p class="aviso">Somente leitura: esta área mostra o plano persistido. A edição por cena '
        "(trocar a mídia, ajustar a janela) ainda não existe aqui.</p>"
        "</div>"
    )


def _area_composicao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    style = _effective_style(style_view)
    if style is None:
        head = ('<p class="aviso">Nenhum estilo efetivo resolvido nesta leitura: os parâmetros de '
                "composição não estão disponíveis.</p>")
        params: dict = {}
    else:
        head = f'<p class="micro">Estilo efetivo: <strong>{e(style.name)}</strong></p>'
        params = dict(style.params)

    caption = _group(params, "caption")
    palette = _group(params, "palette")
    music = _group(params, "music")
    transition = _group(params, "transition")
    motion = params.get("motion")

    caption_bits = []
    if "font_size" in caption:
        caption_bits.append(f"fonte {caption['font_size']}")
    if "bottom" in caption:
        caption_bits.append(f"base {caption['bottom']}")
    caption_text = " · ".join(caption_bits) if caption_bits else "padrão do motor"

    palette_bits = [f"{key}={palette[key]}" for key in ("caption_text", "caption_box", "accent")
                    if key in palette]
    palette_text = " · ".join(palette_bits) if palette_bits else "padrão do motor"

    if isinstance(motion, (list, tuple)) and motion:
        motion_text = ", ".join(str(item) for item in motion)
    else:
        motion_text = "sem ciclo declarado (Ken Burns do motor)"

    music_bits = []
    if "bpm" in music:
        music_bits.append(f"bpm {music['bpm']}")
    if "seed" in music:
        music_bits.append(f"seed {music['seed']}")
    music_text = " · ".join(music_bits) if music_bits else "padrão do plano (bpm 122 · seed 7)"

    if "kind" in transition:
        if transition["kind"] == "fade":
            transition_text = f"fade · {transition.get('duration_ticks', 0)} ticks"
        else:
            transition_text = "none (sem duração)"
    else:
        transition_text = "não declarada"

    rows = (
        _kv("Legenda", e(caption_text))
        + _kv("Paleta", e(palette_text))
        + _kv("Movimento", e(motion_text))
        + _kv("Música", e(music_text))
        + _kv("Transição", e(transition_text))
    )

    notes = (
        '<p class="aviso"><strong>Resolução e FPS são fixos hoje</strong>: quem decide é o motor de '
        "render; esta tela não os configura.</p>"
        '<p class="aviso"><strong>A transição é apenas declarada e ainda não é consumida pelo '
        "compilador</strong> (renderer/app/studio/domain/visual_style.py:502-506): ela fica "
        "carregada no estilo, sem fingir suporte.</p>"
    )
    plan_card = _composition_plan_card(composition_view)
    return (plan_card
            + f'<div class="card"><h2>Composição do vídeo</h2>{head}{rows}</div>'
            + notes)


def _area_qualidade(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    qa = getattr(view.video, "qa_report", None)
    if qa is not None:
        publishable = bool(getattr(qa, "is_publishable", False))
        coverage = getattr(qa, "coverage", None)
        coverage_status = getattr(coverage, "status", "não informada")
        findings = list(getattr(qa, "findings", ()) or ())
        qa_html = (
            '<div class="card"><h3>Relatório de QA do render</h3>'
            + _kv("Publicável", "sim" if publishable else "não")
            + _kv("Cobertura", e(coverage_status))
            + _kv("Achados", str(len(findings)))
            + "</div>"
        )
    else:
        qa_html = ('<div class="card"><h3>Relatório de QA do render</h3>'
                   '<p class="aviso">Relatório de QA do render não disponível nesta leitura.</p>'
                   "</div>")

    if view.stage == Stage.AWAITING_APPROVAL:
        approval_text = "Aguardando aprovação desta versão."
    elif view.stage in (Stage.APPROVED, Stage.COMPLETED):
        approval_text = "Versão aprovada."
    else:
        approval_text = "Ainda não chegou à aprovação."
    approval_rows = _kv("Aprovação", e(approval_text))
    if script_view is not None and script_view.has_script:
        approval_rows += _kv("Aprovação do roteiro",
                             "aprovada" if script_view.approved else "não registrada")
    approval_card = f'<div class="card"><h3>Aprovação desta versão</h3>{approval_rows}</div>'

    if view.stage in _PREVIEW_STAGES:
        preview_html = (f'<p><a class="btn btn-primario" '
                        f'href="/studio/videos/{e(video_id)}/preview">Abrir prévia e aprovar</a></p>')
    else:
        preview_html = ('<p class="aviso">Prévia e aprovação ficam disponíveis após a renderização. '
                        "A decisão de aprovação vive na página de prévia (com CSP própria).</p>")
    semantic = (
        '<p class="aviso"><strong>Avaliação semântica não verificada:</strong> a correspondência '
        "entre roteiro e imagem depende de provider real e não é verificada aqui.</p>"
    )
    return qa_html + approval_card + preview_html + semantic


def _area_publicacao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None, preview=None) -> str:
    if view.publication is not None:
        pub = view.publication
        status_value = getattr(pub.status, "value", str(pub.status))
        rows = _kv("Situação", e(status_value)) + _kv("Tentativa", str(pub.attempt))
        if pub.error:
            rows += _kv("Erro registrado", e(pub.error))
        summary = f'<div class="card"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    else:
        summary = ('<div class="card"><h3>Publicação</h3>'
                   '<p class="muted">Nenhuma publicação registrada para este vídeo.</p></div>')

    # W5.1 (PUB-01): o formulário de aprovação vive aqui agora. Quando a prévia está disponível,
    # o mesmo bloco da página de prévia é renderizado (sem duplicar HTML); a prévia completa
    # continua acessível pelo link. Mudar destino/metadados torna a intenção obsoleta no servidor
    # (A19/A37) e exige uma confirmação nova.
    if preview is not None:
        decision = approval_form.render_approval_decision(preview)
        reviewable = preview.video.status in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED)
    else:
        decision = ""
        reviewable = view.stage in _PREVIEW_STAGES
    heading = ('<p class="aviso" id="publicacao-intencao"><strong>A confirmação de publicação vive aqui.</strong> '
               "Trocar o destino do YouTube ou título/descrição/tags/visibilidade depois de aprovar "
               "invalida a intenção anterior: será preciso confirmar de novo (A19).</p>")

    if reviewable:
        preview_html = (f'<p><a class="btn" href="/studio/videos/{e(video_id)}/preview">'
                        "Abrir prévia completa</a></p>")
    else:
        preview_html = ('<p class="aviso">A prévia fica disponível após a renderização.</p>')

    destination = (
        '<p class="aviso"><strong>Sem destino YouTube conectado, a publicação é recusada.</strong> '
        "O canal precisa de um destino e de uma autorização vigente — o gate falha fechado "
        "(renderer/app/studio/domain/channel.py). Conecte o canal em Canais → Conexão antes de "
        "publicar.</p>"
    )
    return summary + heading + decision + preview_html + destination


def _area_producao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    # O cartão real de produção já traz iniciar/retomar e o link "Abrir execução" quando há run.
    return legacy._video_run_card(view)


_AREA_RENDERERS = {
    "visao-geral": _area_visao_geral,
    "fontes": _area_fontes,
    "narracao": _area_narracao,
    "cenas": _area_cenas,
    "composicao": _area_composicao,
    "qualidade": _area_qualidade,
    "publicacao": _area_publicacao,
    "producao": _area_producao,
}


def _content(view, area: str, *, style_view, script_view, video_id, composition_view=None, preview=None) -> str:
    if area == "publicacao":
        return _area_publicacao(view, style_view=style_view, script_view=script_view,
                                video_id=video_id, preview=preview)
    return _AREA_RENDERERS[area](
        view, style_view=style_view, script_view=script_view, video_id=video_id,
        composition_view=composition_view,
    )


PAGE_JS = """
(function () {
  var runFeedback = document.getElementById('video-run-feedback');

  function wireStart(button) {
    button.addEventListener('click', async function () {
      var videoId = button.getAttribute('data-video-id') || '';
      button.disabled = true;
      button.classList.add('carregando');
      if (window.StudioLoading) window.StudioLoading.start();
      if (runFeedback) runFeedback.textContent = 'Iniciando a produção...';
      try {
        var key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/production-runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
          body: JSON.stringify({})
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok && data.run_id) {
          if (runFeedback) runFeedback.textContent = 'Produção iniciada. Abrindo a execução...';
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) +
            '/production-runs/' + encodeURIComponent(data.run_id);
        } else {
          if (runFeedback) runFeedback.textContent = 'Não foi possível iniciar: '
            + (typeof data.detail === 'string' ? data.detail : 'resposta inválida do servidor.');
          button.disabled = false;
          button.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
        }
      } catch (error) {
        if (runFeedback) runFeedback.textContent = 'Falha de rede ao iniciar a produção. Tente novamente.';
        button.disabled = false;
        button.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
      }
    });
  }
  document.querySelectorAll('#btn-start-production, #btn-new-production').forEach(wireStart);

  var retryBtn = document.getElementById('btn-retry-production');
  if (retryBtn) {
    retryBtn.addEventListener('click', async function () {
      var videoId = retryBtn.getAttribute('data-video-id') || '';
      var runId = retryBtn.getAttribute('data-run-id') || '';
      retryBtn.disabled = true;
      retryBtn.classList.add('carregando');
      if (window.StudioLoading) window.StudioLoading.start();
      if (runFeedback) runFeedback.textContent = 'Retomando a produção...';
      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) +
          '/production-runs/' + encodeURIComponent(runId) + '/retry', { method: 'POST' });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (runFeedback) runFeedback.textContent = 'Produção retomada. Abrindo a execução...';
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) +
            '/production-runs/' + encodeURIComponent(runId);
        } else {
          if (runFeedback) runFeedback.textContent = 'Não foi possível retomar: '
            + (typeof data.detail === 'string' ? data.detail : 'o estado atual não permite nova tentativa.');
          retryBtn.disabled = false;
          retryBtn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
        }
      } catch (error) {
        if (runFeedback) runFeedback.textContent = 'Falha de rede ao retomar a produção. Tente novamente.';
        retryBtn.disabled = false;
        retryBtn.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
      }
    });
  }

  var sourcesForm = document.getElementById('video-sources-form');
  if (sourcesForm) {
    sourcesForm.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var feedback = document.getElementById('video-sources-feedback');
      var button = document.getElementById('btn-add-source');
      var videoId = sourcesForm.getAttribute('data-video-id') || '';
      var urlInput = document.getElementById('source-url');
      var textInput = document.getElementById('source-text');
      var url = urlInput ? urlInput.value.trim() : '';
      var text = textInput ? textInput.value : '';
      if (!url) { if (feedback) feedback.textContent = 'Informe a URL da fonte.'; return; }
      if (button) { button.disabled = true; button.classList.add('carregando'); }
      if (window.StudioLoading) window.StudioLoading.start();
      if (feedback) feedback.textContent = 'Registrando a fonte...';
      try {
        var payload = { url: url };
        if (text.trim()) payload.text = text;
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (feedback) feedback.textContent = 'Fonte registrada. Atualizando...';
          setTimeout(function () { location.reload(); }, 600);
        } else {
          if (feedback) feedback.textContent = 'Não foi possível registrar a fonte: '
            + (typeof data.detail === 'string' ? data.detail : 'verifique a URL e tente novamente.');
          if (button) { button.disabled = false; button.classList.remove('carregando'); }
          if (window.StudioLoading) window.StudioLoading.done();
        }
      } catch (error) {
        if (feedback) feedback.textContent = 'Falha de rede ao registrar a fonte. Tente novamente.';
        if (button) { button.disabled = false; button.classList.remove('carregando'); }
        if (window.StudioLoading) window.StudioLoading.done();
      }
    });
  }

  document.querySelectorAll('.restore-revision').forEach(function (button) {
    button.addEventListener('click', async function () {
      var feedback = document.getElementById('revision-feedback');
      var videoId = button.getAttribute('data-video-id') || '';
      var version = button.getAttribute('data-version') || '';
      var expected = button.getAttribute('data-expected-version') || '';
      var key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      button.disabled = true;
      button.classList.add('carregando');
      if (feedback) feedback.textContent = 'Restaurando a revisão ' + version + '...';
      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) +
          '/script/revisions/' + encodeURIComponent(version) + '/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_version: Number(expected), idempotency_key: key })
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (feedback) feedback.textContent = 'Revisão restaurada como nova versão. Atualizando...';
          setTimeout(function () { location.reload(); }, 500);
        } else {
          if (feedback) feedback.textContent = typeof data.detail === 'string'
            ? data.detail : 'Falha ao restaurar a revisão.';
          button.disabled = false;
          button.classList.remove('carregando');
        }
      } catch (error) {
        if (feedback) feedback.textContent = 'Falha de rede ao restaurar a revisão. Tente novamente.';
        button.disabled = false;
        button.classList.remove('carregando');
      }
    });
  });

  var flagged = new WeakSet();
  var linkError = function (el, shown) {
    var errorId = el.dataset ? el.dataset.error : null;
    if (!errorId) return;
    var ids = (el.getAttribute('aria-describedby') || '').split(/\\s+/).filter(function (id) { return id && id !== errorId; });
    if (shown) ids.push(errorId);
    if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
    else el.removeAttribute('aria-describedby');
  };
  var syncAria = function (el) {
    if (!el.matches || !el.matches('input, select, textarea')) return;
    var invalid = el.matches(':user-invalid');
    if (invalid) {
      el.setAttribute('aria-invalid', 'true');
      linkError(el, true);
      flagged.add(el);
    } else if (flagged.has(el) || el.getAttribute('aria-invalid') !== 'true') {
      el.setAttribute('aria-invalid', 'false');
      linkError(el, false);
      flagged.delete(el);
    }
  };
  document.querySelectorAll('input, select, textarea').forEach(function (el) { syncAria(el); });
  document.addEventListener('blur', function (ev) { syncAria(ev.target); }, true);
  document.addEventListener('input', function (ev) { if (ev.target.hasAttribute && ev.target.hasAttribute('aria-invalid')) syncAria(ev.target); });
  document.addEventListener('change', function (ev) { syncAria(ev.target); }, true);
  document.addEventListener('invalid', function (ev) { syncAria(ev.target); }, true);
})();
"""


def render_video_workspace(view, area, *, style_view=None, script_view=None,
                           composition_view=None, preview=None, projects=(), project_id: str = "",
                           channel_name: str = "") -> tuple[str, dict[str, str]]:
    """Workspace do vídeo: uma área por rota, reusando os blocos reais do detalhe.

    O que a rota precisa passar:
    - `view`: o `VideoDetailView` já montado (`BuildPanel.detail(video_id)`);
    - `area`: o segmento da URL (`visao-geral`…`producao`); desconhecido cai em `visao-geral`;
    - `style_view`: o `VideoStyleView` do vídeo (opcional) — dá o estilo/voz efetivos;
    - `script_view`: o `ScriptPageView` do vídeo (opcional) — dá cenas/trechos e aprovação do roteiro;
    - `composition_view`: a `CompositionView` (W2.3, opcional) — o plano persistido em leitura;
    - `preview`: o `Preview` da publicação (opcional, W5.1) — só a área Publicação usa;
    - `projects`/`project_id`/`channel_name`: contexto da casca (seletor de canal, crumb).
    """
    nonce = secrets.token_urlsafe(16)
    active_area = _normalize_area(area)
    video_id = view.video.id
    title = view.video.title or view.video.topic
    stage_label = legacy.STAGE_LABELS.get(view.stage, view.stage.value)

    channel_crumb = f" / {e(channel_name)}" if channel_name else ""
    body_html = f"""      <section class="pagina" id="pagina-video-workspace" aria-labelledby="t-video">
        <p class="crumb"><a href="/studio/panel/videos">← Vídeos</a>{channel_crumb}</p>
        <div class="cab-video">
          <div>
            <p class="eyebrow">ESPAÇO DO VÍDEO</p>
            <h1 class="h1" id="t-video">{e(title)}</h1>
            <p class="lead" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              {legacy._state_badge(view.stage)}
              <span class="pill pill-{e(view.stage.value)}">{e(stage_label)}</span>
              <span class="micro">Custo do vídeo: {legacy._cost_html(view.cost_text)}</span>
            </p>
          </div>
        </div>
        {_video_area_nav(video_id, active_area)}
        {_content(view, active_area, style_view=style_view, script_view=script_view, video_id=video_id,
                  composition_view=composition_view,
                  preview=preview if active_area == "publicacao" else None)}
      </section>"""

    crumb = f"{channel_name} / {title}" if channel_name else f"Vídeos / {title}"
    # O JS do formulário de aprovação só entra na área Publicação (W5.1); o resto não mudou.
    page_js = PAGE_JS + (approval_form.APPROVAL_JS if active_area == "publicacao" else "")
    html = shell_v3.render_document(
        title="Faceless Studio — Vídeo",
        active="videos",
        crumb=crumb,
        body_html=body_html,
        nonce=nonce,
        projects=list(projects),
        project_id=project_id,
        cost_note="",
        page_js=page_js,
    )
    return html, legacy._headers(nonce)
