"""Tela de Canais (F10) — consome o backend da fatia H e nunca inventa dado.

Fonte de verdade visual: `produto/tela-canais.html` (aprovado em 2026-11-20). A casca aprovada vem
de `api/panel.py` (G1). Onde o mockup mostra dado ilustrativo, esta tela escreve o dado real do
Studio ou um estado vazio explícito; onde o backend não tem a capacidade (reordenação manual de
fallback), o controle aparece indisponível e **não focável**, com o motivo em texto. O
consentimento OAuth do YouTube existe desde a F8: quando o servidor tem o app do Google, o botão
"Conectar"/"Reautorizar" chama `POST .../youtube-oauth/authorize` e redireciona para o Google; sem
o app configurado, o controle fica desabilitado com o motivo real (nunca "não está implementado").
"""
from __future__ import annotations

import html
import secrets
from datetime import datetime
from decimal import Decimal

from ..application.channels_page import ChannelsPageView
from ..domain.provider import Availability, ProviderCard, ProviderKind
from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

KIND_LABELS = {
    ProviderKind.TEXT: "Roteiro",
    ProviderKind.IMAGE: "Imagens",
    ProviderKind.VOICE: "Voz",
    ProviderKind.RENDERER: "Render",
}

_OAUTH_STATE = {
    "CONNECTED": ("s-done", "✓", "Conectado"),
    "EXPIRED": ("s-act", "!", "Expirado: precisa reautorizar"),
    "REVOKED": ("s-fail", "×", "Revogado: precisa reautorizar"),
    "ERROR": ("s-fail", "×", "Erro de autorização"),
    "DISCONNECTED": ("s-idle", "○", "Sem associação"),
}

_DECISION_STATE = {
    "WITHIN": ("s-done", "✓", "Dentro do limite"),
    "SOFT_LIMIT": ("s-act", "!", "Ação necessária"),
    "HARD_BLOCKED": ("s-fail", "×", "Bloqueado pelo teto"),
}

CHANNELS_CSS = """
.list { display: grid; gap: 0.5rem; }
.item-4 { grid-template-columns: minmax(0, 1.7fr) auto auto auto; align-items: center; }
.item-4 { display: grid; gap: 0.75rem; padding: 0.75rem 0; }
.item-title { font-weight: 600; }
.item-sub { font-size: 0.78rem; color: var(--text-dim); }
.cost { font-size: 0.78rem; color: var(--text-muted); white-space: nowrap; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.9rem 1.1rem; }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field .hint { color: var(--text-dim); font-size: 0.72rem; line-height: 1.4; }
.s-idle { color: var(--text-muted); background: var(--surface-raised); border-color: var(--border); }
.pill-row { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
.advanced-body .kv { border-top: 0; }
.new-channel { margin-top: 0.85rem; }
.new-channel summary { cursor: pointer; color: var(--text-muted); font-size: 0.85rem; padding: 0.35rem 0; }
.provider-result { font-size: 0.78rem; color: var(--text-muted); }
.provider-result:empty { display: none; }
@media (max-width: 820px) {
  .item-4 { grid-template-columns: minmax(0, 1fr); }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
}
"""


# ---------------------------------------------------------------------------
# Utilitários de apresentação
# ---------------------------------------------------------------------------


def _badge(kind: str, icon: str, label: str) -> str:
    # Texto primeiro: o rótulo vive no próprio badge, não só no ícone decorativo (regra R1 do contrato).
    return (
        f'<span class="state {e(kind)}">{e(label)} '
        f'<span class="state-icon" aria-hidden="true">{e(icon)}</span></span>'
    )


def _usd(value: object, *, zero_text: str = "US$ 0 (nenhum valor registrado)") -> str:
    """Valor monetário honesto; zero é dito por extenso, nunca `US$ 0,00`."""
    amount = Decimal(str(value))
    if amount == 0:
        return zero_text
    return f"US$ {amount:.2f}".replace(".", ",")


def _input_amount(value: object) -> str:
    return f"{Decimal(str(value)):.2f}"


def _provider_cost(card: ProviderCard) -> str:
    label = card.cost.label
    note = f" ({card.cost.note})" if card.cost.note else ""
    return f"{e(label)}{e(note)}"


def _provider_item(card: ProviderCard, project_id: str) -> str:
    available = card.availability is Availability.AVAILABLE
    state = _badge("s-done", "✓", "Disponível") if available else _badge("s-act", "!", "Indisponível")
    capabilities = ", ".join(card.capabilities) if card.capabilities else "não declarada"
    rate = f"{card.rate_limit_per_min} chamada(s)/min" if card.rate_limit_per_min else "não declarado"
    model_html = f' <code>{e(card.model)}</code>' if card.model else ""
    reason_html = (
        f'<div class="item-sub">Motivo: {e(card.reason or "sem motivo registrado")}</div>'
        if not available else ""
    )
    if available:
        command = (
            f'<button type="button" class="btn btn-sm btn-ghost" data-test-provider="{e(card.kind.value)}" '
            f'data-provider-spec="{e(card.spec)}" data-project-id="{e(project_id)}">Testar conexão</button>'
            f'<div class="provider-result" role="status" aria-live="polite"></div>'
        )
    else:
        command = (
            '<span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">'
            'Testar conexão</span>'
        )
    return f"""
      <div class="item item-4" data-provider-kind="{e(card.kind.value)}" data-provider-spec="{e(card.spec)}">
        <div>
          <div class="item-title">{e(KIND_LABELS.get(card.kind, card.kind.value))} · {e(card.name)}{model_html}</div>
          <div class="item-sub">Capability: {e(capabilities)} · rate limit: {e(rate)} · disponibilidade: {state}</div>
          {reason_html}
        </div>
        <span class="cost"><b>Custo:</b> {_provider_cost(card)}</span>
        {state}
        {command}
      </div>
    """


