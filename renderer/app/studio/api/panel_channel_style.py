"""Componente “Personalizar canal” (F05.T04) — origem, valor efetivo e reset por campo.

Editar a biblioteca e personalizar o canal são atos separados. Este fragmento é o segundo: ele
mostra, para o canal selecionado, **de onde vem** cada valor (canal · estilo · padrão do motor),
qual é o valor efetivo resolvido pelo Core e o que o **reset** devolve — sem que a tela recalcule
precedência (`application.channel_style_page` projeta a partir de `resolve_effective_config`).

Regras de contrato aplicadas aqui:

- ausência = herdar: campo vazio **não** grava nada; o patch enviado é só o que foi declarado e,
  sem nenhum campo, vai ``null`` (o banco grava NULL, nunca ``{}``);
- revisão otimista: 409 aparece como mensagem humana e **não** recarrega nem limpa o que a pessoa
  digitou (só o sucesso recarrega, para refletir as origens novas);
- só o que o render aplica ganha controle; ``transition``/``extra`` aparecem rotulados no
  “Avançado” recolhido, com o motivo e, se houver override, o botão de remover;
- escape de todo dado vindo do banco, nenhum ``on*=`` inline: o JS acompanha a página e roda sob
  o nonce/CSP dela. O componente não emite cabeçalhos: herda os da página de Canais.

Montagem futura (fiação na página de Canais, fora deste stream): incluir o HTML de
``render_channel_style(view)`` e passar ``CHANNEL_STYLE_CSS`` como ``extra_css`` e
``CHANNEL_STYLE_JS`` como ``page_js`` do documento existente.
"""
from __future__ import annotations

import html
import json
from collections.abc import Mapping
from typing import Any

from ..application.channel_style_page import ChannelStyleField, ChannelStylePageView
from ..domain.effective_config import ConfigSource
from .panel_styles import MOTION_OPTIONS

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

_MOTION_LABELS = dict(MOTION_OPTIONS)

CHANNEL_STYLE_CSS = """
.channel-style { margin-top: 0; }
.channel-style .cs-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem 1.1rem;
  margin-top: 1rem;
}
.cs-field { display: flex; flex-direction: column; gap: 0.35rem; border: 0; padding: 0; margin: 0; }
fieldset.cs-field { grid-column: 1 / -1; }
.cs-field legend, .cs-field > label { font-weight: 600; font-size: 0.85rem; padding: 0; }
.cs-line { display: flex; align-items: center; gap: 0.5rem; }
.cs-line .input { flex: 1 1 auto; }
.cs-options { display: flex; flex-wrap: wrap; gap: 0.45rem 0.9rem; align-items: center; }
.cs-option { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; }
.cs-hint { color: var(--text-dim); font-size: 0.72rem; line-height: 1.4; }
.cs-origin b { font-weight: 600; }
.cs-reset { flex: 0 0 auto; white-space: nowrap; }
.cs-inherited { opacity: 0.85; }
.cs-unused-group { margin-top: 0.9rem; }
.cs-unused-group h3 { font-size: 0.85rem; margin: 0 0 0.2rem; }
.cs-unused {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) auto auto;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.5rem 0;
  border-top: 1px solid var(--border-soft);
  font-size: 0.85rem;
}
.cs-unused:first-of-type { border-top: 0; }
.cs-unused .cs-label { font-weight: 600; }
.cs-unused .cs-value { color: var(--text-muted); white-space: nowrap; }
.cs-unused .cs-origin { grid-column: 1 / -1; color: var(--text-dim); font-size: 0.72rem; }
@media (max-width: 820px) {
  .channel-style .cs-grid { grid-template-columns: minmax(0, 1fr); }
  .cs-unused { grid-template-columns: minmax(0, 1fr); }
}
"""

