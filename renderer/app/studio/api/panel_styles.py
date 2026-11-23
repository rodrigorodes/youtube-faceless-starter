"""Tela de Estilos (VS-05a) — a biblioteca compartilhada, só com dado real do Studio.

Lista os estilos do estúdio; cada linha traz nome, um resumo curto dos parâmetros e **quantos
canais usam** (contagem medida no banco, nunca estimada). Criar/editar usa **divulgação
progressiva em dois níveis**: o essencial primeiro (nome · ritmo de câmera · bpm) e o **Avançado**
recolhido (legenda, cores e voz). Nada é obrigatório além do nome. Arquivar, nunca apagar: o
estilo sai da lista e o nome é liberado; os canais voltam ao padrão do estúdio.

F05.T04 — a biblioteca só edita o que o render aplica. `motion`, `music`, `caption`, `palette` e
`voice` são lidos pelo renderer; `transition` (carregada no plano, ainda não aplicada) e `extra`
(bag de extensão sem leitura) continuam aceitos pela API e **preservados** ao salvar, mas aparecem
rotulados como “não aplicado pelo render”, sem controle editável. O `extra` deixou de ser um
textarea de JSON livre: era um controle que não mudava o vídeo. Personalizar um canal é outra
tela (`panel_channel_style`), com patch por camada — editar aqui nunca cria cópia por canal.

Fonte de verdade: `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` §4/§5.3/§6/§7.
"""
from __future__ import annotations

import html
import json
import secrets

from ..application.styles_page import StyleListItem, StylesPageView
from ..domain.visual_style import MOTIONS
from . import panel as shell
from . import shell_v3

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

# Ritmo de câmera: a ordem de exibição prefere os movimentos reais; `none` fica por último.
# Qualquer movimento novo do domínio entra na lista automaticamente (não some da edição).
_MOTION_ORDER = ("zoom_in", "zoom_out", "pan_left", "pan_right", "none")
_MOTION_LABELS = {
    "zoom_in": "Zoom in",
    "zoom_out": "Zoom out",
    "pan_left": "Esquerda",
    "pan_right": "Direita",
    "none": "Nenhum (sem movimento)",
}
_MOTIONS = [m for m in _MOTION_ORDER if m in MOTIONS] + sorted(MOTIONS - set(_MOTION_ORDER))
# Opções de movimento com rótulo legível: uma fonte só para a biblioteca e a personalização do canal.
MOTION_OPTIONS = tuple((motion, _MOTION_LABELS.get(motion, motion)) for motion in _MOTIONS)

_PALETTE_FIELDS = (
    ("caption_text", "Cor do texto da legenda"),
    ("caption_box", "Cor da caixa da legenda"),
    ("accent", "Cor de destaque"),
)

STYLES_CSS = """
.list { display: grid; gap: 0.5rem; }
.style-row {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) auto auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--line2);
}
.style-row:first-child { border-top: 0; }
.item-title { font-weight: 600; }
.item-sub { font-size: 0.78rem; color: var(--dim); }
.item-sub.unused { color: var(--muted); font-style: italic; }
.usage { font-size: 0.78rem; color: var(--muted); white-space: nowrap; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.9rem 1.1rem; }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field .hint { color: var(--dim); font-size: 0.72rem; line-height: 1.4; }
.input {
  width: 100%;
  padding: 0.5rem 0.6rem;
  background: var(--panel2);
  color: var(--txt);
  border: 1px solid var(--line);
  border-radius: 10px;
  font: inherit;
  font-size: max(1rem, 0.9em);
}
.input:focus-visible { outline: 3px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
.input:user-invalid { border-color: var(--bad); }
textarea.input { min-height: 5rem; resize: vertical; }
fieldset.motion-field { border: 0; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.4rem; }
fieldset.motion-field legend { font-weight: 600; font-size: 0.85rem; padding: 0; margin-bottom: 0.15rem; }
.pill-row { display: flex; flex-wrap: wrap; gap: 0.45rem 0.9rem; align-items: center; }
.motion-option { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; }
.style-disclosure { margin-top: 1rem; }
.style-disclosure > summary { cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0; }
.style-disclosure > summary::-webkit-details-marker { display: none; }
.style-form { margin-top: 0.75rem; }
.form-feedback { font-size: 0.8rem; color: var(--muted); }
.empty-cta { margin-top: 0.9rem; }
@media (max-width: 820px) {
  .style-row { grid-template-columns: minmax(0, 1fr); }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
}
"""

