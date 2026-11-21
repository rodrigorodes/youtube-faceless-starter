"""Tela de Equipe (F11): membros, papéis, tenants, chaves BYOK e consumo.

Entra pela casca aprovada (`api/panel.render_sidebar`). Renderiza **somente** dado real do
Studio ou estado vazio explícito: nenhum nome, e-mail, organização ou custo ilustrativo do
mockup embarca. O valor da chave nunca é renderizado — a visão já chega só com a máscara.

A tela é de leitura: as ações de gerir acesso exigem um ator autenticado (F11-02) e aparecem
como indisponíveis, com o motivo em texto e sem entrar na ordem de foco. Não há barra de progresso
(nada aqui é linear) e os IDs/fingerprints ficam no `<details>` fechado.
"""
from __future__ import annotations

import html
import secrets
from datetime import datetime

from ..application.panel import CostBreakdown, MonthCost, cost_summary_text
from ..application.saas import TeamView
from ..domain.saas import ByokStatus, MembershipStatus, Role
from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

TEAM_CSS = """
.team-member, .team-key {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.8rem 0;
  border-top: 1px solid var(--border-soft);
}
.team-member:first-child, .team-key:first-child { border-top: 0; }
.team-person { display: flex; align-items: center; gap: 0.7rem; min-width: 0; }
.team-avatar {
  display: inline-grid; place-items: center; width: 34px; height: 34px; flex: none;
  border-radius: 50%; background: var(--accent-soft); color: var(--text);
  font-size: 0.78rem; font-weight: 700;
}
.team-name { font-weight: 650; color: var(--text); }
.team-sub { color: var(--text-dim); font-size: 0.76rem; overflow-wrap: anywhere; }
.role-badge {
  display: inline-flex; align-items: center; padding: 0.18rem 0.55rem;
  border-radius: 999px; border: 1px solid var(--border); background: var(--surface-raised);
  color: var(--text-muted); font-size: 0.72rem; font-weight: 700; text-transform: lowercase;
}
.role-badge.owner { color: var(--gold); border-color: #6b4a1c; background: var(--warn-surface); }
.role-badge.reviewer { color: var(--info); border-color: #14567a; background: var(--info-surface); }
.mask {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text-muted); background: var(--input-bg); border: 1px solid var(--border-soft);
  border-radius: 6px; padding: 0.05rem 0.35rem;
}
.team-actions { display: flex; flex-wrap: wrap; gap: 0.45rem; }
.team-actions .btn[disabled] { opacity: 0.65; cursor: not-allowed; }
.team-empty { color: var(--text-muted); }
.team-fact { margin: 0.35rem 0; }
.team-fact b { color: var(--text); }
@media (max-width: 820px) {
  .team-member, .team-key { grid-template-columns: minmax(0, 1fr); }
  .team-actions .btn { width: 100%; }
}
"""


def _selo(kind: str, icon: str, label: str) -> str:
    return (f'<span class="state s-{kind}"><span class="glyph" aria-hidden="true">{icon}</span> '
            f'{e(label)}</span>')


def _age(now: datetime, value: datetime | None) -> str:
    if value is None:
        return "data não registrada"
    days = (now - value).days
    return "hoje" if days <= 0 else f"há {days} d"


def _member_status(member) -> str:
    if member.status is MembershipStatus.INVITED:
        return _selo("act", "!", "Convite pendente")
    return _selo("done", "✓", "Ativo")


def _key_status(key) -> str:
    if key.status is ByokStatus.REVOKED:
        return _selo("fail", "×", "Revogada")
    return _selo("done", "✓", "Ativa")


def _usage_text(breakdown: CostBreakdown) -> str:
    return "sem consumo atribuído" if breakdown.calls == 0 else cost_summary_text(breakdown)


def _org_card(view: TeamView) -> str:
    if view.organization is None:
        return f"""
      <section class="card empty" aria-labelledby="h-org">
        <div class="spread">
          <div>
            {_selo("idle", "○", "Sem organização cadastrada")}
            <h2 id="h-org" style="margin:0.6rem 0 0">Nenhuma organização cadastrada</h2>
            <p class="muted" style="margin:0.35rem 0 0">
              O Studio atual é <b>mono-usuário</b>. As tabelas de organização, vínculo e chave
              existem, mas nenhum tenant foi criado e nada em runtime é isolado por organização.
            </p>
          </div>
          {_selo("act", "!", "Modelo implantado · runtime mono-usuário")}
        </div>
      </section>"""
    workspace = view.workspace_name or "não registrado"
    return f"""
      <section class="card" aria-labelledby="h-org">
        <h2 id="h-org">Organização e isolamento</h2>
        <p class="dim" style="margin:0.35rem 0 0.6rem">Um tenant isola registros, storage, jobs,
          custos e logs. O filtro por organização existe no repositório; a sessão que o alimenta
          (F11-02) ainda não existe.</p>
        <div class="kv"><span>Organização</span><span>{e(view.organization.name)}</span></div>
        <div class="kv"><span>Workspace</span><span>{e(workspace)}</span></div>
        <div class="kv"><span>Isolamento aplicado em runtime</span><span>não — mono-usuário</span></div>
        <div class="kv"><span>Teste de vazamento entre tenants</span><span>coberto no repositório</span></div>
      </section>"""


