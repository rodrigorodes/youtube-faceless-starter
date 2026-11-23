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

import json
import secrets
from datetime import datetime
from html import escape as e

from ..application.panel import VideoDetailView
from ..domain.contracts import Video, VideoFormat, VideoStatus
from ..domain.panel import Stage, classify
from . import approval_form
from . import panel as legacy
from . import shell_v3

# Ordem e rótulos do protótipo (`VIDEO_TABS`). A fonte única é `panel_video_nav` (a página legada
# do vídeo também usa a nav, sem import circular). Os nomes seguem reexportados daqui.
from .panel_video_nav import (ALL_AREA_IDS, ALL_VALID_AREAS, AREA_IDS, AREA_LABELS, DEFAULT_AREA, VIDEO_AREAS, area_href,
                              normalize_area, normalize_area as _normalize_area,
                              video_area_nav, video_area_nav as _video_area_nav)

# A prévia (e a aprovação) só existe depois que há artefato renderizado — mesma leitura do
# detalhe antigo. Antes disso, esta tela explica em vez de oferecer um link que não levaria a nada.
_PREVIEW_STAGES = (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED)

# Um run vivo é continuado pela execução, não por uma produção nova.
_LIVE_RUN_STATES = ("CREATED", "RUNNING", "WAITING_HUMAN", "PAUSED")


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


class WorkspaceResult(tuple):
    """Resultado de render_video_workspace compatível com (html, headers) e com 'text in res'."""

    def __contains__(self, item: object) -> bool:
        return item in self[0]

    def __str__(self) -> str:
        return self[0]


