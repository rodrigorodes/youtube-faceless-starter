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
import re
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

  const descInput = form.querySelector('[data-description]');
  const artInput = form.querySelector('[data-art]');
  const extra = Object.assign({}, base.extra || {});
  const desc = descInput ? descInput.value.trim() : '';
  const art = artInput ? artInput.value.trim() : '';
  if (descInput) { if (desc) { extra.description = desc; } else { delete extra.description; } }
  if (artInput) { if (art) { extra.art_prompt = art; } else { delete extra.art_prompt; } }
  if (Object.keys(extra).length) { params.extra = extra; } else { delete params.extra; }

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

function abrirDialogo(id) {
  const dlg = document.getElementById(id);
  if (!dlg) return;
  if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  const campo = dlg.querySelector('[data-name]');
  if (campo) campo.focus();
}
document.querySelectorAll('[data-abrir-dialogo]').forEach((btn) => {
  btn.addEventListener('click', () => abrirDialogo(btn.getAttribute('data-abrir-dialogo')));
});
document.querySelectorAll('dialog.modal').forEach((dlg) => {
  dlg.addEventListener('click', (ev) => {
    if (ev.target === dlg || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlg.close();
  });
});

document.querySelectorAll('[data-vincular-estilo]').forEach((button) => {
  button.addEventListener('click', async () => {
    const root = document.getElementById('pagina-biblioteca');
    const canal = root ? root.getAttribute('data-canal') : '';
    const versao = Number(root ? root.getAttribute('data-canal-versao') : '0');
    const status = document.getElementById('biblioteca-status');
    button.disabled = true;
    if (status) status.textContent = 'Vinculando ao canal...';
    try {
      const response = await fetch('/studio/channels/' + encodeURIComponent(canal), {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: versao, changes: { style_id: button.getAttribute('data-vincular-estilo') } })
      });
      if (response.ok) { window.location.reload(); return; }
      if (status) status.textContent = response.status === 409
        ? 'Outra alteração venceu a corrida: recarregue e tente de novo.'
        : 'Não foi possível vincular o estilo ao canal.';
    } catch (error) {
      if (status) status.textContent = 'Falha de rede ao vincular o estilo.';
    }
    button.disabled = false;
  });
});