def _members_card(view: TeamView) -> str:
    if view.organization is None:
        rows = f'<p class="team-empty">{_selo("idle", "○", "Nenhum membro sem organização")}</p>'
    elif not view.members:
        rows = f'<p class="team-empty">{_selo("idle", "○", "Nenhum membro cadastrado")}</p>'
    else:
        items = []
        for member in view.members:
            initial = (member.display_name or member.email)[:1].upper()
            role = member.role.value
            items.append(f"""
          <div class="team-member">
            <div class="team-person">
              <span class="team-avatar" aria-hidden="true">{e(initial)}</span>
              <div>
                <div class="team-name">{e(member.display_name)}</div>
                <div class="team-sub">{e(member.email)}</div>
              </div>
            </div>
            <span class="role-badge {e(role)}">{e(role)}</span>
            {_member_status(member)}
            <div class="team-actions">
              <button class="btn btn-sm" type="button" aria-disabled="true" disabled
                title="Indisponível: exige ator autenticado (F11-02).">Gerir</button>
            </div>
          </div>""")
        rows = "".join(items)

    return f"""
      <section class="card" aria-labelledby="h-membros">
        <div class="spread">
          <div>
            <h2 id="h-membros">Membros</h2>
            <p class="dim" style="margin:0.3rem 0 0">Papéis por organização. Nome e e-mail são
              dado real do cadastro.</p>
          </div>
          <div class="team-actions">
            <button class="btn btn-sm" type="button" aria-disabled="true" disabled
              title="Indisponível: exige ator autenticado (F11-02).">Convidar</button>
          </div>
        </div>
        {rows}
        <p class="fine">Gerir acesso está indisponível nesta versão: sem sessão de usuário
          (F11-02), o Studio não sabe quem é o owner que autoriza a ação.</p>
      </section>"""


def _roles_card(view: TeamView) -> str:
    rows = "".join(
        f'<div class="kv"><span><span class="role-badge {e(role.value)}">{e(role.value)}</span></span>'
        f'<span style="font-weight:500;color:var(--text-muted)">{e(description)}</span></div>'
        for role, description in view.roles
    )
    return f"""
      <section class="card" aria-labelledby="h-papeis">
        <h2 id="h-papeis">Papéis</h2>
        <p class="dim" style="margin:0.3rem 0 0.6rem">Quatro papéis canônicos. Papel é permissão
          de acesso, não plano comercial.</p>
        {rows}
      </section>"""


def _keys_card(view: TeamView) -> str:
    if view.organization is None:
        body = f'<p class="team-empty">{_selo("idle", "○", "Nenhuma chave sem organização")}</p>'
    elif not view.keys:
        body = (f'<p class="team-empty">{_selo("idle", "○", "Nenhuma chave BYOK cadastrada")}</p>'
                '<p class="fine">O Studio usa as credenciais do ambiente até uma chave do tenant ser '
                'cadastrada. Nenhum valor de chave é exibido depois de salvo.</p>')
    else:
        items = []
        for key in view.keys:
            rotation = (f"rotacionada {_age(view.now, key.rotated_at)}"
                        if key.rotated_at else "nunca rotacionada")
            items.append(f"""
          <div class="team-key">
            <div>
              <div class="team-name">{e(key.provider)}</div>
              <div class="team-sub">Máscara <span class="mask">{e(key.mask)}</span> ·
                criada {_age(view.now, key.created_at)} · {e(rotation)}</div>
            </div>
            <span class="team-sub">{e(_usage_text(key.usage))}</span>
            {_key_status(key)}
            <div class="team-actions">
              <button class="btn btn-sm btn-ghost" type="button" aria-disabled="true" disabled
                title="Indisponível: exige ator autenticado (F11-02).">Revogar…</button>
            </div>
          </div>""")
        body = "".join(items)
    return f"""
      <section class="card" aria-labelledby="h-chaves">
        <div class="spread">
          <div>
            <h2 id="h-chaves">Chaves BYOK</h2>
            <p class="dim" style="margin:0.3rem 0 0">Credencial própria do cliente, por tenant e
              provider. Só a máscara aparece; o valor fica no cofre com permissão restrita.</p>
          </div>
          <div class="team-actions">
            <button class="btn btn-sm" type="button" aria-disabled="true" disabled
              title="Indisponível: exige ator autenticado (F11-02).">Adicionar chave</button>
          </div>
        </div>
        {body}
        <p class="fine">Máscara, status e consumo atribuído aparecem; o valor da chave nunca.
          Rotação e revogação são auditadas por tenant no backend, mas a tela não dispara a ação
          sem sessão.</p>
      </section>"""


