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
import os
from pathlib import Path
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
.hint { color: var(--muted); font-size: 12px; line-height: 1.45; margin: 0; }
.field .hint { margin-top: 1px; }
dialog.estilo-dialog { width: min(720px, calc(100% - 32px)); }
.style-form .modal-header { margin-bottom: 16px; }
.style-form .field > label, fieldset.motion-field legend { font-size: 12px; color: var(--muted); font-weight: 600; }
.style-form .grid-2 + .grid-2 { margin-top: 4px; }
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
fieldset.motion-field legend { padding: 0; margin-bottom: 6px; }
.pill-row { display: flex; flex-wrap: wrap; gap: 0.45rem 0.9rem; align-items: center; }
.motion-field .pill-row { gap: 8px; }
.motion-option {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text);
  background: var(--panel2); border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; cursor: pointer;
}
.motion-option label { cursor: pointer; }
.motion-option:hover { border-color: var(--line2); }
.motion-option:has(input:checked) { border-color: var(--accent); background: var(--accentbg); color: var(--accent2); }
.motion-option:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
details.advanced { margin-top: 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel2); }
.advanced-summary { cursor: pointer; padding: 12px 14px; font-size: 13px; font-weight: 600; color: var(--text); }
details.advanced[open] > .advanced-summary { border-bottom: 1px solid var(--line); }
.advanced-body { padding: 14px 14px 4px; }
.advanced-body .input, .advanced-body textarea { background: var(--bg); }
.form-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }
.form-actions .form-feedback { flex: 1 1 100%; min-height: 1em; }
.form-feedback:empty { display: none; }
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
          + (window.StudioErro.texto(data, 'verifique os campos e tente novamente.'));
        if (button) button.disabled = false;
      }
    } catch (error) {
      if (feedback) feedback.textContent = 'Falha de rede ao salvar o estilo. Tente novamente.';
      if (button) button.disabled = false;
    }
  });
});

const dlgArquivar = document.getElementById('dlg-arquivar-estilo');
let arquivarAlvo = null;
document.querySelectorAll('[data-archive-style]').forEach((button) => {
  button.addEventListener('click', () => {
    arquivarAlvo = button;
    const nome = document.getElementById('arquivar-nome');
    if (nome) nome.textContent = '\u201c' + (button.getAttribute('data-style-name') || 'este estilo') + '\u201d';
    const erro = document.getElementById('arquivar-erro'); if (erro) erro.textContent = '';
    if (dlgArquivar && typeof dlgArquivar.showModal === 'function') dlgArquivar.showModal();
    else if (dlgArquivar) dlgArquivar.setAttribute('open', '');
  });
});
const btnArquivar = document.getElementById('btn-confirmar-arquivar');
if (btnArquivar) btnArquivar.addEventListener('click', async () => {
  if (!arquivarAlvo) return;
  const styleId = arquivarAlvo.getAttribute('data-archive-style');
  const erro = document.getElementById('arquivar-erro');
  btnArquivar.disabled = true;
  if (erro) erro.textContent = 'Arquivando...';
  try {
    const response = await fetch('/studio/styles/' + encodeURIComponent(styleId) + '/archive', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      if (erro) erro.textContent = 'Arquivado. Atualizando...';
      setTimeout(() => window.location.reload(), 500);
      return;
    }
    if (erro) erro.textContent = 'N\u00e3o foi poss\u00edvel arquivar: '
      + (window.StudioErro.texto(data, 'tente novamente.'));
  } catch (error) {
    if (erro) erro.textContent = 'Falha de rede ao arquivar. Tente novamente.';
  }
  btnArquivar.disabled = false;
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
      if (on) { o.classList.add('ativa'); o.setAttribute('aria-selected', 'true'); }
      else { o.classList.remove('ativa'); o.setAttribute('aria-selected', 'false'); }
      const painel = document.getElementById('painel-' + o.getAttribute('data-aba-biblioteca'));
      if (painel) painel.hidden = !on;
    });
  });
});