def _routing_html(view: ChannelsPageView) -> str:
    profile = view.budget.limits.economic_profile.value if view.budget else "BALANCED"
    rows = []
    for decision in view.routes:
        fallbacks = " → ".join(e(card.name) for card in decision.fallbacks)
        fallback_text = f" · fallback: {fallbacks}" if fallbacks else ""
        rows.append(
            f'<div class="kv"><span>Escolha no perfil {e(profile)} — {e(KIND_LABELS.get(decision.kind, decision.kind.value))}</span>'
            f'<span>{e(decision.reason)}{fallback_text}</span></div>'
        )
    for kind, reason in view.route_failures:
        rows.append(
            f'<div class="kv"><span>Escolha no perfil {e(profile)} — {e(KIND_LABELS.get(kind, kind.value))}</span>'
            f'<span>Sem candidato disponível: {e(reason)}</span></div>'
        )
    if not rows:
        return '<p class="muted">Nenhuma porta de provider configurada para roteamento.</p>'
    return "".join(rows)


def _decision_html(view: ChannelsPageView) -> str:
    if view.budget is None:
        return ""
    decision = view.budget.monthly
    kind, icon, label = _DECISION_STATE.get(decision.kind.value, ("s-idle", "○", "Sem classificação"))
    if decision.kind.value == "WITHIN":
        detail = (f"Projetado {_usd(decision.projected_usd, zero_text='US$ 0 (nenhum gasto projetado)')}; "
                  f"limite soft {_usd(decision.soft_usd, zero_text='US$ 0 (soft em zero)')} "
                  f"e hard {_usd(decision.hard_usd, zero_text='US$ 0 (hard em zero)')}.")
    elif decision.kind.value == "SOFT_LIMIT":
        detail = (f"Projetado {_usd(decision.projected_usd)} passou do soft "
                  f"{_usd(decision.soft_usd)}: ")
        detail += "o Studio pausa e pede sua decisão antes de continuar."
    else:
        detail = (f"Projetado {_usd(decision.projected_usd)} passou do hard "
                  f"{_usd(decision.hard_usd)}: ")
        detail += "o Studio para sozinho e não ultrapassa."
    return (
        f'<div class="kv"><span>Limite mensal</span><span class="pill-row">{_badge(kind, icon, label)}</span></div>'
        f'<p class="fine">{e(detail)} Não há projeção de gasto por vídeo registrada: '
        'só os limites por vídeo são exibidos.</p>'
    )


def _summary_rows(view: ChannelsPageView) -> str:
    if view.budget is None:
        return '<p class="muted">Sem canal selecionado: não há orçamento de canal para exibir.</p>'
    summary = view.budget.summary
    labels = summary.labels()
    rows = "".join(
        f'<div class="kv"><span>{e(title)}</span><span>{e(labels[key])}</span></div>'
        for title, key in (("Consumido no mês — real confirmado", "real"),
                           ("Consumido no mês — estimado", "estimate"),
                           ("Chamadas sem custo", "free"),
                           ("Chamadas com custo desconhecido", "unknown"))
    )
    if summary.unattributed_calls:
        rows += (
            f'<div class="kv"><span>Chamadas sem vínculo de vídeo</span>'
            f'<span>{summary.unattributed_calls}</span></div>'
        )
    return rows


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------


