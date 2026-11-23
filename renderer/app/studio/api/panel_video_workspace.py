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
from .panel_videos import _ESTADO

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

    run_line = ""
    if view.latest_run is not None:
        run_state = legacy._RUN_STATE_LABELS.get(view.latest_run.state, view.latest_run.state)
        run_line = f'<p class="micro">Execução mais recente: {e(run_state)}.</p>'
    production_card = (
        '<div class="card"><h3>Produção</h3>'
        f"<p>{e(legacy.STAGE_LABELS.get(view.stage, view.stage.value))}</p>{run_line}"
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
    """`tabSources` do protótipo: título, nota de atenção, cartões `.card.flat` e "+ Adicionar fonte".

    A honestidade é texto **visível** e vem antes da lista, para o operador não confundir
    "registrado" com "extraído" nem com "verificado". O formulário real (mesmos ids e endpoint
    `/sources`) abre num diálogo, como o modal `addsrc` do protótipo.
    """
    sources = list(getattr(view, "sources", None) or [])
    note = (
        '<p class="note" id="fontes-honestidade" style="margin-bottom:16px"><b>Atenção:</b> '
        "uma URL registrada é apenas uma referência — não é fonte extraída nem verificada. "
        "O Studio não verifica nem extrai o conteúdo automaticamente; só o texto colado entra no roteiro, "
        "e nada aqui é fact-checkado.</p>"
    )
    if sources:
        cards = "".join(
            '<div class="card flat between"><div>'
            f'<b>{e(src.url)}</b><p class="sample">{e(src.url)} · {src.chars} caractere{"" if src.chars == 1 else "s"}</p></div>'
            '<div class="row"><span class="pill warn">Registrada, não verificada</span></div></div>'
            for src in sources)
        listing = f'<div class="stack" style="gap:10px" aria-label="Fontes registradas">{cards}</div>'
    else:
        listing = ('<div class="card"><p class="sub">Nenhuma fonte ainda. Adicione uma URL de referência '
                   "ou cole um texto de apoio.</p></div>")
    base_url = getattr(view, "base_video_url", None)
    base_html = ""
    url_value = ""
    if base_url:
        url_value = f' value="{e(base_url)}"'
        origin = f" · {e(view.base_video_source_name)}" if getattr(view, "base_video_source_name", None) else ""
        base_html = (f'<p class="sample" style="margin-bottom:10px">vídeo base: <a href="{e(base_url)}" '
                     f'target="_blank" rel="noopener noreferrer">{e(base_url)}</a>{origin}</p>')
    dialog = f"""<dialog id="dlg-fonte" class="modal" aria-labelledby="t-dlg-fonte">
      <div class="modal-header"><h2 id="t-dlg-fonte">Adicionar fonte</h2>
        <button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>
      <div class="dialogo-corpo">
        <p class="sub" style="margin-bottom:12px">O roteiro só é escrito a partir de fatos das fontes. Sem fonte aproveitável, a produção para no primeiro passo.</p>
        {base_html}
        <form id="video-sources-form" data-video-id="{e(video_id)}" novalidate>
          <div class="field">
            <label for="source-url">URL da fonte <span aria-hidden="true">*</span></label>
            <input type="url" id="source-url" name="url" required data-error="source-url-error"
                   placeholder="https://youtube.com/watch?v=..." aria-describedby="source-rule"{url_value}>
            <p class="sample" id="source-rule">Com texto: o texto colado é a fonte e a URL é só referência.
              Sem texto: o servidor busca a URL, que precisa estar na lista permitida (STUDIO_SOURCE_ALLOWLIST);
              se a busca for recusada, a mensagem do servidor aparece aqui.</p>
            <p class="campo-erro error-msg" id="source-url-error"><span role="img" aria-label="Erro">&#9888;</span> Informe a URL da fonte.</p>
          </div>
          <div class="field">
            <label for="source-text">Texto da fonte <span class="sample">(opcional)</span></label>
            <textarea id="source-text" name="text" rows="4" placeholder="Cole o conteúdo da página quando o site bloquear a leitura"></textarea>
          </div>
          <div class="modal-footer">
            <div id="video-sources-feedback" class="feedback form-feedback" role="status" aria-live="polite" style="margin-right:auto"></div>
            <button class="btn ghost small" type="button" data-fechar-dialogo>Fechar</button>
            <button class="btn primary small" type="submit" id="btn-add-source">Adicionar fonte</button>
          </div>
        </form>
      </div>
    </dialog>"""
    roteiro_link = (f'<p style="margin-top:14px"><a class="btn small" href="/studio/videos/{e(video_id)}/roteiro">'
                    "Abrir roteiro e estrutura</a></p>")
    return (
        '<div id="video-fontes">'
        '<div class="between" style="margin-bottom:14px"><div><h2>Fontes e evidências</h2>'
        '<p class="sub">Referências que sustentam o roteiro deste vídeo.</p></div>'
        '<button type="button" class="btn small" id="btn-abrir-fonte">+ Adicionar fonte</button></div>'
        f"{note}{listing}{roteiro_link}{dialog}</div>"
    )


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


_AUDIO_BADGE = {
    "ok": ("ok", "✓ Áudio atual"),
    "stale": ("warn", "Áudio desatualizado"),
    "none": ("bad", "Sem áudio ainda"),
}


def _words(text: str) -> int:
    return len((text or "").split())


def _secs(text: str) -> int:
    """Estimativa de `secs` do protótipo: ~2,6 palavras por segundo, mínimo de 2 s."""
    return max(2, round(_words(text) / 2.6))


def _fmt_t(total: int) -> str:
    return f"{total // 60}:{total % 60:02d}"


def _scene_count_text(scene: dict) -> str:
    """"N palavras · ~Ns": a duração medida, quando existe, manda sobre a estimativa por palavras."""
    dur = scene.get("duration_s")
    secs = f"{dur:.1f}s" if dur else f"~{_secs(scene['narration'])}s"
    return f"{_words(scene['narration'])} palavras · {secs}"


def _normalize_scenes(scenes, script) -> list[dict]:
    """Cenas do roteiro em dicts simples (aceita `Scene`, objetos e dicts)."""
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
        s_broll_enabled = getattr(s, "broll_enabled", None)
        if s_broll_enabled is None and isinstance(s, dict):
            s_broll_enabled = s.get("broll_enabled")
        s_broll_note = getattr(s, "broll_note", None)
        if s_broll_note is None and isinstance(s, dict):
            s_broll_note = s.get("broll_note")
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
            "broll_enabled": bool(s_broll_enabled or False),
            "broll_note": str(s_broll_note) if s_broll_note is not None else None,
        })

    return normalized_scenes