CHANNEL_STYLE_JS = r"""
(function () {
  var forms = document.querySelectorAll('form[data-channel-style-form]');
  Array.prototype.forEach.call(forms, function (form) {
    var patch;
    try { patch = JSON.parse(form.getAttribute('data-patch') || '{}') || {}; }
    catch (error) { patch = {}; }
    var feedback = form.querySelector('[data-feedback]');
    var submit = form.querySelector('[data-submit]');

    function prune(target, group) {
      if (target[group] && typeof target[group] === 'object'
          && !Array.isArray(target[group]) && Object.keys(target[group]).length === 0) {
        delete target[group];
      }
    }

    function numberField(input, label) {
      var raw = String(input.value).trim();
      if (raw === '') return { empty: true };
      var value = Number(raw);
      if (!isFinite(value)) {
        if (feedback) feedback.textContent = 'Informe um número em ' + label + '.';
        input.focus();
        return { invalid: true };
      }
      return { value: value };
    }

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var collected = JSON.parse(JSON.stringify(patch));
      var inputs = form.querySelectorAll('[data-field]');
      for (var index = 0; index < inputs.length; index += 1) {
        var input = inputs[index];
        var parts = input.getAttribute('data-field').split('.');
        var group = parts[0];
        var key = parts[1];
        var label = input.getAttribute('data-label') || parts.join('.');
        if (input.type === 'number') {
          var parsed = numberField(input, label);
          if (parsed.invalid) return;
          if (parsed.empty) {
            if (collected[group]) { delete collected[group][key]; prune(collected, group); }
            continue;
          }
          collected[group] = collected[group] || {};
          collected[group][key] = parsed.value;
          continue;
        }
        var raw = String(input.value).trim();
        if (raw === '') {
          if (collected[group]) { delete collected[group][key]; prune(collected, group); }
          continue;
        }
        collected[group] = collected[group] || {};
        collected[group][key] = raw;
      }

      var motions = Array.prototype.slice.call(
        form.querySelectorAll('input[data-motion]:checked')
      ).map(function (box) { return box.value; });
      if (motions.length) { collected.motion = motions; } else { delete collected.motion; }

      var hasFields = Object.keys(collected).length > 0;
      var revision = Number(form.getAttribute('data-revision') || '0');
      var endpoint = form.getAttribute('data-endpoint') || '';
      if (submit) submit.disabled = true;
      if (feedback) feedback.textContent = 'Salvando personalização...';
      fetch(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: revision,
                               patch: hasFields ? collected : null })
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      }).then(function (result) {
        if (result.ok) {
          if (feedback) feedback.textContent = 'Personalização salva. Atualizando...';
          setTimeout(function () { window.location.reload(); }, 500);
          return;
        }
        if (submit) submit.disabled = false;
        if (result.status === 409) {
          // Não recarrega: a entrada digitada fica. A pessoa revisa a versão atual quando quiser.
          if (feedback) feedback.textContent = 'Outra pessoa salvou esta personalização antes de você. '
            + 'Nada do que você digitou foi perdido: recarregue a página para ver a versão atual '
            + 'e aplique suas mudanças de novo.';
          return;
        }
        if (result.status === 404) {
          if (feedback) feedback.textContent = 'Este canal não existe mais. Recarregue a página.';
          return;
        }
        var detail = window.StudioErro.texto(result.data, 'verifique os campos e tente novamente.');
        if (feedback) feedback.textContent = 'Não foi possível salvar: ' + detail;
      }).catch(function () {
        if (submit) submit.disabled = false;
        if (feedback) feedback.textContent = 'Falha de rede ao salvar. Seus valores continuam aqui; '
          + 'tente novamente.';
      });
    });

    Array.prototype.forEach.call(form.querySelectorAll('[data-reset-field]'), function (button) {
      button.addEventListener('click', function () {
        var path = button.getAttribute('data-reset-field');
        var parts = path.split('.');
        var label = button.getAttribute('data-reset-label') || path;
        var inherits = button.getAttribute('data-reset-inherits') || 'o padrão do motor';
        var after = button.getAttribute('data-reset-value') || '—';
        if (!window.confirm('Remover a personalização de ' + label + '? O canal volta a '
                            + inherits + '. A biblioteca de estilos não muda.')) return;
        if (parts.length === 1) { delete patch[parts[0]]; }
        else if (patch[parts[0]]) { delete patch[parts[0]][parts[1]]; prune(patch, parts[0]); }
        var row = form.querySelector('[data-field-row="' + path + '"]');
        if (row) {
          Array.prototype.forEach.call(row.querySelectorAll('[data-field]'), function (control) {
            control.value = '';
          });
          Array.prototype.forEach.call(row.querySelectorAll('[data-motion]'), function (box) {
            box.checked = false;
          });
          Array.prototype.forEach.call(row.querySelectorAll('[data-origin-text]'), function (origin) {
            origin.textContent = 'Origem: ' + inherits + ' · efetivo: ' + after;
          });
          button.parentNode && button.parentNode.removeChild(button);
          row.className += ' cs-inherited';
        }
        if (feedback) feedback.textContent = label + ' voltou a herdar. Salve para confirmar.';
      });
    });
  });
})();
"""