def _channel_card(view: ChannelsPageView) -> str:
    project = view.project
    assert project is not None
    name = view.profile.name if view.profile else project.name
    version = f"perfil versionado <code>channel_v{view.profile.version}</code>" if view.profile else (
        "sem perfil de canal registrado"
    )
    options = "".join(
        f'<option value="{e(pid)}"{" selected" if pid == project.id else ""}>{e(label)}</option>'
        for pid, label in view.projects
    )
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>{e(name)}</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">Canal ativo · {version}</p>
          </div>
          <div class="row">
            <label class="sr-only" for="canal-switcher">Canal ativo</label>
            <select id="canal-switcher" class="input" style="width:auto">{options}</select>
          </div>
        </div>
        <details class="new-channel">
          <summary>Adicionar canal</summary>
          <form id="new-channel-form" class="grid-2" style="margin-top:0.6rem">
            <div class="field">
              <label for="novo-canal-nome">Nome do canal</label>
              <input class="input" type="text" id="novo-canal-nome" name="name" maxlength="120" required>
            </div>
            <div class="field">
              <label for="novo-canal-nicho">Nicho editorial</label>
              <input class="input" type="text" id="novo-canal-nicho" name="niche" maxlength="200">
            </div>
            <div class="field">
              <label for="novo-canal-idioma">Idioma</label>
              <select class="input" id="novo-canal-idioma" name="language">
                <option value="pt-BR" selected>Português (Brasil)</option>
                <option value="en-US">Inglês (EUA)</option>
                <option value="es-ES">Espanhol</option>
              </select>
            </div>
            <div class="field" style="justify-content:end">
              <button class="btn btn-primary" type="submit" id="btn-novo-canal">Criar canal</button>
              <div id="new-channel-feedback" class="form-feedback" role="status" aria-live="polite"></div>
            </div>
          </form>
        </details>
      </div>
    """


def _profile_card(view: ChannelsPageView) -> str:
    project = view.project
    assert project is not None
    profile = view.profile
    niche = project.niche or "não informado"
    profile_id = profile.id if profile else ""
    version = profile.version if profile else 0
    default_name = profile.name if profile else project.name
    strategy = profile.strategy if profile else ""
    audience = profile.audience if profile else ""
    pillars = ", ".join(profile.pillars) if profile else ""
    visual = profile.visual_identity if profile else ""
    voice = profile.voice if profile else ""
    language = profile.language if profile else project.language or "pt-BR"
    languages = (("pt-BR", "Português (Brasil)"), ("en-US", "Inglês (EUA)"), ("es-ES", "Espanhol"))
    language_options = "".join(
        f'<option value="{e(code)}"{" selected" if code == language else ""}>{e(label)}</option>'
        for code, label in languages
    )
    if language not in {code for code, _ in languages}:
        language_options += f'<option value="{e(language)}" selected>{e(language)}</option>'
    if profile:
        state = _badge("s-done", "✓", f"Versão {profile.version} registrada")
        submit_label = "Salvar nova versão"
        empty_note = ""
        updated = (
            f'<p class="fine">Última alteração em {profile.updated_at.strftime("%d/%m/%Y %H:%M")}.</p>'
            if profile.updated_at else
            '<p class="fine">Horário da última alteração não registrado.</p>'
        )
    else:
        state = _badge("s-act", "!", "Ação necessária: criar o perfil")
        submit_label = "Criar perfil do canal"
        empty_note = (
            '<p class="muted" id="canal-sem-perfil">Nenhum perfil de canal registrado. '
            'Preencha a estratégia para criar a versão 1.</p>'
        )
        updated = ""
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Estratégia e identidade</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              Cada alteração cria uma versão auditável do perfil do canal. Nada de editar arquivo de configuração.
            </p>
          </div>
          {state}
        </div>
        {empty_note}
        <form id="channel-form" data-profile-id="{e(profile_id)}" data-profile-version="{version}"
              data-project-id="{e(project.id)}" style="margin-top:14px">
          <div class="grid-2">
            <div class="field">
              <label for="canal-nome">Nome do perfil</label>
              <input class="input" type="text" id="canal-nome" name="name" maxlength="120"
                     value="{e(default_name)}" required>
            </div>
            <div class="field">
              <label for="canal-nicho">Nicho</label>
              <input class="input" type="text" id="canal-nicho" value="{e(niche)}" disabled
                     aria-describedby="canal-nicho-hint">
              <span class="hint" id="canal-nicho-hint">Definido na criação do canal; não é editável neste formulário.</span>
            </div>
            <div class="field">
              <label for="canal-estrategia">Estratégia</label>
              <input class="input" type="text" id="canal-estrategia" name="strategy" maxlength="500"
                     value="{e(strategy)}">
            </div>
            <div class="field">
              <label for="canal-idioma">Idioma</label>
              <select class="input" id="canal-idioma" name="language">{language_options}</select>
            </div>
            <div class="field">
              <label for="canal-publico">Público</label>
              <input class="input" type="text" id="canal-publico" name="audience" maxlength="500"
                     value="{e(audience)}">
            </div>
            <div class="field">
              <label for="canal-voz">Voz padrão</label>
              <input class="input" type="text" id="canal-voz" name="voice" maxlength="200"
                     value="{e(voice)}">
              <span class="hint">Especificação do provider de voz (ex.: provedor:modelo).</span>
            </div>
            <div class="field">
              <label for="canal-pilares">Pilares editoriais</label>
              <input class="input" type="text" id="canal-pilares" name="pillars" maxlength="600"
                     value="{e(pillars)}">
              <span class="hint">Separe os pilares por vírgula; repetidos são descartados.</span>
            </div>
            <div class="field">
              <label for="canal-identidade">Identidade visual</label>
              <input class="input" type="text" id="canal-identidade" name="visual_identity" maxlength="2000"
                     value="{e(visual)}">
              <span class="hint">Aplicada a thumbnail, cartelas e legendas.</span>
            </div>
          </div>
          <div class="spread" style="margin-top:1rem">
            <div>
              <button class="btn btn-primary" type="submit" id="btn-salvar-canal">{e(submit_label)}</button>
              <div id="channel-feedback" class="form-feedback" role="status" aria-live="polite"></div>
            </div>
            {updated}
          </div>
        </form>
      </div>
    """


def _style_options(view: ChannelsPageView, selected: str | None) -> str:
    """Opções reais do seletor de Aparência: "padrão do estúdio" + os estilos da biblioteca."""
    options = [
        f'<option value=""{" selected" if selected is None else ""}>'
        "Segue o padrão do estúdio (nenhum estilo)</option>"
    ]
    for style in view.styles:
        chosen = " selected" if style.id == selected else ""
        options.append(f'<option value="{e(style.id)}"{chosen}>{e(style.name)}</option>')
    return "".join(options)