(function () {
  var form = document.getElementById('pixabay-search-form');
  var qInput = document.getElementById('pixabay-query');
  var typeSel = document.getElementById('pixabay-type');
  var fb = document.getElementById('pixabay-feedback');
  var resultsEl = document.getElementById('pixabay-results');
  var quickTags = document.getElementById('pixabay-quick-tags');

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function doSearch(q, type) {
    if (!resultsEl) return;
    resultsEl.innerHTML = '<p class="sub">Buscando mídias no Pixabay...</p>';
    if (fb) fb.textContent = 'Carregando mídias para "' + q + '"...';
    fetch('/studio/media/search?q=' + encodeURIComponent(q) + '&type=' + encodeURIComponent(type) + '&per_page=12')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          resultsEl.innerHTML = '<p class="sub" style="color:var(--bad)">' + esc(data.error || 'Falha ao buscar mídias') + '</p>';
          if (fb) fb.textContent = '';
          return;
        }
        var cands = data.candidates || [];
        if (!cands.length) {
          resultsEl.innerHTML = '<p class="sub">Nenhuma mídia encontrada para "' + esc(q) + '". Tente outra palavra-chave.</p>';
          if (fb) fb.textContent = '';
          return;
        }
        if (fb) fb.textContent = cands.length + ' resultado(s) encontrados para "' + q + '" (' + (type === 'video' ? 'Vídeos' : 'Fotos') + '):';
        resultsEl.innerHTML = cands.map(function (c) {
          var isVid = c.media_type === 'video';
          var mediaBlock = isVid
            ? '<video controls preload="metadata" style="width:100%;height:150px;object-fit:cover;border-radius:8px;background:#000" src="' + esc(c.url) + '"></video>'
            : '<img src="' + esc(c.url) + '" alt="' + esc(c.attribution) + '" loading="lazy" style="width:100%;height:150px;object-fit:cover;border-radius:8px;background:var(--panel2)">';
          var dim = (c.width && c.height) ? (c.width + '×' + c.height) : (isVid ? 'Vídeo HD' : 'Foto HD');
          var user = c.author ? 'Por ' + esc(c.author) : 'Pixabay';
          return '<div class="card" style="padding:10px;display:flex;flex-direction:column;gap:8px">'
            + mediaBlock
            + '<div class="between" style="font-size:12px"><span>' + user + '</span><span class="pill small ok">' + esc(dim) + '</span></div>'
            + '<div class="between sub" style="font-size:11px"><span>' + esc(c.license) + '</span>'
            + '<a class="btn ghost small" href="' + esc(c.source_url || c.url) + '" target="_blank" rel="noopener">Ver original ↗</a>'
            + '</div></div>';
        }).join('');
      })
      .catch(function (err) {
        resultsEl.innerHTML = '<p class="sub" style="color:var(--bad)">Erro ao conectar: ' + esc(err.message) + '</p>';
        if (fb) fb.textContent = '';
      });
  }

  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var q = qInput ? qInput.value.trim() : 'tecnologia';
      var t = typeSel ? typeSel.value : 'image';
      doSearch(q, t);
    });
  }

  if (quickTags) {
    quickTags.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-q]');
      if (!btn) return;
      var q = btn.getAttribute('data-q');
      if (qInput) qInput.value = q;
      var t = typeSel ? typeSel.value : 'image';
      doSearch(q, t);
    });
  }

  var tabMidias = document.querySelector('[data-aba-biblioteca="midias"]');
  if (tabMidias) {
    tabMidias.addEventListener('click', function () {
      if (resultsEl && resultsEl.children.length === 0) {
        var q = qInput ? qInput.value.trim() : 'tecnologia';
        var t = typeSel ? typeSel.value : 'image';
        doSearch(q, t);
      }
    });
  }
})();
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