STYLES_SCRIPT = r"""
function collectStyleParams(form) {
  let base = {};
  try { base = JSON.parse(form.dataset.params || '{}') || {}; } catch (error) { base = {}; }
  const params = Object.assign({}, base);

  const motions = Array.from(form.querySelectorAll('input[data-motion]:checked')).map((c) => c.value);
  if (motions.length) { params.motion = motions; } else { delete params.motion; }

  const music = Object.assign({}, base.music || {});
  const bpmInput = form.querySelector('[data-bpm]');
  const bpm = bpmInput ? String(bpmInput.value).trim() : '';
  if (bpm !== '') { music.bpm = Number(bpm); } else { delete music.bpm; }
  if (Object.keys(music).length) { params.music = music; } else { delete params.music; }

  const sizeInput = form.querySelector('[data-caption-size]');
  const bottomInput = form.querySelector('[data-caption-bottom]');
  const caption = {};
  const size = sizeInput ? String(sizeInput.value).trim() : '';
  const bottom = bottomInput ? String(bottomInput.value).trim() : '';
  if (size !== '') { caption.font_size = Number(size); }
  if (bottom !== '') { caption.bottom = Number(bottom); }
  if (Object.keys(caption).length) { params.caption = caption; } else { delete params.caption; }

  const palette = {};
  form.querySelectorAll('[data-palette]').forEach((input) => {
    const value = input.value.trim();
    if (value) { palette[input.getAttribute('data-palette')] = value; }
  });
  if (Object.keys(palette).length) { params.palette = palette; } else { delete params.palette; }

  const voiceInput = form.querySelector('[data-voice]');
  const model = voiceInput ? voiceInput.value.trim() : '';
  if (model) { params.voice = { model: model }; } else { delete params.voice; }

  // `transition` e `extra` não têm controle (o render não os aplica): ficam intocados no
  // `base` lido de `data-params`, então salvar outro campo não os apaga.
  return params;
}

document.querySelectorAll('form[data-style-form]').forEach((form) => {
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const feedback = form.querySelector('[data-feedback]');
    const button = form.querySelector('[data-submit]');
    const nameField = form.querySelector('[data-name]');
    const name = nameField ? nameField.value.trim() : '';
    if (!name) {
      if (feedback) feedback.textContent = 'Informe o nome do estilo.';
      if (nameField) { nameField.setAttribute('aria-invalid', 'true'); nameField.focus(); }
      return;
    }
    if (nameField) nameField.removeAttribute('aria-invalid');
    let params;
    try { params = collectStyleParams(form); }
    catch (error) { if (feedback) feedback.textContent = String((error && error.message) || error); return; }
    const mode = form.dataset.mode;
    const styleId = form.dataset.styleId || '';
    const version = Number(form.dataset.version || '0');
    if (button) button.disabled = true;
    if (feedback) feedback.textContent = mode === 'edit' ? 'Salvando nova versão...' : 'Criando estilo...';
    try {
      const payload = mode === 'edit'
        ? { expected_version: version, changes: { name: name, params: params } }
        : { name: name, params: params };
      const response = await fetch(mode === 'edit' ? '/studio/styles/' + encodeURIComponent(styleId) : '/studio/styles', {
        method: mode === 'edit' ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        if (feedback) feedback.textContent = 'Salvo. Atualizando...';
        setTimeout(() => window.location.reload(), 500);
      } else if (response.status === 409) {
        if (feedback) feedback.textContent = 'Outra alteração venceu a corrida: recarregue e revise a versão atual.';
        if (button) button.disabled = false;
      } else {
        if (feedback) feedback.textContent = 'Não foi possível salvar: '
          + (typeof data.detail === 'string' ? data.detail : 'verifique os campos e tente novamente.');
        if (button) button.disabled = false;
      }
    } catch (error) {
      if (feedback) feedback.textContent = 'Falha de rede ao salvar o estilo. Tente novamente.';
      if (button) button.disabled = false;
    }
  });
});

document.querySelectorAll('[data-archive-style]').forEach((button) => {
  button.addEventListener('click', async () => {
    const styleId = button.getAttribute('data-archive-style');
    const name = button.getAttribute('data-style-name') || 'este estilo';
    const form = button.closest('form');
    const feedback = form ? form.querySelector('[data-feedback]') : null;
    if (!window.confirm('Arquivar "' + name + '"? Os canais que usavam voltam ao padrão do estúdio. Nada é apagado.')) return;
    button.disabled = true;
    if (feedback) feedback.textContent = 'Arquivando...';
    try {
      const response = await fetch('/studio/styles/' + encodeURIComponent(styleId) + '/archive', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        if (feedback) feedback.textContent = 'Arquivado. Atualizando...';
        setTimeout(() => window.location.reload(), 500);
      } else {
        if (feedback) feedback.textContent = 'Não foi possível arquivar: '
          + (typeof data.detail === 'string' ? data.detail : 'tente novamente.');
        button.disabled = false;
      }
    } catch (error) {
      if (feedback) feedback.textContent = 'Falha de rede ao arquivar. Tente novamente.';
      button.disabled = false;
    }
  });
});

const firstStyle = document.getElementById('btn-criar-primeiro');
if (firstStyle) {
  firstStyle.addEventListener('click', () => {
    const details = document.getElementById('novo-estilo');
    if (details) { details.open = true; details.scrollIntoView({ block: 'start' }); }
    const field = document.getElementById('novo-estilo-nome');
    if (field) field.focus();
  });
}
"""


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------