def _area_cenas(view, *, style_view=None, script_view=None, video_id: str, composition_view=None,
                scenes=None, script=None, channel_voice: str | None = None) -> str:
    if not scenes and (script is None or not getattr(script, "scenes", None)):
        # `prior.scenes` do protótipo (sem cenas): cabeçalho "Storyboard integrado" + cartão vazio.
        # Nada de cena inventada: criar cenas é no roteiro; gerar o que falta é na produção.
        return (
            '<div class="between" style="margin-bottom:16px"><div><h2>Storyboard integrado</h2>'
            '<p class="sub">Texto, mídia, B-roll e narração de cada cena na mesma bancada. '
            "Edite sem trocar de tela.</p></div>"
            f'<div class="row"><a class="btn small" href="/studio/videos/{e(video_id)}/roteiro">+ Nova cena</a>'
            f'<a class="btn small" href="{area_href(video_id, "producao")}">Gerar tudo o que falta</a></div></div>'
            '<div class="stack"></div>'
            '<div class="card"><p class="sub">Sem cenas. Adicione a primeira cena no roteiro.</p></div>'
        )

    normalized_scenes = _normalize_scenes(scenes, script)

    pills_html = []
    for s in normalized_scenes:
        i = s["idx"]
        label = s["label"] or f"Cena {i + 1}"
        is_first = (i == 0)
        pressed = "true" if is_first else "false"
        cls = "btn small primary btn-cena-pill active" if is_first else "btn small btn-cena-pill"
        pills_html.append(
            f'<button type="button" class="{cls}" data-scene-idx="{i}" aria-pressed="{pressed}">'
            f'{i + 1} · {e(label)}{" · atualizar voz" if s["audio_state"] == "stale" else ""}'
            f'</button>'
        )

    header_card = (
        '<div id="storyboard-v3-header">'
        '<div class="between" style="margin-bottom:16px"><div><h2>Conte sua história, cena por cena</h2>'
        '<p class="sub">Selecione uma cena para editar. As demais ficam preservadas.</p></div>'
        '<div class="row">'
        '<button type="button" class="btn small" id="btn-undo-cenas" title="Desfazer alteração" disabled>↶ Desfazer</button>'
        '<button type="button" class="btn small" id="btn-redo-cenas" title="Refazer alteração" disabled>↷ Refazer</button>'
        f'<a class="btn small" href="/studio/videos/{e(video_id)}/roteiro">+ Nova cena</a>'
        '</div></div>'
        '<div class="row seletor-cenas" id="seletor-cenas" style="margin-bottom:16px">'
        + "".join(pills_html)
        + '</div></div>'
    )

    foco = normalized_scenes[0]
    f_idx = foco["idx"]
    f_label = foco["label"] or f"Cena {f_idx + 1}"
    f_asset_id = foco["asset_id"]
    audio_cls, audio_txt = _AUDIO_BADGE.get(foco["audio_state"], _AUDIO_BADGE["none"])
    voice_name = channel_voice or "Voz padrão do estúdio"
    broll_on = bool(foco.get("broll_enabled"))
    first_scene_id = foco["id"]
    script_version = getattr(script, "version", None) or (script.get("version") if isinstance(script, dict) else None) or 0
    focused_card = (
        f'<div class="scene cena-em-foco" id="cena-em-foco" data-active-idx="{f_idx}" data-video-id="{e(video_id)}" '
        f'data-script-version="{int(script_version)}">'
        '<div>'
        f'<div class="thumb" id="foco-midia-preview" style="height:132px;background:var(--panel3);'
        f'{"" if f_asset_id else "border-style:dashed;color:var(--muted);font-size:12px;text-align:center;padding:10px"}">'
        f'<img id="foco-midia-img" src="/studio/videos/{e(video_id)}/scenes/{f_idx}/asset" '
        f'alt="Mídia da cena {f_idx + 1}" style="width:100%;height:100%;object-fit:cover;'
        f'display:{"block" if f_asset_id else "none"};">'
        f'<span class="tag" id="foco-midia-tag" style="display:{"block" if f_asset_id else "none"}">Cena {f_idx + 1}</span>'
        f'<div id="foco-midia-placeholder" style="display:{"none" if f_asset_id else "block"}">'
        'Sem mídia ainda<br><span class="sample">Gere ou escolha uma imagem</span></div>'
        '</div>'
        '<div class="row" style="margin-top:8px">'
        f'<button type="button" class="btn small" id="btn-trocar-midia" data-action="trocar-midia" style="flex:1">'
        f'{"Trocar mídia" if f_asset_id else "Escolher mídia"}</button>'
        f'<label class="btn small {"" if broll_on else "ghost"}" id="lbl-broll" style="cursor:pointer;'
        f'{"border-color:var(--accent);color:var(--accent2)" if broll_on else ""}">'
        f'<input type="checkbox" id="cena-broll-enabled" name="broll_enabled"{" checked" if broll_on else ""} class="sr-only">'
        f'<span id="lbl-broll-txt">{"B-roll ativo" if broll_on else "+ B-roll"}</span>'
        '</label>'
        '</div>'
        f'<div id="cena-broll-note-wrap" style="margin-top:6px;display:{"block" if broll_on else "none"}">'
        f'<input class="sample" type="text" id="cena-broll-note" name="broll_note" aria-label="Descrição do B-roll" '
        f'style="font-size:12px;width:100%" placeholder="O que mostrar no B-roll?" value="{e(foco.get("broll_note") or "")}">'
        '</div>'
        '</div>'
        '<div>'
        '<div class="between" style="margin-bottom:6px">'
        f'<span class="num" id="foco-titulo">CENA {f_idx + 1} · {e(f_label.upper())}</span>'
        f'<span class="sample" id="foco-duracao">{e(_scene_count_text(foco))}</span>'
        '</div>'
        '<label class="sr" for="cena-narration">Texto da cena</label>'
        f'<textarea id="cena-narration" rows="4" placeholder="Texto narrado da cena...">{e(foco["narration"])}</textarea>'
        '<div class="field" style="margin:8px 0 0">'
        '<label for="cena-prompt">Prompt da imagem</label>'
        f'<input type="text" id="cena-prompt" value="{e(foco["image_prompt"])}">'
        '</div>'
        '</div>'
        '<div class="player">'
        '<div class="between">'
        '<span class="lbl">NARRAÇÃO</span>'
        f'<span class="pill {audio_cls} badge-audio" id="foco-audio-badge">{audio_txt}</span>'
        '</div>'
        f'<p class="sample" id="foco-voz-nome">{e(voice_name)}</p>'
        '<div class="prog" id="foco-prog"><b></b></div>'
        '<div class="row">'
        f'<button type="button" class="btn small primary" id="btn-ouvir-trecho" data-scene-id="{e(first_scene_id)}" '
        f'style="flex:1"{" disabled" if foco["audio_state"] == "none" else ""}>▶ Ouvir trecho</button>'
        '</div>'
        '<button type="button" class="btn small ghost long" id="btn-regenerar-voz" data-action="regenerar-voz" '
        f'style="margin-top:6px">{"Gerar áudio da cena" if foco["audio_state"] == "none" else "Regenerar áudio da cena"}</button>'
        '<div class="row" style="margin-top:8px;justify-content:space-between">'
        '<span>'
        '<button type="button" class="btn ghost small" id="btn-mover-cima" aria-label="Mover cena para cima">↑</button>'
        '<button type="button" class="btn ghost small" id="btn-mover-baixo" aria-label="Mover cena para baixo">↓</button>'
        '</span>'
        '<button type="button" class="btn ghost small" id="btn-excluir-cena" style="color:var(--bad)">Excluir</button>'
        '</div>'
        '</div>'
        '</div>'
        '<div class="row" style="margin-top:12px">'
        '<button type="button" class="btn small" id="btn-historico-voz" data-action="historico-voz">Histórico da voz</button>'
        f'<a class="btn ghost small" href="{area_href(video_id, "producao")}">Gerar tudo o que falta</a>'
        '</div>'
        '<p class="sample" id="storyboard-feedback" role="status" style="margin-top:8px"></p>'
    )

    script_content = "".join(
        f'<p style="margin-top:12px"><b>{sc["idx"] + 1}. {e(sc["label"] or "Cena " + str(sc["idx"] + 1))}</b>'
        f'<br>{e(sc["narration"])}</p>'
        for sc in normalized_scenes)

    full_script_details = (
        f'<details class="diag" id="detalhes-roteiro-completo" style="margin-top:18px">'
        f'<summary>Ver roteiro completo · {len(normalized_scenes)} cenas</summary>'
        f'{script_content}'
        f'</details>'
    )

    scenes_json = json.dumps(normalized_scenes, ensure_ascii=False).replace("</", "<\\/")
    script_data_tag = f'<script type="application/json" id="storyboard-scenes-data">{scenes_json}</script>'

    dialogs = (
        '<dialog class="modal" id="dialog-audio-history" aria-labelledby="t-audio-history">'
        '<div class="modal-card">'
        '<div class="spread" style="align-items:center;margin-bottom:10px;">'
        '<h3 id="t-audio-history" style="margin:0;">Versões da voz desta cena · Cena <span id="modal-audio-scene-num">1</span></h3>'
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
        '<h3 id="t-trocar-midia" style="margin:0;">Mídia para esta cena · Cena <span id="modal-media-scene-num">1</span></h3>'
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


def _area_composicao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None,
                     scenes=None, script=None) -> str:
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
    raw_video = getattr(view, "video", view)
    style_patch_revision = getattr(raw_video, "style_patch_revision", 0) or 0
    font_size_val = caption.get("font_size", 42)
    bottom_val = caption.get("bottom", 96)
    raw_pos = caption.get("position", "bottom")
    caption_pos = "top" if raw_pos in ("top", "topo") else ("middle" if raw_pos in ("middle", "meio") else "bottom")
    caption_font = caption.get("font_family", "dejavu")
    raw_style = caption.get("style_kind", "box")
    caption_style = "simple" if raw_style in ("simple", "simples") else "box"
    trans_kind = transition.get("kind", "fade")
    color_text_val = palette.get("caption_text", "#ffffff")
    color_box_val = palette.get("caption_box", "#00000099")
    color_accent_val = palette.get("accent", "#a78bfa")
    music_bpm = music.get("bpm", 122)
    music_seed = music.get("seed", 7)
    is_static_motion = isinstance(motion, (list, tuple)) and len(motion) == 0

    def _opt(value: str, label: str, selected: bool, disabled: bool = False) -> str:
        return (f'<option value="{value}"{" selected" if selected else ""}{" disabled" if disabled else ""}>'
                f"{e(label)}</option>")

    def _seg_radio(name: str, value: str, label: str, checked: bool) -> str:
        return (f'<label class="seg-btn"><input type="radio" class="sr-only" name="{name}" value="{value}"'
                f'{" checked" if checked else ""}>{e(label)}</label>')

    soon = '<span class="pill pill-espera">Em breve</span>'
    first_scene = next(iter(_normalize_scenes(scenes, script)), None)
    sample_text = " ".join((first_scene["narration"] if first_scene else "").split()[:6]) or "Legenda de exemplo"
    short = getattr(getattr(raw_video, "format", None), "value", getattr(raw_video, "format", "short")) == "short"
    cap_scale = 0.5 if short else 0.42
    cap_pos_css = {"top": "top:12%", "middle": "top:46%"}.get(caption_pos, f"bottom:12%")
    cap_box_css = "" if caption_style == "simple" else "background:rgba(0,0,0,.65);"
    cap_font_css = {"dejavu": "DejaVu Sans", "roboto": "Roboto", "georgia": "Georgia", "inter": "Inter"}.get(
        caption_font, "Inter")
    try:
        cap_px = round(float(font_size_val) * cap_scale)
    except (TypeError, ValueError):
        cap_px = round(42 * cap_scale)
    preview_card = (
        '<div class="card"><h3 style="margin-bottom:12px">Prévia da composição</h3>'
        f'<div class="frame {"r916" if short else "r169"}" id="frame"><div class="bg" style="background:var(--panel3)"></div>'
        '<span style="font-size:60px;position:relative">🎞️</span>'
        f'<div class="cap" id="cap" style="{cap_pos_css};font-size:{cap_px}px;{cap_box_css}'
        f'font-family:{e(cap_font_css)},sans-serif">{e(sample_text)}</div></div>'
        '<p class="sample" style="margin-top:8px;text-align:center">Prévia aproximada das legendas — '
        "não é o vídeo renderizado.</p></div>"
    )
    scene_items = _normalize_scenes(scenes, script)
    base_track = " → ".join(
        f'Cena {i + 1} ({"com mídia" if sc["asset_id"] else "sem mídia"})' for i, sc in enumerate(scene_items)
    ) or "sem cenas"
    total_secs = sum(_secs(sc["narration"]) for sc in scene_items)
    pos_label = {"top": "topo", "middle": "meio", "bottom": "base"}[caption_pos]
    if scene_items:
        broll_on = [sc for sc in scene_items if sc["broll_enabled"]]
        broll_text = (" · ".join(f'{e(sc["label"] or "Cena " + str(sc["idx"] + 1))}: {e(sc["broll_note"] or "inserto")}'
                                 for sc in broll_on)
                      or '<span style="color:var(--muted)">Nenhum B-roll ativo</span>')
        timeline_card = (
            '<div class="card"><h3 style="margin-bottom:12px">Linha do tempo</h3>'
            f'<div class="track"><span>Mídia base</span><div style="background:var(--accentbg);border-color:var(--line2);'
            f'color:var(--accent2)">{e(base_track)}</div></div>'
            f'<div class="track"><span>B-roll</span><div style="color:var(--warn)">{broll_text}</div></div>'
            f'<div class="track"><span>Narração</span><div style="color:var(--ok)">Narração contínua · ~{_fmt_t(total_secs)}</div></div>'
            f'<div class="track"><span>Música</span><div>bpm {e(str(music_bpm))} · seed {e(str(music_seed))}</div></div>'
            f'<div class="track"><span>Legendas</span><div>{e(cap_font_css)} · '
            f'{"Texto simples" if caption_style == "simple" else "Caixa discreta"} · {pos_label}</div></div></div>'
        )
    else:
        timeline_card = (
            '<div class="card"><h3 style="margin-bottom:12px">Linha do tempo</h3>'
            '<p class="sub">Sem cenas no roteiro: a linha do tempo aparece quando houver cenas.</p></div>'
        )
    style_name = _style_name(style_view) or (style.name if style is not None else None)
    parametros = (
        '<aside class="card" style="position:sticky;top:80px"><h3 style="margin-bottom:6px">Parâmetros</h3>'
        '<p class="sample" style="margin-bottom:14px">Herdados do estilo e do canal. Mudar aqui vale só para este vídeo.</p>'
        f'<form id="form-composicao" data-video-id="{e(video_id)}" data-endpoint="/studio/videos/{e(video_id)}/style-patch">'
        f'<input type="hidden" id="comp-patch-revision" value="{style_patch_revision}">'
        '<div class="field"><label for="composicao-caption-font">Fonte da legenda</label>'
        '<select id="composicao-caption-font" name="comp-fonte">'
        + _opt("dejavu", "DejaVu (padrão)", caption_font == "dejavu")
        + _opt("roboto", "Roboto", caption_font == "roboto")
        + _opt("georgia", "Georgia", caption_font == "georgia")
        + _opt("inter", "Inter", caption_font == "inter")
        + "</select></div>"
        '<div class="field"><label for="composicao-caption-style">Estilo da legenda</label>'
        '<select id="composicao-caption-style" name="comp-estilo">'
        + _opt("box", "Caixa discreta", caption_style == "box")
        + _opt("simple", "Texto simples", caption_style == "simple")
        + _opt("destaque", "Destaque por palavra (em breve)", False, disabled=True)
        + "</select></div>"
        '<div class="field"><span class="lbl">Posição</span><div class="seg" role="group">'
        + _seg_radio("comp-posicao", "top", "Topo", caption_pos == "top")
        + _seg_radio("comp-posicao", "middle", "Meio", caption_pos == "middle")
        + _seg_radio("comp-posicao", "bottom", "Base", caption_pos == "bottom")
        + "</div></div>"
        f'<div class="field"><label for="composicao-font-size">Tamanho da legenda: <b id="composicao-font-size-v">{e(str(font_size_val))}</b></label>'
        f'<input type="range" id="composicao-font-size" name="caption.font_size" min="16" max="96" value="{e(str(font_size_val))}"></div>'
        '<div class="field"><label for="composicao-bottom">Distância da base (px)</label>'
        f'<input type="number" id="composicao-bottom" name="caption.bottom" value="{e(str(bottom_val))}" min="0" max="400"'
        f'{" disabled" if caption_pos != "bottom" else ""}></div>'
        '<div class="grid2"><div class="field"><label for="composicao-music-bpm">Andamento da música (BPM)</label>'
        f'<input type="number" id="composicao-music-bpm" name="music.bpm" value="{e(str(music_bpm))}" min="20" max="300"></div>'
        '<div class="field"><label for="composicao-music-seed">Semente da música (seed)</label>'
        f'<input type="number" id="composicao-music-seed" name="music.seed" value="{e(str(music_seed))}" min="0"></div></div>'
        f'<div class="field"><label for="comp-music-vol">Volume da música {soon}</label>'
        '<input type="range" id="comp-music-vol" min="0" max="60" value="20" disabled></div>'
        f'<div class="field"><label class="tog"><input type="checkbox" id="comp-ducking" disabled><i></i>'
        f"Abaixar a música quando houver voz {soon}</label></div>"
        '<div class="grid2"><div class="field"><label for="comp-res">Resolução</label>'
        '<select id="comp-res" disabled><option>Fixa no motor</option></select></div>'
        '<div class="field"><label for="comp-fps">Quadros/s</label>'
        '<select id="comp-fps" disabled><option>25 fps (vigente)</option></select></div></div>'
        '<div class="grid2"><div class="field"><label for="composicao-transition">Transição</label>'
        '<select id="composicao-transition" name="comp-transicao">'
        + _opt("fade", "Fade suave", trans_kind == "fade")
        + _opt("none", "Corte seco", trans_kind == "none")
        + _opt("deslizar", "Deslizar (em breve)", False, disabled=True)
        + "</select></div>"
        '<div class="field"><label for="composicao-motion">Movimento</label>'
        '<select id="composicao-motion" name="motion">'
        + _opt("zoom_lento", "Zoom lento", not is_static_motion)
        + _opt("estatico", "Estático", is_static_motion)
        + "</select></div></div>"
        '<details class="diag" style="margin-bottom:14px"><summary>Cores da legenda</summary>'
        '<div class="field" style="margin-top:10px"><label for="composicao-color-text">Cor do texto da legenda</label>'
        f'<input type="text" id="composicao-color-text" name="palette.caption_text" value="{e(str(color_text_val))}"></div>'
        '<div class="field"><label for="composicao-color-box">Cor da caixa da legenda</label>'
        f'<input type="text" id="composicao-color-box" name="palette.caption_box" value="{e(str(color_box_val))}"></div>'
        '<div class="field"><label for="composicao-color-accent">Cor de destaque (accent)</label>'
        f'<input type="text" id="composicao-color-accent" name="palette.accent" value="{e(str(color_accent_val))}"></div>'
        "</details>"
        '<div class="field"><label for="comp-vstyle">Estilo visual do vídeo</label>'
        f'<select id="comp-vstyle" disabled><option>{e(style_name or "Nenhum estilo resolvido")}</option></select></div>'
        '<button type="submit" class="btn primary small long" id="btn-salvar-composicao">Salvar composição</button>'
        '<p id="composicao-feedback" class="sample" role="status" aria-live="polite" style="margin-top:8px"></p>'
        "</form></aside>"
    )
    tecnico = (
        '<details class="diag"><summary>Ver detalhes técnicos da composição</summary>'
        f'<div style="margin-top:12px">{plan_card}'
        f'<div class="card"><h2>Composição do vídeo</h2>{head}{rows}</div>{notes}</div></details>'
    )
    return f'<div class="two"><div class="stack">{preview_card}{timeline_card}{tecnico}</div>{parametros}</div>'