def _area_cenas(view, *, style_view=None, script_view=None, video_id: str, composition_view=None,
                scenes=None, script=None) -> str:
    if scenes is None and script is None:
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

    # Modo Storyboard V3 (com cenas fornecidas ou lista explícita)
    raw_scenes = scenes
    if raw_scenes is None and script is not None:
        raw_scenes = getattr(script, "scenes", None)
        if raw_scenes is None and isinstance(script, dict):
            raw_scenes = script.get("scenes")
    if raw_scenes is None:
        raw_scenes = []

    normalized_scenes = []
    for idx, s in enumerate(raw_scenes):
        s_id = getattr(s, "id", None) or (s.get("id") if isinstance(s, dict) else f"s{idx + 1}")
        s_idx = getattr(s, "idx", None) if getattr(s, "idx", None) is not None else (s.get("idx") if isinstance(s, dict) else idx)
        s_narration = getattr(s, "narration", None) or getattr(s, "text", None) or (s.get("narration") or s.get("text") if isinstance(s, dict) else "")
        s_caption = getattr(s, "caption", "") or (s.get("caption", "") if isinstance(s, dict) else "")
        s_label = getattr(s, "label", None) or getattr(s, "title", None) or (s.get("label") or s.get("title") if isinstance(s, dict) else f"Cena {idx + 1}")
        s_prompt = getattr(s, "image_prompt", None) or getattr(s, "prompt", None) or (s.get("image_prompt") or s.get("prompt") if isinstance(s, dict) else "")
        s_dur = getattr(s, "duration_s", None) or getattr(s, "duration", None) or (s.get("duration_s") or s.get("duration") if isinstance(s, dict) else None)
        s_asset = getattr(s, "asset_id", None) or (s.get("asset_id") if isinstance(s, dict) else None)
        s_audio = getattr(s, "audio_state", None) or (s.get("audio_state") if isinstance(s, dict) else ("ok" if s_dur else "none"))
        s_hist = getattr(s, "audio_history", None) or getattr(s, "voice_history", None) or (s.get("audio_history") if isinstance(s, dict) else None) or (s.get("voice_history") if isinstance(s, dict) else [])
        normalized_hist = []
        for h in (s_hist or []):
            normalized_hist.append({
                "version": getattr(h, "version", None) or (h.get("version") if isinstance(h, dict) else 1),
                "text": getattr(h, "text", None) or getattr(h, "narration", None) or (h.get("text") or h.get("narration") if isinstance(h, dict) else ""),
                "duration_s": getattr(h, "duration_s", None) or (h.get("duration_s") if isinstance(h, dict) else None),
            })

        normalized_scenes.append({
            "id": str(s_id or f"s{idx+1}"),
            "idx": int(s_idx if s_idx is not None else idx),
            "narration": str(s_narration or ""),
            "caption": str(s_caption or ""),
            "label": str(s_label or f"Cena {idx + 1}"),
            "image_prompt": str(s_prompt or ""),
            "duration_s": float(s_dur) if s_dur is not None else None,
            "asset_id": str(s_asset) if s_asset else None,
            "audio_state": str(s_audio or "none"),
            "audio_history": normalized_hist,
        })

    pills_html = []
    for s in normalized_scenes:
        i = s["idx"]
        label = s["label"] or f"Cena {i + 1}"
        is_first = (i == 0)
        pressed = "true" if is_first else "false"
        cls = "btn btn-sm btn-cena-pill active btn-primario" if is_first else "btn btn-sm btn-cena-pill btn-ghost"
        pills_html.append(
            f'<button type="button" class="{cls}" data-scene-idx="{i}" aria-pressed="{pressed}">'
            f'{i + 1} · {e(label)}'
            f'</button>'
        )
    if not pills_html:
        pills_html.append('<span class="pill">Nenhuma cena registrada</span>')

    header_card = (
        '<div class="card" id="storyboard-v3-header" style="margin-bottom:16px;">'
        '<div class="spread" style="align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">'
        '<div>'
        '<h2 style="margin:0;">Cenas e mídias · Storyboard</h2>'
        '<p class="micro" style="margin:2px 0 0 0;">Edite cada cena individualmente, troque mídia e acompanhe a narração.</p>'
        '</div>'
        '<div class="row" style="display:flex;gap:8px;align-items:center;">'
        '<button type="button" class="btn btn-ghost btn-sm" id="btn-undo-cenas" title="Desfazer alteração" disabled>↶ Desfazer</button>'
        '<button type="button" class="btn btn-ghost btn-sm" id="btn-redo-cenas" title="Refazer alteração" disabled>↷ Refazer</button>'
        '</div>'
        '</div>'
        f'<div class="seletor-cenas" id="seletor-cenas" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">'
        + "".join(pills_html)
        + '</div></div>'
    )

    if normalized_scenes:
        foco = normalized_scenes[0]
        total = len(normalized_scenes)
        f_idx = foco["idx"]
        f_label = foco["label"] or f"Cena {f_idx + 1}"
        f_dur = f"{foco['duration_s']:.1f} s" if foco["duration_s"] is not None else "sem duração medida"
        f_audio = foco["audio_state"]
        f_audio_badge = f'<span class="pill pill-{e(f_audio)} badge-audio" id="foco-audio-badge">Áudio: {e(f_audio)}</span>'
        f_asset_id = foco["asset_id"]
        has_img = "block" if f_asset_id else "none"
        no_img = "none" if f_asset_id else "flex"

        focused_card = (
            f'<div class="card cena-em-foco" id="cena-em-foco" data-active-idx="{f_idx}" data-video-id="{e(video_id)}">'
            '<div class="spread" style="align-items:center;margin-bottom:14px;border-bottom:1px solid var(--linha);padding-bottom:10px;">'
            '<div>'
            f'<h3 id="foco-titulo" style="margin:0;">Cena {f_idx + 1} de {total} · {e(f_label)}</h3>'
            f'<span class="micro" id="foco-duracao">{e(f_dur)}</span>'
            '</div>'
            '<div class="row" style="display:flex;gap:8px;align-items:center;">'
            f'{f_audio_badge}'
            '</div>'
            '</div>'
            '<div class="grade-cena-foco" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">'
            '<div class="col-visual">'
            '<label><strong>Mídia da cena</strong></label>'
            '<div class="cena-midia-preview" id="foco-midia-preview" style="background:var(--superficie-2);border-radius:var(--raio);min-height:160px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;margin-bottom:8px;border:1px solid var(--linha);">'
            f'<img id="foco-midia-img" src="/studio/videos/{e(video_id)}/scenes/{f_idx}/asset" alt="Preview da cena {f_idx + 1}" style="max-width:100%;max-height:220px;object-fit:cover;display:{has_img};">'
            f'<div id="foco-midia-placeholder" style="display:{no_img};align-items:center;justify-content:center;flex-direction:column;gap:6px;padding:16px;text-align:center;">'
            '<span style="font-size:36px;" aria-hidden="true">🎞️</span>'
            '<span class="micro">Arte gerada por IA / Stock Pexels</span>'
            '</div>'
            '</div>'
            '<button type="button" class="btn btn-sm btn-ghost" id="btn-trocar-midia" data-action="trocar-midia" style="width:100%;">Trocar mídia</button>'
            '</div>'
            '<div class="col-narrativa" style="display:flex;flex-direction:column;gap:10px;">'
            '<div>'
            '<label for="cena-narration"><strong>Narração da cena</strong></label>'
            f'<textarea id="cena-narration" class="campo" rows="4" style="width:100%;resize:vertical;" placeholder="Texto narrado da cena...">{e(foco["narration"])}</textarea>'
            '</div>'
            '<div>'
            '<label for="cena-prompt"><strong>Prompt visual da cena</strong></label>'
            f'<textarea id="cena-prompt" class="campo" rows="2" style="width:100%;resize:vertical;" placeholder="Descrição visual para geração de imagem...">{e(foco["image_prompt"])}</textarea>'
            '</div>'
            '<div class="row" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;">'
            '<button type="button" class="btn btn-sm btn-primario" id="btn-regenerar-voz" data-action="regenerar-voz">Regenerar voz</button>'
            '<button type="button" class="btn btn-sm btn-ghost" id="btn-historico-voz" data-action="historico-voz">Histórico da voz</button>'
            '</div>'
            '</div>'
            '</div>'
            '</div>'
        )
    else:
        focused_card = (
            f'<div class="card cena-em-foco" id="cena-em-foco" data-active-idx="0" data-video-id="{e(video_id)}">'
            '<div class="spread" style="align-items:center;margin-bottom:14px;border-bottom:1px solid var(--linha);padding-bottom:10px;">'
            '<div>'
            '<h3 id="foco-titulo" style="margin:0;">Nenhuma cena no roteiro</h3>'
            '<span class="micro" id="foco-duracao">0.0 s</span>'
            '</div>'
            '<div class="row" style="display:flex;gap:8px;align-items:center;">'
            '<span class="pill pill-none badge-audio" id="foco-audio-badge">Áudio: none</span>'
            '</div>'
            '</div>'
            '<p class="vazio">Gere ou adicione cenas no roteiro para editar narração e mídia.</p>'
            '<div class="row" style="display:flex;gap:8px;margin-top:12px;">'
            '<button type="button" class="btn btn-sm" id="btn-trocar-midia" disabled>Trocar mídia</button>'
            '<button type="button" class="btn btn-sm btn-primario" id="btn-regenerar-voz" disabled>Regenerar voz</button>'
            '<button type="button" class="btn btn-sm btn-ghost" id="btn-historico-voz" disabled>Histórico da voz</button>'
            '</div>'
            '</div>'
        )

    script_items = []
    for s in normalized_scenes:
        i = s["idx"]
        label = s["label"] or f"Cena {i + 1}"
        dur_str = f" · {s['duration_s']:.1f} s" if s["duration_s"] is not None else ""
        script_items.append(
            f'<li style="padding:8px 0;border-bottom:1px solid var(--linha);">'
            f'<p style="margin:0 0 4px 0;"><strong>{i + 1}. {e(label)}</strong><span class="micro">{e(dur_str)}</span></p>'
            f'<p style="margin:0 0 4px 0;">{e(s["narration"])}</p>'
            f'<p class="micro muted" style="margin:0;">Prompt: {e(s["image_prompt"])}</p>'
            f'</li>'
        )

    if not script_items:
        script_content = '<p class="vazio">Nenhuma cena registrada no roteiro.</p>'
    else:
        script_content = f'<ul class="pilha" style="gap:8px;list-style:none;padding:0;margin:0;">{"".join(script_items)}</ul>'

    full_script_details = (
        f'<details class="diag" id="detalhes-roteiro-completo" style="margin-top:16px;">'
        f'<summary>Ver roteiro completo · {len(normalized_scenes)} cenas</summary>'
        f'<div class="roteiro-completo-conteudo" style="padding-top:12px;">'
        f'{script_content}'
        f'</div>'
        f'</details>'
    )

    scenes_json = json.dumps(normalized_scenes, ensure_ascii=False).replace("</", "<\\/")
    script_data_tag = f'<script type="application/json" id="storyboard-scenes-data">{scenes_json}</script>'

    dialogs = (
        '<dialog class="modal" id="dialog-audio-history" aria-labelledby="t-audio-history">'
        '<div class="modal-card">'
        '<div class="spread" style="align-items:center;margin-bottom:10px;">'
        '<h3 id="t-audio-history" style="margin:0;">Histórico da voz — Cena <span id="modal-audio-scene-num">1</span></h3>'
        '<button type="button" class="btn btn-ghost btn-sm modal-close" aria-label="Fechar">&times;</button>'
        '</div>'
        '<p class="micro">Versões anteriores geradas para a narração desta cena. Você pode ouvir e restaurar qualquer versão.</p>'
        '<ul class="pilha" id="dialog-audio-history-list" style="margin:12px 0;">'
        '<li class="vazio">Nenhuma versão anterior gravada para esta cena.</li>'
        '</ul>'
        '<div id="audio-history-feedback" class="form-feedback" role="status" style="margin-top:8px;"></div>'
        '<div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;">'
        '<button type="button" class="btn btn-sm modal-close">Fechar</button>'
        '</div>'
        '</div>'
        '</dialog>'
        '<dialog class="modal" id="dialog-trocar-midia" aria-labelledby="t-trocar-midia">'
        '<div class="modal-card">'
        '<div class="spread" style="align-items:center;margin-bottom:10px;">'
        '<h3 id="t-trocar-midia" style="margin:0;">Trocar mídia — Cena <span id="modal-media-scene-num">1</span></h3>'
        '<button type="button" class="btn btn-ghost btn-sm modal-close" aria-label="Fechar">&times;</button>'
        '</div>'
        '<p class="micro">Selecione uma imagem de banco ou edite o prompt para gerar uma nova arte.</p>'
        '<div class="campo" style="margin:12px 0;">'
        '<label for="trocar-midia-prompt"><strong>Prompt visual da cena</strong></label>'
        '<textarea id="trocar-midia-prompt" class="campo" rows="3" style="width:100%;"></textarea>'
        '</div>'
        '<div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;">'
        '<button type="button" class="btn btn-sm modal-close">Cancelar</button>'
        '<button type="button" class="btn btn-sm btn-primario" id="btn-confirmar-trocar-midia">Salvar nova mídia</button>'
        '</div>'
        '</div>'
        '</dialog>'
    )

    return header_card + focused_card + full_script_details + dialogs + script_data_tag


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

    # Controles ativos suportados e controles de evolução (Plano 2) com honestidade visual
    font_size_val = caption.get("font_size", 42)
    bottom_val = caption.get("bottom", 96)
    color_text_val = palette.get("caption_text", "#ffffff")
    color_box_val = palette.get("caption_box", "#00000099")
    color_accent_val = palette.get("accent", "#a78bfa")
    is_static_motion = isinstance(motion, (list, tuple)) and len(motion) == 0

    controls_card = (
        '<div class="card" id="card-controles-composicao">'
        '<h2>Ajustes de composição e legendas V3</h2>'
        f'<form id="form-composicao" data-video-id="{e(video_id)}" data-endpoint="/studio/videos/{e(video_id)}/style">'
        '<div class="grid-2">'
        '  <div>'
        '    <h3>Legenda (Controles ativos)</h3>'
        '    <div class="campo">'
        '      <label for="composicao-font-size">Tamanho da legenda (font_size)</label>'
        f'      <input type="number" id="composicao-font-size" name="caption.font_size" class="input campo" value="{e(str(font_size_val))}" min="16" max="96">'
        '    </div>'
        '    <div class="campo">'
        '      <label for="composicao-bottom">Distância da base (bottom, px)</label>'
        f'      <input type="number" id="composicao-bottom" name="caption.bottom" class="input campo" value="{e(str(bottom_val))}" min="0" max="400">'
        '    </div>'
        '  </div>'
        '  <div>'
        '    <h3>Paleta de cores (Controles ativos)</h3>'
        '    <div class="campo">'
        '      <label for="composicao-color-text">Cor do texto da legenda</label>'
        f'      <input type="text" id="composicao-color-text" name="palette.caption_text" class="input campo" value="{e(str(color_text_val))}">'
        '    </div>'
        '    <div class="campo">'
        '      <label for="composicao-color-box">Cor da caixa da legenda</label>'
        f'      <input type="text" id="composicao-color-box" name="palette.caption_box" class="input campo" value="{e(str(color_box_val))}">'
        '    </div>'
        '    <div class="campo">'
        '      <label for="composicao-color-accent">Cor de destaque (accent)</label>'
        f'      <input type="text" id="composicao-color-accent" name="palette.accent" class="input campo" value="{e(str(color_accent_val))}">'
        '    </div>'
        '  </div>'
        '</div>'
        '<div class="campo" style="margin-top:1rem">'
        '  <label for="composicao-motion">Movimento de câmera</label>'
        '  <select id="composicao-motion" name="motion" class="input campo">'
        f'    <option value="zoom_lento"{" selected" if not is_static_motion else ""}>Zoom lento (Ken Burns padrão: zoom_in, pan_left)</option>'
        f'    <option value="estatico"{" selected" if is_static_motion else ""}>Estático (sem movimento)</option>'
        '  </select>'
        '</div>'
        '<div style="margin-top:1.5rem;padding-top:1.25rem;border-top:1px solid var(--line, #e3e0ea)">'
        '  <h3>Evolução de Composição</h3>'
        '  <div class="campo">'
        '    <label>Posição da legenda <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '    <div style="display:flex;gap:1.5rem;margin-top:0.35rem">'
        '      <label><input type="radio" name="caption_pos" value="topo" disabled> Topo</label>'
        '      <label><input type="radio" name="caption_pos" value="meio" disabled> Meio</label>'
        '      <label><input type="radio" name="caption_pos" value="base" checked disabled> Base (vigente)</label>'
        '    </div>'
        '  </div>'
        '  <div class="grid-2" style="margin-top:1rem">'
        '    <div class="campo">'
        '      <label for="composicao-fonte-fam">Fonte da legenda <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '      <select id="composicao-fonte-fam" class="input campo" disabled>'
        '        <option value="inter" selected disabled>Inter</option>'
        '        <option value="roboto" disabled>Roboto</option>'
        '        <option value="georgia" disabled>Georgia</option>'
        '      </select>'
        '    </div>'
        '    <div class="campo">'
        '      <label>Estilo da legenda <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '      <div style="display:flex;gap:1rem;margin-top:0.35rem;flex-wrap:wrap">'
        '        <label><input type="radio" name="caption_style" value="destaque" disabled> Destaque por palavra</label>'
        '        <label><input type="radio" name="caption_style" value="caixa" checked disabled> Caixa (vigente)</label>'
        '        <label><input type="radio" name="caption_style" value="simples" disabled> Simples</label>'
        '      </div>'
        '    </div>'
        '  </div>'
        '  <div class="grid-2" style="margin-top:1rem">'
        '    <div class="campo">'
        '      <label>Transição entre cenas <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '      <div style="display:flex;gap:1rem;margin-top:0.35rem">'
        '        <label><input type="radio" name="transicao_tipo" value="fade" checked disabled> Fade</label>'
        '        <label><input type="radio" name="transicao_tipo" value="corte" disabled> Corte seco</label>'
        '        <label><input type="radio" name="transicao_tipo" value="deslizar" disabled> Deslizar</label>'
        '      </div>'
        '    </div>'
        '    <div class="campo">'
        '      <label>Taxa de quadros / FPS</label>'
        '      <div style="display:flex;gap:0.75rem;align-items:center;margin-top:0.35rem;flex-wrap:wrap">'
        '        <span class="pill pill-ok">25 fps (vigente)</span>'
        '        <label><input type="radio" name="fps_opt" value="24" disabled> 24 fps <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '        <label><input type="radio" name="fps_opt" value="30" disabled> 30 fps <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '        <label><input type="radio" name="fps_opt" value="60" disabled> 60 fps <span class="pill pill-espera">Em breve no Plano 2</span></label>'
        '      </div>'
        '    </div>'
        '  </div>'
        '</div>'
        '<div style="margin-top:1.5rem;display:flex;align-items:center;gap:1rem">'
        '  <button type="submit" class="btn btn-primary" id="btn-salvar-composicao">Salvar composição</button>'
        '  <p id="composicao-feedback" class="dica" role="status" aria-live="polite" style="margin:0"></p>'
        '</div>'
        '</form>'
        '</div>'
    )

    return (
        plan_card
        + controls_card
        + f'<div class="card"><h2>Composição do vídeo</h2>{head}{rows}</div>'
        + notes
    )