def _modal_header(title: str, title_id: str) -> str:
    return (f'<div class="modal-header"><h2 id="{title_id}">{e(title)}</h2>'
            '<button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>')


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
        {_modal_header("Criar novo estilo", prefix + "-titulo")}
        <div class="field"><label for="{prefix}-nome">Nome</label>
          <input type="text" id="{prefix}-nome" name="name" maxlength="120" required data-name placeholder="Ex.: Noir Poético"></div>
        {desc_fields}
        <div class="form-actions" style="justify-content:flex-end">
          <button class="btn ghost small" type="button" data-fechar-dialogo>Cancelar</button>
          <button class="btn primary small" type="submit" data-submit>Salvar na biblioteca</button>
        </div>
        <div class="form-feedback" data-feedback role="status" aria-live="polite"></div>
      </form>
    """
    return f"""
      <form class="style-form" data-style-form data-mode="{mode}" data-style-id="{e(style_id)}"
            data-version="{version}" data-params="{e(json.dumps(params, ensure_ascii=False))}">
        {_modal_header("Editar estilo", prefix + "-titulo")}
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
        <div class="form-actions">
          <div class="pill-row">
            <button class="btn primary" type="submit" data-submit>{e(submit_label)}</button>
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


def _dialog(dialog_id: str, form_html: str, *, wide: bool = False) -> str:
    return (f'<dialog id="{e(dialog_id)}" class="modal{" estilo-dialog" if wide else ""}" aria-label="Estilo">'
            f'{form_html}</dialog>')


def _render_voice_cards(channel_voice: str, project_id: str) -> str:
    is_faber_active = (channel_voice in ("piper:pt_BR-faber-medium", "pt_BR-faber-medium") or not channel_voice)
    is_jeff_active = (channel_voice in ("piper:pt_BR-jeff-medium", "pt_BR-jeff-medium"))
    is_demo_active = (channel_voice in ("demo", "demo:"))

    faber_pill = '<span class="pill accent">✓ Ativa no canal</span>' if is_faber_active else '<span class="pill ok">✓ Instalada</span>'
    jeff_pill = '<span class="pill accent">✓ Ativa no canal</span>' if is_jeff_active else '<span class="pill">Compatível</span>'
    demo_pill = '<span class="pill accent">✓ Ativa no canal</span>' if is_demo_active else '<span class="pill">Desenvolvimento</span>'

    config_link = f'/studio/configuracoes/canais?project_id={e(project_id)}' if project_id else '/studio/configuracoes/canais'

    return f"""
      <div class="between" style="margin-bottom:14px">
        <div>
          <p class="sub">Catálogo de vozes neurais locais e integradas para narração. A voz é herdada em todos os novos vídeos do canal ativo.</p>
        </div>
        <a class="btn ghost small" href="{config_link}">⚙ Configurar voz no canal</a>
      </div>
      <div class="grid3">
        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px{' ;border:2px solid var(--accent);background:var(--accentbg)' if is_faber_active else ''}">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Piper Faber (pt-BR)</b>
                <p class="sub" style="margin:2px 0 0">Voz neural oficial (Padrão do Studio)</p>
              </div>
              {faber_pill}
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Narração masculina natural em português brasileiro, com baixa latência e síntese totalmente offline via CPU.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Motor</span><b>Piper Neural ONNX</b></div>
              <div class="between"><span class="sub">Idioma</span><b>Português (Brasil)</b></div>
              <div class="between"><span class="sub">Ritmo medido</span><b>~172 palavras/min</b></div>
              <div class="between"><span class="sub">Custo de API</span><span class="pill ok" style="padding:1px 8px;font-size:11px">Gratuito (Local)</span></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px" class="between">
            <code class="mono" style="font-size:11px">piper:pt_BR-faber-medium</code>
            <span class="sub" style="font-size:11px">Voz padrão</span>
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px{' ;border:2px solid var(--accent);background:var(--accentbg)' if is_jeff_active else ''}">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Piper Jeff (pt-BR)</b>
                <p class="sub" style="margin:2px 0 0">Voz neural alternativa</p>
              </div>
              {jeff_pill}
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Voz masculina alternativa para estilo documental e ritmo pausado em português.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Motor</span><b>Piper Neural ONNX</b></div>
              <div class="between"><span class="sub">Idioma</span><b>Português (Brasil)</b></div>
              <div class="between"><span class="sub">Ritmo medido</span><b>~165 palavras/min</b></div>
              <div class="between"><span class="sub">Custo de API</span><span class="pill ok" style="padding:1px 8px;font-size:11px">Gratuito (Local)</span></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px" class="between">
            <code class="mono" style="font-size:11px">piper:pt_BR-jeff-medium</code>
            <span class="sub" style="font-size:11px">Suporte nativo</span>
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px{' ;border:2px solid var(--accent);background:var(--accentbg)' if is_demo_active else ''}">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Demo Tone (Sintético)</b>
                <p class="sub" style="margin:2px 0 0">Ambiente de teste e dev</p>
              </div>
              {demo_pill}
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Modo sintético instantâneo para testes de ponta a ponta sem geração de áudio neural.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Motor</span><b>Gerador de tom sintético</b></div>
              <div class="between"><span class="sub">Idioma</span><b>Neutro</b></div>
              <div class="between"><span class="sub">Tempo de síntese</span><b>Instantâneo (&lt; 0.1s)</b></div>
              <div class="between"><span class="sub">Custo de API</span><span class="pill ok" style="padding:1px 8px;font-size:11px">Sem custo</span></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px" class="between">
            <code class="mono" style="font-size:11px">demo:</code>
            <span class="sub" style="font-size:11px">Desenvolvimento</span>
          </div>
        </div>
      </div>
    """