def _param_summary(params: dict) -> str:
    """Resumo curto e honesto **do que o render aplica**; `transition`/`extra` não entram aqui."""
    parts = []
    motion = params.get("motion")
    if isinstance(motion, list) and motion:
        parts.append(" + ".join(str(item) for item in motion))
    music = params.get("music")
    if isinstance(music, dict) and music.get("bpm") is not None:
        parts.append(f"{music['bpm']} bpm")
    caption = params.get("caption")
    if isinstance(caption, dict) and caption.get("font_size") is not None:
        parts.append(f"legenda {caption['font_size']}px")
    if params.get("palette"):
        parts.append("cores")
    if params.get("voice"):
        parts.append("voz")
    if parts:
        return " · ".join(parts)
    if params:
        return "nenhum parâmetro aplicado pelo render"
    return "sem parâmetros declarados"


def _unused_param_labels(params: dict) -> list[str]:
    """Parâmetros declarados que o render **não** aplica hoje (rotulados, nunca fingidos)."""
    labels = []
    if params.get("transition"):
        labels.append("transição")
    extra = params.get("extra")
    if isinstance(extra, dict) and extra:
        count = len(extra)
        labels.append(f"extra ({count} chave{'s' if count != 1 else ''})")
    return labels


def _unused_param_note(params: dict) -> str:
    labels = _unused_param_labels(params)
    if not labels:
        return ""
    return (f'<div class="item-sub unused">Declarado e não aplicado pelo render: '
            f'{e(", ".join(labels))}. Preservado ao salvar.</div>')


def _usage_text(count: int) -> str:
    if count <= 0:
        return "Nenhum canal usa"
    if count == 1:
        return "1 canal usa"
    return f"{count} canais usam"


def _motion_checkboxes(prefix: str, selected: set[str]) -> str:
    options = []
    for motion in _MOTIONS:
        field_id = f"{prefix}-motion-{motion}"
        checked = " checked" if motion in selected else ""
        options.append(
            f'<span class="motion-option">'
            f'<input type="checkbox" id="{field_id}" value="{e(motion)}" data-motion{checked}>'
            f'<label for="{field_id}">{e(_MOTION_LABELS.get(motion, motion))}</label>'
            f"</span>"
        )
    return "".join(options)


def _value(params: dict, section: str, key: str) -> str:
    block = params.get(section)
    if isinstance(block, dict) and block.get(key) is not None:
        return str(block[key])
    return ""