def _consumption_card(view: TeamView) -> str:
    if view.tenant_cost.calls:
        tenant_rows = shell.cost_breakdown_rows(view.tenant_cost)
    else:
        tenant_rows = ('<div class="kv"><span>Custo do tenant</span>'
                       '<span>sem registro de uso atribuído</span></div>')
    if view.member_costs:
        member_rows = "".join(
            f'<div class="kv"><span>{e(item.label)}</span><span>{e(cost_summary_text(item.cost))}</span></div>'
            for item in view.member_costs)
    else:
        member_rows = '<div class="kv"><span>Por membro</span><span>sem registro de uso atribuído</span></div>'
    return f"""
      <section class="card" aria-labelledby="h-consumo">
        <h2 id="h-consumo">Consumo por tenant</h2>
        <p class="dim" style="margin:0.3rem 0 0.6rem">Medição de uso atribuído por organização e
          membro. Custo real, estimado e desconhecido são separados; ausência não vira zero.</p>
        {tenant_rows}
        {member_rows}
        <p class="fine">Custos das APIs do cliente são medidos, não cobrados por uma tabela de
          preços da plataforma: não há plano, crédito ou preço nosso nesta versão.</p>
      </section>"""


def _advanced_card(view: TeamView) -> str:
    if view.organization is None:
        body = '<p class="fine" style="margin:0">Sem organização, não há IDs técnicos a mostrar.</p>'
    else:
        member_ids = "".join(
            f'<div class="kv"><span>{e(m.display_name)}</span><span>{e(m.membership_id)}</span></div>'
            for m in view.members)
        key_ids = "".join(
            f'<div class="kv"><span>{e(k.provider)} · impressão</span><span>{e(k.fingerprint)}</span></div>'
            for k in view.keys)
        body = (f'<div class="kv"><span>Organização</span><span>{e(view.organization.id)}</span></div>'
                f'{member_ids}{key_ids}')
    return f"""
      <details class="card">
        <summary>Detalhes técnicos (IDs e impressões digitais)</summary>
        <p class="fine">IDs de vínculo e impressão sha256 da chave. A impressão identifica a chave
          sem guardar nem exibir o valor.</p>
        {body}
      </details>"""


def _side_card(month: MonthCost | None) -> str:
    if month is None:
        return """
        <div class="side-card">
          <h2>Orçamento do mês</h2>
          <p>Não disponível: o banco do Studio não está configurado nesta execução.</p>
        </div>"""
    return shell.budget_side_card(month)


def render_team(view: TeamView, *, month: MonthCost | None = None) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    organization_state = (
        _selo("idle", "○", "Sem organização cadastrada") if view.organization is None
        else _selo("done", "✓", "Organização cadastrada")
    )
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Equipe</title>
  <style nonce="{nonce}">{shell.CSS}{TEAM_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#equipe-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="equipe", base_href="/studio/panel", side_card_html=_side_card(month))}
    <main class="main-content" id="equipe-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="equipe-heading">Equipe</h1>
            <p class="page-goal">Ação primária: <b>gerir acesso</b>. O caminho de organização,
              papel e BYOK está implantado no banco; a aplicação em runtime ainda é mono-usuário.</p>
          </div>
          {organization_state}
        </div>
        <p class="fine" style="margin-top:0.6rem">{e(view.runtime_note)}</p>
      </div>

      {_org_card(view)}
      {_members_card(view)}
      {_roles_card(view)}
      {_keys_card(view)}
      {_consumption_card(view)}
      {_advanced_card(view)}
    </main>

    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-indisp-equipe">
        <h2 id="h-indisp-equipe">Por que as ações estão indisponíveis</h2>
        <p class="muted" style="margin:0">{e(view.actions_note)}</p>
      </section>
      <section class="card" aria-labelledby="h-fronteira">
        <h2 id="h-fronteira">Fronteira de tenant</h2>
        <p class="muted" style="margin:0">Toda leitura e escrita do repositório recebe a
          organização do ator e a filtra no banco. O teste cross-tenant não acessa conteúdo nem
          credenciais de outra organização.</p>
      </section>
      <section class="card" aria-labelledby="h-correcao">
        <h2 id="h-correcao">Estado desta tela</h2>
        <p class="muted" style="margin:0">O F11 estava adiado e foi liberado em 2026-11-20: o
          modelo de dados existe. O que ainda falta é a sessão/OIDC que autoriza as ações; até
          lá, a tela mostra o estado real e não finge executar gestão de acesso.</p>
      </section>
    </aside>
  </div>
</body>
</html>"""
    return page, shell._headers(nonce)