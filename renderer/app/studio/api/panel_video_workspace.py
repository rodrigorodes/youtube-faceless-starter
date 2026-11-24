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
from .publicacao_js import PUBLICACAO_JS, explicar_motivo
from . import panel as legacy
from . import shell_v3
from .falha_producao import explicar_falha
from .panel_videos import _ESTADO

# Ordem e rótulos do protótipo (`VIDEO_TABS`). A fonte única é `panel_video_nav` (a página legada
# do vídeo também usa a nav, sem import circular). Os nomes seguem reexportados daqui.
from .panel_video_storyboard_js import RUN_JS, STORYBOARD_JS
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
    if _live_run(view):
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
    if view.stage == Stage.APPROVED and _publication_failed(view):
        return ("A publicação falhou",
                "A versão continua renderizada e aprovada. Veja o motivo, corrija a causa e tente publicar de novo.",
                area_href(video_id, "publicacao"), "Abrir publicação")
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


def _area_direcao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None) -> str:
    video = getattr(view, "video", None)
    brief = getattr(video, "creative_brief", None) if video else None
    pacing_val = getattr(video, "pacing_preset", "dynamic") if video else "dynamic"
    pacing_label = {"cinematic": "Cinemático", "balanced": "Balanceado"}.get(pacing_val, "Dinâmico")
    budget_val = getattr(video, "budget_cap_usd", None) if video else None
    budget_label = f"US$ {budget_val:.2f}" if budget_val is not None else "padrão do servidor"

    if not brief:
        return (
            '<div class="between" style="margin:14px 14px 16px">'
            '<div><h2>Direção criativa</h2>'
            '<p class="sub">O briefing que guia roteiro, mídia, ritmo e música. Gerado a partir do tema; você pode ajustar antes de produzir.</p></div>'
            f'<div class="row"><button class="btn primary small" type="button" id="btn-gerar-briefing" onclick="gerarBriefing(\'{e(video_id)}\')">⚡ Gerar briefing</button></div>'
            '</div>'
            '<div class="card" style="margin:14px"><p>Nenhum briefing criativo gerado ainda para este vídeo. '
            'Clique no botão acima para criar o briefing estruturado com gancho, estrutura, direção visual e orientações de áudio.</p></div>'
        )

    hook = e(str(brief.get("hook", "")))
    goal = e(str(brief.get("narrative_goal", "")))
    structure = brief.get("content_structure", [])
    structure_html = "".join(f"<li>{e(str(item))}</li>" for item in structure)
    tone = e(str(brief.get("tone", "")))
    pacing = e(str(brief.get("pacing", "")))
    visual = e(str(brief.get("visual_direction", "")))
    audio = e(str(brief.get("audio_guidance", "")))
    media_types = brief.get("recommended_media_types", ["image", "video"])
    media_map = {"image": "Imagem", "video": "Vídeo stock", "graphic": "Gráfico", "text": "Texto"}
    media_pills = "".join(f'<span class="pill accent" style="margin-right:6px">{media_map.get(m, m)}</span>' for m in media_types)
    captions = e(str(brief.get("caption_strategy", "")))
    criteria = brief.get("quality_criteria", [])
    criteria_html = "".join(f"<li>{e(str(c))}</li>" for c in criteria)

    return f"""
<div class="between" style="margin:14px 14px 16px"><div><h2>Direção criativa</h2>
<p class="sub">O briefing que guia roteiro, mídia, ritmo e música. Gerado a partir do tema; você pode ajustar antes de produzir.</p></div>
<div class="row"><span class="pill ok">✓ Briefing gerado</span><button class="btn small" type="button" id="btn-regenerar-briefing" onclick="gerarBriefing('{e(video_id)}')">↻ Regenerar briefing</button></div></div>
<div class="two" style="padding:0 14px 14px"><div class="stack">
 <div class="card"><h3 style="margin-bottom:8px">Gancho · primeiros 3 s</h3>
  <textarea id="brief-hook" rows="2" style="width:100%">{hook}</textarea>
  <div class="field" style="margin-top:10px"><label for="brief-narrative-goal">Objetivo narrativo</label>
  <textarea id="brief-narrative-goal" rows="2" style="width:100%">{goal}</textarea></div></div>
 <div class="card"><h3 style="margin-bottom:8px">Estrutura do conteúdo</h3>
  <ol id="brief-structure" style="margin:0 0 0 18px;line-height:1.9">{structure_html}</ol></div>
 <div class="grid2">
  <div class="card"><h3 style="margin-bottom:6px">Tom</h3><input type="text" id="brief-tone" value="{tone}"></div>
  <div class="card"><h3 style="margin-bottom:6px">Ritmo</h3><input type="text" id="brief-pacing" value="{pacing}"></div>
  <div class="card"><h3 style="margin-bottom:6px">Direção visual</h3><textarea id="brief-visual" rows="3" style="width:100%">{visual}</textarea></div>
  <div class="card"><h3 style="margin-bottom:6px">Orientação de áudio</h3><textarea id="brief-audio" rows="3" style="width:100%">{audio}</textarea></div>
 </div>
 <div class="card"><h3 style="margin-bottom:8px">Tipos de mídia recomendados</h3><div class="row" id="brief-media-types">{media_pills}</div>
  <div class="field" style="margin-top:10px"><label for="brief-captions">Estratégia de legendas</label><input type="text" id="brief-captions" value="{captions}"></div></div>
 <div class="card"><h3 style="margin-bottom:8px">Critérios de qualidade</h3>
  <ul id="brief-criteria" style="margin:0 0 0 18px;line-height:1.9">{criteria_html}</ul></div>
</div>
<aside class="card" style="position:sticky;top:80px;align-self:start"><h3>Como o briefing é usado</h3>
 <p class="sub" style="margin:4px 0 12px">Cada decisão abaixo lê este briefing.</p>
 <div class="between sub"><span>Roteiro e cenas</span><b style="color:var(--text)">estrutura e gancho</b></div>
 <div class="between sub"><span>Busca de mídia</span><b style="color:var(--text)">direção visual + tipos</b></div>
 <div class="between sub"><span>Ritmo de cortes</span><b style="color:var(--text)">{pacing_label}</b></div>
 <div class="between sub"><span>Música</span><b style="color:var(--text)">orientação de áudio</b></div>
 <div class="between sub"><span>Teto de custo</span><b style="color:var(--text)">{budget_label}</b></div>
 <div class="hr"></div>
 <button class="btn primary long" type="button" id="btn-salvar-briefing" onclick="salvarBriefing('{e(video_id)}')">Salvar ajustes do briefing</button>
 <p class="sample" style="margin-top:8px">Salvar não refaz o que já foi renderizado; vale para as próximas gerações.</p>
 <div id="brief-feedback" class="form-feedback" role="status" style="margin-top:8px"></div>
</aside></div>
"""


DIRECAO_JS = """
window.gerarBriefing = function (vid) {
  var btn = document.getElementById('btn-gerar-briefing') || document.getElementById('btn-regenerar-briefing');
  if (btn) { btn.disabled = true; btn.textContent = 'Gerando briefing...'; }
  fetch('/studio/videos/' + encodeURIComponent(vid) + '/direction', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }).then(function (r) {
    if (!r.ok) throw new Error('Falha ao gerar briefing');
    return r.json();
  }).then(function () {
    window.location.reload();
  }).catch(function (err) {
    alert('Erro ao gerar briefing: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = '↻ Regenerar briefing'; }
  });
};

window.salvarBriefing = function (vid) {
  var b = {
    hook: document.getElementById('brief-hook') ? document.getElementById('brief-hook').value : '',
    narrative_goal: document.getElementById('brief-narrative-goal') ? document.getElementById('brief-narrative-goal').value : '',
    tone: document.getElementById('brief-tone') ? document.getElementById('brief-tone').value : '',
    pacing: document.getElementById('brief-pacing') ? document.getElementById('brief-pacing').value : '',
    visual_direction: document.getElementById('brief-visual') ? document.getElementById('brief-visual').value : '',
    audio_guidance: document.getElementById('brief-audio') ? document.getElementById('brief-audio').value : '',
    caption_strategy: document.getElementById('brief-captions') ? document.getElementById('brief-captions').value : ''
  };
  var fb = document.getElementById('brief-feedback');
  if (fb) { fb.textContent = 'Salvando ajustes...'; fb.className = 'form-feedback'; }
  fetch('/studio/videos/' + encodeURIComponent(vid) + '/direction', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brief: b })
  }).then(function (r) {
    if (!r.ok) throw new Error('Falha ao salvar ajustes');
    return r.json();
  }).then(function () {
    if (fb) { fb.textContent = 'Ajustes salvos com sucesso!'; fb.className = 'form-feedback ok'; }
  }).catch(function (err) {
    if (fb) { fb.textContent = 'Erro ao salvar: ' + err.message; fb.className = 'form-feedback err'; }
  });
};
"""


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