def _area_qualidade(view, *, style_view=None, script_view=None, video_id: str, composition_view=None, preview=None) -> str:
    # 1. Prévia em destaque centralizada no topo
    if view.stage in _PREVIEW_STAGES:
        output_asset_param = f"?output_asset_id={e(preview.output_asset_id)}" if (preview and getattr(preview, "output_asset_id", None)) else ""
        preview_card = (
            '<div class="card card-preview-destaque" style="text-align:center;margin-bottom:1.5rem">'
            f'<div class="player" style="max-width:720px;margin:0 auto;overflow:hidden;background:#000;border-radius:var(--raio, 8px)">'
            f'<video controls preload="metadata" poster="/studio/videos/{e(video_id)}/thumbnail" '
            f'src="/studio/videos/{e(video_id)}/file{output_asset_param}" style="width:100%;max-height:480px;display:block">'
            f'<track kind="captions" srclang="pt-BR" label="Português" src="/studio/videos/{e(video_id)}/subtitles.vtt" default>'
            '</video>'
            '</div>'
            f'<p style="margin-top:0.75rem"><a class="btn btn-ghost btn-sm" href="/studio/videos/{e(video_id)}/preview">Abrir prévia completa</a></p>'
            '</div>'
        )
    else:
        preview_card = (
            '<div class="card card-preview-destaque" style="text-align:center;margin-bottom:1.5rem">'
            '<p class="aviso">Prévia e aprovação ficam disponíveis após a renderização. '
            'A decisão de aprovação vive na página de prévia (com CSP própria).</p>'
            '</div>'
        )

    # 2. Resumo de revisão e ação de aprovação
    qa = getattr(view.video, "qa_report", None)
    has_blocking = False
    actionable_issues = []
    if qa is not None:
        publishable = bool(getattr(qa, "is_publishable", False))
        coverage = getattr(qa, "coverage", None)
        coverage_status = getattr(coverage, "status", "não informada")
        findings = list(getattr(qa, "findings", ()) or ())
        for f in findings:
            ev = getattr(f, "evidence", str(f))
            sev = getattr(f, "severity", "warning")
            cid = getattr(f, "check_id", "")
            actionable_issues.append((sev, ev, cid))
            if sev == "blocking":
                has_blocking = True
        if not publishable:
            has_blocking = True
    else:
        publishable = False
        coverage_status = "não informada"
        findings = []

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

    if has_blocking and actionable_issues:
        readiness_badge = '<span class="pill pill-err">Atenção: pendências identificadas</span>'
        readiness_html = (
            f'<div class="readiness-box" style="margin:1rem 0;">'
            f'<p><strong>Situação:</strong> {readiness_badge}</p>'
            '<p class="aviso"><strong>Pendências técnicas para resolução:</strong></p>'
            '<ul class="lista-pendencias" style="margin:0.5rem 0 0 1.25rem;color:var(--err);">'
            + "".join(
                f'<li><strong>[{e(sev)}]</strong> {e(ev)}' + (f' <span class="hint">({e(cid)})</span>' if cid else '') + '</li>'
                for sev, ev, cid in actionable_issues
            )
            + '</ul></div>'
        )
    elif view.stage not in _PREVIEW_STAGES:
        readiness_badge = '<span class="pill pill-espera">Aguardando renderização</span>'
        readiness_html = (
            f'<div class="readiness-box" style="margin:1rem 0;">'
            f'<p><strong>Situação:</strong> {readiness_badge} — Aguardando renderização do vídeo para revisão.</p>'
            '</div>'
        )
    else:
        readiness_badge = '<span class="pill pill-good">Pronto para sua revisão</span>'
        readiness_html = (
            f'<div class="readiness-box" style="margin:1rem 0;">'
            f'<p><strong>Situação:</strong> {readiness_badge} — Pronto para sua revisão.</p>'
            '</div>'
        )

    if view.stage in _PREVIEW_STAGES and view.stage not in (Stage.APPROVED, Stage.COMPLETED):
        action_button = (
            '<div class="acoes" style="margin-top:1.25rem;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
            f'<button type="button" class="btn btn-primario" data-a="approve" data-video-id="{e(video_id)}" id="btn-approve-video">'
            '✓ Aprovar e preparar publicação →'
            '</button>'
            '<span id="approve-feedback" class="feedback" role="status" aria-live="polite"></span>'
            '</div>'
        )
    elif view.stage in (Stage.APPROVED, Stage.COMPLETED):
        action_button = (
            '<div class="acoes" style="margin-top:1.25rem;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
            f'<a class="btn btn-primario" href="/studio/panel/videos/{e(video_id)}/publicacao">'
            '✓ Avançar para publicação →'
            '</a>'
            '</div>'
        )
    else:
        action_button = (
            '<div class="acoes" style="margin-top:1.25rem;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
            f'<button type="button" class="btn btn-primario" data-a="approve" data-video-id="{e(video_id)}" id="btn-approve-video" disabled>'
            '✓ Aprovar e preparar publicação →'
            '</button>'
            '<span class="micro muted">Aprovação disponível após a renderização</span>'
            '</div>'
        )

    review_card = (
        '<div class="card card-revisao">'
        '<h3>Revisão e Aprovação da Versão</h3>'
        f'{approval_rows}'
        f'{readiness_html}'
        f'{action_button}'
        '</div>'
    )

    # 3. Verificações técnicas em detalhes expansíveis
    if qa is not None:
        qa_html = (
            '<div class="card" style="margin-top:0.75rem"><h4>Relatório de QA do render</h4>'
            + _kv("Publicável", "sim" if publishable else "não")
            + _kv("Cobertura", e(coverage_status))
            + _kv("Achados", str(len(findings)))
        )
        if findings:
            findings_items = "".join(
                f'<li><strong>{e(getattr(f, "check_id", "CHECK"))}</strong> ({e(getattr(f, "severity", "info"))}): '
                f'{e(getattr(f, "evidence", str(f)))}</li>'
                for f in findings
            )
            qa_html += f'<div style="margin-top:0.75rem"><p class="micro"><strong>Detalhamento dos achados:</strong></p><ul class="cenas">{findings_items}</ul></div>'
        qa_html += '</div>'
    else:
        qa_html = (
            '<div class="card" style="margin-top:0.75rem"><h4>Relatório de QA do render</h4>'
            '<p class="aviso">Relatório de QA do render não disponível nesta leitura.</p>'
            '</div>'
        )

    technical_details = (
        '<details class="diag">'
        '<summary>Ver todas as verificações técnicas</summary>'
        '<div style="margin-top:1rem">'
        '<p class="muted micro">Verificações automatizadas do renderizador: integridade do contêiner, taxa de quadros, loudness de áudio e conformidade de legenda.</p>'
        f'{qa_html}'
        '</div>'
        '</details>'
    )

    # 4. Disclaimer explícito
    disclaimer = (
        '<p class="aviso" style="margin-top:1.5rem">'
        '<strong>Avaliação semântica não verificada:</strong> '
        'Verificações ilustrativas/técnicas. QA técnico não verifica fatos do roteiro '
        '(veracidade factual) nem a correspondência entre roteiro e imagem (depende de provider real e não é verificada aqui).'
        '</p>'
    )

    return preview_card + review_card + technical_details + disclaimer