def _render_script_template_cards() -> str:
    return """
      <div class="between" style="margin-bottom:14px">
        <div>
          <p class="sub">Arquétipos e estruturas de roteiro comprovadas para retenção de audiência, engajamento e validação editorial estrita.</p>
        </div>
        <span class="pill ok">3 modelos disponíveis</span>
      </div>
      <div class="grid3">
        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Shorts Viral de Alta Retenção</b>
                <p class="sub" style="margin:2px 0 0">Fatos rápidos &amp; Curiosidades</p>
              </div>
              <span class="pill accent">Short 9:16</span>
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Gancho magnético obrigatório nos primeiros 3 segundos, cortes a cada 5–10s e foco total em retenção inicial.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Cenas</span><b>4 a 6 cenas rápidas</b></div>
              <div class="between"><span class="sub">Duração estimada</span><b>~35 a 58 segundos</b></div>
              <div class="between"><span class="sub">Regra editorial</span><b>1 fato auditado por cena</b></div>
              <div class="between"><span class="sub">Ritmo de fala</span><b>170–180 palavras/min</b></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px">
            <span class="sub" style="font-size:11.5px">💡 Ideal para YouTube Shorts, TikTok e Reels</span>
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Documentário em 3 Atos</b>
                <p class="sub" style="margin:2px 0 0">Narrativa aprofundada</p>
              </div>
              <span class="pill">Vídeo 16:9</span>
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Estrutura em capítulos com gancho contextual, desenvolvimento gradual dos fatos e clímax conclusivo com chamada para ação.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Estrutura</span><b>Capítulos com ScriptPlan</b></div>
              <div class="between"><span class="sub">Duração estimada</span><b>3 a 10+ minutos</b></div>
              <div class="between"><span class="sub">Regra editorial</span><b>Fact-check de claims com zero alucinação</b></div>
              <div class="between"><span class="sub">Ritmo de fala</span><b>150–165 palavras/min</b></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px">
            <span class="sub" style="font-size:11.5px">💡 Ideal para vídeo-ensaios, história, ciência e mistérios</span>
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:16px">
          <div>
            <div class="between" style="align-items:flex-start;margin-bottom:8px">
              <div>
                <b style="font-size:15px">Fato Histórico do Dia</b>
                <p class="sub" style="margin:2px 0 0">Conteúdo do calendário &amp; Notícias</p>
              </div>
              <span class="pill">Híbrido 9:16 / 16:9</span>
            </div>
            <p class="sub" style="font-size:12.5px;margin-bottom:12px">Acontecimentos marcantes da data corrente, integrando pesquisa automática na Wikipédia e validação de datas e nomes.</p>
            <div class="stack" style="gap:6px;font-size:12px;margin-bottom:14px">
              <div class="between"><span class="sub">Estrutura</span><b>Gancho temporal → Fato → Impacto</b></div>
              <div class="between"><span class="sub">Pesquisa</span><b>Wikipedia Research API</b></div>
              <div class="between"><span class="sub">Regra editorial</span><b>Datas e números conferidos</b></div>
              <div class="between"><span class="sub">Automação</span><b>Apto para piloto automático diário</b></div>
            </div>
          </div>
          <div style="border-top:1px solid var(--line);padding-top:10px">
            <span class="sub" style="font-size:11.5px">💡 Ideal para canais 'Hoje na História' e notícias</span>
          </div>
        </div>
      </div>
    """