# `extract_claims` descarta frases com menos de 40 caracteres: abaixo disso a fonte nunca rende afirmação.
_MIN_CHARS_AFIRMACAO = 40


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
            '<div class="row"><span class="pill warn">Registrada, não verificada</span>'
            + ('<span class="pill bad" title="O roteiro só usa frases de 40 a 400 caracteres com número ou nome '
               'próprio. Com menos de 40 caracteres, esta fonte não gera nenhuma afirmação.">'
               'Texto curto demais para o roteiro</span>' if src.chars < _MIN_CHARS_AFIRMACAO else "")
            + '</div></div>'
            for src in sources)
        listing = f'<div class="stack" style="gap:10px" aria-label="Fontes registradas">{cards}</div>'
    else:
        listing = ('<div class="card"><p class="sub">Nenhuma fonte ainda. Adicione uma URL de referência '
                   "ou cole um texto de apoio.</p></div>")
    mode = getattr(view.video, "production_mode", None)
    mode = str(getattr(mode, "value", mode) or "").lower()
    autostart = (mode == "piloto" and not sources and view.stage == Stage.PENDING and not _run_is_live(view))
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
        <form id="video-sources-form" data-video-id="{e(video_id)}"{' data-autostart="1"' if autostart else ""} novalidate>
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
            <textarea id="source-text" name="text" rows="4" aria-describedby="source-text-rule" placeholder="Cole o conteúdo da página quando o site bloquear a leitura"></textarea>
            <p class="sample" id="source-text-rule">Para o roteiro, cole frases completas (40 a 400 caracteres) com
              números, datas ou nomes próprios. Uma URL sozinha, ou um texto muito curto, não gera afirmações.</p>
          </div>
          <div class="modal-footer">
            <div id="video-sources-feedback" class="feedback form-feedback" role="status" aria-live="polite" style="margin-right:auto"></div>
            <button class="btn ghost small" type="button" data-fechar-dialogo>Fechar</button>
            <button class="btn primary small" type="submit" id="btn-add-source">Adicionar fonte</button>
          </div>
        </form>
      </div>
    </dialog>"""
    wait_note = ""
    if autostart:
        wait_note = (
            f'<div class="note info" id="piloto-aguarda-fonte" role="status" style="margin-bottom:16px">'
            '<b>Piloto automático pronto para pesquisar.</b> O Studio pesquisa o tema na Wikipédia, escreve o '
            'roteiro só com os fatos desse texto e produz até a sua aprovação (roteiro, voz, mídia e composição). '
            'Se não achar uma fonte com fatos verificáveis, avisa e você adiciona uma. Nada aqui é fact-checkado '
            'por fora: a fonte registrada em Fontes é o que sustenta o roteiro.<div style="margin-top:10px">'
            f'<button type="button" class="btn primary small" id="btn-piloto-pesquisar" data-video-id="{e(video_id)}">'
            'Pesquisar e produzir</button> <span id="piloto-pesquisar-feedback" class="sample" role="status" '
            'aria-live="polite"></span></div></div>')
    return (
        '<div id="video-fontes">'
        '<div class="between" style="margin-bottom:14px"><div><h2>Fontes e evidências</h2>'
        '<p class="sub">Referências que sustentam o roteiro deste vídeo.</p></div>'
        f'<button type="button" class="btn small" id="btn-abrir-fonte">+ Adicionar fonte</button></div>'
        f"{wait_note}{note}{listing}{dialog}</div>"
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


def _normalize_scenes(scenes, script, assets=None) -> list[dict]:
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
            "asset_tag": _asset_tag((assets or {}).get(int(s_idx if s_idx is not None else idx))) if s_asset else "",
        })

    return normalized_scenes


def _script_version(script) -> int:
    value = getattr(script, "version", None) or (script.get("version") if isinstance(script, dict) else None)
    return int(value or 0)


def _scene_editable(view, script=None) -> bool:
    """O roteiro só aceita edição em IDEA/SCRIPTED e com roteiro versionado; fora disso a UI não finge."""
    status = getattr(getattr(view, "video", None), "status", None)
    return status in (VideoStatus.IDEA, VideoStatus.SCRIPTED) and bool(_script_version(script))


# "Pedir ajustes": versões renderizadas, em revisão ou aprovadas (e não publicadas) voltam à edição (POST /reopen).
_REOPENABLE = (VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED)


def _reopen_button(view, video_id: str, *, cls: str = "btn ghost long small",
                   label: str = "Pedir ajustes (reabre a edição)") -> str:
    status = getattr(getattr(view, "video", None), "status", None)
    if status not in _REOPENABLE:
        return ""
    return (f'<button type="button" class="{cls}" data-reopen data-video-id="{e(video_id)}" '
            f'data-status="{status.value}">{e(label)}</button>'
            '<span id="reopen-feedback" class="feedback" role="status" aria-live="polite"></span>')


_LOCKED_TITLE = "O roteiro só pode ser editado enquanto o vídeo está em Ideia ou Roteirizado."


def _structure_editable(script_view) -> bool:
    """Texto, ordem, inclusão e exclusão de cena são gravados em qualquer roteiro versionado.

    O roteiro longo edita sobre o plano de capítulos; o roteiro curto (gerado pelas fontes) não tem plano e
    é editado sem revisão de capítulos, só com a checagem de lastro do texto novo nas fontes. A trava que
    existia aqui bloqueava todo Short e foi removida.
    """
    return True


def _nova_cena_btn(video_id: str, script, editable: bool = True, structure: bool = True) -> str:
    """`addscene` do protótipo: adiciona a cena na própria bancada (sem trocar de tela).

    Sem roteiro versionado não há como gravar uma cena; o botão fica desabilitado e diz por quê.
    """
    version = _script_version(script)
    off = ""
    if not version:
        off = ' disabled title="Este vídeo ainda não tem roteiro para receber cenas."'
    elif not editable:
        off = f' disabled title="{_LOCKED_TITLE}"'
    return (f'<button type="button" class="btn small" id="btn-nova-cena" data-a="addscene" '
            f'data-video-id="{e(video_id)}" data-script-version="{version}"{off}>+ Nova cena</button>')


def _asset_tag(asset) -> str:
    """Tag do `thumb` do protótipo ('Arte IA' / 'Vídeo stock'), decidida pelo asset real."""
    if asset is None:
        return ""
    if str(getattr(asset, "license", "")).startswith("ai-generated"):
        return "Arte IA"
    kind = getattr(getattr(asset, "kind", None), "value", getattr(asset, "kind", ""))
    return "Vídeo stock" if kind == "video" else "Imagem stock"


def _clock(secs: float) -> str:
    return f"0:{int(round(secs)):02d}"


def _scene_secs(scene: dict) -> int:
    dur = scene.get("duration_s")
    return int(round(dur)) if dur else _secs(scene["narration"])


def _scene_thumb(video_id: str, s: dict, i: int) -> str:
    """`thumb(s, v, 230, 132)`: sem mídia o vazio tracejado; com mídia, o asset real da cena."""
    if not s.get("asset_id"):
        return ('<div class="thumb" data-f="thumb" style="height:132px;background:var(--panel3);'
                'border-style:dashed;color:var(--muted);font-size:12px;text-align:center;padding:10px">'
                'Sem mídia ainda<br><span class="sample">Gere ou escolha uma imagem</span></div>')
    tag = (s.get("asset_tag") or "Mídia") + (" · +B-roll" if s.get("broll_enabled") else "")
    return ('<div class="thumb" data-f="thumb" style="height:132px;background:var(--panel3)">'
            f'<img src="/studio/videos/{e(video_id)}/scenes/{e(s["id"])}/asset" alt="Mídia da cena {i + 1}" '
            'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">'
            f'<span class="tag">{e(tag)}</span><span class="time">{_clock(_scene_secs(s))}</span></div>')


def _scene_card(video_id: str, s: dict, i: int, total: int, *, voice_name: str, editable: bool,
                structure: bool = True) -> str:
    """`sceneCard(v, s, i)` do protótipo, com os dados reais da cena (a mesma estrutura, os mesmos textos)."""
    sid = e(s["id"])
    aud_cls, aud_txt = _AUDIO_BADGE.get(s["audio_state"], _AUDIO_BADGE["none"])
    secs = _scene_secs(s)
    media = bool(s.get("asset_id"))
    broll = bool(s.get("broll_enabled"))
    lock = "" if editable else f' disabled title="{_LOCKED_TITLE}"'
    ro = "" if editable else f' readonly title="{_LOCKED_TITLE}"'
    # Texto/prompt/ordem/exclusão dependem do plano; mídia, B-roll e voz não.
    fixed = "" if editable else f' title="{_LOCKED_TITLE}"'
    ro_text = f" readonly{fixed}" if fixed else ""
    lock_text = f" disabled{fixed}" if fixed else ""
    off_move = lambda cond: " disabled" if (cond or fixed) else ""  # noqa: E731
    broll_btn_style = "border-color:var(--accent);color:var(--accent2)" if broll else ""
    note = (f'<input type="text" class="sample" style="margin-top:6px;font-size:12px" aria-label="Descrição do B-roll" '
            f'data-a="brollnote" data-sid="{sid}" value="{e(s.get("broll_note") or "")}" '
            f'placeholder="O que mostrar no B-roll?"{ro}>') if broll else ""
    return (
        f'<div class="scene" data-sid="{sid}">'
        f'<div>{_scene_thumb(video_id, s, i)}'
        '<div class="row" style="margin-top:8px">'
        f'<button class="btn small" style="flex:1" data-a="media" data-sid="{sid}"{lock}>'
        f'{"Trocar mídia" if media else "Escolher mídia"}</button>'
        f'<button class="btn small {"" if broll else "ghost"}" style="{broll_btn_style}" '
        f'aria-pressed="{"true" if broll else "false"}" data-a="broll" data-sid="{sid}"{lock}>'
        f'{"B-roll ativo" if broll else "+ B-roll"}</button></div>'
        f'{note}</div>'
        '<div><div class="between" style="margin-bottom:6px">'
        f'<span class="num">CENA {i + 1} · {e(s["label"].upper())}</span>'
        f'<span class="sample" data-count="{sid}">{e(_scene_count_text(s))}</span></div>'
        f'<label class="sr" for="tx-{sid}">Texto da cena {i + 1}</label>'
        f'<textarea id="tx-{sid}" rows="4" data-a="text" data-sid="{sid}"{ro_text}>{e(s["narration"])}</textarea>'
        '<div class="field" style="margin:8px 0 0">'
        f'<label for="pr-{sid}">Prompt da imagem</label>'
        f'<input type="text" id="pr-{sid}" data-a="prompt" data-sid="{sid}" value="{e(s["image_prompt"])}"{ro_text}></div></div>'
        '<div class="player"><div class="between"><span class="lbl">NARRAÇÃO</span>'
        f'<span class="pill {aud_cls}" data-audpill="{sid}">{aud_txt}</span></div>'
        f'<p class="sample">{e(voice_name)}</p>'
        f'<div class="prog" style="--d:{secs}s"><b></b></div>'
        '<div class="row">'
        f'<button class="btn small primary" style="flex:1" data-a="play" data-sid="{sid}"'
        f'{" disabled" if s["audio_state"] == "none" else ""}>▶ Ouvir trecho</button></div>'
        f'<button class="btn small ghost long" style="margin-top:6px" data-a="regen" data-sid="{sid}"{lock}>'
        f'{"Gerar áudio da cena" if s["audio_state"] == "none" else "Regenerar áudio da cena"}</button>'
        '<p class="sample" style="margin-top:6px" data-f="voicenote">Áudio real da cena: gerado pelo estúdio, não simulado.</p>'
        '<div class="row" style="margin-top:8px;justify-content:space-between"><span>'
        f'<button class="btn ghost small" aria-label="Mover cena para cima" data-a="mv" data-d="-1" data-sid="{sid}"'
        f'{off_move(i == 0)}>↑</button>'
        f'<button class="btn ghost small" aria-label="Mover cena para baixo" data-a="mv" data-d="1" data-sid="{sid}"'
        f'{off_move(i == total - 1)}>↓</button></span>'
        f'<button class="btn ghost small" style="color:var(--bad)" data-a="delscene" data-sid="{sid}"{lock_text}>Excluir</button>'
        '</div></div>'
        f'<div class="card-shots" style="grid-column:1/-1;padding:12px;margin-top:8px;background:var(--panel2,#16181f);border-radius:10px;border:1px solid var(--line,#2a2d38)">'
        f'<div class="between" style="margin-bottom:8px"><span class="lbl">TOMADAS DESTA CENA</span><span class="row">'
        f'<span class="sample">Ritmo:</span><select style="width:auto" data-a="scene-pacing" data-sid="{sid}">'
        f'<option value="inherit">Herdar do vídeo (Dinâmico)</option><option value="balanced">Balanceado</option><option value="cinematic">Cinemático</option></select>'
        f'<button type="button" class="btn small ghost" style="margin-left:6px;border-style:dashed;white-space:nowrap" data-a="media" data-sid="{sid}">+ Adicionar mídia</button>'
        f'</span></div>'
        f'<p class="sample" style="margin:0">Sem tomadas ainda. Escolha a mídia da cena e o ritmo divide em tomadas.</p>'
        f'</div></div>'
    )


def _storyboard_dialogs() -> str:
    """Modais do v3 (`nativeModal`): histórico da voz e mídia da cena; abertos com `showModal()`."""
    return (
        '<dialog class="modal" id="dlg-audio-history" aria-labelledby="t-audio-history">'
        '<h2 id="t-audio-history">Versões da voz desta cena</h2>'
        '<p class="sample" id="audio-history-scene"></p>'
        '<div id="audio-history-list"></div>'
        '<form method="dialog" style="margin-top:16px"><button class="btn ghost small" value="close">Voltar</button></form>'
        '</dialog>'
        '<dialog class="modal" id="dlg-media" aria-labelledby="t-media">'
        '<h2 id="t-media">Mídia para esta cena</h2>'
        '<p class="sample" id="media-scene"></p>'
        '<div class="row" style="margin:12px 0" id="media-tabs">'
        '<button type="button" class="btn small primary" data-a="media-tab" data-v="video">Deste vídeo</button>'
        '<button type="button" class="btn small" data-a="media-tab" data-v="channel">Do canal</button>'
        '<button type="button" class="btn small" data-a="media-tab" data-v="files">Meus arquivos</button>'
        '<button type="button" class="btn small" data-a="media-tab" data-v="stock">Stock</button>'
        '<button type="button" class="btn small" data-a="media-tab" data-v="generate">Gerar</button></div>'
        '<div id="media-body" role="status"></div>'
        '<form method="dialog" style="margin-top:16px"><button class="btn ghost small" value="close">Voltar</button></form>'
        '</dialog>'
    )


def _empty_storyboard(view, video_id: str) -> str:
    """Storyboard sem cenas: o roteiro nasce das fontes, então o caminho real é fonte → roteiro.

    Não existe "criar cena do zero" no backend (toda cena é gravada numa versão de roteiro, e a versão
    nasce da geração a partir das fontes). Por isso o estado vazio diz isso e oferece a próxima ação
    de verdade, em vez de um "adicione a primeira cena" que não tinha como ser cumprido.
    """
    if getattr(view, "sources", None):
        action = ('<button type="button" class="btn primary" id="btn-gerar-roteiro" '
                  f'data-video-id="{e(video_id)}">Gerar roteiro e cenas</button>')
        text = ("As fontes já estão registradas. Gere o roteiro: ele vira as cenas aqui, "
                "e então você edita texto, mídia e voz de cada uma.")
    else:
        action = f'<a class="btn primary" href="{area_href(video_id, "fontes")}">Adicionar fonte</a>'
        text = ("O roteiro é escrito a partir dos fatos das fontes. Adicione uma fonte "
                "(URL ou texto colado) para gerar as cenas.")
    return ('<div class="card" id="storyboard-vazio"><h3>Este vídeo ainda não tem cenas</h3>'
            f'<p class="sub" style="margin:6px 0 12px">{text}</p>'
            f'<div class="row">{action}</div>'
            '<p class="sample" id="roteiro-feedback" role="status" aria-live="polite" style="margin-top:8px"></p></div>')


def _area_cenas(view, *, style_view=None, script_view=None, video_id: str, composition_view=None,
                scenes=None, script=None, channel_voice: str | None = None, scene_assets=None) -> str:
    """`tabScenes` do protótipo (com Desfazer/Refazer do v3): um `sceneCard` completo por cena, na ordem do roteiro."""
    editable = _scene_editable(view, script)
    structure = _structure_editable(script_view)
    items = _normalize_scenes(scenes, script, scene_assets)
    voice_name = channel_voice or "Voz padrão do estúdio"
    version = _script_version(script)
    cards = "".join(_scene_card(video_id, s, i, len(items), voice_name=voice_name, editable=editable,
                                  structure=structure)
                    for i, s in enumerate(items))
    blank = {"id": "__sid__", "label": "", "narration": "", "image_prompt": "", "duration_s": None,
             "asset_id": None, "audio_state": "none", "broll_enabled": False, "broll_note": None}
    template = ('<template id="scene-card-template">'
                + _scene_card(video_id, blank, 0, 2, voice_name=voice_name, editable=editable,
                            structure=structure) + '</template>')
    empty = _empty_storyboard(view, video_id) if not items else ""
    gen_off = "" if items else ' disabled title="Sem cenas: gere o roteiro primeiro."'
    data = {"video_id": video_id, "version": version, "editable": editable, "structure": structure, "voice": voice_name,
            "scenes": [{k: v for k, v in s.items() if k != "audio_history"} | {"audio_history": s["audio_history"]}
                       for s in items]}
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    script_content = "".join(
        f'<p style="margin-top:12px"><b>{i + 1}. {e(sc["label"])}</b><br>{e(sc["narration"])}</p>'
        for i, sc in enumerate(items))
    locked_note = ""
    if items and not editable and version and getattr(view.video, "status", None) in _REOPENABLE:
        approved = view.video.status is VideoStatus.APPROVED
        locked_note = (
            '<div class="note" id="storyboard-bloqueado" style="margin-bottom:14px"><b>Esta versão está bloqueada para '
            f'edição</b> porque já foi renderizada e está {"aprovada" if approved else "em revisão"}. '
            'Para mudar texto, mídia ou voz, peça ajustes: a '
            f'{"aprovação, o " if approved else ""}render e o QA atuais ficam obsoletos e será preciso produzir e '
            'aprovar de novo.<div class="row" style="margin-top:10px">'
            f'{_reopen_button(view, video_id, cls="btn small", label="Pedir ajustes")}</div></div>')
    return (
        '<div id="storyboard" data-video-id="' + e(video_id) + '">'
        '<div class="between" style="margin-bottom:16px"><div><h2>Storyboard integrado</h2>'
        '<p class="sub">Texto, mídia, B-roll e narração de cada cena na mesma bancada. '
        'Edite sem trocar de tela.</p></div>'
        '<div class="row">'
        '<button type="button" class="btn small" id="btn-undo-cenas" data-a="undo-v3" disabled>↶ Desfazer</button>'
        '<button type="button" class="btn small" id="btn-redo-cenas" data-a="redo-v3" disabled>↷ Refazer</button>'
        f'{_nova_cena_btn(video_id, script, editable, structure)}</div></div>'
        f'{locked_note}'
        f'<div class="stack" id="storyboard-cards">{cards}</div>'
        f'{empty}'
        '<div class="row" style="margin-top:12px">'
        '<button type="button" class="btn small" id="btn-historico-voz" data-a="audio-history">Histórico da voz</button>'
        '<button type="button" class="btn ghost small" id="btn-gerar-faltante" data-a="genmissing" '
        f'data-video-id="{e(video_id)}"{gen_off}>'
        'Gerar tudo o que falta</button></div>'
        '<p class="sample" id="storyboard-feedback" role="status" aria-live="polite" style="margin-top:8px"></p>'
        f'<details class="diag" style="margin-top:18px"><summary>Ver roteiro completo · {len(items)} cenas</summary>'
        f'<div id="storyboard-fullscript">{script_content}</div></details>'
        f'{template}{_storyboard_dialogs()}'
        f'<script type="application/json" id="storyboard-data">{data_json}</script>'
        '</div>'
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


def _area_composicao(view, *, style_view=None, script_view=None, video_id: str, composition_view=None,
                     scenes=None, script=None, scene_assets=None, channel_voice: str | None = None) -> str:
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
    first_scene = next(iter(_normalize_scenes(scenes, script, scene_assets)), None)
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
        f'<div class="frame {"r916" if short else "r169"}{" static" if is_static_motion else ""}" id="frame" data-short="{"1" if short else "0"}"><div class="bg" style="background:var(--panel3)"></div>'
        '<span style="font-size:60px;position:relative">🎞️</span>'
        f'<div class="cap" id="cap" style="{cap_pos_css};font-size:{cap_px}px;{cap_box_css}'
        f'font-family:{e(cap_font_css)},sans-serif">{e(sample_text)}</div></div>'
        '<p class="sample" style="margin-top:8px;text-align:center">Prévia aproximada das legendas — '
        "não é o vídeo renderizado.</p></div>"
    )
    scene_items = _normalize_scenes(scenes, script, scene_assets)
    base_track = " → ".join(
        f'Cena {i + 1} ({(sc["asset_tag"] or "com mídia") if sc["asset_id"] else "sem mídia"})'
        for i, sc in enumerate(scene_items)) or "sem cenas"
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
            f'<div class="track"><span>Narração</span><div style="color:var(--ok)">Narração contínua · {e(channel_voice or "Voz padrão do estúdio")} · ~{_fmt_t(total_secs)}</div></div>'
            f'<div class="track"><span>Música</span><div>bpm {e(str(music_bpm))} · seed {e(str(music_seed))}</div></div>'
            f'<div class="track"><span>Legendas</span><div id="track-legendas">{e(cap_font_css)} · '
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
        + _opt("destaque", "Destaque por palavra (karaokê)", caption_style == "destaque")
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
        '<div class="field" style="margin:10px 0">'
        '<label for="comp-music-track">Trilha escolhida pelo Diretor de áudio</label>'
        '<select id="comp-music-track" name="music.track">'
        '<option value="sci-fi">Sci-Fi Survival Dreamscape · CC0 (sugerida pelo tom)</option>'
        '<option value="ambient">Ambient Music · CC0</option>'
        '<option value="electronic">Electronic Minute No 258 · CC0</option>'
        '<option value="none">Sem música</option>'
        '</select>'
        '<p class="sample" style="margin-top:4px">Só faixas CC0 do catálogo do estúdio; a licença aparece no relatório de entrega.</p></div>'
        '<div class="grid2"><div class="field"><label for="composicao-music-bpm">Andamento da música (BPM)</label>'
        f'<input type="number" id="composicao-music-bpm" name="music.bpm" value="{e(str(music_bpm))}" min="20" max="300"></div>'
        '<div class="field"><label for="composicao-music-seed">Semente da música (seed)</label>'
        f'<input type="number" id="composicao-music-seed" name="music.seed" value="{e(str(music_seed))}" min="0"></div></div>'
        '<div class="field"><label for="comp-music-vol">Volume da música: <b id="comp-music-vol-v">20</b></label>'
        '<input type="range" id="comp-music-vol" name="music.volume" min="0" max="60" value="20"></div>'
        '<div class="field"><label class="tog"><input type="checkbox" id="comp-ducking" name="music.ducking" checked><i></i>'
        'Abaixar a música quando houver voz</label>'
        '<p class="sample" style="margin-top:4px">Compressão sidechain: a música cai sob a narração e volta nas pausas; fade-out no final.</p></div>'
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
            f'<p style="text-align:center;margin-top:8px"><a class="btn ghost small" href="/studio/videos/{e(video_id)}/preview">Abrir prévia completa</a>'
            f'<span style="display:inline-block;margin-left:10px">'
            f'<a class="btn primary small" id="btn-baixar-mp4" href="/studio/videos/{e(video_id)}/download{output_asset_param}" download>⬇ Baixar vídeo (.mp4)</a></span></p>'
            f'<p class="sample" style="text-align:center;margin-top:6px">MP4 H.264 + AAC · 1080×1920 (9:16)</p>'
            '</div>'
        )
    else:
        preview_card = (
            '<div class="card card-preview-destaque"><h3 style="margin-bottom:10px">Prévia da versão</h3>'
            '<p class="sub">Ainda não há versão renderizada. Prévia e aprovação ficam disponíveis '
            "após a renderização.</p>"
            f'<p style="margin-top:10px"><a class="btn ghost small" id="btn-baixar-mp4" href="/studio/videos/{e(video_id)}/download">⬇ Baixar vídeo (.mp4)</a></p>'
            "</div>"
        )

    pacing_val = getattr(getattr(view, "video", None), "pacing_preset", "dynamic") or "dynamic"
    pacing_label = {"cinematic": "Cinemático", "balanced": "Balanceado"}.get(pacing_val, "Dinâmico")
    dur_text = legacy._duration_text(getattr(getattr(view, "video", None), "target_duration_s", None)) if getattr(getattr(view, "video", None), "target_duration_s", None) else "automática"

    audiovisual_summary_card = (
        '<div class="card" id="card-resumo-audiovisual" style="margin-top:14px">'
        '<h3 style="margin-bottom:8px">Resumo audiovisual desta versão</h3>'
        f'<div class="between sub"><span>Duração</span><b style="color:var(--text)">{e(dur_text)}</b></div>'
        f'<div class="between sub"><span>Cortes / tomadas</span><b style="color:var(--text)">ritmo {e(pacing_label)}</b></div>'
        '<div class="between sub"><span>Música</span><b style="color:var(--text)">Sci-Fi Survival Dreamscape · CC0</b></div>'
        '<div class="between sub"><span>Mixagem</span><b style="color:var(--text)">música baixa sob a voz · fade-out</b></div>'
        '<div class="between sub"><span>Legendas</span><b style="color:var(--text)">destaque por palavra · área segura</b></div>'
        '<div class="between sub"><span>Mídias</span><b style="color:var(--text)">Pexels · Pixabay</b></div>'
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
            f"Ir para publicação →</a>{_reopen_button(view, video_id)}</div>"
        )
    else:
        # A API aprova uma REVISÃO de render específica (`output_asset_id`): a que o usuário viu na prévia.
        # Sem ela conhecida, aprovar às cegas seria recusado; o botão fica desabilitado e diz o motivo.
        revision = getattr(preview, "output_asset_id", None) if preview is not None else None
        if not rendered:
            disabled = " disabled"
        elif not revision:
            disabled = ' disabled title="Abra a prévia completa para revisar o render antes de aprovar."'
        else:
            disabled = ""
        revision_attr = f' data-output-asset-id="{e(revision)}"' if revision else ""
        actions = (
            '<div class="stack" style="gap:8px">'
            f'<button type="button" class="btn ok long" data-a="approve" data-video-id="{e(video_id)}"{revision_attr} '
            f'id="btn-approve-video"{disabled}>✓ Aprovar e preparar publicação →</button>'
            + (_reopen_button(view, video_id) or
               f'<a class="btn ghost long small" href="{area_href(video_id, "cenas")}">Pedir ajustes (volta ao storyboard)</a>')
            + '<span id="approve-feedback" class="feedback" role="status" aria-live="polite"></span></div>'
        )
    aside = (
        '<aside class="card" style="position:sticky;top:80px"><h3>Aprovação desta versão</h3>'
        '<p class="sub" style="margin:4px 0 12px">Aprovar marca esta versão como a oficial. '
        "Publicar é um passo separado.</p>"
        f'{note}<p class="sub" style="margin-bottom:10px">{e(approval_text)}</p>{actions}</aside>'
    )
    script_line = ""
    if script_view is not None and script_view.has_script:
        versao_hash = next((v.content_hash for v in script_view.versions if v.current and v.content_hash), "")
        if script_view.approved:
            script_line = '<p class="sub" style="margin:-4px 0 12px">Aprovação do roteiro: aprovada.</p>'
        elif not versao_hash:
            # Roteiro curto (gerado pelas fontes) não tem plano de capítulos e, sem plano, não tem hash de conteúdo:
            # a aprovação por versão não se aplica e a decisão é a aprovação do vídeo (acima).
            script_line = ('<p class="sub" style="margin:-4px 0 12px">Aprovação do roteiro: não se aplica a roteiro '
                           'curto, sem plano de capítulos. Vale a aprovação do vídeo.</p>')
        else:
            script_line = '<p class="sub" style="margin:-4px 0 12px">Aprovação do roteiro: não registrada.</p>'
            if script_view.version:
                # Aprovar a versão do roteiro acontece aqui, sem sair para a página antiga de Roteiro.
                script_line += (
                    '<div style="margin:0 0 12px"><button type="button" class="btn small" id="btn-approve-script" '
                    f'data-video-id="{e(video_id)}" data-version="{script_view.version}" data-hash="{e(versao_hash)}">'
                    f'Aprovar versão {script_view.version} do roteiro</button> '
                    '<span id="approve-script-feedback" class="feedback" role="status" aria-live="polite"></span></div>')
    aside = aside.replace("</aside>", f"{script_line}</aside>") if script_line else aside
    return f'<div class="two"><div class="stack">{preview_card}{audiovisual_summary_card}{issues_card}{technical_details}</div>{aside}</div>'


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
    if _publication_failed(view) and not is_published:
        action_btn_text = "Tentar publicar de novo"

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
    heading = ('<div class="note" id="publicacao-intencao" style="margin:14px 0"><b>A confirmação de publicação vive aqui.</b> '
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
        preview_html = (f'<p style="margin-top:12px"><a class="btn small" href="/studio/videos/{e(video_id)}/preview">'
                        "Abrir prévia completa</a></p>") if approved else (
            '<p class="sample" style="margin-top:12px">A prévia fica disponível após a renderização.</p>')

    failed_pub = (_publication_failed(view) and not is_published)
    failure_note = ""
    if failed_pub:
        raw = (getattr(pub, "error", None) or "").strip()
        explained = explicar_motivo(raw)
        failure_note = (
            '<div class="note" id="publicacao-falhou" role="alert" style="margin-bottom:14px">'
            '<b>A publicação falhou.</b> A versão continua renderizada e aprovada: não precisa renderizar de novo. '
            f'{e(explained) if explained else "Corrija a causa e tente de novo."}'
            + (f'<br><span class="sample">Motivo técnico: {e(raw)}</span>' if raw else "")
            + "</div>")
    left = (
        '<div class="card"><h3 style="margin-bottom:12px">Dados de publicação no YouTube</h3>'
        f"{failure_note}{gate_note}{summary}{heading}{decision}{options_card}{preview_html}</div>"
    )
    destino = (e(channel_name) if channel_name else "Canal do vídeo")
    if is_published:
        action = '<div class="note okn">✓ Publicado.</div>'
    else:
        # Sem versão aprovada nem em revisão não há o que publicar: o botão fica desligado e diz por quê.
        blocked_attr = (' disabled aria-describedby="publicar-motivo"' if not approved and not reviewable else "")
        reason = ('<p class="sample" id="publicar-motivo" style="margin-top:8px">Aprove uma versão na aba Qualidade '
                  "para liberar a publicação.</p>" if blocked_attr else "")
        rearm_attr = ' data-rearm="1"' if (_publication_failed(view) and not is_published) else ""
        action = (f'<button type="button" class="btn ok long" id="btn-publicar-acao" data-video-id="{e(video_id)}"{rearm_attr}{blocked_attr}>'
                  f"{action_btn_text}</button>{reason}"
                  '<p id="publicar-feedback" class="feedback" role="status" aria-live="polite" style="margin-top:8px"></p>'
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
        bruto = st.error_message or st.error_class
        explicada = explicar_falha(bruto)
        err = (f'<p style="color:var(--bad);font-size:12.5px">{e(explicada.texto if explicada else bruto)}</p>'
               if st.status == "FAILED" and bruto else "")
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
    mode = mode or ""
    diag = (
        '<details class="diag"><summary>Diagnóstico técnico</summary>'
        f'<p class="mono" style="margin-top:8px">video_id={e(video_id)}<br>modo={e(mode)}'
        f'<br>estado={e(view.stage.value)}'
        f'{"<br>execução=" + e(run.run_id) + " (" + e(run.state) + ")" if run is not None else ""}</p></details>'
    )
    return (f'<div class="two"><div class="stack">{steps_card}{legacy._video_run_card(view)}</div>'
            f'<aside class="stack">{cost_card}{diag}</aside></div>')


_AREA_RENDERERS = {
    "direcao": _area_direcao,
    "visao-geral": _area_visao_geral,
    "fontes": _area_fontes,
    "narracao": _area_narracao,
    "cenas": _area_cenas,
    "composicao": _area_composicao,
    "qualidade": _area_qualidade,
    "publicacao": _area_publicacao,
    "producao": _area_producao,
}


def _live_run(view) -> bool:
    """Há execução viva que ainda importa. Aprovado/publicado: o run segue aberto só até a publicação
    (pausa humana final), e isso não é mais produção em andamento."""
    run = getattr(view, "latest_run", None)
    return (run is not None and run.state in _LIVE_RUN_STATES
            and view.stage not in (Stage.APPROVED, Stage.COMPLETED))


def _run_is_live(view) -> bool:
    """Produção em andamento: o estágio observável OU uma execução viva (entre etapas o estágio pode piscar)."""
    return view.stage == Stage.IN_PRODUCTION or _live_run(view)


def _impact_dialog(missing: int) -> str:
    """`impact` do v3 ("Atualizar esta versão"): o que a produção vai refazer, antes de iniciar."""
    return (
        '<dialog class="modal" id="dlg-impacto" aria-labelledby="t-impacto">'
        '<h2 id="t-impacto">Atualizar esta versão</h2>'
        f'<p style="margin:12px 0"><span id="impact-n">{missing}</span> cena(s) precisam de mídia ou voz atualizadas. '
        'As demais serão preservadas; a montagem será atualizada.</p>'
        '<p class="sub">Estimativa de custo indisponível: o custo é medido durante a execução.</p>'
        '<p class="sample">A publicação anterior não muda. Será necessária nova aprovação.</p>'
        '<div class="row" style="margin-top:16px">'
        '<button type="button" class="btn primary" id="btn-confirmar-render" autofocus>Confirmar atualização</button>'
        '<form method="dialog"><button class="btn ghost small" value="close">Voltar</button></form></div>'
        '</dialog>'
    )


def _dock(view, video_id: str, scenes, script, scene_assets=None) -> str:
    """`dock(v)` do protótipo: resumo fixo no rodapé, nas abas Cenas e Composição."""
    items = _normalize_scenes(scenes, script, scene_assets)
    if view.stage == Stage.COMPLETED:
        return ('<div class="dock"><span class="sub">Publicado.</span>'
                f'<a class="btn small" href="{area_href(video_id, "publicacao")}">Ver publicação</a></div>')
    total = sum(_secs(sc["narration"]) for sc in items)
    missing = sum(1 for sc in items if not sc["asset_id"] or sc["audio_state"] != "ok")
    running = _run_is_live(view)
    needs = view.stage in (Stage.PENDING, Stage.FAILED) and not running
    aviso = (f'<span class="pill warn" id="dock-missing">{missing} cena(s) sem mídia ou áudio atual</span>'
             if needs and missing else "")
    if running:
        acao = ('<button type="button" class="btn primary" id="btn-render" disabled aria-busy="true" '
                f'data-video-id="{e(video_id)}">⚡ Produção em andamento…</button>')
    elif needs and not items and not getattr(view, "sources", None):
        acao = ('<button type="button" class="btn primary" id="btn-render" disabled '
                'title="Adicione uma fonte primeiro: o roteiro nasce dela.">'
                '🎬 Gerar o que falta e renderizar</button>')
    elif needs:
        acao = (f'<button type="button" class="btn primary" id="btn-render" data-a="render" '
                f'data-video-id="{e(video_id)}">🎬 Gerar o que falta e renderizar</button>')
    else:
        acao = f'<a class="btn ok" href="{area_href(video_id, "qualidade")}">Ir para aprovação →</a>'
    return (f'<div class="dock" id="dock" data-needs="{"1" if needs else "0"}"><div class="row" id="dock-info">'
            f'<b id="dock-count">{len(items)} cenas</b>'
            f'<span class="sub" id="dock-dur">~{_fmt_t(total)} · estimativa de custo não disponível</span>{aviso}'
            '<span class="sample" id="run-feedback" role="status" aria-live="polite"></span></div>'
            f'<div class="row">{acao}</div></div>'
            f'{_impact_dialog(missing) if needs else ""}')


def _content(view, area: str, *, style_view, script_view, video_id, composition_view=None, preview=None,
             scenes=None, script=None, channel_voice: str | None = None, channel_name: str = "",
             scene_assets=None) -> str:
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
                           channel_voice=channel_voice, scene_assets=scene_assets
                           ) + _dock(view, video_id, scenes, script, scene_assets)
    if area == "composicao":
        return _area_composicao(view, style_view=style_view, script_view=script_view, video_id=video_id,
                                composition_view=composition_view, scenes=scenes,
                                script=script, scene_assets=scene_assets,
                                channel_voice=channel_voice) + _dock(view, video_id, scenes, script, scene_assets)
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
            + (window.StudioErro.texto(data, 'resposta inválida do servidor.'));
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
            + (window.StudioErro.texto(data, 'o estado atual não permite nova tentativa.'));
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

  var btnPesquisar = document.getElementById('btn-piloto-pesquisar');
  if (btnPesquisar) {
    btnPesquisar.addEventListener('click', async function () {
      var videoId = btnPesquisar.getAttribute('data-video-id') || '';
      var fb = document.getElementById('piloto-pesquisar-feedback');
      btnPesquisar.disabled = true; btnPesquisar.classList.add('carregando');
      if (fb) fb.textContent = 'Iniciando a produção...';
      var chave = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      try {
        var run = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/production-runs', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': chave }, body: '{}' });
        var data = await run.json().catch(function () { return {}; });
        if (!run.ok) {
          if (fb) fb.textContent = 'A produção não pôde iniciar: ' + window.StudioErro.texto(data, 'tente novamente.', run.status);
          btnPesquisar.disabled = false; btnPesquisar.classList.remove('carregando');
          return;
        }
        location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/cenas';
      } catch (e) {
        if (fb) fb.textContent = 'Falha de rede ao iniciar a produção. Tente novamente.';
        btnPesquisar.disabled = false; btnPesquisar.classList.remove('carregando');
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
          if (sourcesForm.hasAttribute('data-autostart')) {
            // Piloto automático: a fonte era o único dado que faltava; a produção começa sozinha.
            if (feedback) feedback.textContent = 'Fonte registrada. Iniciando a produção...';
            var chave = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
            var run = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/production-runs', {
              method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': chave }, body: '{}' });
            var runData = await run.json().catch(function () { return {}; });
            if (!run.ok) {
              try { sessionStorage.setItem('flash-' + videoId, 'A produção não pôde iniciar: '
                + window.StudioErro.texto(runData, 'tente novamente.', run.status)); } catch (e) {}
            }
            location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/cenas';
            return;
          }
          if (feedback) feedback.textContent = 'Fonte registrada. Atualizando...';
          setTimeout(function () { location.reload(); }, 600);
        } else {
          if (feedback) feedback.textContent = 'Não foi possível registrar a fonte: '
            + (window.StudioErro.texto(data, 'verifique a URL e tente novamente.'));
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
          if (feedback) feedback.textContent = window.StudioErro.texto(data, 'Falha ao restaurar a revisão.');
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

  var approveScriptBtn = document.getElementById('btn-approve-script');
  if (approveScriptBtn) {
    approveScriptBtn.addEventListener('click', async function () {
      var fbs = document.getElementById('approve-script-feedback');
      approveScriptBtn.disabled = true;
      if (fbs) fbs.textContent = 'Registrando aprovação do roteiro…';
      try {
        var res = await fetch('/studio/videos/' + encodeURIComponent(approveScriptBtn.dataset.videoId) + '/script/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: Number(approveScriptBtn.dataset.version), content_hash: approveScriptBtn.dataset.hash })
        });
        var dados = await res.json().catch(function () { return {}; });
        if (res.ok) {
          if (fbs) fbs.textContent = 'Versão do roteiro aprovada. Atualizando…';
          setTimeout(function () { location.reload(); }, 700);
        } else {
          approveScriptBtn.disabled = false;
          if (fbs) fbs.textContent = 'Não foi possível aprovar o roteiro: ' + window.StudioErro.texto(dados, 'tente novamente.', res.status);
        }
      } catch (erro) {
        approveScriptBtn.disabled = false;
        if (fbs) fbs.textContent = 'Falha de rede ao aprovar o roteiro. Tente novamente.';
      }
    });
  }

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
          body: JSON.stringify({ output_asset_id: approveBtn.getAttribute('data-output-asset-id') })
        });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          if (fb) fb.textContent = 'Aprovado com sucesso! Redirecionando para publicação...';
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/publicacao';
        } else {
          if (fb) fb.textContent = 'Não foi possível aprovar: ' + (window.StudioErro.texto(data, 'erro no servidor.'));
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
    // O clique aprova a versão (se ainda estiver em revisão) e executa a publicação pela API existente.
    // O resultado vem do servidor e é traduzido; só `UPLOADED` aparece como sucesso.
    var pubFeedback = document.getElementById('publicar-feedback');
    var say = function (text, bad) {
      if (!pubFeedback) return;
      pubFeedback.textContent = text;
      pubFeedback.classList.toggle('erro', !!bad);
    };
    btnPublishAction.addEventListener('click', async function (ev) {
      ev.preventDefault();
      var scheduled = !!(scheduleRadio && scheduleRadio.checked);
      if (scheduled && !validateBrasiliaSchedule()) return;
      var videoId = btnPublishAction.getAttribute('data-video-id') || '';
      var reloading = false;
      btnPublishAction.disabled = true;
      btnPublishAction.classList.add('carregando');
      if (window.StudioLoading) window.StudioLoading.start();
      try {
        if (document.getElementById('approve') && window.StudioAprovacao) {
          say('Aprovando a versão…');
          var at = '';
          if (scheduled) {
            var raw = scheduleInput.value.trim();
            at = new Date(raw.length === 16 ? raw + ':00-03:00' : raw + '-03:00').toISOString();
          }
          var ap = await window.StudioAprovacao.aprovar(at);
          if (!ap.ok) {
            say('Não foi possível aprovar a versão: ' + window.StudioErro.texto(ap.data, 'tente novamente.', ap.status), true);
            return;
          }
        }
        if (btnPublishAction.hasAttribute('data-rearm')) {
          // A publicação anterior foi bloqueada antes de enviar algo: volta para a fila (o servidor só aceita
          // quando prova que nada foi enviado) e então tenta publicar. Nenhuma etapa anterior é refeita.
          say('Preparando nova tentativa…');
          var rearm = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/publication/rearm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
          var rearmData = await rearm.json().catch(function () { return {}; });
          if (!rearm.ok) {
            say('Não foi possível tentar de novo: ' + window.StudioErro.texto(rearmData, 'tente novamente.', rearm.status), true);
            return;
          }
        }
        say('Enviando ao YouTube…');
        var res = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/publication/publish', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) {
          say('Não foi possível publicar: ' + window.StudioErro.texto(data, 'tente novamente.', res.status), true);
          return;
        }
        var out = window.StudioPublicacao.explicar(data);
        say(out.texto, !out.ok);
        if (out.ok) { reloading = true; setTimeout(function () { location.reload(); }, 1500); }
      } catch (err) {
        say('Falha de rede ao publicar. Confira a aba antes de tentar de novo: o envio pode ter sido feito.', true);
      } finally {
        if (!reloading) {
          btnPublishAction.disabled = false;
          btnPublishAction.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
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

    // Prévia viva (`tabComp` do protótipo): a legenda e o movimento seguem os parâmetros antes de salvar.
    function liveComposition() {
      var cap = document.getElementById('cap'), frame = document.getElementById('frame');
      if (!cap || !frame) return;
      var pos = compForm.querySelector('input[name="comp-posicao"]:checked');
      var posV = pos ? pos.value : 'bottom';
      var style = (document.getElementById('composicao-caption-style') || {}).value;
      var fontSel = document.getElementById('composicao-caption-font');
      var size = Number((document.getElementById('composicao-font-size') || {}).value) || 42;
      var scale = frame.getAttribute('data-short') === '1' ? 0.5 : 0.42;
      cap.style.top = posV === 'top' ? '12%' : posV === 'middle' ? '46%' : '';
      cap.style.bottom = posV === 'bottom' ? '12%' : '';
      cap.style.fontSize = Math.round(size * scale) + 'px';
      cap.style.background = style === 'simple' ? '' : 'rgba(0,0,0,.65)';
      if (fontSel) cap.style.fontFamily = (fontSel.selectedOptions[0].textContent.replace(/ \(.*\)$/, '')) + ',sans-serif';
      var motion = document.getElementById('composicao-motion');
      frame.classList.toggle('static', !!motion && motion.value === 'estatico');
      var track = document.getElementById('track-legendas');
      if (track && fontSel) {
        var labels = { top: 'topo', middle: 'meio', bottom: 'base' };
        track.textContent = fontSel.selectedOptions[0].textContent.replace(/ \(.*\)$/, '') + ' \u00b7 '
          + (style === 'simple' ? 'Texto simples' : 'Caixa discreta') + ' \u00b7 ' + labels[posV];
      }
    }
    compForm.addEventListener('input', liveComposition);
    compForm.addEventListener('change', liveComposition);

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
            + (window.StudioErro.texto(data, 'verifique os parâmetros e tente novamente.'));
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

  // "Pedir ajustes": confirma no diálogo do tema, reabre a edição (aprovação, render e QA ficam obsoletos) e volta ao storyboard.
  var dlgReopen = document.getElementById('dlg-reopen');
  var reopenFrom = null;
  function reopenAberto(btn) {
    reopenFrom = btn;
    var erro = document.getElementById('reopen-erro'); if (erro) erro.textContent = '';
    if (dlgReopen && typeof dlgReopen.showModal === 'function') dlgReopen.showModal();
    else if (dlgReopen) dlgReopen.setAttribute('open', '');
  }
  document.querySelectorAll('[data-reopen]').forEach(function (btn) {
    btn.addEventListener('click', function () { reopenAberto(btn); });
  });
  if (dlgReopen) {
    dlgReopen.addEventListener('click', function (ev) {
      if (ev.target === dlgReopen || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlgReopen.close();
    });
    var ok = document.getElementById('btn-confirmar-reopen');
    if (ok) ok.addEventListener('click', async function () {
      var videoId = reopenFrom ? (reopenFrom.getAttribute('data-video-id') || '') : '';
      var erro = document.getElementById('reopen-erro');
      if (!videoId) return;
      ok.disabled = true; ok.classList.add('carregando');
      if (erro) erro.textContent = 'Reabrindo para edição...';
      try {
        var response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/reopen', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        var data = await response.json().catch(function () { return {}; });
        if (response.ok) {
          try { sessionStorage.setItem('flash-' + videoId, 'Vídeo reaberto para ajustes. Edite e use "Gerar tudo o que falta" para produzir de novo; a aprovação anterior não vale mais.'); } catch (e) {}
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/cenas';
          return;
        }
        if (erro) erro.textContent = 'Não foi possível reabrir: ' + window.StudioErro.texto(data, 'tente novamente.', response.status);
      } catch (err) {
        if (erro) erro.textContent = 'Falha de rede ao reabrir. Tente novamente.';
      }
      ok.disabled = false; ok.classList.remove('carregando');
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


def _publication_failed(view) -> bool:
    """A publicação registrada falhou (o render e a aprovação do vídeo seguem valendo)."""
    status = getattr(getattr(view, "publication", None), "status", None)
    return str(getattr(status, "value", status) or "").upper() == "FAILED"


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


def _reopen_dialog(view) -> str:
    """Confirmação de "Pedir ajustes" no tema (a antiga `window.confirm` era um modal nativo do navegador)."""
    status = getattr(getattr(view, "video", None), "status", None)
    if status not in _REOPENABLE:
        return ""
    lost = "A aprovação, o render e o QA atuais" if status is VideoStatus.APPROVED else "O render e o QA atuais"
    return (
        '<dialog id="dlg-reopen" class="modal" aria-labelledby="t-reopen">'
        '<div class="modal-header"><h2 id="t-reopen">Pedir ajustes</h2>'
        '<button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>'
        '<div class="dialogo-corpo">'
        '<p style="margin:0 0 10px">O vídeo volta para edição: texto, ordem, mídia e voz das cenas ficam liberados.</p>'
        f'<p class="sub">{lost} ficam obsoletos e será preciso produzir e aprovar de novo. '
        'Nada é apagado: as versões anteriores continuam no histórico.</p>'
        '<p id="reopen-erro" class="feedback" role="alert" aria-live="assertive"></p>'
        '<div class="row" style="margin-top:16px">'
        '<button type="button" class="btn primary" id="btn-confirmar-reopen" autofocus>Reabrir para edição</button>'
        '<button type="button" class="btn ghost small" data-fechar-dialogo>Voltar</button></div>'
        '</div></dialog>'
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
    if _publication_failed(view) and view.stage != Stage.FAILED:
        pills.insert(1, '<span class="pill bad">Publicação falhou</span>')
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
        {_version_dialog(view)}{_reopen_dialog(view)}"""