def _style_form(prefix: str, *, style=None) -> str:
    """Formulário de criar/editar com divulgação progressiva em dois níveis.

    Nível 1 é a própria divulgação (o `<details>` que o contém). Nível 2 é o "Avançado". Só os
    parâmetros que o render aplica ganham controle; o que não tem suporte (`transition`, `extra`)
    é preservado a partir do `data-params` e aparece rotulado como não aplicado — nada é
    inventado, nada é perdido sem querer e nenhum controle promete efeito que não existe.
    """
    is_edit = style is not None
    params = dict(style.params) if is_edit else {}
    selected_motions = set(params.get("motion") or [])
    unused_labels = _unused_param_labels(params)
    unused_note = (
        f'<p class="hint" id="{prefix}-nao-aplicado">Declarado neste estilo, não aplicado pelo '
        f'render hoje: {e(", ".join(unused_labels))}. Não há controle de edição; o valor é '
        f'preservado ao salvar.</p>'
        if unused_labels else ""
    )
    mode = "edit" if is_edit else "create"
    style_id = style.id if is_edit else ""
    version = style.version if is_edit else 0
    name = style.name if is_edit else ""
    submit_label = "Salvar nova versão" if is_edit else "Criar estilo"
    archive_button = (
        f'<button class="btn" type="button" data-archive-style="{e(style_id)}" '
        f'data-style-name="{e(name)}">Arquivar</button>'
        if is_edit else ""
    )
    palette_fields = "".join(
        f'<div class="field">'
        f'<label for="{prefix}-{key}">{e(label)}</label>'
        f'<input class="input" type="text" id="{prefix}-{key}" data-palette="{key}" '
        f'value="{e(_value(params, "palette", key))}" maxlength="9" placeholder="#RRGGBB" '
        f'pattern="^#[0-9A-Fa-f]{{6}}([0-9A-Fa-f]{{2}})?$" aria-describedby="{prefix}-{key}-hint">'
        f'<span class="hint" id="{prefix}-{key}-hint">Hex como #RRGGBB ou #RRGGBBAA. Vazio = padrão do render.</span>'
        f"</div>"
        for key, label in _PALETTE_FIELDS
    )
    return f"""
      <form class="style-form" data-style-form data-mode="{mode}" data-style-id="{e(style_id)}"
            data-version="{version}" data-params="{e(json.dumps(params, ensure_ascii=False))}">
        <div class="grid-2">
          <div class="field">
            <label for="{prefix}-nome">Nome do estilo</label>
            <input class="input" type="text" id="{prefix}-nome" name="name" value="{e(name)}"
                   maxlength="120" required data-name aria-describedby="{prefix}-nome-hint">
            <span class="hint" id="{prefix}-nome-hint">Um nome ativo por vez: arquivar libera o nome para reúso.</span>
          </div>
          <fieldset class="motion-field">
            <legend>Ritmo de câmera</legend>
            <div class="pill-row">{_motion_checkboxes(prefix, selected_motions)}</div>
            <span class="hint" id="{prefix}-motion-hint">Sem ritmo escolhido, o render usa o próprio ciclo. Vale para todos os canais que usam este estilo.</span>
          </fieldset>
          <div class="field">
            <label for="{prefix}-bpm">Música (bpm)</label>
            <input class="input" type="number" inputmode="numeric" min="20" max="300" step="1"
                   id="{prefix}-bpm" data-bpm value="{e(_value(params, "music", "bpm"))}"
                   aria-describedby="{prefix}-bpm-hint">
            <span class="hint" id="{prefix}-bpm-hint">20 a 300 bpm. Vazio = sem batida declarada.</span>
          </div>
        </div>
        <details class="advanced" id="{prefix}-avancado">
          <summary class="advanced-summary">Avançado — legenda, cores e voz</summary>
          <div class="advanced-body">
            <div class="grid-2">
              <div class="field">
                <label for="{prefix}-caption-size">Tamanho da legenda (px)</label>
                <input class="input" type="number" inputmode="numeric" min="8" max="400" step="1"
                       id="{prefix}-caption-size" data-caption-size
                       value="{e(_value(params, "caption", "font_size"))}">
              </div>
              <div class="field">
                <label for="{prefix}-caption-bottom">Distância do rodapé (px)</label>
                <input class="input" type="number" inputmode="numeric" min="0" step="1"
                       id="{prefix}-caption-bottom" data-caption-bottom
                       value="{e(_value(params, "caption", "bottom"))}">
              </div>
              {palette_fields}
              <div class="field">
                <label for="{prefix}-voice">Voz (modelo)</label>
                <input class="input" type="text" id="{prefix}-voice" data-voice maxlength="200"
                       value="{e(_value(params, "voice", "model"))}"
                       aria-describedby="{prefix}-voice-hint">
                <span class="hint" id="{prefix}-voice-hint">Modelo de voz do provider. Vazio = padrão do render.</span>
              </div>
            </div>
            {unused_note}
          </div>
        </details>
        <div class="spread" style="margin-top:1rem">
          <div class="pill-row">
            <button class="btn btn-primary" type="submit" data-submit>{e(submit_label)}</button>
            {archive_button}
          </div>
          <div class="form-feedback" data-feedback role="status" aria-live="polite"></div>
        </div>
      </form>
    """


def _create_card() -> str:
    return f"""
      <details class="style-disclosure" id="novo-estilo">
        <summary>
          <span class="btn btn-primary btn-compact">+ Novo estilo</span>
          <span class="dim" style="font-size:0.85rem">criar um estilo reutilizável entre canais</span>
        </summary>
        {_style_form("novo-estilo")}
      </details>
    """