def _origin_text(source: str, style_name: str | None) -> str:
    """Texto humano da camada vencedora — a mesma linguagem em toda a tela."""
    if source == ConfigSource.CHANNEL.value:
        return "canal"
    if source == ConfigSource.STYLE.value:
        return f"herda do estilo {style_name}" if style_name else "herda do estilo"
    if source == ConfigSource.VIDEO.value:
        return "vídeo"
    if source == ConfigSource.DECLARED.value:
        return "declarado"
    return "padrão do motor"


def _format(value: Any, field: ChannelStyleField) -> str:
    if field.control == "motion":
        items = tuple(value or ())
        if not items:
            return "ciclo do motor"
        return " + ".join(_MOTION_LABELS.get(str(item), str(item)) for item in items)
    if value is None:
        return ""
    if field.group == "music" and field.key == "bpm":
        return f"{value} bpm"
    if field.group == "caption":
        return f"{value} px"
    if field.group == "transition" and field.key == "duration_ticks":
        return f"{value} ticks"
    if field.group == "extra" and isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _effective_text(field: ChannelStyleField) -> str:
    formatted = _format(field.effective, field)
    if formatted:
        return formatted
    return "o motor decide" if field.origin == ConfigSource.ENGINE_DEFAULT.value else "sem valor"


def _origin_line(field: ChannelStyleField, style_name: str | None) -> str:
    origin = _origin_text(field.origin, style_name)
    text = f"Origem: {origin} · efetivo: {_effective_text(field)}"
    if field.overridden:
        inherited = _origin_text(field.inherited_origin, style_name)
        value = _format(field.inherited, field) or "sem valor"
        text += f". Sem a personalização, {inherited} ({value})"
    return text


def _reset_button(field: ChannelStyleField, style_name: str | None) -> str:
    if not field.overridden:
        return ""
    inherits = _origin_text(field.inherited_origin, style_name)
    after = _format(field.inherited, field) or "—"
    return (
        f'<button class="btn btn-sm btn-ghost cs-reset" type="button" '
        f'data-reset-field="{e(field.path)}" data-reset-label="{e(field.label)}" '
        f'data-reset-inherits="{e(inherits)}" data-reset-value="{e(after)}" '
        f'aria-label="Remover a personalização de {e(field.label)}; o canal volta a: {e(inherits)}">'
        f'Remover</button>'
    )


def _motion_options(field: ChannelStyleField) -> str:
    checked = set(field.effective or ()) if field.overridden else set()
    options = []
    for motion, label in MOTION_OPTIONS:
        field_id = f"estilo-canal-motion-{motion}"
        mark = " checked" if motion in checked else ""
        options.append(
            f'<span class="cs-option">'
            f'<input type="checkbox" id="{field_id}" value="{e(motion)}" data-motion{mark}>'
            f'<label for="{field_id}">{e(label)}</label>'
            f"</span>"
        )
    return "".join(options)


def _applied_field(field: ChannelStyleField, view: ChannelStylePageView) -> str:
    field_id = "estilo-canal-" + field.path.replace(".", "-")
    hint_id = f"{field_id}-hint"
    line = _origin_line(field, view.style_name)
    reset = _reset_button(field, view.style_name)
    if field.control == "motion":
        return f"""
        <fieldset class="cs-field" data-field-row="{e(field.path)}">
          <legend>{e(field.label)}</legend>
          <div class="cs-options">{_motion_options(field)}</div>
          <span class="cs-hint" id="{hint_id}" data-origin-text>{e(line)}</span>
          {reset}
        </fieldset>
        """
    input_type = "number" if field.control == "int" else "text"
    attrs = "inputmode=\"numeric\" step=\"1\"" if input_type == "number" else ""
    if field.control == "color":
        attrs = ('maxlength="9" placeholder="#RRGGBB" '
                 'pattern="^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"')
    elif field.control == "text":
        attrs = 'maxlength="200" placeholder="herda"'
    elif input_type == "number":
        attrs = 'inputmode="numeric" step="1" placeholder="herda"'
    bounds = ""
    if field.minimum is not None:
        bounds += f' min="{field.minimum}"'
    if field.maximum is not None:
        bounds += f' max="{field.maximum}"'
    # O controle mostra o **override cru** (para editar), nunca o valor de exibição formatado.
    value = ""
    if field.overridden and field.effective is not None:
        value = str(field.effective)
    return f"""
        <div class="cs-field" data-field-row="{e(field.path)}">
          <label for="{field_id}">{e(field.label)}</label>
          <div class="cs-line">
            <input class="input" type="{input_type}" id="{field_id}"
                   data-field="{e(field.path)}" data-label="{e(field.label)}"
                   value="{e(value)}" {attrs}{bounds} aria-describedby="{hint_id}">
            {reset}
          </div>
          <span class="cs-hint" id="{hint_id}" data-origin-text>{e(line)}</span>
        </div>
    """