def _area_qualidade(view, *, style_view=None, script_view=None, video_id: str, composition_view=None, preview=None) -> str:
    # 1. Prévia da versão (`tabQA`: cartão com `.frame`; sem versão renderizada, só o aviso)
    short = getattr(getattr(view.video, "format", None), "value", getattr(view.video, "format", "short")) == "short"
    if view.stage in _PREVIEW_STAGES:
        output_asset_param = f"?output_asset_id={e(preview.output_asset_id)}" if (preview and getattr(preview, "output_asset_id", None)) else ""
        preview_card = (
            '<div class="card card-preview-destaque"><h3 style="margin-bottom:10px">Prévia da versão</h3>'
            f'<div class="frame {"r916" if short else "r169"}" style="max-width:{"230px" if short else "560px"}">'
            f'<video controls preload="metadata" poster="/studio/videos/{e(video_id)}/thumbnail" '
            f'src="/studio/videos/{e(video_id)}/file{output_asset_param}" '
            'style="width:100%;height:100%;object-fit:contain;display:block;background:#000">'
            f'<track kind="captions" srclang="pt-BR" label="Português" src="/studio/videos/{e(video_id)}/subtitles.vtt" default>'
            '</video></div>'
            f'<p style="text-align:center;margin-top:8px"><a class="btn ghost small" href="/studio/videos/{e(video_id)}/preview">Abrir prévia completa</a></p>'
            '</div>'
        )
    else:
        preview_card = (
            '<div class="card card-preview-destaque"><h3 style="margin-bottom:10px">Prévia da versão</h3>'
            '<p class="sub">Ainda não há versão renderizada. Prévia e aprovação ficam disponíveis '
            "após a renderização.</p></div>"
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

    blocks = sum(1 for sev, _ev, _cid in actionable_issues if sev == "blocking")
    warns = len(actionable_issues) - blocks
    rendered = view.stage in _PREVIEW_STAGES
    if actionable_issues or (qa is not None and not publishable):
        issues_title = "Pontos para revisar"
    else:
        issues_title = "Pronto para sua revisão"
    issue_lines = "".join(
        f'<p class="sub" style="margin-top:8px">{e(cid or "QA")} · {e(ev)}</p>'
        for _sev, ev, cid in actionable_issues)
    if not rendered:
        issue_lines = ('<p class="sub" style="margin-top:8px"><span class="pill pill-espera">Aguardando renderização</span>'
                       " Aguardando renderização do vídeo para revisão.</p>")
        issues_title = "Pontos para revisar"
    review_btn = (f'<a class="btn small" href="{area_href(video_id, "cenas")}">Revisar cenas</a>'
                  if actionable_issues else "")
    issues_card = (
        f'<div class="card card-revisao"><h3>{issues_title}</h3>{issue_lines}{review_btn}'
        '<p class="sample"><strong>Avaliação semântica não verificada:</strong> verificações técnicas. '
        "QA técnico não verifica fatos do roteiro (veracidade factual) nem a correspondência entre "
        "roteiro e imagem (depende de provider real e não é verificada aqui).</p></div>"
    )

    # 3. Verificações técnicas em detalhes expansíveis (`<details class="diag">` do protótipo)
    if qa is not None:
        qa_html = (
            '<div class="card"><h3>Relatório de QA do render</h3>'
            '<p class="sub" style="margin:2px 0 14px">Verificações automatizadas do renderizador: integridade '
            "do contêiner, taxa de quadros, loudness de áudio e conformidade de legenda.</p>"
            + _kv("Publicável", "sim" if publishable else "não")
            + _kv("Cobertura", e(coverage_status))
            + _kv("Achados", str(len(findings)))
        )
        if findings:
            findings_items = "".join(
                f'<div class="gate"><div><b style="font-size:13px">{e(getattr(f, "check_id", "CHECK"))}</b>'
                f'<small>{e(getattr(f, "evidence", str(f)))}</small></div>'
                f'<span class="pill {"bad" if getattr(f, "severity", "info") == "blocking" else "warn"}">'
                f'{"✕ Bloqueia" if getattr(f, "severity", "info") == "blocking" else "! Atenção"}</span></div>'
                for f in findings
            )
            qa_html += f'<div class="stack" style="gap:8px;margin-top:12px">{findings_items}</div>'
        qa_html += "</div>"
    else:
        qa_html = (
            '<div class="card"><h3>Relatório de QA do render</h3>'
            '<p class="aviso">Relatório de QA do render não disponível nesta leitura.</p></div>'
        )
    technical_details = (
        '<details class="diag"><summary>Ver todas as verificações técnicas</summary>'
        f'<div style="margin-top:12px">{qa_html}</div></details>'
    )

    # 4. Aside "Aprovação" (`tabQA`): nota de bloqueios/avisos + ação de aprovação
    if blocks:
        note_cls, note_msg = "note", "Resolva os bloqueios no storyboard antes de aprovar."
    elif not rendered:
        note_cls, note_msg = "note", "Aprovação disponível após a renderização."
    else:
        note_cls, note_msg = "note okn", "Elegível para aprovação."
    note = (f'<div class="{note_cls}" style="margin-bottom:14px"><b>{blocks} bloqueio(s) · {warns} aviso(s)</b>'
            f"<br>{note_msg}</div>")
    if view.stage in (Stage.APPROVED, Stage.COMPLETED):
        actions = (
            '<div class="note okn" style="margin-bottom:12px">✓ Versão aprovada.</div>'
            f'<div class="stack" style="gap:8px"><a class="btn primary long" href="{area_href(video_id, "publicacao")}">'
            "Ir para publicação →</a></div>"
        )
    else:
        disabled = "" if rendered else " disabled"
        actions = (
            '<div class="stack" style="gap:8px">'
            f'<button type="button" class="btn ok long" data-a="approve" data-video-id="{e(video_id)}" '
            f'id="btn-approve-video"{disabled}>✓ Aprovar e preparar publicação →</button>'
            f'<a class="btn ghost long small" href="{area_href(video_id, "cenas")}">Pedir ajustes (volta ao storyboard)</a>'
            '<span id="approve-feedback" class="feedback" role="status" aria-live="polite"></span></div>'
        )
    aside = (
        '<aside class="card" style="position:sticky;top:80px"><h3>Aprovação desta versão</h3>'
        '<p class="sub" style="margin:4px 0 12px">Aprovar marca esta versão como a oficial. '
        "Publicar é um passo separado.</p>"
        f'{note}<p class="sub" style="margin-bottom:10px">{e(approval_text)}</p>{actions}</aside>'
    )
    script_line = ""
    if script_view is not None and script_view.has_script:
        script_line = (f'<p class="sub" style="margin:-4px 0 12px">Aprovação do roteiro: '
                       f'{"aprovada" if script_view.approved else "não registrada"}.</p>')
    aside = aside.replace("</aside>", f"{script_line}</aside>") if script_line else aside
    return f'<div class="two"><div class="stack">{preview_card}{issues_card}{technical_details}</div>{aside}</div>'


def _area_publicacao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None, preview=None,
                     channel_name: str = "") -> str:
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
        summary = f'<div class="card flat"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
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
        summary = f'<div class="card flat"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    elif pub is not None:
        status_value = getattr(pub.status, "value", str(pub.status))
        rows = _kv("Situação", e(status_value)) + _kv("Tentativa", str(pub.attempt))
        if pub.error:
            rows += _kv("Erro registrado", e(pub.error))
        summary = f'<div class="card flat"><h3>Publicação</h3><p class="muted">Registro de publicação deste vídeo.</p>{rows}</div>'
    else:
        summary = ('<div class="card flat"><h3>Publicação</h3>'
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
        '<div id="card-opcoes-publicacao" style="margin-top:14px">'
        f'{dirty_html}'
        f'{scheduled_note}'
        '<div class="field"><span class="lbl">Modalidade de publicação</span>'
        '<div class="seg" role="group">'
        f'<label class="seg-btn"><input type="radio" class="sr-only" name="tipo-publicacao" id="publicar-agora" value="imediato"{checked_now}>Publicar agora</label>'
        f'<label class="seg-btn"><input type="radio" class="sr-only" name="tipo-publicacao" id="agendar-publicacao" value="agendado"{checked_sched}>Agendar publicação</label>'
        '</div></div>'
        f'<div class="field campo-agendamento" id="bloco-agendamento"{sched_style}>'
        '<label for="agendamento-data">Data e horário de publicação</label>'
        f'<input type="datetime-local" id="agendamento-data" name="agendamento-data" value="{e(sched_input_val)}">'
        '<p class="sample">Horário de Brasília · UTC−03:00. Agendar não publica agora.</p>'
        '<span id="agendamento-feedback" class="feedback" role="status" aria-live="polite"></span>'
        '</div>'
        '</div>'
    )

    # W5.1 (PUB-01): o formulário de aprovação vive aqui agora. Quando a prévia está disponível,
    # o mesmo bloco da página de prévia é renderizado (sem duplicar HTML); a prévia completa
    # continua acessível pelo link. Mudar destino/metadados torna a intenção obsoleta no servidor
    # (A19/A37) e exige uma confirmação nova.
    if preview is not None:
        decision = approval_form.render_approval_decision(preview, bare=True)
        reviewable = preview.video.status in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED)
    else:
        decision = ""
        reviewable = view.stage in _PREVIEW_STAGES
    heading = ('<div class="note" id="publicacao-intencao"><b>A confirmação de publicação vive aqui.</b> '
               "Trocar o destino do YouTube ou título/descrição/tags/visibilidade depois de aprovar "
               "invalida a intenção anterior: será preciso confirmar de novo (A19).</div>")

    approved = view.stage in (Stage.APPROVED, Stage.COMPLETED) or is_published
    gate_note = ""
    if not approved and not reviewable:
        gate_note = ('<div class="note" style="margin-bottom:14px">Aprove uma versão na aba Qualidade para liberar '
                     f'a publicação. <a class="btn small" href="{area_href(video_id, "qualidade")}">Ir para Qualidade</a></div>')

    if reviewable:
        preview_html = (f'<p style="margin-top:12px"><a class="btn small" href="/studio/videos/{e(video_id)}/preview">'
                        "Abrir prévia completa</a></p>")
    else:
        preview_html = '<p class="sample" style="margin-top:12px">A prévia fica disponível após a renderização.</p>'

    left = (
        '<div class="card"><h3 style="margin-bottom:12px">Dados de publicação no YouTube</h3>'
        f"{gate_note}{summary}{heading}{decision}{options_card}{preview_html}</div>"
    )
    destino = (e(channel_name) if channel_name else "Canal do vídeo")
    if is_published:
        action = '<div class="note okn">✓ Publicado.</div>'
    else:
        action = (f'<button type="button" class="btn ok long" id="btn-publicar-acao" data-video-id="{e(video_id)}">'
                  f"{action_btn_text}</button>"
                  '<div style="margin-top:8px"><a class="btn small long" href="/studio/panel/conexoes">Abrir Conexões</a></div>'
                  '<p class="sample" style="margin-top:10px">Nada é enviado sem este clique.</p>')
    aside = (
        '<aside class="card" style="position:sticky;top:80px"><div class="between"><h3>Canal de destino</h3></div>'
        f'<div class="card flat" style="margin:12px 0"><b>{destino}</b>'
        '<p class="sample">Sem destino YouTube conectado e autorização vigente, a publicação é recusada '
        "(o gate falha fechado — renderer/app/studio/domain/channel.py). Conecte o canal em "
        "Configurações → Conexões antes de publicar.</p></div>"
        f"{action}</aside>"
    )
    return f'<div class="two">{left}{aside}</div>'