def _load_music_tracks() -> list[dict]:
    paths = [
        Path("/data/music-candidates/manifest.json"),
        Path("storage/music-candidates/manifest.json"),
        Path(__file__).resolve().parents[4] / "storage" / "music-candidates" / "manifest.json",
    ]
    for p in paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
    return []


def _render_music_card(m: dict) -> str:
    title = str(m.get("title") or "Trilha sonora")
    creator = str(m.get("creator") or "Estúdio")
    dur_ms = m.get("duration_ms") or 0
    mins, secs = divmod(int(round(dur_ms / 1000)), 60)
    dur_str = f"{mins} min {secs:02d} s" if mins else f"{secs} s"
    license_str = str(m.get("license") or "CC0").upper()
    file_name = str(m.get("file") or "")
    from ..domain.music import infer_mood_tags
    tags = infer_mood_tags(title, str(m.get("note") or ""))
    tag_pills = "".join(f'<span class="pill accent" style="margin-right:4px">{e(t)}</span>' for t in tags[:2])
    return f"""<div class="card" style="display:flex;flex-direction:column;justify-content:space-between;padding:14px">
      <div>
        <div class="between" style="align-items:flex-start">
          <div>
            <b style="font-size:14.5px">{e(title)}</b>
            <p class="sub" style="margin:2px 0 6px">Por <b>{e(creator)}</b> · {dur_str}</p>
          </div>
          <span class="pill ok">✓ {e(license_str)}</span>
        </div>
        <div class="row" style="margin:6px 0 10px;gap:4px">
          {tag_pills}
          <span class="pill ok">Local (Storage)</span>
        </div>
      </div>
      <div style="margin-top:6px">
        <audio controls preload="none" style="width:100%;height:36px" src="/studio/music/{e(file_name)}"></audio>
      </div>
    </div>"""