def _appearance_card(view: ChannelsPageView) -> str:
    """A aba Aparência: uma escolha (não um formulário). Sem estilo escolhido não é erro.

    O seletor lê a biblioteca pelo caso de uso — a tela não consulta o banco. "Criar novo estilo"
    leva à biblioteca compartilhada; nada de preview, cor ou percentual inventado.
    """
    profile = view.profile
    selected = profile.style_id if profile else None
    options = _style_options(view, selected)
    create_link = '<a class="btn" href="/studio/panel/estilos">Criar novo estilo</a>'
    if profile is not None:
        intro = ("O canal segue um estilo da biblioteca; cada vídeo pode sobrepor. "
                 "Sem estilo escolhido, o render usa o padrão do estúdio.")
        control = f"""
          <form id="appearance-form" data-profile-id="{e(profile.id)}"
                data-profile-version="{profile.version}">
            <div class="field">
              <label for="canal-estilo">Segue o estilo</label>
              <select class="input" id="canal-estilo" name="style_id" aria-describedby="canal-estilo-hint">
                {options}
              </select>
              <span class="hint" id="canal-estilo-hint">O estilo é compartilhado entre canais: editar na biblioteca vale para todos que o usam.</span>
            </div>
            <div class="spread" style="margin-top:1rem">
              <div class="pill-row">
                <button class="btn btn-primary" type="submit" id="btn-salvar-aparencia">Salvar aparência</button>
                {create_link}
              </div>
              <div id="appearance-feedback" class="form-feedback" role="status" aria-live="polite"></div>
            </div>
          </form>
        """
    else:
        intro = "Crie o perfil do canal para escolher um estilo; por ora ele segue o padrão do estúdio."
        control = f"""
          <div class="field">
            <label for="canal-estilo">Segue o estilo</label>
            <select class="input" id="canal-estilo" name="style_id" disabled
                    aria-describedby="canal-estilo-hint">
              {options}
            </select>
            <span class="hint" id="canal-estilo-hint">O estilo é compartilhado entre canais; a escolha fica disponível depois de criar o perfil.</span>
          </div>
          <div class="pill-row" style="margin-top:1rem">{create_link}</div>
        """
    count = len(view.styles)
    library_note = ("Nenhum estilo na biblioteca ainda." if count == 0
                    else f"{count} estilo(s) na biblioteca.")
    return f"""
      <div class="card" id="canal-aparencia">
        <div class="spread">
          <div>
            <h2>Aparência</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">{e(intro)}</p>
          </div>
        </div>
        <div style="margin-top:14px">{control}</div>
        <p class="fine">{e(library_note)}</p>
      </div>
    """


def _providers_card(view: ChannelsPageView) -> str:
    project = view.project
    assert project is not None
    items = "".join(_provider_item(card, project.id) for card in view.providers)
    if view.providers_error:
        items = (
            f'<p class="warning" role="note">Catálogo de providers indisponível: {e(view.providers_error)}.</p>'
        )
    elif not items:
        items = '<p class="muted">Nenhuma porta de provider configurada para este canal.</p>'
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Providers por tarefa</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              Cada tarefa aponta para um provider com capability, custo estimado, rate limit e disponibilidade real.
            </p>
          </div>
          <span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">Reordenar fallback</span>
        </div>
        <p class="fine">Reordenar fallback manualmente não está implementado nesta versão: o roteamento é derivado do
        perfil econômico do canal e recalculado a cada leitura.</p>
        <div class="list" style="margin-top:14px">{items}</div>
        {_routing_html(view)}
        <p class="fine">Custo estimado não é preço cobrado, e custo desconhecido não é tratado como zero.
        Disponibilidade reflete o estado real do provider: sem implementação validada, aparece indisponível com o motivo.</p>
      </div>
    """


def _budget_card(view: ChannelsPageView) -> str:
    if view.budget is None:
        return ""
    budget = view.budget
    limits = budget.limits
    if budget.configured:
        configured_note = (
            '<p class="fine">Limites do canal persistidos'
            + (f" em {limits.updated_at.strftime('%d/%m/%Y %H:%M')}" if limits.updated_at else "")
            + '.</p>'
        )
    else:
        configured_note = (
            '<p class="fine"><b>Nenhum limite de canal persistido.</b> Valem os tetos padrão do servidor '
            f'(hard mensal {_usd(limits.hard_monthly_usd, zero_text="US$ 0 (bloqueia operação paga)")}, '
            f'hard por vídeo {_usd(limits.hard_video_usd, zero_text="US$ 0 (bloqueia operação paga)")}). '
            'Salvar abaixo passa a persistir a configuração deste canal.</p>'
        )
    limit_rows = "".join(
        f'<div class="kv"><span>{e(title)}</span><span>{_usd(value, zero_text="US$ 0 (bloqueia operação paga)")}</span></div>'
        for title, value in (("Limite soft mensal", limits.soft_monthly_usd),
                             ("Limite hard mensal", limits.hard_monthly_usd),
                             ("Limite soft por vídeo", limits.soft_video_usd),
                             ("Limite hard por vídeo", limits.hard_video_usd))
    )
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Orçamento do canal</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              Limites por mês e por vídeo. Real, estimado, sem custo e desconhecido nunca são somados num número só.
            </p>
          </div>
          <span class="chip-metric">Perfil econômico: {e(limits.economic_profile.value)}</span>
        </div>
        {configured_note}
        <form id="budget-form" data-project-id="{e(view.project.id)}" style="margin-top:14px">
          <div class="grid-2">
            <div class="field">
              <label for="limite-soft-mensal">Limite soft mensal (US$)</label>
              <input class="input" type="text" inputmode="decimal" id="limite-soft-mensal" name="soft_monthly_usd"
                     value="{e(_input_amount(limits.soft_monthly_usd))}">
              <span class="hint">Ao atingir, o Studio pausa e pede sua decisão.</span>
            </div>
            <div class="field">
              <label for="limite-hard-mensal">Limite hard mensal (US$)</label>
              <input class="input" type="text" inputmode="decimal" id="limite-hard-mensal" name="hard_monthly_usd"
                     value="{e(_input_amount(limits.hard_monthly_usd))}">
              <span class="hint">Ao atingir, o Studio para sozinho. Não ultrapassa.</span>
            </div>
            <div class="field">
              <label for="limite-soft-video">Limite soft por vídeo (US$)</label>
              <input class="input" type="text" inputmode="decimal" id="limite-soft-video" name="soft_video_usd"
                     value="{e(_input_amount(limits.soft_video_usd))}">
            </div>
            <div class="field">
              <label for="limite-hard-video">Limite hard por vídeo (US$)</label>
              <input class="input" type="text" inputmode="decimal" id="limite-hard-video" name="hard_video_usd"
                     value="{e(_input_amount(limits.hard_video_usd))}">
            </div>
          </div>
          <div class="spread" style="margin-top:1rem">
            <button class="btn btn-primary" type="submit" id="btn-salvar-orcamento">Salvar limites</button>
            <div id="budget-feedback" class="form-feedback" role="status" aria-live="polite"></div>
          </div>
        </form>
        <div style="margin-top:14px">{limit_rows}</div>
        <div style="margin-top:14px">{_summary_rows(view)}</div>
        {_decision_html(view)}
      </div>
    """


