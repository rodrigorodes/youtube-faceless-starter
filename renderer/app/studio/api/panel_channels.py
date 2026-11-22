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
import re
import secrets
from datetime import datetime
from decimal import Decimal

from ..application.channel_budget import economic_profile_options
from ..application.channels_page import ChannelsPageView
from ..domain.provider import (
    Availability,
    CostKind,
    EconomicProfile,
    ProviderCard,
    ProviderKind,
)
from . import panel as shell
from . import shell_v3
from .panel_channel_style import CHANNEL_STYLE_CSS, CHANNEL_STYLE_JS, render_channel_style

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
/* Sanfona / Accordion dos painéis de canais */
details.painel-sanfona {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 20px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
details.painel-sanfona:hover {
  border-color: #3b3748;
}
details.painel-sanfona[open] {
  border-color: #433d52;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}
summary.sanfona-cabecalho {
  list-style: none;
  cursor: pointer;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  user-select: none;
  background: transparent;
  transition: background-color 0.15s ease;
}
summary.sanfona-cabecalho::-webkit-details-marker {
  display: none;
}
summary.sanfona-cabecalho:hover {
  background: color-mix(in srgb, var(--panel2) 55%, transparent);
}
.sanfona-titulos {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sanfona-titulos h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: light-dark(#111116, #ffffff);
}
.sanfona-subtitulo {
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
}
.sanfona-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sanfona-seta {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--panel2);
  color: var(--muted);
  flex-shrink: 0;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), color 0.15s ease, background 0.15s ease;
}
details.painel-sanfona[open] > summary .sanfona-seta {
  transform: rotate(180deg);
  color: var(--accent);
  background: var(--soft);
}
.sanfona-corpo {
  padding: 14px 22px 24px;
  border-top: 1px solid var(--line);
  animation: sanfonaDesce 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes sanfonaDesce {
  from { opacity: 0.5; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Grade e Cards de Providers por Tarefa */
.grade-providers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}
.cartao-provider {
  border: 1px solid var(--line);
  background: var(--panel2);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.cartao-provider:hover {
  border-color: #4b455b;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
.cartao-provider-topo {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.cartao-provider-tipo {
  display: block;
  font-size: 11px;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--accent);
  margin-bottom: 3px;
}
.cartao-provider-nome {
  font-size: 14.5px;
  font-weight: 700;
  color: light-dark(#111116, #ffffff);
}
.cartao-provider-modelo {
  font-size: 11px;
  background: var(--soft);
  color: var(--accent);
  padding: 2px 6px;
  border-radius: 5px;
  margin-left: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.cartao-provider-metas {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  margin-top: 8px;
}
.meta-item { display: inline-flex; gap: 4px; align-items: baseline; }
.meta-sep { color: var(--line); }
.cartao-provider-motivo {
  margin-top: 8px;
  font-size: 12px;
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 25%, transparent);
  border-radius: 8px;
  padding: 8px 10px;
  line-height: 1.4;
}
.cartao-provider-inferior {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  flex-wrap: wrap;
}
.porta-spec { font-size: 11px; }
.provider-acao { display: flex; align-items: center; gap: 8px; }
.provider-result { font-size: 12px; color: var(--muted); }
.provider-result:empty { display: none; }

/* Bloco de Roteamento Econômico */
.bloco-roteamento {
  margin-top: 20px;
  padding: 16px;
  background: var(--panel2);
  border-radius: 12px;
  border: 1px solid var(--line);
}
.roteamento-item {
  padding: 8px 0;
}

.list { display: grid; gap: 0.5rem; }
.cost { font-size: 12px; color: var(--muted); white-space: nowrap; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.9rem 1.1rem; }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field .hint { color: var(--muted); font-size: 0.72rem; line-height: 1.4; }
.s-idle { color: var(--muted); background: var(--surface-raised); border-color: var(--border); }
.pill-row { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
.advanced-body .kv { border-top: 0; }
.new-channel { margin-top: 0.85rem; }
.new-channel summary { cursor: pointer; color: var(--muted); font-size: 0.85rem; padding: 0.35rem 0; }
/* F06.T03: conexão × configuração × credencial lado a lado, sem prometer BYOK. */
.tres-estados { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.estado-bloco {
  border: 1px solid var(--line);
  background: var(--panel2);
  border-radius: 12px;
  padding: 14px 16px;
}
.estado-bloco h3 { margin: 0 0 6px; font-size: 13px; font-weight: 750; color: var(--txt); }
.estado-bloco .kv { align-items: flex-start; gap: 10px; }
.estado-bloco .kv > span:last-child { text-align: right; line-height: 1.45; }
/* Escolha do perfil econômico em cartões — protótipo `settingsProduction` (`pillrow` + `.choice`,
   `prototype/index.html:488` e 627). Um clique e o "porquê" ao lado; radio nativo, sem JS. */
.perfis-escolha { border: 0; padding: 0; margin: 0; }
.perfis-escolha legend { color: var(--muted); font-size: 0.8rem; padding: 0 0 6px; }
.perfis-escolha .hint { display: block; margin-top: 8px; }
.choice {
  display: block;
  flex: 1;
  min-width: 190px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel2);
  cursor: pointer;
  font-size: 0.82rem;
}
.choice:hover { border-color: var(--accent); }
.choice.ativo { border-color: var(--accent); background: var(--soft); }
.choice strong { display: block; margin-bottom: 6px; }
.choice input[type="radio"] { margin: 0 8px 0 0; }
.choice .sample { display: block; color: var(--muted); font-size: 0.72rem; line-height: 1.45; }
@media (max-width: 820px) {
  .grade-providers { grid-template-columns: 1fr; }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
  .tres-estados { grid-template-columns: minmax(0, 1fr); }
  .estado-bloco .kv > span:last-child { text-align: left; }
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
    """Custo declarado em texto humano; preço não confirmado nunca vira valor nem zero."""
    if card.cost.kind is CostKind.UNKNOWN:
        note = f" ({card.cost.note})" if card.cost.note else ""
        return f"Custo desconhecido — nenhum preço confirmado; não é tratado como zero{note}"
    label = card.cost.label
    note = f" ({card.cost.note})" if card.cost.note else ""
    return f"{e(label)}{e(note)}"


# F06.T03: o motivo do roteador é categoria técnica; a tela traduz para texto humano sem
# prometer provider e sem repetir o enum/inglês cru do domínio.
_ROUTE_EXCLUSION_LABELS = {
    "unknown cost": "custo desconhecido",
    "non-production provider": "provider de demonstração/placeholder não executa em produção",
    "missing the port capability": "não declara a capability da porta",
    "cost above the cap": "custo acima do teto",
}
_QUALITY_FLOOR = re.compile(r"quality (\d+) below the profile floor (\d+)")


def _route_failure_text(kind: ProviderKind, profile: EconomicProfile | str, reason: str) -> str:
    """Explica, em português, por que uma porta ficou sem candidato — nunca inventa um."""
    kind_label = KIND_LABELS.get(kind, getattr(kind, "value", str(kind)))
    profile_label = profile.value if isinstance(profile, EconomicProfile) else str(profile)
    categories: list[str] = []
    quality = _QUALITY_FLOOR.search(reason or "")
    if quality:
        categories.append(
            f"qualidade {quality.group(1)} abaixo do piso de qualidade {quality.group(2)}"
        )
    for needle, label in _ROUTE_EXCLUSION_LABELS.items():
        if needle in (reason or "") and label not in categories:
            categories.append(label)
    if categories:
        return (f"Nenhum provider de {kind_label} atende ao perfil {profile_label}: "
                + "; ".join(categories) + ".")
    return (f"Nenhum provider de {kind_label} atende ao perfil {profile_label} neste momento; "
            "o roteador não registrou um motivo categorizado.")


def _provider_item(card: ProviderCard, project_id: str) -> str:
    available = card.availability is Availability.AVAILABLE
    state = _badge("s-done", "✓", "Disponível") if available else _badge("s-act", "!", "Indisponível")
    capabilities = ", ".join(card.capabilities) if card.capabilities else "não declarada"
    rate = f"{card.rate_limit_per_min} chamada(s)/min" if card.rate_limit_per_min else "não declarado"
    model_html = f' <code class="cartao-provider-modelo">{e(card.model)}</code>' if card.model else ""
    reason_html = (
        f'<div class="item-sub cartao-provider-motivo"><b>Motivo:</b> {e(card.reason or "sem motivo registrado")}</div>'
        if not available else ""
    )
    if available:
        command = (
            f'<div class="provider-acao">'
            f'<button type="button" class="btn btn-sm btn-ghost" data-test-provider="{e(card.kind.value)}" '
            f'data-provider-spec="{e(card.spec)}" data-project-id="{e(project_id)}">Testar conexão</button>'
            f'<div class="provider-result" role="status" aria-live="polite"></div>'
            f'</div>'
        )
    else:
        command = (
            f'<div class="provider-acao">'
            '<span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">'
            'Testar conexão</span>'
            f'</div>'
        )
    kind_label = KIND_LABELS.get(card.kind, card.kind.value)
    return f"""
      <div class="item item-4 cartao-provider" data-provider-kind="{e(card.kind.value)}" data-provider-spec="{e(card.spec)}">
        <div class="cartao-provider-corpo">
          <div class="cartao-provider-topo">
            <div>
              <span class="cartao-provider-tipo">{e(kind_label)}</span>
              <div class="item-title cartao-provider-nome">{e(card.name)}{model_html}</div>
            </div>
            <div class="cartao-provider-badge">{state}</div>
          </div>
          <div class="item-sub cartao-provider-metas">
            <span class="meta-item"><b>Capability:</b> <code>{e(capabilities)}</code></span>
            <span class="meta-sep">·</span>
            <span class="meta-item"><b>rate limit:</b> {e(rate)}</span>
            <span class="meta-sep">·</span>
            <span class="meta-item"><b>disponibilidade:</b> {state}</span>
          </div>
          {reason_html}
        </div>
        <div class="cartao-provider-inferior">
          <span class="cost" data-cost-kind="{e(card.cost.kind.value)}"><b>Custo:</b> {_provider_cost(card)}</span>
          <span class="dim porta-spec">Porta: <code>{e(card.spec)}</code></span>
          {command}
        </div>
      </div>
    """


def _routing_html(view: ChannelsPageView) -> str:
    profile_value = view.budget.limits.economic_profile if view.budget else EconomicProfile.BALANCED
    profile = profile_value.value
    rows = []
    for decision in view.routes:
        fallbacks = " → ".join(e(card.name) for card in decision.fallbacks)
        fallback_text = f" · fallback: {fallbacks}" if fallbacks else ""
        rows.append(
            f'<div class="kv roteamento-item"><span><b>Escolha no perfil {e(profile)}</b> — {e(KIND_LABELS.get(decision.kind, decision.kind.value))}</span>'
            f'<span>{e(decision.reason)}{fallback_text}</span></div>'
        )
    for kind, reason in view.route_failures:
        rows.append(
            f'<div class="kv roteamento-item" data-route-failure="{e(kind.value)}">'
            f'<span><b>Escolha no perfil {e(profile)}</b> — {e(KIND_LABELS.get(kind, kind.value))}</span>'
            f'<span>{e(_route_failure_text(kind, profile_value, reason))}</span></div>'
        )
    if not rows:
        return '<p class="muted">Nenhuma porta de provider configurada para roteamento.</p>'
    return (
        f'<div class="bloco-roteamento">'
        f'<h3 style="margin:0 0 10px;font-size:14px;font-weight:700">Roteamento econômico ativo</h3>'
        f'{"".join(rows)}'
        f'</div>'
    )


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
    version = f"perfil versionado <code>channel_v{view.profile.version}</code>" if view.profile else (
        "sem perfil de canal registrado"
    )
    # O nome do canal ativo e o seletor vivem no card do topo; aqui fica só o que ainda não
    # tem outro lugar: criar o próximo canal. Sem duplicar o cabeçalho do canal atual.
    return f"""
      <details class="card painel-sanfona" id="painel-identidade">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Adicionar canal</h2>
            <p class="dim sanfona-subtitulo">Criar outro canal neste estúdio · atual: {version}</p>
          </div>
          <div class="sanfona-meta">
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          <form id="new-channel-form" class="grid-2" style="margin-top:0.2rem">
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
              <button class="btn btn-primary" type="submit" id="btn-criar-canal">Criar canal</button>
              <div id="new-channel-feedback" class="form-feedback" role="status" aria-live="polite"></div>
            </div>
          </form>
        </div>
      </details>
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
    narrative = profile.narrative if profile else ""
    target_duration_s = profile.target_duration_s if profile else ""
    cta = profile.cta if profile else ""
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
      <details class="card painel-sanfona" id="painel-perfil">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Identidade do canal</h2>
            <p class="dim sanfona-subtitulo">
              O que está definido aqui vale para cada vídeo novo. Cada alteração cria uma versão auditável.
            </p>
          </div>
          <div class="sanfona-meta">
            {state}
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          {empty_note}
          <form id="channel-form" data-profile-id="{e(profile_id)}" data-profile-version="{version}"
                data-project-id="{e(project.id)}" style="margin-top:6px">
            <!-- Paridade com o protótipo: as escolhas do dia a dia ficam na linha, pré-preenchidas
                 pelo perfil real do canal. O resto do perfil continua disponível, sem competir
                 visualmente com voz e idioma. -->
            <div class="item-config">
              <div><b><label for="canal-voz">Voz do narrador</label></b>
                <small>Declarado, ainda não aplicado: a voz dos vídeos novos ainda vem do estilo ou do padrão do estúdio.</small></div>
              <input class="input" type="text" id="canal-voz" name="voice" maxlength="200"
                     value="{e(voice)}" style="max-width:280px" placeholder="provedor:modelo"
                     aria-describedby="canal-voz-hint">
              <span class="sr-only" id="canal-voz-hint">Especificação do provider de voz, no formato provedor:modelo.</span>
            </div>
            <div class="item-config">
              <div><b><label for="canal-idioma">Idioma padrão</label></b>
                <small>Idioma de roteiro e narração</small></div>
              <select class="input" id="canal-idioma" name="language" style="max-width:190px">{language_options}</select>
            </div>
            <details class="advanced" id="perfil-detalhes">
              <summary class="advanced-summary">Detalhes do perfil</summary>
              <div class="advanced-body">
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
                    <label for="canal-publico">Público</label>
                    <input class="input" type="text" id="canal-publico" name="audience" maxlength="500"
                           value="{e(audience)}">
                  </div>
                  <div class="field">
                    <label for="canal-pilares">Pilares editoriais</label>
                    <input class="input" type="text" id="canal-pilares" name="pillars" maxlength="600"
                           value="{e(pillars)}">
                    <span class="hint">Separe os pilares por vírgula; repetidos são descartados.</span>
                  </div>
                  <div class="field">
                    <label for="canal-narrativa">Estilo narrativo</label>
                    <input class="input" type="text" id="canal-narrativa" name="narrative" maxlength="4000"
                           value="{e(narrative)}">
                    <span class="hint">Orientação de estilo usada no roteiro dos vídeos novos (até 4000 caracteres).</span>
                  </div>
                  <div class="field">
                    <label for="canal-duracao">Duração padrão (segundos)</label>
                    <input class="input" type="number" inputmode="numeric" id="canal-duracao"
                           name="target_duration_s" min="1" max="36000" value="{e(target_duration_s)}">
                    <span class="hint">Alvo de duração dos vídeos novos: entre 1 e 36000 segundos.</span>
                  </div>
                  <div class="field">
                    <label for="canal-cta">Chamada para ação</label>
                    <input class="input" type="text" id="canal-cta" name="cta" maxlength="500"
                           value="{e(cta)}">
                    <span class="hint">Frase de encerramento pedida no roteiro (até 500 caracteres).</span>
                  </div>
                  <div class="field">
                    <label for="canal-identidade">Identidade visual</label>
                    <input class="input" type="text" id="canal-identidade" name="visual_identity" maxlength="2000"
                           value="{e(visual)}">
                    <span class="hint">Declarado, ainda não aplicado: hoje não altera thumbnail, cartelas nem legendas.</span>
                  </div>
                </div>
              </div>
            </details>
            <div class="spread" style="margin-top:14px">
              <div>
                <button class="btn btn-primary" type="submit" id="btn-salvar-canal">{e(submit_label)}</button>
                <div id="channel-feedback" class="form-feedback" role="status" aria-live="polite"></div>
              </div>
              {updated}
            </div>
          </form>
        </div>
      </details>
    """


def _style_gallery(view: ChannelsPageView, selected: str | None, disabled: str = "") -> str:
    """Estilo como cartões (paridade com o protótipo), com amostra e rádio junto do nome.

    A lista é a biblioteca real. "Segue o padrão do estúdio" continua existindo como cartão
    porque é uma escolha real (não um estilo inventado) — e limpar a escolha precisa ser possível.
    """
    def card(value: str, name: str, amostra: str | None = None) -> str:
        checked = " checked" if (selected or "") == value else ""
        return (
            f'<label class="cartao-estilo"><span class="amostra" aria-hidden="true">{e((amostra or name).upper())}</span>'
            f'<span class="cartao-rodape"><input type="radio" name="style_id" value="{e(value)}"'
            f'{checked}{disabled}> {e(name)}</span></label>'
        )

    cards = [card("", "Segue o padrão do estúdio", "Padrão")]
    cards.extend(card(style.id, style.name) for style in view.styles)
    joined = "".join(cards)
    return f'<div class="galeria" style="width:100%">{joined}</div>'


def _appearance_card(view: ChannelsPageView) -> str:
    """A aba Aparência: uma escolha (não um formulário). Sem estilo escolhido não é erro.

    O seletor lê a biblioteca pelo caso de uso — a tela não consulta o banco. "Criar novo estilo"
    leva à biblioteca compartilhada; nada de preview, cor ou percentual inventado.
    """
    profile = view.profile
    selected = profile.style_id if profile else None
    gallery = _style_gallery(view, selected)
    gallery_disabled = _style_gallery(view, selected, disabled=" disabled")
    create_link = '<a class="btn" href="/studio/panel/estilos">Criar novo estilo</a>'
    if profile is not None:
        intro = ("O estilo escolhido aqui é aplicado a cada vídeo novo. "
                 "Cada vídeo ainda pode sobrepor; sem estilo escolhido, o render usa o padrão do estúdio.")
        control = f"""
          <form id="appearance-form" data-profile-id="{e(profile.id)}"
                data-profile-version="{profile.version}">
            <fieldset class="pills" style="display:block;width:100%" aria-describedby="canal-estilo-hint">
              <legend>Estilo visual padrão</legend>
              {gallery}
            </fieldset>
            <p class="hint" id="canal-estilo-hint">O estilo é compartilhado entre canais: editar na
            biblioteca vale para todos que o usam.</p>
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
          <fieldset class="pills" style="display:block;width:100%" aria-describedby="canal-estilo-hint">
            <legend>Estilo visual padrão</legend>
            {gallery_disabled}
          </fieldset>
          <p class="hint" id="canal-estilo-hint">O estilo é compartilhado entre canais; a escolha
          fica disponível depois de criar o perfil.</p>
          <div class="pill-row" style="margin-top:1rem">{create_link}</div>
        """
    count = len(view.styles)
    library_note = ("Nenhum estilo na biblioteca ainda." if count == 0
                    else f"{count} estilo(s) na biblioteca.")
    return f"""
      <details class="card painel-sanfona" id="canal-aparencia">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Estilo visual do canal</h2>
            <p class="dim sanfona-subtitulo">{e(intro)}</p>
          </div>
          <div class="sanfona-meta">
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          <div style="margin-top:6px">{control}</div>
          <p class="fine">{e(library_note)}</p>
        </div>
      </details>
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
      <details class="card painel-sanfona" id="painel-providers">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Providers por tarefa</h2>
            <p class="dim sanfona-subtitulo">
              Cada tarefa aponta para um provider com capability, custo estimado, rate limit e disponibilidade real.
            </p>
          </div>
          <div class="sanfona-meta">
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          <div class="spread" style="margin-bottom:12px;align-items:center">
            <p class="fine" style="margin:0">
              Roteamento derivado do perfil econômico do canal e recalculado a cada leitura.
            </p>
            <span class="btn btn-sm btn-ghost is-disabled" aria-disabled="true" tabindex="-1">Reordenar fallback</span>
          </div>
          <p class="fine" style="margin-top:0">Reordenar fallback manualmente não está implementado nesta versão: o roteamento é derivado do
          perfil econômico do canal e recalculado a cada leitura.</p>
          <div class="grade-providers list" style="margin-top:14px">{items}</div>
          {_routing_html(view)}
          <p class="fine" style="margin-top:14px">Custo estimado não é preço cobrado, e custo desconhecido não é tratado como zero.
          Disponibilidade reflete o estado real do provider: sem implementação validada, aparece indisponível com o motivo.</p>
        </div>
      </details>
    """


def _budget_card(view: ChannelsPageView) -> str:
    if view.budget is None:
        return ""
    budget = view.budget
    limits = budget.limits
    profile_value = limits.economic_profile
    if budget.configured:
        configured_note = (
            '<p class="fine">Limites do canal persistidos'
            + (f" em {limits.updated_at.strftime('%d/%m/%Y %H:%M')}" if limits.updated_at else "")
            + '.</p>'
        )
        origin = "persistidos neste canal"
    else:
        configured_note = (
            '<p class="fine"><b>Nenhum limite de canal persistido.</b> Valem os tetos padrão do servidor '
            f'(hard mensal {_usd(limits.hard_monthly_usd, zero_text="US$ 0 (bloqueia operação paga)")}, '
            f'hard por vídeo {_usd(limits.hard_video_usd, zero_text="US$ 0 (bloqueia operação paga)")}). '
            'Salvar abaixo passa a persistir a configuração deste canal.</p>'
        )
        origin = "padrão do servidor, sem nada persistido para este canal"
    # UX (protótipo `settingsProduction`, `prototype/index.html:627`): o perfil é uma **escolha em
    # cartões** — um clique e o "porquê" ao lado — em vez de um `<select>` com a explicação à parte.
    # Continua sendo um radio nativo, com o mesmo nome de campo (`economic_profile`) e sem JS.
    profile_choices = "".join(
        f'<label class="choice{" ativo" if option.active else ""}">'
        f'<input type="radio" name="economic_profile" value="{e(option.profile.value)}"'
        f'{" checked" if option.active else ""}>'
        f'<strong>{e(option.profile.value)} — {e(option.label)}</strong>'
        f'<span class="sample">{e(option.description)}</span>'
        + (f" {_badge('s-done', '✓', 'Perfil ativo')}" if option.active else "")
        + "</label>"
        for option in economic_profile_options(profile_value)
    )
    limit_rows = "".join(
        f'<div class="kv"><span>{e(title)}</span><span>{_usd(value, zero_text="US$ 0 (bloqueia operação paga)")}</span></div>'
        for title, value in (("Limite soft mensal (vigente)", limits.soft_monthly_usd),
                             ("Limite hard mensal (vigente)", limits.hard_monthly_usd),
                             ("Limite soft por vídeo (vigente)", limits.soft_video_usd),
                             ("Limite hard por vídeo (vigente)", limits.hard_video_usd))
    )
    return f"""
      <details class="card painel-sanfona" id="painel-orcamento">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Orçamento do canal</h2>
            <p class="dim sanfona-subtitulo">
              Limites por mês e por vídeo. Real, estimado, sem custo e desconhecido nunca são somados num número só.
            </p>
          </div>
          <div class="sanfona-meta">
            <span class="chip-metric">Perfil econômico: {e(limits.economic_profile.value)}</span>
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          {configured_note}
          <form id="budget-form" data-project-id="{e(view.project.id)}" style="margin-top:14px">
            <fieldset class="perfis-escolha" aria-describedby="perfil-economico-hint">
              <legend>Perfil econômico do canal</legend>
              <div class="pill-row">{profile_choices}</div>
              <span class="hint" id="perfil-economico-hint">O perfil decide o roteamento de providers
              (seção Providers) e é salvo junto com os limites. Nada de trocar código para mudar de perfil.</span>
            </fieldset>
            <div class="grid-2" style="margin-top:14px">
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
          <p class="fine"><b>Origem dos limites vigentes:</b> {e(origin)}.</p>
          <div style="margin-top:14px">
            <h3 style="margin:0 0 6px;font-size:14px;font-weight:700">Gasto do mês</h3>
            <p class="fine" style="margin-top:0">O teto desconta real confirmado + estimado. Chamadas sem
            custo e de custo desconhecido aparecem separadas: nenhuma delas vira zero nem entra num
            número inventado.</p>
            {_summary_rows(view)}
          </div>
          {_decision_html(view)}
        </div>
      </details>
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
      <details class="card painel-sanfona" id="painel-youtube">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Canal do YouTube</h2>
            <p class="dim sanfona-subtitulo">
              Associação e status do OAuth. Só o estado e os escopos aparecem; nenhum segredo é exibido.
            </p>
          </div>
          <div class="sanfona-meta">
            {_badge(kind, icon, label)}
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          <div class="list" style="margin-top:14px">
            <div class="item" style="padding:0.6rem 0">{channel_info}</div>
            <div class="item" style="padding:0.6rem 0">
              {credential_line}
              {_oauth_controls(view, status)}
            </div>
          </div>
        </div>
      </details>
    """


def _credential_in_use_text(status: str) -> str:
    """Credencial que a execução realmente usa — sem inferir BYOK a partir de cadastro."""
    if status == "CONNECTED":
        return ("OAuth do Google registrado no secret store do servidor: é essa a credencial usada "
                "na publicação. Nenhum valor volta para o browser.")
    if status in {"EXPIRED", "REVOKED", "ERROR"}:
        return ("A credencial OAuth do YouTube está com problema; a publicação exige reautorização "
                "antes de rodar.")
    return "Nenhuma credencial OAuth em uso: o canal do YouTube não está associado."


def _prefs_card(view: ChannelsPageView) -> str:
    """F06.T03: conexão (YouTube), configuração (provider) e credencial usada são coisas distintas.

    G10: a tela nunca sugere que uma chave BYOK cadastrada esteja em uso. A execução deste canal
    resolve providers e YouTube pela configuração do servidor; BYOK pertence à tela de Equipe e
    está fora do caminho de execução (ADR fs31-005, mono-operador).
    """
    yt = view.youtube or {}
    status = str(yt.get("oauth_status") or "DISCONNECTED")
    kind, icon, status_label = _OAUTH_STATE.get(status, ("s-idle", "○", "Estado desconhecido"))
    channel_id = yt.get("channel_id")
    if channel_id:
        target_html = f"{e(yt.get('title') or 'Canal associado')} · <code>{e(channel_id)}</code>"
    else:
        target_html = "Nenhum canal do YouTube associado a este canal do Studio."
    if view.providers_error:
        configuration_rows = (
            f'<p class="warning" role="note">Configuração de providers indisponível: '
            f'{e(view.providers_error)}.</p>'
        )
    else:
        configuration_rows = "".join(
            f'<div class="kv"><span>{e(KIND_LABELS.get(card.kind, card.kind.value))}</span>'
            f'<span><code>{e(card.spec)}</code> — '
            + ("disponível" if card.availability is Availability.AVAILABLE else "indisponível agora")
            + "</span></div>"
            for card in view.providers
        ) or '<p class="muted">Nenhuma configuração de provider registrada para este canal.</p>'
    return f"""
      <details class="card painel-sanfona" id="painel-credenciais">
        <summary class="sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2>Conexão, configuração e credencial</h2>
            <p class="dim sanfona-subtitulo">
              Três coisas diferentes: o canal do YouTube associado, o provider escolhido e a
              credencial que a execução realmente usa.
            </p>
          </div>
          <div class="sanfona-meta">
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="sanfona-corpo">
          <div class="tres-estados">
            <section class="estado-bloco" aria-labelledby="h-conexao">
              <h3 id="h-conexao">Conexão</h3>
              <p class="fine">Canal do YouTube associado ao Studio.</p>
              <div class="kv"><span>Estado</span><span>{_badge(kind, icon, status_label)}</span></div>
              <div class="kv"><span>Canal</span><span>{target_html}</span></div>
            </section>
            <section class="estado-bloco" aria-labelledby="h-configuracao">
              <h3 id="h-configuracao">Configuração</h3>
              <p class="fine">Provider escolhido por tarefa; o spec real vem da configuração do canal.</p>
              {configuration_rows}
            </section>
            <section class="estado-bloco" aria-labelledby="h-credencial">
              <h3 id="h-credencial">Credencial utilizada</h3>
              <div class="kv"><span>Na execução</span><span>Credencial da implantação do Studio
              (ambiente do servidor), resolvida por provider; providers locais não usam chave.
              {e(_credential_in_use_text(status))}</span></div>
              <div class="kv"><span>BYOK</span><span>{_badge("s-idle", "○", "Não usada")}
              BYOK está fora do caminho de execução deste canal: não é usada pelo roteamento nem
              pela execução. Cadastro não é uso — a chave cadastrada na
              <a href="/studio/panel/equipe">tela de Equipe</a> fica registrada, mas não alimenta
              este canal (mono-operador, ADR fs31-005).</span></div>
            </section>
          </div>
        </div>
      </details>
    """


def _advanced_card(view: ChannelsPageView) -> str:
    project = view.project
    assert project is not None
    profile = view.profile
    config_items = "".join(
        f'<div class="kv"><span><code>{e(key)}</code></span><span><code>{e(value)}</code></span></div>'
        for key, value in view.public_config.items()
    ) or '<p class="dim">Nenhuma porta de provider sobrescrita no canal; valem os padrões do servidor.</p>'
    profile_line = (
        f'<p>Perfil: <code>{e(profile.id)}</code> · versão {profile.version}</p>'
        if profile else '<p>Perfil: não registrado para este canal.</p>'
    )
    unattributed = view.budget.summary.unattributed_calls if view.budget else 0
    return f"""
      <details class="card advanced painel-sanfona" id="canais-avancado">
        <summary class="advanced-summary sanfona-cabecalho">
          <div class="sanfona-titulos">
            <h2 style="font-size:14px;font-weight:600;margin:0">Avançado — identificadores, configuração sanitizada e uso</h2>
          </div>
          <div class="sanfona-meta">
            <span class="sanfona-seta" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>
        </summary>
        <div class="advanced-body sanfona-corpo">
          <p>Canal: <code>{e(project.id)}</code> · nicho: <code>{e(project.niche or "não informado")}</code>
             · idioma: <code>{e(project.language)}</code></p>
          {profile_line}
          <div>
            <h3>Configuração pública do canal</h3>
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
    content_html = """
      <div class="card empty" id="canais-sem-canal">
        <h2>Nenhum canal cadastrado</h2>
        <p class="muted">Sem canal não há perfil, providers, orçamento ou associação do YouTube para configurar.</p>
        <p class="fine">Crie o primeiro canal no painel — é ele que agrupa os vídeos, o perfil, os providers e o orçamento.</p>
        <a class="btn btn-primary" href="/studio/panel">Ir ao painel criar o canal</a>
      </div>
    """
    body = shell_v3.render_settings_page_body(
        active_section="canais",
        section_title="Canais",
        content_html=content_html,
    )
    html = shell_v3.render_document(
        title="Faceless Studio — Canais",
        active="canais",
        crumb="Configurações / Canais",
        body_html=body,
        nonce=nonce,
        projects=[],
        project_id="",
        cost_note="",
        extra_css=CHANNELS_CSS,
    )
    return html, shell._headers(nonce)


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


def _channels_page_js(project_id: str) -> str:
    """JavaScript da tela de Canais (canal ativo, formulários de perfil/aparência, novo canal).

    W1.5: a mesma casca serve às seções de Configurações que **reusam** os cartões desta tela
    (`api/panel_settings.py`), sem duplicar o formulário nem a persistência.
    """
    return f"""
    try {{
      document.querySelectorAll('details.painel-sanfona').forEach((det) => {{
        if (det.id !== 'canais-avancado' && det.id !== 'painel-identidade') {{
          det.open = true;
        }}
      }});
    }} catch (e) {{}}

    const projectId = "{e(project_id)}";
    const trocarCanal = (id) => {{
      if (window.StudioLoading) window.StudioLoading.start('Trocando canal ativo…');
      window.location.href = '/studio/canais?project_id=' + encodeURIComponent(id);
    }};
    const switcher = document.getElementById('canal-switcher');
    if (switcher) {{
      switcher.addEventListener('change', () => trocarCanal(switcher.value));
    }}
    document.querySelectorAll('[data-trocar-canal]').forEach((button) => {{
      button.addEventListener('click', () => trocarCanal(button.getAttribute('data-trocar-canal')));
    }});

    const newChannel = document.getElementById('new-channel-form');
    if (newChannel) {{
      newChannel.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('new-channel-feedback');
        const button = document.getElementById('btn-criar-canal');
        const name = (document.getElementById('novo-canal-nome').value || '').trim();
        if (!name) {{ if (feedback) feedback.textContent = 'Informe o nome do canal.'; return; }}
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start('Criando canal…');
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
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao criar o canal. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
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
          narrative: document.getElementById('canal-narrativa').value.trim(),
          cta: document.getElementById('canal-cta').value.trim(),
          visual_identity: document.getElementById('canal-identidade').value.trim(),
          voice: document.getElementById('canal-voz').value.trim()
        }};
        // Duração é inteiro 1–36000: vazio não é 0, então o campo só entra quando preenchido.
        const duracaoRaw = (document.getElementById('canal-duracao').value || '').trim();
        if (duracaoRaw) changes.target_duration_s = Number(duracaoRaw);
        if (!changes.name) {{ if (feedback) feedback.textContent = 'Informe o nome do perfil.'; return; }}
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start(profileId ? 'Salvando nova versão do canal…' : 'Criando perfil do canal…');
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
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar o perfil: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique os campos e tente novamente.');
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar o perfil. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }}

    const appearanceForm = document.getElementById('appearance-form');
    if (appearanceForm) {{
      appearanceForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('appearance-feedback');
        const button = document.getElementById('btn-salvar-aparencia');
        const chosen = appearanceForm.querySelector('input[name="style_id"]:checked');
        const profileId = appearanceForm.getAttribute('data-profile-id') || '';
        const version = Number(appearanceForm.getAttribute('data-profile-version') || '0');
        const value = chosen ? chosen.value : '';
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start('Salvando aparência…');
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
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar a aparência: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique o estilo e tente novamente.');
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar a aparência. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
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
          hard_video_usd: (document.getElementById('limite-hard-video').value || '').trim(),
          economic_profile: (budgetForm.querySelector('input[name="economic_profile"]:checked') || {{}}).value || ''
        }};
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start('Salvando limites de orçamento…');
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
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar os limites. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }}

    const reauth = document.getElementById('youtube-reauth');
    if (reauth) {{
      reauth.addEventListener('click', async () => {{
        const feedback = document.getElementById('youtube-feedback');
        const path = reauth.getAttribute('data-authorize-path');
        reauth.disabled = true;
        reauth.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start('Conectando ao Google…');
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
            reauth.classList.remove('carregando');
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao iniciar o consentimento. Tente novamente.';
          reauth.disabled = false;
          reauth.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
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
        revoke.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start('Revogando acesso…');
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
            revoke.classList.remove('carregando');
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao revogar. Tente novamente.';
          revoke.disabled = false;
          revoke.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
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
        button.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start('Testando conexão do provider…');
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
        button.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
      }});
    }});
    """


def render_channels(view: ChannelsPageView, channel_style=None) -> tuple[str, dict[str, str]]:
    """Página de Canais: casca aprovada + dado real do Studio ou estado vazio explícito.

    `channel_style` (F05.T04) é a projeção de personalização do canal; quando ausente a
    página é a mesma de antes (sem controle novo).
    """
    if view.project is None:
        return _empty_page(_sidebar_card(view))
    nonce = secrets.token_urlsafe(16)
    project = view.project
    channel_style_html = render_channel_style(channel_style) if channel_style is not None else ""
    # FS31 pedido do operador: o canal ativo é a primeira decisão da tela e vale para tudo —
    # estilo, voz, idioma e orçamento. Por isso ele fica fixo no topo, não escondido na sanfona.
    switch_options = "".join(
        f'<option value="{e(pid)}"{" selected" if pid == project.id else ""}>{e(label)}</option>'
        for pid, label in view.projects
    )
    channel_rows = "".join(
        (
            f'<div class="item-config" data-canal="{e(pid)}">'
            f'<div><b>{e(label)}</b><small>'
            + ("O canal que está ativo agora" if pid == project.id
               else "Trocar para este canal em todas as telas")
            + "</small></div>"
            + ('<span class="selo">ATIVO</span>' if pid == project.id else
               f'<button class="btn btn-sm" type="button" data-trocar-canal="{e(pid)}">Trocar</button>')
            + "</div>"
        )
        for pid, label in view.projects
    )
    channel_switch_html = f"""
      <div class="card" id="canal-ativo-card">
        <div class="spread" style="align-items:center;gap:12px;flex-wrap:wrap">
          <div>
            <h2 style="margin:0">Canal ativo</h2>
            <p class="dim" style="margin:2px 0 0;font-size:13px">
              Um canal por vez fica ativo — ele define estilo, voz, idioma e orçamento em todas as telas.
            </p>
          </div>
          <div class="campo" style="margin:0;min-width:220px">
            <label for="canal-switcher">Trocar canal ativo</label>
            <select id="canal-switcher" class="input">{switch_options}</select>
          </div>
        </div>
        <div style="margin-top:10px">{channel_rows}</div>
      </div>"""
    content_html = f"""
      {channel_switch_html}
      {_profile_card(view)}
      {_appearance_card(view)}
      {channel_style_html}
      {_providers_card(view)}
      {_budget_card(view)}
      {_youtube_card(view)}
      {_prefs_card(view)}
      {_advanced_card(view)}
      {_channel_card(view)}
    """
    body_page = shell_v3.render_settings_page_body(
        active_section="canais",
        section_title="Canais",
        content_html=content_html,
        project_id=project.id,
    )
    page_js = _channels_page_js(project.id)
    html = shell_v3.render_document(
        title="Faceless Studio — Canais",
        active="canais",
        crumb="Configurações / Canais",
        body_html=body_page,
        nonce=nonce,
        projects=[(project.id, project.name)],
        project_id=project.id,
        cost_note="",
        page_js=page_js + CHANNEL_STYLE_JS,
        extra_css=CHANNELS_CSS + CHANNEL_STYLE_CSS,
    )
    return html, shell._headers(nonce)