def _archive_dialog() -> str:
    """Confirmação de "Arquivar" no tema (a antiga `window.confirm` era um modal nativo do navegador)."""
    return (
        '<dialog id="dlg-arquivar-estilo" class="modal" aria-labelledby="t-arquivar-estilo">'
        '<div class="modal-header"><h2 id="t-arquivar-estilo">Arquivar estilo</h2>'
        '<button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>'
        '<p style="margin:0 0 10px">Arquivar <b id="arquivar-nome">este estilo</b>? '
        'Os canais que usavam voltam ao padrão do estúdio.</p>'
        '<p class="hint">Nada é apagado: o nome fica livre para reúso e o estilo continua no histórico.</p>'
        '<p id="arquivar-erro" class="form-feedback" role="alert" aria-live="assertive"></p>'
        '<div class="form-actions" style="justify-content:flex-end">'
        '<button class="btn ghost small" type="button" data-fechar-dialogo>Voltar</button>'
        '<button class="btn primary" type="button" id="btn-confirmar-arquivar" autofocus>Arquivar estilo</button></div>'
        '</dialog>'
    )


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
        _dialog(f"editar-{item.style.id}", _style_form(f"editar-{item.style.id}", style=item.style), wide=True)
        for item in view.items) + _archive_dialog()
    vozes_html = _render_voice_cards(channel_voice, project_id)
    modelos_html = _render_script_template_cards()
    abas = (
        ("estilos", "Estilos visuais"),
        ("vozes", "Vozes"),
        ("musicas", "Músicas"),
        ("midias", "Mídias & Stock (Pixabay)"),
        ("modelos", "Modelos de roteiro"),
    )
    tabs = "".join(
        f'<button class="tab{" ativa" if k == "estilos" else ""}" type="button" data-aba-biblioteca="{k}" aria-selected="{"true" if k == "estilos" else "false"}">{l}</button>'
        for k, l in abas
    )

    music_items = _load_music_tracks()
    if music_items:
        musicas_html = f"""
          <div class="between" style="margin-bottom:14px">
            <div>
              <p class="sub">Trilhas sonoras livres de royalties (CC0) armazenadas no Studio, prontas para mixagem na composição com ducking automático.</p>
            </div>
            <span class="pill ok">{len(music_items)} trilhas disponíveis</span>
          </div>
          <div class="grid3">{"".join(_render_music_card(m) for m in music_items)}</div>
        """
    else:
        musicas_html = '<p class="sub">Nenhuma trilha encontrada em storage/music-candidates.</p>'

    has_pixabay = bool(os.getenv("PIXABAY_API_KEY", "").strip())
    pixabay_badge = '<span class="pill ok">✓ Pixabay API conectada</span>' if has_pixabay else '<span class="pill warn">PIXABAY_API_KEY ausente no .env</span>'
    midias_html = f"""
      <div class="between" style="margin-bottom:14px">
        <div>
          <p class="sub">Busque fotos e vídeos em alta resolução para ilustrar temas, cenas e capas do canal ativo.</p>
        </div>
        {pixabay_badge}
      </div>
      <div class="card" style="margin-bottom:16px">
        <form id="pixabay-search-form" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
          <div class="field" style="flex:1;min-width:240px;margin:0">
            <label for="pixabay-query">Palavra-chave de busca</label>
            <input class="input" type="text" id="pixabay-query" placeholder="Ex.: tecnologia, inteligência artificial, robótica, natureza..." value="tecnologia">
          </div>
          <div class="field" style="width:160px;margin:0">
            <label for="pixabay-type">Tipo de mídia</label>
            <select class="input" id="pixabay-type">
              <option value="image">Fotos &amp; Imagens</option>
              <option value="video">Vídeos stock</option>
            </select>
          </div>
          <button class="btn primary small" type="submit" id="btn-pixabay-buscar" style="height:38px;padding:0 18px">🔍 Buscar</button>
        </form>
        <div class="row" style="margin-top:10px;gap:6px" id="pixabay-quick-tags">
          <span class="sub" style="font-size:12px;margin-right:4px">Sugestões:</span>
          <button type="button" class="pill" data-q="tecnologia">Tecnologia</button>
          <button type="button" class="pill" data-q="inteligencia artificial">IA</button>
          <button type="button" class="pill" data-q="negocios">Negócios</button>
          <button type="button" class="pill" data-q="natureza">Natureza</button>
          <button type="button" class="pill" data-q="cidade futurista">Cidade</button>
          <button type="button" class="pill" data-q="espaco sideral">Espaço</button>
        </div>
      </div>
      <div id="pixabay-feedback" class="sample" style="margin-bottom:12px"></div>
      <div id="pixabay-results" class="grid3"></div>
    """

    body_page = f"""      <section class="pagina" id="pagina-biblioteca" aria-labelledby="t-biblioteca" data-canal="{e(project_id)}" data-canal-versao="{e(channel_version or 0)}">
        <div class="head"><div><p class="eyebrow">Recursos reutilizáveis</p><h1 id="t-biblioteca">Biblioteca</h1><p class="sub">Canal ativo: {e(nome_canal)}</p></div></div>
        <nav class="tabs" aria-label="Biblioteca">{tabs}</nav>
        <div id="painel-estilos">
          <div class="between" style="margin-bottom:14px"><p class="sub">O estilo vinculado ao canal é herdado por todos os novos vídeos.</p><button class="btn small" type="button" data-abrir-dialogo="novo-estilo-dialog">+ Criar novo estilo</button></div>
          {cards}
          <p class="sample" id="biblioteca-status" role="status" aria-live="polite"></p>
        </div>
        <div id="painel-vozes" hidden>{vozes_html}</div>
        <div id="painel-musicas" hidden>{musicas_html}</div>
        <div id="painel-midias" hidden>{midias_html}</div>
        <div id="painel-modelos" hidden>{modelos_html}</div>
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