def _area_publicacao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None, preview=None) -> str:
    video = getattr(view, "video", view)
    pub = getattr(view, "publication", None)

    # 1. Edições pendentes (dirty / pending revisions)
    is_dirty = bool(
        getattr(view, "dirty", False)
        or getattr(view, "is_dirty", False)
        or getattr(view, "pending_revisions", False)
        or getattr(video, "dirty", False)
        or getattr(video, "is_dirty", False)
        or getattr(video, "pending_revisions", False)
    )

    # 2. Agendamento / publish_at
    publish_at = (
        (getattr(pub, "publish_at", None) if pub is not None else None)
        or getattr(view, "publish_at", None)
        or getattr(video, "publish_at", None)
        or (getattr(preview.publication, "publish_at", None) if preview and getattr(preview, "publication", None) else None)
        or (getattr(preview.approval, "publish_at", None) if preview and getattr(preview, "approval", None) else None)
    )

    data_str = ""
    sched_input_val = ""
    if publish_at is not None:
        if isinstance(publish_at, datetime):
            data_str = publish_at.strftime("%d/%m/%Y às %H:%M")
            sched_input_val = publish_at.strftime("%Y-%m-%dT%H:%M")
        else:
            data_str = str(publish_at)
            sched_input_val = str(publish_at)

    # 3. Estado publicado
    is_published = False
    if pub is not None:
        pub_status_str = getattr(pub.status, "value", str(pub.status)).upper()
        if pub_status_str in ("UPLOADED", "PUBLISHED"):
            is_published = True
    if getattr(view, "stage", None) == Stage.COMPLETED or getattr(video, "status", None) == VideoStatus.PUBLISHED:
        is_published = True

    # 4. Estado agendado
    is_scheduled = False
    if not is_published:
        if publish_at is not None:
            is_scheduled = True
        elif pub is not None and getattr(pub.status, "value", str(pub.status)).upper() in ("SCHEDULED", "AGENDADO"):
            is_scheduled = True
        elif str(getattr(video, "status", "")).upper() in ("SCHEDULED", "AGENDADO"):
            is_scheduled = True

    # Resumo / Cartão de status
    if is_published:
        if pub is not None:
            status_value = getattr(pub.status, "value", str(pub.status))
            status_line = f'{e(status_value)} — <span class="pill pill-good">Publicado</span>'
            rows = _kv("Situação", status_line) + _kv("Tentativa", str(pub.attempt))
            if pub.error:
                rows += _kv("Erro registrado", e(pub.error))
        else:
            rows = _kv("Situação", '<span class="pill pill-good">Publicado</span>')
        summary = f'<div class="card"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    elif is_scheduled:
        if pub is not None:
            status_value = getattr(pub.status, "value", str(pub.status))
            status_line = f'{e(status_value)} — <span class="pill pill-info">Agendado</span>'
            rows = _kv("Situação", status_line)
            if data_str:
                rows += _kv("Agendamento", f"Agendado para {e(data_str)} (Horário de Brasília)")
            rows += _kv("Tentativa", str(pub.attempt))
            if pub.error:
                rows += _kv("Erro registrado", e(pub.error))
        else:
            rows = _kv("Situação", '<span class="pill pill-info">Agendado</span>')
            if data_str:
                rows += _kv("Agendamento", f"Agendado para {e(data_str)} (Horário de Brasília)")
        summary = f'<div class="card"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    elif pub is not None:
        status_value = getattr(pub.status, "value", str(pub.status))
        rows = _kv("Situação", e(status_value)) + _kv("Tentativa", str(pub.attempt))
        if pub.error:
            rows += _kv("Erro registrado", e(pub.error))
        summary = f'<div class="card"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    else:
        summary = ('<div class="card"><h3>Publicação</h3>'
                   '<p class="muted">Nenhuma publicação registrada para este vídeo.</p></div>')

    # Opções de publicação V3 (imediato vs agendado)
    dirty_html = ""
    if is_dirty:
        dirty_html = (
            '<div class="aviso aviso-alerta" id="aviso-edicoes-pendentes" style="margin-bottom:1rem">'
            '<strong>Edições pendentes: o agendamento precisa ser revisado após novas alterações.</strong>'
            '</div>'
        )

    scheduled_note = ""
    if is_scheduled and data_str:
        scheduled_note = f'<div class="aviso aviso-info" style="margin-bottom:1rem">Agendado para {e(data_str)} · Brasília. Ainda não publicado.</div>'

    action_btn_text = "Atualizar agendamento" if is_scheduled else "Publicar agora"

    checked_now = ' checked' if not is_scheduled else ''
    checked_sched = ' checked' if is_scheduled else ''
    sched_style = '' if is_scheduled else ' style="display:none"'

    options_card = (
        '<div class="card" id="card-opcoes-publicacao" style="margin-top:1.25rem">'
        '<h3>Opções de Publicação</h3>'
        f'{dirty_html}'
        f'{scheduled_note}'
        '<div class="campo">'
        '<label class="rotulo"><strong>Modalidade de publicação:</strong></label>'
        '<div class="grupo-radios" style="display:flex;gap:1.5rem;margin:0.5rem 0;flex-wrap:wrap">'
        '<label class="radio-opcao" style="display:flex;align-items:center;gap:6px;cursor:pointer">'
        f'<input type="radio" name="tipo-publicacao" id="publicar-agora" value="imediato"{checked_now}>'
        '<span>Publicar agora (Publicar imediatamente)</span>'
        '</label>'
        '<label class="radio-opcao" style="display:flex;align-items:center;gap:6px;cursor:pointer">'
        f'<input type="radio" name="tipo-publicacao" id="agendar-publicacao" value="agendado"{checked_sched}>'
        '<span>Agendar publicação (Agendar para depois)</span>'
        '</label>'
        '</div>'
        '</div>'
        f'<div class="campo campo-agendamento" id="bloco-agendamento"{sched_style}>'
        '<label for="agendamento-data"><strong>Data e horário de publicação</strong></label>'
        f'<input type="datetime-local" id="agendamento-data" name="agendamento-data" class="campo" value="{e(sched_input_val)}">'
        '<p class="dica">Horário de Brasília · UTC−03:00. Agendar não publica agora.</p>'
        '<span id="agendamento-feedback" class="feedback" role="status" aria-live="polite"></span>'
        '</div>'
        '<div class="acoes" style="margin-top:1.25rem">'
        f'<button type="button" class="btn btn-primario" id="btn-publicar-acao" data-video-id="{e(video_id)}">{action_btn_text}</button>'
        '</div>'
        '</div>'
    )

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
    return summary + heading + options_card + decision + preview_html + destination


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