_RUN_PILL = {"SUCCEEDED": ("ok", "✓"), "RUNNING": ("accent", "…"), "WAITING_HUMAN": ("accent", "…"),
             "FAILED": ("bad", "✕")}


def _progress_html(stages, *, run_id: str = "", video_id: str = "", template: bool = False) -> str:
    """`progressCard(v)` do protótipo: etapas reais da execução; a barra é o nº de etapas concluídas, nunca um percentual inventado."""
    total = len(stages)
    done = sum(1 for _label, state in stages if state == "SUCCEEDED")
    pct = round(done / total * 100) if total else 0
    pills = "".join(
        f'<span class="pill {_RUN_PILL.get(state, ("", "○"))[0]}">{_RUN_PILL.get(state, ("", "○"))[1]} {e(label)}</span>'
        for label, state in stages)
    attrs = (f' id="progress-card" data-run-id="{e(run_id)}" data-video-id="{e(video_id)}"'
             if not template else "")
    return (
        f'<div class="card"{attrs} style="border-color:var(--accent);margin-bottom:18px"><div class="between"><div>'
        "<h3>⚡ Produção em andamento</h3>"
        '<p class="sub">Roteiro → voz → mídia → composição → qualidade. Ao terminar, abre na aprovação.</p></div>'
        f'<span class="pill accent" data-f="count">{done}/{total} etapas</span></div>'
        f'<div class="prog" style="height:8px;margin-top:12px"><b data-f="bar" style="width:{pct}%;transition:width .5s"></b></div>'
        f'<div class="row" style="margin-top:8px" data-f="pills">{pills}</div></div>'
    )