_STEP_ICON = {"SUCCEEDED": ("ok", "✓"), "RUNNING": ("run", "…"), "FAILED": ("fail", "✕")}
_STEP_TEXT = {"SUCCEEDED": "Concluída", "RUNNING": "Em andamento", "FAILED": "Falhou"}


def _usd(value: float | None) -> str:
    return "não medido" if value is None else "US$ " + f"{value:.2f}".replace(".", ",")


def _area_producao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    """`tabProd` do protótipo: "Etapas da produção" + aside "Custo do vídeo" e "Diagnóstico técnico".

    As etapas e o custo por etapa vêm do que foi registrado (`view.steps`, `view.usage`); etapa sem
    uso medido mostra "não medido" e nunca entra como zero. O cartão real de produção
    (iniciar/retomar/nova produção, com o motivo do servidor) fica logo abaixo.
    """
    steps = list(getattr(view, "steps", None) or [])
    usage = list(getattr(view, "usage", None) or [])
    cost_by_step: dict[str, float] = {}
    for u in usage:
        cost_by_step[u.step] = cost_by_step.get(u.step, 0.0) + float(u.cost_usd)
    rows = []
    for st in steps:
        icon_cls, icon = _STEP_ICON.get(st.status, ("", "○"))
        err = (f'<p style="color:var(--bad);font-size:12.5px">{e(st.error_message or st.error_class)}</p>'
               if st.status == "FAILED" and (st.error_message or st.error_class) else "")
        label = legacy._PRODUCTION_STAGE_LABELS.get(st.step, st.step)
        rows.append(
            f'<div class="step"><span class="ic {icon_cls}">{icon}</span><div style="flex:1"><b>{e(label)}</b>{err}'
            f'<p class="sample">{_STEP_TEXT.get(st.status, "Aguardando")}</p></div>'
            f'<span class="sample">{_usd(cost_by_step.get(st.step))}</span></div>')
    steps_html = "".join(rows) or '<p class="sub" style="margin-top:8px">Nenhuma etapa executada ainda.</p>'
    steps_card = (f'<div class="card"><div class="between"><h3>Etapas da produção</h3></div>'
                  f'<div style="margin-top:8px">{steps_html}</div></div>')
    measured = sum(cost_by_step.values())
    partial = bool(steps) and any(st.step not in cost_by_step for st in steps)
    cost_card = (
        '<div class="card"><h3>Custo do vídeo</h3>'
        f'<p style="font-size:22px;font-weight:760;margin:6px 0">{e(view.cost_text)}</p>'
        f'<p class="sample">{"Etapas sem custo medido não são somadas como zero." if partial else "Custo registrado pelo uso real do vídeo."}'
        f'{" Soma medida: " + _usd(measured) + "." if usage else ""}</p></div>'
    )
    run = getattr(view, "latest_run", None)
    mode = getattr(getattr(view.video, "production_mode", None), "value", getattr(view.video, "production_mode", ""))
    diag = (
        '<details class="diag"><summary>Diagnóstico técnico</summary>'
        f'<p class="mono" style="margin-top:8px">video_id={e(video_id)}<br>modo={e(mode)}'
        f'<br>estado={e(view.stage.value)}'
        f'{"<br>execução=" + e(run.run_id) + " (" + e(run.state) + ")" if run is not None else ""}</p></details>'
    )
    return (f'<div class="two"><div class="stack">{steps_card}{legacy._video_run_card(view)}</div>'
            f'<aside class="stack">{cost_card}{diag}</aside></div>')


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