def _not_applied_section(view: ChannelStylePageView) -> str:
    fields = view.not_applied_fields
    if not fields:
        return ""
    blocks = []
    for group, title in (("transition", "Transição"), ("extra", "Extra")):
        reason = next((item.reason for item in fields if item.group == group), "")
        rows = [item for item in fields if item.group == group]
        if not rows:
            continue
        rendered = "".join(
            f"""
            <div class="cs-unused" data-field-row="{e(item.path)}">
              <span class="cs-label">{e(item.label)}</span>
              <span class="cs-value">{e(_format(item.effective, item) or "sem valor")}</span>
              <span class="cs-origin" data-origin-text>Origem: {e(_origin_text(item.origin, view.style_name))}</span>
              {_reset_button(item, view.style_name)}
            </div>
            """
            for item in rows
        )
        blocks.append(
            f'<div class="cs-unused-group"><h3>{e(title)}</h3>'
            f'<p class="cs-hint">{e(reason)}</p>{rendered}</div>'
        )
    return f"""
      <details class="advanced" id="estilo-canal-nao-aplicado">
        <summary class="advanced-summary">Avançado — declarado e não aplicado pelo render</summary>
        <div class="advanced-body">
          <p class="cs-hint">Estes parâmetros existem no contrato do estilo, mas o render ainda não
          os aplica. Não há controle de valor: o que já está declarado aparece aqui e pode ser
          removido da personalização do canal.</p>
          {"".join(blocks)}
        </div>
      </details>
    """


def _base_text(view: ChannelStylePageView) -> str:
    if view.style_id is None:
        return ("Este canal não usa estilo da biblioteca: o padrão do motor é a base. "
                "Personalizar aqui cria exceções só deste canal.")
    if view.style_archived:
        return (f"O estilo {view.style_name or ''} está arquivado — o render não o aplica hoje. "
                "O padrão do motor é a base até o canal escolher outro estilo.")
    version = f" (versão {view.style_version})" if view.style_version is not None else ""
    return (f"Este canal usa o estilo {view.style_name or ''}{version}. "
            "Personalizar aqui não altera a biblioteca: o estilo continua igual para os outros canais.")


def render_channel_style(view: ChannelStylePageView) -> str:
    """Fragmento HTML do componente (sem casca): a página de Canais decide onde montar."""
    patch_document = json.dumps(view.patch_document(), ensure_ascii=False)
    revision_text = ("nunca personalizado" if view.revision == 0
                     else f"personalização na revisão {view.revision}")
    fields = "".join(_applied_field(item, view) for item in view.applied_fields)
    return f"""
    <section class="card channel-style" aria-labelledby="personalizar-estilo-canal"
             data-channel-style data-profile-id="{e(view.channel_id)}"
             data-revision="{view.revision}">
      <div class="spread">
        <div>
          <h2 id="personalizar-estilo-canal">Personalizar este canal</h2>
          <p class="dim" style="margin:4px 0 0;font-size:12.5px">{e(_base_text(view))}</p>
        </div>
        <span class="chip-metric">{e(revision_text)}</span>
      </div>
      <p class="cs-hint">Campo vazio = herda a camada de baixo; nada é copiado da biblioteca.
        O valor efetivo é o mesmo que o Core usa no render.</p>
      <form class="channel-style-form" data-channel-style-form
            data-patch="{e(patch_document)}" data-revision="{view.revision}"
            data-endpoint="/studio/channels/{e(view.channel_id)}/style-patch">
        <div class="cs-grid">{fields}</div>
        {_not_applied_section(view)}
        <div class="spread" style="margin-top:1rem">
          <div class="pill-row">
            <button class="btn btn-primary" type="submit" data-submit>Salvar personalização</button>
          </div>
          <div class="form-feedback" role="status" aria-live="polite" data-feedback></div>
        </div>
      </form>
    </section>
    """