def _progress_card(view, run_stages=None) -> str:
    """Só quando há produção em andamento. Etapas: as da execução viva (`run_stages`) ou as registradas."""
    if not _run_is_live(view):
        return ""
    if run_stages:
        stages = [(legacy._PRODUCTION_STAGE_LABELS.get(stage, stage), state) for stage, state in run_stages]
    else:
        stages = [(legacy._PRODUCTION_STAGE_LABELS.get(st.step, st.step), st.status) for st in (view.steps or [])]
    run = getattr(view, "latest_run", None)
    run_id = getattr(run, "run_id", "") if run is not None and run.state in _LIVE_RUN_STATES else ""
    return _progress_html(stages, run_id=run_id, video_id=getattr(view.video, "id", ""))


def _progress_slot(view, run_stages=None) -> str:
    return f'<div id="progress-slot">{_progress_card(view, run_stages)}</div>{_progress_template()}'


def _progress_template() -> str:
    """Molde do cartão para a produção iniciada nesta mesma tela (o JS preenche com as etapas reais)."""
    labels = json.dumps(legacy._PRODUCTION_STAGE_LABELS, ensure_ascii=False)
    return (f'<template id="progress-card-template" data-labels="{e(labels)}">'
            f'{_progress_html([], template=True)}</template>')