def _empty_card() -> str:
    return """
      <div class="card empty" id="estilos-vazio">
        <h2>Nenhum estilo ainda</h2>
        <p class="muted">A biblioteca está vazia. Crie o primeiro estilo para reusá-lo em vários canais.</p>
        <p class="fine">Sem estilo escolhido, o canal segue o padrão do estúdio — e está ótimo. Criar um estilo não muda nenhum canal sozinho.</p>
        <div class="empty-cta">
          <button class="btn btn-primary" type="button" id="btn-criar-primeiro">Criar o primeiro estilo</button>
        </div>
      </div>
    """


def _style_row(item: StyleListItem) -> str:
    style = item.style
    prefix = f"editar-{style.id}"
    return f"""
      <li class="style-row" data-style-id="{e(style.id)}">
        <div>
          <div class="item-title">{e(style.name)}</div>
          <div class="item-sub">{e(_param_summary(style.params))} · versão {style.version}</div>
          {_unused_param_note(style.params)}
        </div>
        <span class="usage">{e(_usage_text(item.channels_using))}</span>
        <details class="style-disclosure">
          <summary class="btn btn-sm btn-ghost">Editar</summary>
          {_style_form(prefix, style=style)}
        </details>
      </li>
    """


def _list_card(view: StylesPageView) -> str:
    rows = "".join(_style_row(item) for item in view.items)
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Biblioteca de estilos</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              Estilo é compartilhado entre canais. O resumo mostra o que o render aplica; a contagem é medida no banco.
            </p>
          </div>
          <span class="chip-metric">{len(view.items)} estilo(s)</span>
        </div>
        <ul class="list" style="margin-top:14px">{rows}</ul>
      </div>
    """


def _rail(view: StylesPageView) -> str:
    channels_with_style = sum(item.channels_using for item in view.items)
    return f"""
      <aside class="rail" aria-label="Resumo">
        <section class="card" aria-labelledby="h-biblioteca">
          <h2 id="h-biblioteca">A biblioteca</h2>
          <div class="kv"><span>Estilos ativos</span><span>{len(view.items)}</span></div>
          <div class="kv"><span>Canais com estilo</span><span>{channels_with_style}</span></div>
          <p class="fine">Estilo é compartilhado: editar aqui vale para todos os canais que o usam. Nada de copiar à mão.</p>
        </section>
        <section class="card" aria-labelledby="h-arquivar">
          <h2 id="h-arquivar">Arquivar, não apagar</h2>
          <p class="fine">Arquivar tira o estilo da lista e libera o nome; os canais que usavam voltam ao padrão do estúdio. O histórico das versões é preservado.</p>
        </section>
      </aside>
    """


def _sidebar_card(view: StylesPageView) -> str:
    return f"""
        <div class="side-card">
          <h2>Biblioteca de estilos</h2>
          <div class="kv"><span>Estilos ativos</span><span>{len(view.items)}</span></div>
          <div class="kv"><span>Canais com estilo</span><span>{sum(item.channels_using for item in view.items)}</span></div>
        </div>
    """


def render_styles(view: StylesPageView, *, projects: list[tuple[str, str]] | None = None,
                  project_id: str = "") -> tuple[str, dict[str, str]]:
    """Página da Biblioteca de estilos: casca aprovada + lista real + criar/editar/arquivar.

    W1.5: é o item **Biblioteca** do menu principal (protótipo `NAV` → `library`), não uma seção
    de Configurações. Recebe o canal ativo para a topbar e para os links não perderem o contexto.
    """
    nonce = secrets.token_urlsafe(16)
    body = _empty_card() if view.is_empty else _list_card(view)
    content_html = f"""
      <div class="card">
        <div class="spread">
          <p class="page-goal" style="color: var(--text-muted); font-size: 0.85rem; margin: 0">
            Ação primária: <b>manter estilos reutilizáveis</b>. O estilo é compartilhado — separado do canal, para não virar cópia à mão.
          </p>
          <span class="chip-metric">{len(view.items)} estilo(s)</span>
        </div>
      </div>
      {body}
      {_create_card()}
    """
    # UX: o título da página já diz "Biblioteca"; o cartão não repete o mesmo `<h2>` (protótipo
    # `library`, `prototype/index.html:635`, também não tem cabeçalho duplicado).
    body_page = shell_v3.render_library_page_body(
        title="Estilos reutilizáveis",
        lead="Os estilos são reutilizados; personalizações do canal permanecem independentes.",
        content_html=content_html,
    )
    html = shell_v3.render_document(
        title="Faceless Studio — Biblioteca",
        active="biblioteca",
        crumb="Biblioteca",
        body_html=body_page,
        nonce=nonce,
        projects=projects or [],
        project_id=project_id,
        cost_note="",
        page_js=STYLES_SCRIPT,
        extra_css=STYLES_CSS,
    )
    return html, shell._headers(nonce)