def _dock(view, video_id: str, scenes, script) -> str:
    """`dock(v)` do protótipo: resumo fixo no rodapé, nas abas Cenas e Composição."""
    items = _normalize_scenes(scenes, script)
    if view.stage == Stage.COMPLETED:
        return ('<div class="dock"><span class="sub">Publicado.</span>'
                f'<a class="btn small" href="{area_href(video_id, "publicacao")}">Ver publicação</a></div>')
    total = sum(_secs(sc["narration"]) for sc in items)
    missing = sum(1 for sc in items if not sc["asset_id"] or sc["audio_state"] != "ok")
    needs = view.stage in (Stage.PENDING, Stage.FAILED)
    aviso = (f'<span class="pill warn">{missing} cena(s) sem mídia ou áudio atual</span>'
             if needs and missing else "")
    if needs:
        acao = f'<a class="btn primary" href="{area_href(video_id, "producao")}">🎬 Gerar o que falta e renderizar</a>'
    else:
        acao = f'<a class="btn ok" href="{area_href(video_id, "qualidade")}">Ir para aprovação →</a>'
    return (f'<div class="dock"><div class="row"><b>{len(items)} cenas</b>'
            f'<span class="sub">~{_fmt_t(total)} · estimativa de custo não disponível</span>{aviso}</div>'
            f'<div class="row">{acao}</div></div>')