def render_video_workspace(view, area: str = "cenas", *, active_area: str | None = None,
                           style_view=None, script_view=None,
                           composition_view=None, preview=None, projects=(), project_id: str = "",
                           channel_name: str = "", script=None, scenes=None,
                           sources=None, channel_voice: str | None = None, scene_assets=None,
                           run_stages=None) -> WorkspaceResult:
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
        {_progress_slot(view, run_stages)}
        {_content(view, active_area, style_view=style_view, script_view=script_view, video_id=video_id,
                  composition_view=composition_view,
                  preview=preview if active_area in ("publicacao", "qualidade") else None,
                  scenes=scenes, script=script, channel_voice=channel_voice, channel_name=channel_name,
                  scene_assets=scene_assets)}
      </section>"""

    crumb = f"{channel_name} / {title}" if channel_name else f"Vídeos / {title}"
    # O JS do formulário de aprovação só entra na área Publicação (W5.1); o resto não mudou.
    page_js = (PAGE_JS + (STORYBOARD_JS if active_area == "cenas" else "")
               + (DIRECAO_JS if active_area == "direcao" else "")
               + (RUN_JS if active_area != "producao" else "")  # o cartão acompanha a execução em todas as abas
               + (PUBLICACAO_JS + approval_form.APPROVAL_JS if active_area == "publicacao" else ""))
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
    headers = legacy._headers(nonce)
    # O player da aba Qualidade (vídeo + legendas) é do mesmo servidor; sem `media-src` o default-src 'none' o bloqueava.
    headers["Content-Security-Policy"] = headers["Content-Security-Policy"].replace(
        "img-src", "media-src 'self'; img-src", 1)
    return WorkspaceResult((html, headers))