def _oauth_controls(view: ChannelsPageView, status: str) -> str:
    """Controles do consentimento OAuth conforme o estado real do canal.

    O fluxo existe (F8). Sem app OAuth no servidor, o controle fica desabilitado **com o motivo
    real**; nunca se repete que "não está implementado".
    """
    label = "Conectar" if status == "DISCONNECTED" else "Reautorizar"
    if status == "CONNECTED":
        label = "Reconectar"
    if not view.oauth_available:
        reason = view.oauth_unavailable_reason or "OAuth do YouTube não configurado no servidor"
        return (
            '<span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">'
            f"{e(label)}</span>"
            f'<p class="fine">{e(reason)}. Enquanto isso, a associação do canal pode ser feita '
            "pela API do Studio e as credenciais ficam no secret store.</p>"
        )
    if not view.oauth_authorize_path:
        # Projeção sem caminho não deve prometer ação: mantém desabilitado com motivo explícito.
        return (
            '<span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">'
            f"{e(label)}</span>"
            '<p class="fine">O servidor não expôs o endpoint de autorização; a conexão está '
            "indisponível nesta leitura.</p>"
        )
    revoke = ""
    if status == "CONNECTED" and view.oauth_revoke_path:
        revoke = (
            f'<button type="button" class="btn btn-sm btn-ghost" id="youtube-revoke" '
            f'data-revoke-path="{e(view.oauth_revoke_path)}">Revogar acesso</button>'
        )
    return (
        f'<div class="pill-row">'
        f'<button type="button" class="btn btn-sm btn-primary" id="youtube-reauth" '
        f'data-authorize-path="{e(view.oauth_authorize_path)}">{e(label)}</button>'
        f"{revoke}"
        f"</div>"
        '<div class="provider-result" id="youtube-feedback" role="status" aria-live="polite"></div>'
        '<p class="fine">Ao acionar, o Google abre a tela de consentimento; o servidor troca o código '
        "pelo canal associado e guarda os tokens no secret store. Nenhum valor de credencial volta "
        "para o browser.</p>"
    )