def _content(view, area: str, *, style_view, script_view, video_id, composition_view=None, preview=None,
             scenes=None, script=None, channel_voice: str | None = None, channel_name: str = "") -> str:
    if area == "publicacao":
        return _area_publicacao(view, style_view=style_view, script_view=script_view,
                                video_id=video_id, preview=preview, channel_name=channel_name)
    if area == "qualidade":
        return _area_qualidade(view, style_view=style_view, script_view=script_view,
                               video_id=video_id, composition_view=composition_view,
                               preview=preview)
    if area == "cenas":
        return _area_cenas(view, style_view=style_view, script_view=script_view, video_id=video_id,
                           composition_view=composition_view, scenes=scenes, script=script,
                           channel_voice=channel_voice) + _dock(view, video_id, scenes, script)
    if area == "composicao":
        return _area_composicao(view, style_view=style_view, script_view=script_view, video_id=video_id,
                                composition_view=composition_view, scenes=scenes,
                                script=script) + _dock(view, video_id, scenes, script)
    return _AREA_RENDERERS[area](
        view, style_view=style_view, script_view=script_view, video_id=video_id,
        composition_view=composition_view,
    )


PAGE_JS = """
(function () {
  var runFeedback = document.getElementById('video-run-feedback');
  var dlgFonte = document.getElementById('dlg-fonte');
  var btnFonte = document.getElementById('btn-abrir-fonte');
  if (dlgFonte && btnFonte) {
    btnFonte.addEventListener('click', function () {
      if (typeof dlgFonte.showModal === 'function') dlgFonte.showModal(); else dlgFonte.setAttribute('open', '');
      var u = document.getElementById('source-url'); if (u) u.focus();
    });
    dlgFonte.addEventListener('click', function (ev) {
      if (ev.target === dlgFonte || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlgFonte.close();
    });
  }
  var dlgVersoes = document.getElementById('dlg-versoes');
  var btnVersoes = document.getElementById('btn-versoes');
  if (dlgVersoes && btnVersoes) {
    btnVersoes.addEventListener('click', function () {
      if (typeof dlgVersoes.showModal === 'function') dlgVersoes.showModal(); else dlgVersoes.setAttribute('open', '');
    });
    dlgVersoes.addEventListener('click', function (ev) {
      if (ev.target === dlgVersoes || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlgVersoes.close();
    });
  }

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

  var AUDIO_BADGE = {
    ok: ['ok', '\u2713 \u00c1udio atual'],
    stale: ['warn', '\u00c1udio desatualizado'],
    none: ['bad', 'Sem \u00e1udio ainda']
  };
  function setBadge(badge, state) {
    var b = AUDIO_BADGE[state] || AUDIO_BADGE.none;
    badge.textContent = b[1];
    badge.className = 'pill ' + b[0] + ' badge-audio';
  }
  function countText(s) {
    var words = ((s.narration || '').trim().match(/\\S+/g) || []).length;
    var secs = (typeof s.duration_s === 'number' && s.duration_s) ? (s.duration_s.toFixed(1) + 's')
      : ('~' + Math.max(2, Math.round(words / 2.6)) + 's');
    return words + ' palavras \u00b7 ' + secs;
  }
  function syncBroll() {
    var chk = document.getElementById('cena-broll-enabled');
    var lbl = document.getElementById('lbl-broll');
    var txt = document.getElementById('lbl-broll-txt');
    if (!chk || !lbl) return;
    lbl.classList.toggle('ghost', !chk.checked);
    lbl.style.borderColor = chk.checked ? 'var(--accent)' : '';
    lbl.style.color = chk.checked ? 'var(--accent2)' : '';
    if (txt) txt.textContent = chk.checked ? 'B-roll ativo' : '+ B-roll';
  }

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
        pill.classList.add('active', 'primary');
      } else {
        pill.classList.remove('active', 'primary');
      }
    });

    var card = document.getElementById('cena-em-foco');
    if (card) card.setAttribute('data-active-idx', String(idx));

    var titulo = document.getElementById('foco-titulo');
    if (titulo) titulo.textContent = 'CENA ' + (idx + 1) + ' · ' + (s.label || ('Cena ' + (idx + 1))).toUpperCase();

    var duracao = document.getElementById('foco-duracao');
    if (duracao) duracao.textContent = countText(s);

    var badge = document.getElementById('foco-audio-badge');
    if (badge) {
      setBadge(badge, s.audio_state);
    }

    var nar = document.getElementById('cena-narration');
    if (nar) nar.value = s.narration || '';

    var prm = document.getElementById('cena-prompt');
    if (prm) prm.value = s.image_prompt || '';

    var brollChk = document.getElementById('cena-broll-enabled');
    if (brollChk) brollChk.checked = Boolean(s.broll_enabled);
    syncBroll();

    var brollNote = document.getElementById('cena-broll-note');
    if (brollNote) brollNote.value = s.broll_note || '';

    var brollWrap = document.getElementById('cena-broll-note-wrap');
    if (brollWrap) brollWrap.style.display = s.broll_enabled ? 'block' : 'none';

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
        placeholder.style.display = 'block';
      }
      var prev = document.getElementById('foco-midia-preview');
      if (prev) prev.style.borderStyle = s.asset_id ? '' : 'dashed';
      var tag = document.getElementById('foco-midia-tag');
      if (tag) { tag.textContent = 'Cena ' + (idx + 1); tag.style.display = s.asset_id ? 'block' : 'none'; }
      var tb = document.getElementById('btn-trocar-midia');
      if (tb) tb.textContent = s.asset_id ? 'Trocar m\u00eddia' : 'Escolher m\u00eddia';
    }

    var numAudio = document.getElementById('modal-audio-scene-num');
    if (numAudio) numAudio.textContent = String(idx + 1);

    var numMedia = document.getElementById('modal-media-scene-num');
    if (numMedia) numMedia.textContent = String(idx + 1);

    var mediaPrompt = document.getElementById('trocar-midia-prompt');
    if (mediaPrompt) mediaPrompt.value = s.image_prompt || '';

    renderAudioHistory(idx);
  }
  var renderActiveScene = focusScene;

  var mediaImg = document.getElementById('foco-midia-img');
  if (mediaImg) {
    mediaImg.addEventListener('error', function () {
      mediaImg.style.display = 'none';
      var placeholder = document.getElementById('foco-midia-placeholder');
      if (placeholder) placeholder.style.display = 'block';
      var tagErr = document.getElementById('foco-midia-tag');
      if (tagErr) tagErr.style.display = 'none';
      var prevErr = document.getElementById('foco-midia-preview');
      if (prevErr) prevErr.style.borderStyle = 'dashed';
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
            setBadge(badge, 'ok');
          }
          if (pill) {
            var label = s.label || ('Cena ' + (currentActiveIdx + 1));
            pill.textContent = (currentActiveIdx + 1) + ' · ' + label;
          }
        } else {
          s.audio_state = 'stale';
          if (badge) {
            setBadge(badge, 'stale');
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
        var cnt = document.getElementById('foco-duracao');
        if (cnt) cnt.textContent = countText(scenesData[currentActiveIdx]);
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

  var initBrollChk = document.getElementById('cena-broll-enabled');
  var initBrollWrap = document.getElementById('cena-broll-note-wrap');
  if (initBrollChk && initBrollWrap) {
    initBrollWrap.style.display = initBrollChk.checked ? 'block' : 'none';
  }

  var brollChkEl = document.getElementById('cena-broll-enabled');
  if (brollChkEl) {
    brollChkEl.addEventListener('change', function () {
      pushSnapshot();
      var enabled = Boolean(brollChkEl.checked);
      if (scenesData[currentActiveIdx]) {
        scenesData[currentActiveIdx].broll_enabled = enabled;
      }
      var wrap = document.getElementById('cena-broll-note-wrap');
      if (wrap) wrap.style.display = enabled ? 'block' : 'none';
      syncBroll();
    });
  }

  var isEditingBrollNote = false;
  var brollNoteEl = document.getElementById('cena-broll-note');
  if (brollNoteEl) {
    brollNoteEl.addEventListener('focusin', function () {
      if (!isEditingBrollNote) {
        pushSnapshot();
        isEditingBrollNote = true;
      }
    });
    brollNoteEl.addEventListener('input', function () {
      if (!isEditingBrollNote) {
        pushSnapshot();
        isEditingBrollNote = true;
      }
      if (scenesData[currentActiveIdx]) {
        scenesData[currentActiveIdx].broll_note = brollNoteEl.value;
      }
    });
    brollNoteEl.addEventListener('blur', function () {
      isEditingBrollNote = false;
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

  // ---- ações reais da cena em foco: ouvir, regenerar voz, mover e excluir ----
  var sbCard = document.getElementById('cena-em-foco');
  var sbVideoId = sbCard ? (sbCard.getAttribute('data-video-id') || '') : '';
  var sbVersion = sbCard ? Number(sbCard.getAttribute('data-script-version') || 0) : 0;
  var sbFeedback = document.getElementById('storyboard-feedback');

  function sbSay(text) { if (sbFeedback) sbFeedback.textContent = text; }
  function sbCall(method, url, body) {
    var key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
    var payload = body ? Object.assign({ idempotency_key: key }, body) : null;
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: payload ? JSON.stringify(payload) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; });
    });
  }
  function sbDetail(d, fallback) { return (d && typeof d.detail === 'string') ? d.detail : fallback; }
  function sbSyncMove() {
    var up = document.getElementById('btn-mover-cima');
    var down = document.getElementById('btn-mover-baixo');
    if (up) up.disabled = currentActiveIdx <= 0 || !sbVersion;
    if (down) down.disabled = currentActiveIdx >= scenesData.length - 1 || !sbVersion;
  }
  var sbFocus = focusScene;
  focusScene = function (idx) { sbFocus(idx); sbSyncMove(); syncPlayer(); };

  var sbAudio = null;
  function syncPlayer() {
    var s = scenesData[currentActiveIdx];
    var play = document.getElementById('btn-ouvir-trecho');
    var regen = document.getElementById('btn-regenerar-voz');
    if (sbAudio) { sbAudio.pause(); sbAudio = null; }
    var prog = document.getElementById('foco-prog');
    if (prog) prog.classList.remove('run');
    if (play) { play.textContent = '\u25b6 Ouvir trecho'; play.disabled = !s || s.audio_state === 'none'; }
    if (regen && s) regen.textContent = s.audio_state === 'none' ? 'Gerar \u00e1udio da cena' : 'Regenerar \u00e1udio da cena';
  }
  var playBtn = document.getElementById('btn-ouvir-trecho');
  if (playBtn) {
    playBtn.addEventListener('click', function () {
      var s = scenesData[currentActiveIdx];
      if (!s) return;
      var prog = document.getElementById('foco-prog');
      if (sbAudio) { syncPlayer(); return; }
      sbAudio = new Audio('/studio/videos/' + encodeURIComponent(sbVideoId) + '/scenes/' +
                          encodeURIComponent(s.id) + '/narration.wav?t=' + Date.now());
      sbAudio.addEventListener('ended', syncPlayer);
      sbAudio.addEventListener('error', function () { syncPlayer(); sbSay('N\u00e3o foi poss\u00edvel carregar o \u00e1udio desta cena.'); });
      sbAudio.play().then(function () {
        playBtn.textContent = '\u25a0 Parar';
        if (prog) { prog.style.setProperty('--d', (s.duration_s || 3) + 's'); prog.classList.add('run'); }
      }).catch(function () { syncPlayer(); sbSay('N\u00e3o foi poss\u00edvel tocar o \u00e1udio desta cena.'); });
    });
  }
  var regenBtn = document.getElementById('btn-regenerar-voz');
  if (regenBtn) {
    regenBtn.addEventListener('click', function () {
      var s = scenesData[currentActiveIdx];
      if (!s) return;
      regenBtn.disabled = true;
      sbSay('Gerando o \u00e1udio da cena\u2026');
      sbCall('POST', '/studio/videos/' + encodeURIComponent(sbVideoId) + '/scenes/' +
             encodeURIComponent(s.id) + '/narration/regenerate').then(function (res) {
        regenBtn.disabled = false;
        if (res.ok) {
          s.audio_state = 'ok';
          if (typeof res.data.duration_s === 'number') s.duration_s = res.data.duration_s;
          var badge = document.getElementById('foco-audio-badge');
          if (badge) setBadge(badge, 'ok');
          var dur = document.getElementById('foco-duracao');
          if (dur) dur.textContent = countText(s);
          syncPlayer();
          sbSay('\u00c1udio da cena atualizado.');
        } else {
          sbSay('N\u00e3o foi poss\u00edvel gerar o \u00e1udio: ' + sbDetail(res.data, 'tente novamente.'));
        }
      }).catch(function () { regenBtn.disabled = false; sbSay('Falha de rede ao gerar o \u00e1udio.'); });
    });
  }
  function sbMove(delta) {
    var from = currentActiveIdx, to = from + delta;
    if (!sbVersion || to < 0 || to >= scenesData.length) return;
    var order = scenesData.map(function (_s, i) { return i; });
    order[from] = to; order[to] = from;
    sbSay('Reordenando\u2026');
    sbCall('POST', '/studio/videos/' + encodeURIComponent(sbVideoId) + '/script/scenes/reorder',
           { expected_version: sbVersion, order: order }).then(function (res) {
      if (res.ok) { location.reload(); }
      else { sbSay('N\u00e3o foi poss\u00edvel reordenar: ' + sbDetail(res.data, 'tente novamente.')); }
    }).catch(function () { sbSay('Falha de rede ao reordenar.'); });
  }
  var upBtn = document.getElementById('btn-mover-cima');
  var downBtn = document.getElementById('btn-mover-baixo');
  if (upBtn) upBtn.addEventListener('click', function () { sbMove(-1); });
  if (downBtn) downBtn.addEventListener('click', function () { sbMove(1); });
  var delBtn = document.getElementById('btn-excluir-cena');
  if (delBtn) {
    delBtn.addEventListener('click', function () {
      if (!sbVersion) return;
      if (!window.confirm('Excluir a cena ' + (currentActiveIdx + 1) + '? Esta a\u00e7\u00e3o cria uma nova vers\u00e3o do roteiro.')) return;
      sbSay('Excluindo\u2026');
      sbCall('DELETE', '/studio/videos/' + encodeURIComponent(sbVideoId) + '/script/scenes/' + currentActiveIdx,
             { expected_version: sbVersion }).then(function (res) {
        if (res.ok) { location.reload(); }
        else { sbSay('N\u00e3o foi poss\u00edvel excluir: ' + sbDetail(res.data, 'tente novamente.')); }
      }).catch(function () { sbSay('Falha de rede ao excluir.'); });
    });
  }
  sbSyncMove();

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

  // Composição V3: submissão de alterações de estilo (PATCH /studio/videos/{id}/style-patch)
  var compForm = document.getElementById('form-composicao');
  if (compForm) {
    var compBottomInput = document.getElementById('composicao-bottom');
    var compPosRadios = compForm.querySelectorAll('input[name="comp-posicao"]');
    var fsRange = document.getElementById('composicao-font-size');
    var fsOut = document.getElementById('composicao-font-size-v');
    if (fsRange && fsOut) fsRange.addEventListener('input', function () { fsOut.textContent = fsRange.value; });
    function syncBottomInputState() {
      var checkedPos = compForm.querySelector('input[name="comp-posicao"]:checked');
      if (compBottomInput && checkedPos) {
        compBottomInput.disabled = (checkedPos.value !== 'bottom');
      }
    }
    compPosRadios.forEach(function (radio) {
      radio.addEventListener('change', syncBottomInputState);
    });
    syncBottomInputState();

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
      var bpmInput = document.getElementById('composicao-music-bpm');
      var seedInput = document.getElementById('composicao-music-seed');
      var revInput = document.getElementById('comp-patch-revision');
      var expectedRev = revInput ? Number(revInput.value) || 0 : 0;

      var posRadio = compForm.querySelector('input[name="comp-posicao"]:checked');
      var fontSelect = document.getElementById('composicao-caption-font');
      var estiloRadio = compForm.querySelector('[name="comp-estilo"]');
      var transRadio = compForm.querySelector('[name="comp-transicao"]');

      var captionPos = posRadio ? posRadio.value : 'bottom';
      var captionFont = fontSelect ? fontSelect.value : 'dejavu';
      var captionEstilo = estiloRadio ? estiloRadio.value : 'box';
      var transKind = transRadio ? transRadio.value : 'fade';
      var transTicks = transKind === 'fade' ? 25 : 0;

      var captionObj = {
        font_size: fontSizeInput ? Number(fontSizeInput.value) || 42 : 42,
        position: captionPos,
        font_family: captionFont,
        style_kind: captionEstilo
      };
      if (captionPos === 'bottom') {
        captionObj.bottom = bottomInput ? Number(bottomInput.value) || 96 : 96;
      }

      var patch = {
        caption: captionObj,
        transition: {
          kind: transKind,
          duration_ticks: transTicks
        },
        palette: {
          caption_text: colorTextInput ? colorTextInput.value.trim() : '#ffffff',
          caption_box: colorBoxInput ? colorBoxInput.value.trim() : '#00000099',
          accent: colorAccentInput ? colorAccentInput.value.trim() : '#a78bfa'
        },
        motion: (motionInput && motionInput.value === 'estatico') ? [] : ['zoom_in', 'pan_left'],
        music: {
          bpm: bpmInput ? Number(bpmInput.value) || 122 : 122,
          seed: seedInput ? Number(seedInput.value) || 7 : 7
        }
      };

      var payload = {
        expected_revision: expectedRev,
        patch: patch
      };

      if (button) { button.disabled = true; button.classList.add('carregando'); }
      if (window.StudioLoading) window.StudioLoading.start();
      if (feedback) feedback.textContent = 'Salvando composição...';

      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/style-patch', {
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


def _style_name(style_view) -> str | None:
    """Nome do estilo efetivo do vídeo (override ou herdado do canal); None se não houver."""
    if style_view is None:
        return None
    override = getattr(style_view, "override_style_id", None)
    if override:
        for style in getattr(style_view, "styles", ()) or ():
            if getattr(style, "id", None) == override:
                return style.name
        return None
    return getattr(style_view, "inherited_style_name", None) or None


def _version_dialog(view) -> str:
    """Histórico de versões do protótipo, só com o que existe: a versão renderizada, se houver."""
    if view.stage in _PREVIEW_STAGES:
        body = ('<div class="between" style="padding:8px 0;border-bottom:1px solid var(--line)">'
                '<b>Versão atual</b><span class="sub">renderizada · as versões anteriores não são '
                "registradas nesta tela</span></div>")
    else:
        body = '<p class="sub">Nenhuma versão renderizada.</p>'
    return (
        '<dialog id="dlg-versoes" class="modal" aria-labelledby="t-versoes">'
        '<div class="modal-header"><h2 id="t-versoes">Histórico de versões</h2>'
        '<button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>'
        f'<div class="dialogo-corpo"><div style="margin:10px 0">{body}</div>'
        '<button class="btn small" type="button" data-fechar-dialogo>Fechar</button></div></dialog>'
    )


def _workspace_header(view, video_id: str, title: str, *, channel_name: str = "", style_view=None,
                      channel_voice: str | None = None) -> str:
    """Cabeçalho de `pgVideo`: voltar + caminho, eyebrow de modo, h1, pills e ações."""
    mode = getattr(view.video, "production_mode", None)
    mode_value = getattr(mode, "value", mode)
    eyebrow = "🎬 Modo Diretor" if mode_value == "diretor" else "⚡ Criado no piloto automático"
    label, tone = _ESTADO.get(view.stage, (view.stage.value, ""))
    fmt = getattr(getattr(view.video, "format", None), "value", getattr(view.video, "format", None))
    pills = [f'<span class="pill {tone}">{e(label)}</span>',
             f'<span class="pill">{"Short 9:16" if fmt == "short" else "Vídeo 16:9"}</span>']
    if channel_voice:
        pills.append(f'<span class="pill">🎙 {e(channel_voice)}</span>')
    style_name = _style_name(style_view)
    if style_name:
        pills.append(f'<span class="pill">🎨 {e(style_name)}</span>')
    editar = ""
    if mode_value != "diretor" and view.stage != Stage.PENDING:
        editar = f'<a class="btn small" href="{area_href(video_id, "cenas")}">Editar no Modo Diretor</a>'
    caminho = f"{e(channel_name)} / {e(title)}" if channel_name else e(title)
    return f"""        <p class="sub" style="margin-bottom:8px"><a class="btn ghost small" href="/studio/panel/videos">← Vídeos</a> &nbsp; {caminho}</p>
        <div class="head"><div><p class="eyebrow">{eyebrow}</p><h1 id="t-video">{e(title)}</h1>
          <div class="row" style="margin-top:6px">{"".join(pills)}</div></div>
          <div class="row">{editar}<button class="btn small" type="button" id="btn-versoes">Histórico de versões</button></div>
          <a class="btn ghost small" href="{area_href(video_id, "producao")}">Ver progresso / Diagnóstico</a></div>
        {_version_dialog(view)}"""


def _progress_card(view) -> str:
    """Cartão de `progressCard` — só quando há produção em andamento, com as etapas registradas."""
    if view.stage != Stage.IN_PRODUCTION:
        return ""
    steps = list(view.steps or [])
    done = sum(1 for s in steps if s.status == "SUCCEEDED")
    total = len(steps)
    pct = round(done / total * 100) if total else 0
    pills = "".join(
        f'<span class="pill {"ok" if s.status == "SUCCEEDED" else "accent" if s.status == "RUNNING" else "bad" if s.status == "FAILED" else ""}">'
        f'{"✓" if s.status == "SUCCEEDED" else "…" if s.status == "RUNNING" else "✕" if s.status == "FAILED" else "○"} '
        f'{e(legacy._PRODUCTION_STAGE_LABELS.get(s.step, s.step))}</span>'
        for s in steps)
    return (
        '<div class="card" style="border-color:var(--accent);margin-bottom:18px"><div class="between"><div>'
        "<h3>⚡ Produção em andamento</h3>"
        '<p class="sub">Roteiro → voz → mídia → composição → qualidade. Ao terminar, abre na aprovação.</p></div>'
        f'<span class="pill accent">{done}/{total} etapas</span></div>'
        f'<div class="prog" style="height:8px;margin-top:12px"><b style="width:{pct}%;transition:width .5s"></b></div>'
        f'<div class="row" style="margin-top:8px">{pills}</div></div>'
    )


def render_video_workspace(view, area: str = "cenas", *, active_area: str | None = None,
                           style_view=None, script_view=None,
                           composition_view=None, preview=None, projects=(), project_id: str = "",
                           channel_name: str = "", script=None, scenes=None,
                           sources=None, channel_voice: str | None = None) -> WorkspaceResult:
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

    dots = {}
    if view.stage == Stage.AWAITING_APPROVAL:
        dots["qualidade"] = "Aguardando você"
    body_html = f"""      <section class="pagina" id="pagina-video-workspace" aria-labelledby="t-video">
{_workspace_header(view, video_id, title, channel_name=channel_name, style_view=style_view,
                   channel_voice=channel_voice)}
        {_video_area_nav(video_id, active_area, dots)}
        {_progress_card(view)}
        {_content(view, active_area, style_view=style_view, script_view=script_view, video_id=video_id,
                  composition_view=composition_view,
                  preview=preview if active_area in ("publicacao", "qualidade") else None,
                  scenes=scenes, script=script, channel_voice=channel_voice, channel_name=channel_name)}
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