def _content(view, area: str, *, style_view, script_view, video_id, composition_view=None, preview=None,
             scenes=None, script=None) -> str:
    if area == "publicacao":
        return _area_publicacao(view, style_view=style_view, script_view=script_view,
                                video_id=video_id, preview=preview)
    if area == "qualidade":
        return _area_qualidade(view, style_view=style_view, script_view=script_view,
                               video_id=video_id, composition_view=composition_view,
                               preview=preview)
    if area == "cenas":
        return _area_cenas(view, style_view=style_view, script_view=script_view, video_id=video_id,
                           composition_view=composition_view, scenes=scenes, script=script)
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

  // --- Storyboard V3 Client JS (Cena em foco, Desfazer/Refazer, Modais) ---
  var scenesDataEl = document.getElementById('storyboard-scenes-data');
  var scenesData = [];
  if (scenesDataEl && scenesDataEl.textContent) {
    try { scenesData = JSON.parse(scenesDataEl.textContent); } catch (e) { scenesData = []; }
  }

  var currentActiveIdx = 0;
  var undoStack = [];
  var redoStack = [];
  var MAX_SNAPSHOTS = 30;

  function getStoryboardSnapshot() {
    var narEl = document.getElementById('cena-narration');
    var prmEl = document.getElementById('cena-prompt');
    return {
      scenes: JSON.parse(JSON.stringify(scenesData)),
      activeIdx: currentActiveIdx,
      narration: narEl ? narEl.value : '',
      prompt: prmEl ? prmEl.value : ''
    };
  }

  function updateUndoRedoButtons() {
    var btnUndo = document.getElementById('btn-undo-cenas');
    var btnRedo = document.getElementById('btn-redo-cenas');
    if (btnUndo) btnUndo.disabled = (undoStack.length === 0);
    if (btnRedo) btnRedo.disabled = (redoStack.length === 0);
  }

  function pushSnapshot() {
    undoStack.push(getStoryboardSnapshot());
    if (undoStack.length > MAX_SNAPSHOTS) undoStack.shift();
    redoStack = [];
    updateUndoRedoButtons();
  }

  function focusScene(idx) {
    if (!scenesData || idx < 0 || idx >= scenesData.length) return;
    currentActiveIdx = idx;
    var s = scenesData[idx];

    document.querySelectorAll('.btn-cena-pill').forEach(function (pill) {
      var pIdx = Number(pill.getAttribute('data-scene-idx'));
      var isAct = (pIdx === idx);
      pill.setAttribute('aria-pressed', isAct ? 'true' : 'false');
      if (isAct) {
        pill.classList.add('active', 'btn-primario');
        pill.classList.remove('btn-ghost');
      } else {
        pill.classList.remove('active', 'btn-primario');
        pill.classList.add('btn-ghost');
      }
    });

    var card = document.getElementById('cena-em-foco');
    if (card) card.setAttribute('data-active-idx', String(idx));

    var titulo = document.getElementById('foco-titulo');
    if (titulo) titulo.textContent = 'Cena ' + (idx + 1) + ' de ' + scenesData.length + ' · ' + (s.label || ('Cena ' + (idx + 1)));

    var duracao = document.getElementById('foco-duracao');
    if (duracao) duracao.textContent = (typeof s.duration_s === 'number') ? (s.duration_s.toFixed(1) + ' s') : 'sem duração medida';

    var badge = document.getElementById('foco-audio-badge');
    if (badge) {
      badge.textContent = 'Áudio: ' + (s.audio_state || 'none');
      badge.className = 'pill pill-' + (s.audio_state || 'none') + ' badge-audio';
    }

    var nar = document.getElementById('cena-narration');
    if (nar) nar.value = s.narration || '';

    var prm = document.getElementById('cena-prompt');
    if (prm) prm.value = s.image_prompt || '';

    var videoId = card ? (card.getAttribute('data-video-id') || '') : '';
    var img = document.getElementById('foco-midia-img');
    var placeholder = document.getElementById('foco-midia-placeholder');
    if (img && placeholder) {
      if (s.asset_id) {
        img.src = '/studio/videos/' + encodeURIComponent(videoId) + '/scenes/' + idx + '/asset';
        img.style.display = 'block';
        placeholder.style.display = 'none';
      } else {
        img.style.display = 'none';
        placeholder.style.display = 'flex';
      }
    }

    var numAudio = document.getElementById('modal-audio-scene-num');
    if (numAudio) numAudio.textContent = String(idx + 1);

    var numMedia = document.getElementById('modal-media-scene-num');
    if (numMedia) numMedia.textContent = String(idx + 1);

    var mediaPrompt = document.getElementById('trocar-midia-prompt');
    if (mediaPrompt) mediaPrompt.value = s.image_prompt || '';

    renderAudioHistory(idx);
  }

  var mediaImg = document.getElementById('foco-midia-img');
  if (mediaImg) {
    mediaImg.addEventListener('error', function () {
      mediaImg.style.display = 'none';
      var placeholder = document.getElementById('foco-midia-placeholder');
      if (placeholder) placeholder.style.display = 'flex';
    });
  }

  document.querySelectorAll('.btn-cena-pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      var idx = Number(pill.getAttribute('data-scene-idx'));
      focusScene(idx);
    });
  });

  function renderAudioHistory(idx) {
    var listEl = document.getElementById('dialog-audio-history-list') || document.getElementById('lista-historico-audio');
    if (!listEl) return;
    var s = (scenesData && scenesData[idx]) ? scenesData[idx] : null;
    var history = (s && s.audio_history) ? s.audio_history : [];
    if (!history || history.length === 0) {
      listEl.innerHTML = '<li class="vazio">Nenhuma versão anterior gravada para esta cena.</li>';
      return;
    }
    var html = '';
    history.forEach(function (h) {
      var v = h.version || 1;
      var dur = (typeof h.duration_s === 'number') ? (h.duration_s.toFixed(1) + ' s') : 'sem duração';
      var textSafe = (h.text || '').replace(/"/g, '&quot;');
      html += '<li class="spread" style="align-items:center;padding:8px 0;border-bottom:1px solid var(--linha);">' +
        '<div><strong>v' + v + '</strong> · ' + dur + '<br><small class="micro">' + (h.text || '') + '</small></div>' +
        '<div class="row" style="display:flex;gap:6px;">' +
        '<button type="button" class="btn btn-sm btn-ghost btn-ouvir-audio" data-version="' + v + '">Ouvir</button>' +
        '<button type="button" class="btn btn-sm btn-restaurar-audio" data-version="' + v + '" data-text="' + textSafe + '">Restaurar voz</button>' +
        '</div></li>';
    });
    listEl.innerHTML = html;
    wireAudioRestoreButtons();
  }

  function wireAudioRestoreButtons() {
    document.querySelectorAll('.btn-restaurar-audio').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var versionText = btn.getAttribute('data-text') || '';
        var narEl = document.getElementById('cena-narration');
        var currentNarration = narEl ? narEl.value.trim() : '';
        var s = scenesData[currentActiveIdx];
        if (!s) return;

        var isIdentical = (versionText.trim() === currentNarration);
        var badge = document.getElementById('foco-audio-badge');
        var pill = document.querySelector('.btn-cena-pill[data-scene-idx="' + currentActiveIdx + '"]');

        if (isIdentical) {
          s.audio_state = 'ok';
          if (badge) {
            badge.textContent = 'Áudio: pronto (ok)';
            badge.className = 'pill pill-ok badge-audio';
          }
          if (pill) {
            var label = s.label || ('Cena ' + (currentActiveIdx + 1));
            pill.textContent = (currentActiveIdx + 1) + ' · ' + label;
          }
        } else {
          s.audio_state = 'stale';
          if (badge) {
            badge.textContent = 'Áudio: desatualizado (stale)';
            badge.className = 'pill pill-stale badge-audio';
          }
          if (pill) {
            var label = s.label || ('Cena ' + (currentActiveIdx + 1));
            pill.textContent = (currentActiveIdx + 1) + ' · ' + label + ' · atualizar voz';
          }
        }

        var fb = document.getElementById('audio-history-feedback');
        if (fb) {
          fb.textContent = isIdentical ? 'Voz restaurada (áudio sincronizado).' : 'Voz restaurada com narração diferente (marcada como stale).';
        }

        var dialog = document.getElementById('dialog-audio-history');
        if (dialog) {
          if (typeof dialog.close === 'function') {
            dialog.close();
          } else {
            dialog.removeAttribute('open');
            dialog.style.display = 'none';
          }
        }
      });
    });
  }

  var isEditingNarration = false;
  var isEditingPrompt = false;

  var narEl = document.getElementById('cena-narration');
  if (narEl) {
    narEl.addEventListener('focusin', function () {
      if (!isEditingNarration) {
        pushSnapshot();
        isEditingNarration = true;
      }
    });
    narEl.addEventListener('input', function () {
      if (!isEditingNarration) {
        pushSnapshot();
        isEditingNarration = true;
      }
      if (scenesData[currentActiveIdx]) {
        scenesData[currentActiveIdx].narration = narEl.value;
      }
    });
    narEl.addEventListener('blur', function () {
      isEditingNarration = false;
    });
  }

  var prmEl = document.getElementById('cena-prompt');
  if (prmEl) {
    prmEl.addEventListener('focusin', function () {
      if (!isEditingPrompt) {
        pushSnapshot();
        isEditingPrompt = true;
      }
    });
    prmEl.addEventListener('input', function () {
      if (!isEditingPrompt) {
        pushSnapshot();
        isEditingPrompt = true;
      }
      if (scenesData[currentActiveIdx]) {
        scenesData[currentActiveIdx].image_prompt = prmEl.value;
      }
    });
    prmEl.addEventListener('blur', function () {
      isEditingPrompt = false;
    });
  }

  var btnUndo = document.getElementById('btn-undo-cenas');
  if (btnUndo) {
    btnUndo.addEventListener('click', function () {
      if (undoStack.length === 0) return;
      redoStack.push(getStoryboardSnapshot());
      var snap = undoStack.pop();
      if (snap) {
        scenesData = snap.scenes;
        focusScene(snap.activeIdx);
        var nar = document.getElementById('cena-narration');
        if (nar) {
          nar.value = snap.narration;
          if (scenesData[snap.activeIdx]) scenesData[snap.activeIdx].narration = snap.narration;
        }
        var prm = document.getElementById('cena-prompt');
        if (prm) {
          prm.value = snap.prompt;
          if (scenesData[snap.activeIdx]) scenesData[snap.activeIdx].image_prompt = snap.prompt;
        }
      }
      updateUndoRedoButtons();
    });
  }

  var btnRedo = document.getElementById('btn-redo-cenas');
  if (btnRedo) {
    btnRedo.addEventListener('click', function () {
      if (redoStack.length === 0) return;
      undoStack.push(getStoryboardSnapshot());
      var snap = redoStack.pop();
      if (snap) {
        scenesData = snap.scenes;
        focusScene(snap.activeIdx);
        var nar = document.getElementById('cena-narration');
        if (nar) {
          nar.value = snap.narration;
          if (scenesData[snap.activeIdx]) scenesData[snap.activeIdx].narration = snap.narration;
        }
        var prm = document.getElementById('cena-prompt');
        if (prm) {
          prm.value = snap.prompt;
          if (scenesData[snap.activeIdx]) scenesData[snap.activeIdx].image_prompt = snap.prompt;
        }
      }
      updateUndoRedoButtons();
    });
  }

  function wireModal(triggerId, dialogId) {
    var trigger = document.getElementById(triggerId);
    var dialog = document.getElementById(dialogId);
    if (!trigger || !dialog) return;
    trigger.addEventListener('click', function () {
      if (typeof dialog.showModal === 'function') {
        try { dialog.showModal(); } catch (e) { dialog.setAttribute('open', ''); dialog.style.display = 'block'; }
      } else {
        dialog.setAttribute('open', '');
        dialog.style.display = 'block';
      }
    });
    dialog.querySelectorAll('.modal-close').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (typeof dialog.close === 'function') {
          dialog.close();
        } else {
          dialog.removeAttribute('open');
          dialog.style.display = 'none';
        }
      });
    });
  }

  wireModal('btn-historico-voz', 'dialog-audio-history');
  wireModal('btn-trocar-midia', 'dialog-trocar-midia');

  var approveBtn = document.querySelector('button[data-a="approve"]');
  if (approveBtn) {
    approveBtn.addEventListener('click', async function () {
      var videoId = approveBtn.getAttribute('data-video-id') || '';
      var fb = document.getElementById('approve-feedback');
      approveBtn.disabled = true;
      approveBtn.classList.add('carregando');
      if (window.StudioLoading) window.StudioLoading.start();
      if (fb) fb.textContent = 'Aprovando vídeo e preparando publicação...';
      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (fb) fb.textContent = 'Aprovado com sucesso! Redirecionando para publicação...';
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/publicacao';
        } else {
          if (fb) fb.textContent = 'Não foi possível aprovar: ' + (typeof data.detail === 'string' ? data.detail : 'erro no servidor.');
          approveBtn.disabled = false;
          approveBtn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
        }
      } catch (err) {
        if (fb) fb.textContent = 'Falha de rede ao aprovar. Tente novamente.';
        approveBtn.disabled = false;
        approveBtn.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
      }
    });
  }

  // Validação e alternância de agendamento na aba de publicação
  var scheduleInput = document.getElementById('agendamento-data');
  var scheduleRadio = document.getElementById('agendar-publicacao');
  var nowRadio = document.getElementById('publicar-agora');
  var scheduleFeedback = document.getElementById('agendamento-feedback');
  var btnPublishAction = document.getElementById('btn-publicar-acao');
  var scheduleBlock = document.getElementById('bloco-agendamento');

  function validateBrasiliaSchedule() {
    if (!scheduleInput) return true;
    var isScheduleMode = scheduleRadio ? scheduleRadio.checked : true;
    if (!isScheduleMode) {
      if (scheduleFeedback) {
        scheduleFeedback.textContent = '';
        scheduleFeedback.classList.remove('erro');
      }
      return true;
    }
    var val = scheduleInput.value.trim();
    if (!val) {
      if (scheduleFeedback) {
        scheduleFeedback.textContent = 'Escolha uma data futura no horário de Brasília.';
        scheduleFeedback.classList.add('erro');
      }
      return false;
    }
    // Formato datetime-local: "YYYY-MM-DDTHH:mm" -> interpreta como Horário de Brasília (UTC-03:00)
    var isoString = val.length === 16 ? val + ':00-03:00' : (val.length === 19 ? val + '-03:00' : val);
    var scheduledMillis = new Date(isoString).getTime();
    if (isNaN(scheduledMillis) || scheduledMillis <= Date.now()) {
      if (scheduleFeedback) {
        scheduleFeedback.textContent = 'Escolha uma data futura no horário de Brasília.';
        scheduleFeedback.classList.add('erro');
      }
      return false;
    }
    if (scheduleFeedback) {
      scheduleFeedback.textContent = '';
      scheduleFeedback.classList.remove('erro');
    }
    return true;
  }

  function syncPublishAt() {
    var pAt = document.getElementById('publish_at');
    if (!pAt) return;
    if (nowRadio && nowRadio.checked) {
      pAt.value = '';
    } else if (scheduleInput && scheduleInput.value) {
      pAt.value = scheduleInput.value;
    }
  }

  if (scheduleRadio && nowRadio && scheduleBlock) {
    scheduleRadio.addEventListener('change', function () {
      if (scheduleRadio.checked) {
        scheduleBlock.style.display = 'block';
        validateBrasiliaSchedule();
        syncPublishAt();
      }
    });
    nowRadio.addEventListener('change', function () {
      if (nowRadio.checked) {
        scheduleBlock.style.display = 'none';
        if (scheduleFeedback) {
          scheduleFeedback.textContent = '';
          scheduleFeedback.classList.remove('erro');
        }
        syncPublishAt();
      }
    });
  }

  if (scheduleInput) {
    scheduleInput.addEventListener('input', function () {
      validateBrasiliaSchedule();
      syncPublishAt();
    });
    scheduleInput.addEventListener('change', function () {
      validateBrasiliaSchedule();
      syncPublishAt();
    });
  }

  if (btnPublishAction) {
    btnPublishAction.addEventListener('click', function (e) {
      if (scheduleRadio && scheduleRadio.checked) {
        if (!validateBrasiliaSchedule()) {
          e.preventDefault();
          return false;
        }
      }
    });
  }

  // Composição V3: submissão de alterações de estilo (PATCH /studio/videos/{id}/style)
  var compForm = document.getElementById('form-composicao');
  if (compForm) {
    compForm.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var videoId = compForm.getAttribute('data-video-id') || '';
      var feedback = document.getElementById('composicao-feedback');
      var button = document.getElementById('btn-salvar-composicao');
      var fontSizeInput = document.getElementById('composicao-font-size');
      var bottomInput = document.getElementById('composicao-bottom');
      var colorTextInput = document.getElementById('composicao-color-text');
      var colorBoxInput = document.getElementById('composicao-color-box');
      var colorAccentInput = document.getElementById('composicao-color-accent');
      var motionInput = document.getElementById('composicao-motion');

      var payload = {
        caption: {
          font_size: fontSizeInput ? Number(fontSizeInput.value) || 42 : 42,
          bottom: bottomInput ? Number(bottomInput.value) || 96 : 96
        },
        palette: {
          caption_text: colorTextInput ? colorTextInput.value.trim() : '#ffffff',
          caption_box: colorBoxInput ? colorBoxInput.value.trim() : '#00000099',
          accent: colorAccentInput ? colorAccentInput.value.trim() : '#a78bfa'
        },
        motion: (motionInput && motionInput.value === 'estatico') ? [] : ['zoom_in', 'pan_left']
      };

      if (button) { button.disabled = true; button.classList.add('carregando'); }
      if (window.StudioLoading) window.StudioLoading.start();
      if (feedback) feedback.textContent = 'Salvando composição...';

      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/style', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (feedback) feedback.textContent = 'Composição salva com sucesso. Atualizando...';
          setTimeout(function () { location.reload(); }, 500);
        } else {
          if (feedback) feedback.textContent = 'Não foi possível salvar: '
            + (typeof data.detail === 'string' ? data.detail : 'verifique os parâmetros e tente novamente.');
          if (button) { button.disabled = false; button.classList.remove('carregando'); }
          if (window.StudioLoading) window.StudioLoading.done();
        }
      } catch (err) {
        if (feedback) feedback.textContent = 'Falha de rede ao salvar a composição. Tente novamente.';
        if (button) { button.disabled = false; button.classList.remove('carregando'); }
        if (window.StudioLoading) window.StudioLoading.done();
      }
    });
  }
})();
"""


def _workspace_header(view, video_id: str, title: str, stage_label: str) -> str:
    """Cabeçalho do workspace com título, badge de estado, custo e link de diagnóstico."""
    diag_href = area_href(video_id, "producao")
    return f"""        <div class="cab-video">
          <div>
            <p class="eyebrow">ESPAÇO DO VÍDEO</p>
            <h1 class="h1" id="t-video">{e(title)}</h1>
            <p class="lead" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              {legacy._state_badge(view.stage)}
              <span class="pill pill-{e(view.stage.value)}">{e(stage_label)}</span>
              <span class="micro">Custo do vídeo: {legacy._cost_html(view.cost_text)}</span>
            </p>
          </div>
          <div class="cab-acoes" style="display:flex;gap:8px;align-items:center">
            <a class="btn btn-ghost btn-sm" href="{diag_href}">Ver progresso / Diagnóstico</a>
          </div>
        </div>"""


def render_video_workspace(view, area: str = "cenas", *, active_area: str | None = None,
                           style_view=None, script_view=None,
                           composition_view=None, preview=None, projects=(), project_id: str = "",
                           channel_name: str = "", script=None, scenes=None,
                           sources=None) -> WorkspaceResult:
    """Workspace do vídeo: uma área por rota, reusando os blocos reais do detalhe.

    O que a rota precisa passar:
    - `view`: o `VideoDetailView` já montado (`BuildPanel.detail(video_id)`) ou um `Video`;
    - `area`: o segmento da URL (`cenas`…`fontes`, ou `producao`); desconhecido cai em `cenas`;
    - `style_view`: o `VideoStyleView` do vídeo (opcional) — dá o estilo/voz efetivos;
    - `script_view`: o `ScriptPageView` do vídeo (opcional) — dá cenas/trechos e aprovação do roteiro;
    - `composition_view`: a `CompositionView` (W2.3, opcional) — o plano persistido em leitura;
    - `preview`: o `Preview` da publicação (opcional, W5.1) — só a área Publicação usa;
    - `projects`/`project_id`/`channel_name`: contexto da casca (seletor de canal, crumb);
    - `scenes`: lista opcional de `Scene` para o Storyboard V3;
    - `script`: roteiro opcional para o Storyboard V3.
    """
    if active_area is not None:
        area = active_area
    if not hasattr(view, "video"):
        video_obj = view if isinstance(view, Video) else Video(
            id=getattr(view, "id", "v" * 32),
            project_id=getattr(view, "project_id", "p" * 32),
            topic=getattr(view, "topic", "Tema"),
            format=getattr(view, "format", VideoFormat.short),
            status=getattr(view, "status", VideoStatus.SCRIPTED),
        )
        view = VideoDetailView(
            video=video_obj,
            stage=classify(video_obj.status),
            cost_text="sem registro de uso",
            steps=[],
            usage=[],
            render_error=None,
            publication=None,
            sources=list(sources or []),
            latest_run=None,
        )
    elif sources is not None and not view.sources:
        view = VideoDetailView(
            video=view.video,
            stage=view.stage,
            cost_text=view.cost_text,
            steps=view.steps,
            usage=view.usage,
            render_error=view.render_error,
            publication=view.publication,
            sources=list(sources),
            latest_run=view.latest_run,
        )

    nonce = secrets.token_urlsafe(16)
    active_area = _normalize_area(area)
    video_id = getattr(view.video, "id", "")
    title = getattr(view.video, "title", None) or getattr(view.video, "topic", "Vídeo")
    stage_label = legacy.STAGE_LABELS.get(view.stage, view.stage.value)

    channel_crumb = f" / {e(channel_name)}" if channel_name else ""
    body_html = f"""      <section class="pagina" id="pagina-video-workspace" aria-labelledby="t-video">
        <p class="crumb"><a href="/studio/panel/videos">← Vídeos</a>{channel_crumb}</p>
{_workspace_header(view, video_id, title, stage_label)}
        {_video_area_nav(video_id, active_area)}
        {_content(view, active_area, style_view=style_view, script_view=script_view, video_id=video_id,
                  composition_view=composition_view,
                  preview=preview if active_area in ("publicacao", "qualidade") else None,
                  scenes=scenes, script=script)}
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
    return WorkspaceResult((html, legacy._headers(nonce)))