def _youtube_card(view: ChannelsPageView) -> str:
    yt = view.youtube or {}
    status = str(yt.get("oauth_status") or "DISCONNECTED")
    kind, icon, label = _OAUTH_STATE.get(status, ("s-idle", "○", "Estado desconhecido"))
    channel_id = yt.get("channel_id")
    title = yt.get("title") or ""
    scopes = list(yt.get("scopes") or [])
    expires = yt.get("token_expires_at")
    expires_text = "expiração não registrada"
    if expires:
        try:
            moment = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            expires_text = f"expira em {moment.strftime('%d/%m/%Y %H:%M')}"
        except ValueError:
            expires_text = "expiração registrada em formato não reconhecido"
    if channel_id:
        channel_info = (
            f'<div class="item-title">{e(title) or "Canal associado"}</div>'
            f'<div class="item-sub">ID do canal: <code>{e(channel_id)}</code> · escopos: '
            + (", ".join(f"<code>{e(scope)}</code>" for scope in scopes) if scopes
               else "nenhum escopo registrado")
            + f"</div>"
        )
        credential_line = (
            f'<div class="item-title">Credencial (OAuth)</div>'
            f'<div class="item-sub">Metadados do secret store do servidor · {e(expires_text)}. '
            'Nenhum valor de credencial (access token, refresh token, client secret ou máscara) '
            'volta para o browser.</div>'
        )
    else:
        channel_info = (
            '<div class="item-title">Nenhum canal do YouTube associado</div>'
            '<div class="item-sub">A associação existe no backend (metadados + secret store), '
            'mas ainda não foi feita para este canal.</div>'
        )
        credential_line = (
            '<div class="item-title">Credencial (OAuth)</div>'
            '<div class="item-sub">Nenhuma credencial registrada para este canal.</div>'
        )
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Canal do YouTube</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              Associação e status do OAuth. Só o estado e os escopos aparecem; nenhum segredo é exibido.
            </p>
          </div>
          {_badge(kind, icon, label)}
        </div>
        <div class="list" style="margin-top:14px">
          <div class="item" style="padding:0.6rem 0">{channel_info}</div>
          <div class="item" style="padding:0.6rem 0">
            {credential_line}
            {_oauth_controls(view, status)}
          </div>
        </div>
      </div>
    """


def _advanced_card(view: ChannelsPageView) -> str:
    project = view.project
    assert project is not None
    profile = view.profile
    config_items = "".join(
        f'<div class="kv"><span><code>{e(key)}</code></span><span><code>{e(value)}</code></span></div>'
        for key, value in view.public_config.items()
    ) or '<p class="dim">Nenhuma porta de provider sobrescrita no projeto; valem os padrões do servidor.</p>'
    profile_line = (
        f'<p>Perfil: <code>{e(profile.id)}</code> · versão {profile.version}</p>'
        if profile else '<p>Perfil: não registrado para este canal.</p>'
    )
    unattributed = view.budget.summary.unattributed_calls if view.budget else 0
    return f"""
      <details class="advanced" id="canais-avancado">
        <summary class="advanced-summary">Avançado — identificadores, configuração sanitizada e uso</summary>
        <div class="advanced-body">
          <p>Projeto: <code>{e(project.id)}</code> · nicho: <code>{e(project.niche or "não informado")}</code>
             · idioma: <code>{e(project.language)}</code></p>
          {profile_line}
          <div>
            <h3>Configuração pública do projeto</h3>
            <p class="fine">Lista branca das portas de provider. Qualquer chave com cara de segredo é descartada antes de chegar ao browser.</p>
            {config_items}
          </div>
          <p>Chamadas sem vínculo de vídeo no mês: {unattributed} (visibilidade; não entram no gasto do canal).</p>
        </div>
      </details>
    """


def _rail_html(view: ChannelsPageView) -> str:
    profile_version = f"<code>channel_v{view.profile.version}</code>" if view.profile else "não registrado"
    budget_state = "persistido no canal" if (view.budget and view.budget.configured) else "padrão do servidor"
    oauth_state = str((view.youtube or {}).get("oauth_status") or "DISCONNECTED")
    oauth_flow = "disponível" if view.oauth_available else "indisponível no servidor"
    return f"""
      <aside class="rail" aria-label="Resumo">
        <section class="card" aria-labelledby="h-versionamento">
          <h2 id="h-versionamento">Versionamento</h2>
          <p class="fine" style="margin:0">Cada alteração cria uma versão do <code>ChannelProfile</code>,
          auditável. Nada de editar arquivo de configuração nem trocar código para mudar estratégia,
          providers ou orçamento.</p>
        </section>
        <section class="card" aria-labelledby="h-segredos">
          <h2 id="h-segredos">Segredos</h2>
          <p class="fine" style="margin:0">Credenciais vivem no secret store, <b>não</b> no
          <code>Project.config</code> devolvido ao browser. A tela mostra apenas estado e escopos.</p>
        </section>
        <section class="card" aria-labelledby="h-estado-canais">
          <h2 id="h-estado-canais">Estado</h2>
          <div class="kv"><span>Perfil do canal</span><span>{profile_version}</span></div>
          <div class="kv"><span>Orçamento</span><span>{e(budget_state)}</span></div>
          <div class="kv"><span>OAuth</span><span>{e(oauth_state)}</span></div>
          <div class="kv"><span>Fluxo de consentimento</span><span>{e(oauth_flow)}</span></div>
          <p class="fine">Estado lido do Studio no momento da abertura desta página.</p>
        </section>
      </aside>
    """


def _empty_page(side_card_html: str) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Canais</title>
  <style nonce="{nonce}">{shell.CSS}{CHANNELS_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#canais-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="canais", channels_href="/studio/canais", side_card_html=side_card_html)}
    <main class="main-content" id="canais-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="canais-heading">Canais</h1>
            <p class="page-goal" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem">
              Ação primária: <b>configurar canal</b>. A configuração vive no Studio, não em arquivo de ambiente.
            </p>
          </div>
          <span class="screen-no dim">F10 · Canais</span>
        </div>
      </div>
      <div class="card empty" id="canais-sem-canal">
        <h2>Nenhum canal cadastrado</h2>
        <p class="muted">Sem canal não há perfil, providers, orçamento ou associação do YouTube para configurar.</p>
        <p class="fine">Crie o primeiro canal no painel — o canal é o projeto que agrupa os vídeos.</p>
        <a class="btn btn-primary" href="/studio/panel">Ir ao painel criar o canal</a>
      </div>
    </main>
    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-sem-canal">
        <h2 id="h-sem-canal">Orçamento do mês</h2>
        <p class="fine" style="margin:0">Sem canal selecionado: não há orçamento de canal para exibir.</p>
      </section>
    </aside>
  </div>
</body>
</html>"""
    return page, shell._headers(nonce)