const abas = Array.prototype.slice.call(document.querySelectorAll('[data-aba-biblioteca]'));
abas.forEach((aba) => {
  aba.addEventListener('click', () => {
    abas.forEach((o) => {
      const on = o === aba;
      if (on) o.setAttribute('aria-current', 'page'); else o.removeAttribute('aria-current');
      const painel = document.getElementById('painel-' + o.getAttribute('data-aba-biblioteca'));
      if (painel) painel.hidden = !on;
    });
  });
});
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
    extra = params.get("extra") if isinstance(params.get("extra"), dict) else {}
    desc_fields = (
        f'<div class="field"><label for="{prefix}-descricao">Descrição curta</label>'
        f'<input type="text" id="{prefix}-descricao" data-description maxlength="200" value="{e(extra.get("description", ""))}"></div>'
        f'<div class="field"><label for="{prefix}-arte">Instrução de arte (prompt base)</label>'
        f'<textarea id="{prefix}-arte" rows="3" data-art maxlength="500" placeholder="Ex.: noir, preto e branco, alto contraste">'
        f'{e(extra.get("art_prompt", ""))}</textarea></div>'
    )
    if not is_edit:
        # `renderModal` → `m.t==='style'` do protótipo: Nome, Descrição curta, Instrução de arte.
        return f"""
      <form class="style-form" style="margin:0" data-style-form data-mode="create" data-style-id="" data-version="0" data-params="{{}}">
        <h3>Criar novo estilo</h3>
        <div class="field" style="margin-top:12px"><label for="{prefix}-nome">Nome</label>
          <input type="text" id="{prefix}-nome" name="name" maxlength="120" required data-name placeholder="Ex.: Noir Poético"></div>
        {desc_fields}
        <div class="row" style="justify-content:flex-end">
          <button class="btn ghost small" type="button" data-fechar-dialogo>Cancelar</button>
          <button class="btn primary small" type="submit" data-submit>Salvar na biblioteca</button>
        </div>
        <div class="form-feedback" data-feedback role="status" aria-live="polite"></div>
      </form>
    """
    return f"""
      <form class="style-form" data-style-form data-mode="{mode}" data-style-id="{e(style_id)}"
            data-version="{version}" data-params="{e(json.dumps(params, ensure_ascii=False))}">
        <h3>Editar estilo</h3>
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
        <div class="grid-2" style="margin-top:0.9rem">{desc_fields}</div>
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


def _estilo_descricao(style) -> str:
    extra = style.params.get("extra") if isinstance(style.params.get("extra"), dict) else {}
    desc = str(extra.get("description") or "").strip()
    return desc or _param_summary(style.params)


def _estilo_thumb(style) -> str:
    """Miniatura: o gradiente vem da paleta real do estilo; sem paleta, o fundo neutro da casca."""
    palette = style.params.get("palette") if isinstance(style.params.get("palette"), dict) else {}
    cor = str(palette.get("accent") or "")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", cor):
        cor = "#2b2540"
    return f"linear-gradient(135deg,{cor},#15171c)"


def _style_card(item: StyleListItem, ativo: bool, tem_canal: bool) -> str:
    style = item.style
    estilo = ('style="border:2px solid var(--accent);background:var(--accentbg);padding:17px"' if ativo else "")
    selo = '<span class="pill accent">✓ Ativo no canal</span>' if ativo else ""
    if ativo:
        acao = '<span class="sample" style="color:var(--ok)">Padrão herdado para novos vídeos</span>'
    elif tem_canal:
        acao = (f'<button class="btn small" type="button" data-vincular-estilo="{e(style.id)}">Vincular ao canal</button>')
    else:
        acao = '<span class="sample">Sem canal ativo para vincular.</span>'
    editar = (f'<button class="btn ghost small" type="button" data-abrir-dialogo="editar-{e(style.id)}" '
              f'style="margin-left:6px">Editar</button>')
    return f"""<div class="card" data-style-id="{e(style.id)}" {estilo}>
          <div class="thumb" style="height:100px;background:{e(_estilo_thumb(style))};margin-bottom:10px"><span style="font-size:34px">🎨</span></div>
          <div class="between"><b>{e(style.name)}</b>{selo}</div>
          <p class="sub" style="margin:4px 0 10px">{e(_estilo_descricao(style))}</p>
          {acao}{editar}
        </div>"""


def _dialog(dialog_id: str, form_html: str) -> str:
    return (f'<dialog id="{e(dialog_id)}" class="modal" aria-label="Estilo">'
            f'{form_html}</dialog>')


def render_styles(view: StylesPageView, *, projects: list[tuple[str, str]] | None = None,
                  project_id: str = "", channel_name: str = "", channel_style_id: str | None = None,
                  channel_version: int | None = None, channel_voice: str = "") -> tuple[str, dict[str, str]]:
    """Biblioteca (`pgLibrary`): abas Estilos visuais / Vozes / Músicas / Modelos de roteiro.

    Estilos vêm da biblioteca real; "Vincular ao canal" grava `style_id` no perfil do canal ativo.
    Vozes, Músicas e Modelos de roteiro não têm catálogo no produto: o painel diz isso em vez de
    inventar itens do mockup.
    """
    nonce = secrets.token_urlsafe(16)
    nome_canal = channel_name or next((n for pid, n in (projects or []) if pid == project_id), "") or "nenhum canal"
    tem_canal = bool(project_id) and channel_version is not None
    if view.is_empty:
        cards = '<div class="card" id="estilos-vazio"><p class="sub">A biblioteca ainda não tem estilos. Use "+ Criar novo estilo".</p></div>'
    else:
        cards = '<div class="grid3">' + "".join(
            _style_card(item, item.style.id == channel_style_id, tem_canal) for item in view.items) + "</div>"
    dialogs = _dialog("novo-estilo-dialog", _style_form("novo-estilo")) + "".join(
        _dialog(f"editar-{item.style.id}", _style_form(f"editar-{item.style.id}", style=item.style))
        for item in view.items)
    voz = (f'Ainda não há catálogo de vozes na biblioteca. A voz do canal ativo é "{e(channel_voice)}" e é definida no perfil do canal.'
           if channel_voice else "Ainda não há catálogo de vozes na biblioteca. A voz é definida no perfil de cada canal.")
    abas = (("estilos", "Estilos visuais"), ("vozes", "Vozes"), ("musicas", "Músicas"), ("modelos", "Modelos de roteiro"))
    atual = ' aria-current="page"'
    tabs = "".join(f'<button class="tab" type="button" data-aba-biblioteca="{k}"{atual if k == "estilos" else ""}>{l}</button>'
                   for k, l in abas)
    body_page = f"""      <section class="pagina" id="pagina-biblioteca" aria-labelledby="t-biblioteca" data-canal="{e(project_id)}" data-canal-versao="{e(channel_version or 0)}">
        <div class="head"><div><p class="eyebrow">Recursos reutilizáveis</p><h1 id="t-biblioteca">Biblioteca</h1><p class="sub">Canal ativo: {e(nome_canal)}</p></div></div>
        <nav class="tabs" aria-label="Biblioteca">{tabs}</nav>
        <div id="painel-estilos">
          <div class="between" style="margin-bottom:14px"><p class="sub">O estilo vinculado ao canal é herdado por todos os novos vídeos.</p><button class="btn small" type="button" data-abrir-dialogo="novo-estilo-dialog">+ Criar novo estilo</button></div>
          {cards}
          <p class="sample" id="biblioteca-status" role="status" aria-live="polite"></p>
        </div>
        <div id="painel-vozes" hidden><p class="sub">{voz}</p></div>
        <div id="painel-musicas" hidden><p class="sub">Ainda não há biblioteca de músicas. O ritmo (bpm) é um parâmetro de cada estilo visual.</p></div>
        <div id="painel-modelos" hidden><p class="sub">Ainda não há modelos de roteiro cadastrados.</p></div>
        {dialogs}
      </section>"""
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