def _sidebar_card(view: ChannelsPageView) -> str:
    if view.budget is None:
        return (
            '<div class="side-card"><h2>Orçamento do mês</h2>'
            '<p>Sem canal selecionado: não há orçamento de canal para exibir.</p></div>'
        )
    labels = view.budget.summary.labels()
    rows = "".join(
        f'<div class="kv"><span>{e(title)}</span><span>{e(labels[key])}</span></div>'
        for title, key in (("Real", "real"), ("Estimado", "estimate"),
                           ("Sem custo", "free"), ("Desconhecido", "unknown"))
    )
    return f"""
        <div class="side-card">
          <h2>Orçamento do mês</h2>
          {rows}
        </div>
    """


def render_channels(view: ChannelsPageView) -> tuple[str, dict[str, str]]:
    """Página de Canais: casca aprovada + dado real do Studio ou estado vazio explícito."""
    if view.project is None:
        return _empty_page(_sidebar_card(view))
    nonce = secrets.token_urlsafe(16)
    project = view.project
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Canais</title>
  <style nonce="{nonce}">{shell.CSS}{CHANNELS_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#canais-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="canais", channels_href="/studio/canais", side_card_html=_sidebar_card(view))}
    <main class="main-content" id="canais-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="canais-heading">Canais</h1>
            <p class="page-goal" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem">
              Ação primária: <b>configurar canal</b>. A configuração vive no Studio, não em arquivo de ambiente.
            </p>
          </div>
          <span class="screen-no dim">F10 · Canais</span>
        </div>
      </div>
      {_channel_card(view)}
      {_profile_card(view)}
      {_appearance_card(view)}
      {_providers_card(view)}
      {_budget_card(view)}
      {_youtube_card(view)}
      {_advanced_card(view)}
    </main>
    {_rail_html(view)}
  </div>
  <script nonce="{nonce}">
    const projectId = "{e(project.id)}";
    const switcher = document.getElementById('canal-switcher');
    if (switcher) {{
      switcher.addEventListener('change', () => {{
        window.location.href = '/studio/canais?project_id=' + encodeURIComponent(switcher.value);
      }});
    }}

    const newChannel = document.getElementById('new-channel-form');
    if (newChannel) {{
      newChannel.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('new-channel-feedback');
        const button = document.getElementById('btn-novo-canal');
        const name = (document.getElementById('novo-canal-nome').value || '').trim();
        if (!name) {{ if (feedback) feedback.textContent = 'Informe o nome do canal.'; return; }}
        if (button) button.disabled = true;
        if (feedback) feedback.textContent = 'Criando canal...';
        try {{
          const response = await fetch('/studio/projects', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              name: name,
              niche: (document.getElementById('novo-canal-nicho').value || '').trim(),
              language: document.getElementById('novo-canal-idioma').value
            }})
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok && data.id) {{
            window.location.href = '/studio/canais?project_id=' + encodeURIComponent(data.id);
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível criar o canal: '
              + (typeof data.detail === 'string' ? data.detail : 'resposta inválida do servidor.');
            if (button) button.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao criar o canal. Tente novamente.';
          if (button) button.disabled = false;
        }}
      }});
    }}

    function splitPillars(raw) {{
      return raw.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
    }}

    const channelForm = document.getElementById('channel-form');
    if (channelForm) {{
      channelForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('channel-feedback');
        const button = document.getElementById('btn-salvar-canal');
        const profileId = channelForm.getAttribute('data-profile-id') || '';
        const version = Number(channelForm.getAttribute('data-profile-version') || '0');
        const changes = {{
          name: document.getElementById('canal-nome').value.trim(),
          strategy: document.getElementById('canal-estrategia').value.trim(),
          language: document.getElementById('canal-idioma').value,
          audience: document.getElementById('canal-publico').value.trim(),
          pillars: splitPillars(document.getElementById('canal-pilares').value),
          visual_identity: document.getElementById('canal-identidade').value.trim(),
          voice: document.getElementById('canal-voz').value.trim()
        }};
        if (!changes.name) {{ if (feedback) feedback.textContent = 'Informe o nome do perfil.'; return; }}
        if (button) button.disabled = true;
        if (feedback) feedback.textContent = profileId ? 'Salvando nova versão...' : 'Criando o perfil...';
        try {{
          const target = profileId
            ? '/studio/channels/' + encodeURIComponent(profileId)
            : '/studio/projects/' + encodeURIComponent(channelForm.getAttribute('data-project-id')) + '/channels';
          const payload = profileId ? {{ expected_version: version, changes: changes }} : changes;
          const response = await fetch(target, {{
            method: profileId ? 'PATCH' : 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (feedback) feedback.textContent = 'Perfil salvo. Atualizando...';
            setTimeout(() => window.location.reload(), 500);
          }} else if (response.status === 409) {{
            if (feedback) feedback.textContent = 'Outra alteração venceu a corrida: recarregue e revise a versão atual.';
            if (button) button.disabled = false;
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar o perfil: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique os campos e tente novamente.');
            if (button) button.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar o perfil. Tente novamente.';
          if (button) button.disabled = false;
        }}
      }});
    }}

    const appearanceForm = document.getElementById('appearance-form');
    if (appearanceForm) {{
      appearanceForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('appearance-feedback');
        const button = document.getElementById('btn-salvar-aparencia');
        const select = document.getElementById('canal-estilo');
        const profileId = appearanceForm.getAttribute('data-profile-id') || '';
        const version = Number(appearanceForm.getAttribute('data-profile-version') || '0');
        const value = select ? select.value : '';
        if (button) button.disabled = true;
        if (feedback) feedback.textContent = 'Salvando aparência...';
        try {{
          const response = await fetch('/studio/channels/' + encodeURIComponent(profileId), {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ expected_version: version, changes: {{ style_id: value || null }} }})
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (feedback) feedback.textContent = 'Aparência salva. Atualizando...';
            setTimeout(() => window.location.reload(), 500);
          }} else if (response.status === 409) {{
            if (feedback) feedback.textContent = 'Outra alteração venceu a corrida: recarregue e revise a versão atual.';
            if (button) button.disabled = false;
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar a aparência: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique o estilo e tente novamente.');
            if (button) button.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar a aparência. Tente novamente.';
          if (button) button.disabled = false;
        }}
      }});
    }}

    const budgetForm = document.getElementById('budget-form');
    if (budgetForm) {{
      budgetForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('budget-feedback');
        const button = document.getElementById('btn-salvar-orcamento');
        const body = {{
          soft_monthly_usd: (document.getElementById('limite-soft-mensal').value || '').trim(),
          hard_monthly_usd: (document.getElementById('limite-hard-mensal').value || '').trim(),
          soft_video_usd: (document.getElementById('limite-soft-video').value || '').trim(),
          hard_video_usd: (document.getElementById('limite-hard-video').value || '').trim()
        }};
        if (button) button.disabled = true;
        if (feedback) feedback.textContent = 'Salvando limites...';
        try {{
          const response = await fetch('/studio/projects/' + encodeURIComponent(projectId) + '/budget', {{
            method: 'PUT',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(body)
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (feedback) feedback.textContent = 'Limites salvos. Atualizando...';
            setTimeout(() => window.location.reload(), 500);
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar os limites: '
              + (typeof data.detail === 'string' ? data.detail : 'o soft não pode passar do hard.');
            if (button) button.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar os limites. Tente novamente.';
          if (button) button.disabled = false;
        }}
      }});
    }}

    const reauth = document.getElementById('youtube-reauth');
    if (reauth) {{
      reauth.addEventListener('click', async () => {{
        const feedback = document.getElementById('youtube-feedback');
        const path = reauth.getAttribute('data-authorize-path');
        reauth.disabled = true;
        if (feedback) feedback.textContent = 'Abrindo a tela de consentimento do Google...';
        try {{
          const response = await fetch(path, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }}
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok && data.authorization_url) {{
            window.location.href = data.authorization_url;
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível iniciar o consentimento: '
              + (typeof data.detail === 'string' ? data.detail : 'o servidor não devolveu a URL de autorização.');
            reauth.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao iniciar o consentimento. Tente novamente.';
          reauth.disabled = false;
        }}
      }});
    }}

    const revoke = document.getElementById('youtube-revoke');
    if (revoke) {{
      revoke.addEventListener('click', async () => {{
        const feedback = document.getElementById('youtube-feedback');
        const path = revoke.getAttribute('data-revoke-path');
        if (!window.confirm('Revogar o acesso do Studio ao canal do YouTube?')) return;
        revoke.disabled = true;
        if (feedback) feedback.textContent = 'Revogando o acesso no Google...';
        try {{
          const response = await fetch(path, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }}
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (feedback) feedback.textContent = 'Acesso revogado. Atualizando...';
            setTimeout(() => window.location.reload(), 500);
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível revogar: '
              + (typeof data.detail === 'string' ? data.detail : 'tente novamente.');
            revoke.disabled = false;
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao revogar. Tente novamente.';
          revoke.disabled = false;
        }}
      }});
    }}

    document.querySelectorAll('[data-test-provider]').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const kind = button.getAttribute('data-test-provider');
        const spec = button.getAttribute('data-provider-spec');
        const targetProject = button.getAttribute('data-project-id') || projectId;
        const result = button.parentElement.querySelector('.provider-result');
        button.disabled = true;
        if (result) result.textContent = 'Executando a sonda...';
        try {{
          const response = await fetch('/studio/projects/' + encodeURIComponent(targetProject) + '/providers/test', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ kind: kind, spec: spec || null }})
          }});
          const data = await response.json().catch(() => ({{}}));
          if (result) {{
            if (!response.ok) {{
              result.textContent = 'Não foi possível testar agora. Nenhum resultado foi medido.';
            }} else if (!data.checked) {{
              result.textContent = 'Nenhuma sonda foi executada: ' + (data.reason || 'sem motivo registrado');
            }} else if (data.available) {{
              result.textContent = 'Sonda executada: a conexão respondeu. ' + (data.reason || '');
            }} else {{
              result.textContent = 'Sonda executada: a conexão falhou. ' + (data.reason || '');
            }}
          }}
        }} catch (error) {{
          if (result) result.textContent = 'Não foi possível testar agora: falha de rede. Nada foi medido.';
        }}
        button.disabled = false;
      }});
    }});
  </script>
</body>
</html>"""
    return page, shell._headers(nonce)