"""Tela de Equipe (F11): membros, papéis, tenants, chaves BYOK e consumo.

Entra pela casca aprovada (`api/panel.render_sidebar`). Renderiza **somente** dado real do
Studio ou estado vazio explícito: nenhum nome, e-mail, organização ou custo ilustrativo do
mockup embarca. O valor da chave nunca é renderizado — a visão já chega só com a máscara.

As mutações (membro, papel, BYOK) são expostas pelos endpoints JSON em `api/routes.py`
(`/studio/panel/equipe/...`) e executadas por esta tela. O ator é o **operador autenticado do
painel**; a autorização é o RBAC do domínio (papel do vínculo ativo na organização). A tela
declara o que ainda não existe — login por SSO/OIDC (F11-02), envio de e-mail de convite,
cobrança/créditos e isolamento de runtime por tenant — em vez de fingir. Sem organização, os
controles ficam indisponíveis (não há o que gerir). Não há barra de progresso (nada aqui é
linear) e os IDs/fingerprints ficam no `<details>` fechado.
"""
from __future__ import annotations

import html
import secrets
from datetime import datetime

from ..application.panel import CostBreakdown, MonthCost, cost_summary_text
from ..application.saas import TeamView
from ..domain.saas import ROLE_PERMISSIONS, ByokStatus, MembershipStatus, Permission, Role
from . import panel as shell
from . import shell_v3

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
.role-badge.reviewer { color: var(--info); border-color: var(--accent); background: var(--info-surface); }
.mask {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text-muted); background: var(--input-bg); border: 1px solid var(--border-soft);
  border-radius: 6px; padding: 0.05rem 0.35rem;
}
.team-actions { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
.team-actions .btn[disabled] { opacity: 0.65; cursor: not-allowed; }
.team-add { position: relative; }
.team-add summary { cursor: pointer; list-style: none; }
.team-add summary::-webkit-details-marker { display: none; }
.team-add-form {
  display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: end; margin-top: 0.6rem;
  padding: 0.7rem; border: 1px solid var(--border-soft); border-radius: 8px; background: var(--surface-raised);
}
.team-add-form .field { min-width: 10rem; }
.role-select { width: auto; }
.team-empty { color: var(--text-muted); }
.team-fact { margin: 0.35rem 0; }
.team-fact b { color: var(--text); }
/* Matriz de papéis (análise de Configurações 3.3): permissão de relance, do RBAC real. */
.papeis-matriz-wrap { margin-top: 1rem; overflow-x: auto; }
.papeis-matriz { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.papeis-matriz caption { text-align: left; color: var(--text-dim); font-size: 0.76rem; padding-bottom: 0.5rem; }
.papeis-matriz th, .papeis-matriz td {
  text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border-soft); white-space: nowrap;
}
.papeis-matriz thead th { color: var(--text-dim); font-weight: 650; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.04em; }
.papeis-matriz tbody th { font-weight: 500; }
.papeis-matriz .sim { color: var(--ok); font-weight: 650; }
.papeis-matriz .nao { color: var(--text-dim); }
@media (max-width: 820px) {
  .team-member, .team-key { grid-template-columns: minmax(0, 1fr); }
  .team-actions .btn { width: 100%; }
}
"""

TEAM_JS = """
    function teamFeedback(name) { return document.querySelector('[data-feedback="' + name + '"]'); }

    async function teamSend(url, options, feedbackName) {
      const box = teamFeedback(feedbackName);
      try {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (response.ok) {
          if (box) box.textContent = 'Ação concluída. Atualizando...';
          setTimeout(() => window.location.reload(), 500);
          return;
        }
        if (response.status === 403) {
          if (box) box.textContent = 'Seu papel na organização não autoriza esta ação.';
        } else {
          const detail = (data && typeof data.detail === 'string') ? data.detail : 'confira os campos.';
          if (box) box.textContent = 'Não foi possível concluir: ' + detail;
        }
      } catch (error) {
        if (box) box.textContent = 'Falha de rede. Tente novamente.';
      }
    }

    document.querySelectorAll('form.team-add-form').forEach((form) => {
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const org = form.getAttribute('data-organization-id');
        const keyAction = form.getAttribute('data-key-action');
        if (keyAction === 'rotate') {
          const keyId = form.getAttribute('data-key-id');
          const value = form.querySelector('[name="value"]').value;
          await teamSend('/studio/panel/equipe/keys/' + encodeURIComponent(keyId) + '/rotate',
            { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ organization_id: org, value: value }) }, 'keys');
          return;
        }
        if (form.getAttribute('data-team-form') === 'member') {
          const email = form.querySelector('[name="email"]').value.trim();
          const role = form.querySelector('[name="role"]').value;
          await teamSend('/studio/panel/equipe/members',
            { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ organization_id: org, email: email, role: role }) }, 'members');
          return;
        }
        const provider = form.querySelector('[name="provider"]').value.trim();
        const value = form.querySelector('[name="value"]').value;
        await teamSend('/studio/panel/equipe/keys',
          { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ organization_id: org, provider: provider, value: value }) }, 'keys');
      });
    });

    document.querySelectorAll('[data-member-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const row = button.closest('[data-membership-id]');
        const membershipId = row.getAttribute('data-membership-id');
        const form = document.querySelector('form.team-add-form[data-team-form="member"]');
        const org = form ? form.getAttribute('data-organization-id') : '';
        if (button.getAttribute('data-member-action') === 'role') {
          const role = row.querySelector('.role-select').value;
          await teamSend('/studio/panel/equipe/members/' + encodeURIComponent(membershipId),
            { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ organization_id: org, role: role }) }, 'members');
        } else {
          await teamSend('/studio/panel/equipe/members/' + encodeURIComponent(membershipId)
            + '?organization_id=' + encodeURIComponent(org), { method: 'DELETE' }, 'members');
        }
      });
    });

    document.querySelectorAll('[data-key-action="revoke"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const keyId = button.getAttribute('data-key-id');
        const org = button.getAttribute('data-organization-id');
        await teamSend('/studio/panel/equipe/keys/' + encodeURIComponent(keyId)
          + '?organization_id=' + encodeURIComponent(org), { method: 'DELETE' }, 'keys');
      });
    });
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
          custos e logs. O filtro por organização existe no repositório e é alimentado pelo vínculo
          do operador autenticado; o login por SSO/OIDC (F11-02) ainda não é a fonte de identidade.</p>
        <div class="kv"><span>Organização</span><span>{e(view.organization.name)}</span></div>
        <div class="kv"><span>Workspace</span><span>{e(workspace)}</span></div>
        <div class="kv"><span>Isolamento aplicado em runtime</span><span>não — mono-usuário</span></div>
        <div class="kv"><span>Teste de vazamento entre tenants</span><span>coberto no repositório</span></div>
      </section>"""


def _members_card(view: TeamView) -> str:
    if view.organization is None:
        rows = f'<p class="team-empty">{_selo("idle", "○", "Nenhum membro sem organização")}</p>'
        controls = (
            '<div class="team-actions">'
            '<button class="btn btn-sm" type="button" disabled '
            'title="Indisponível: sem organização cadastrada não há membro para gerir.">Adicionar membro</button>'
            '</div>'
        )
        footer = (
            '<p class="fine">Sem organização não há membro, papel ou vínculo para gerir. O ator é o operador '
            'autenticado do painel; o login por SSO/OIDC (F11-02) ainda não é a fonte de identidade.</p>'
        )
    else:
        org_id = view.organization.id
        items = []
        for member in view.members:
            initial = (member.display_name or member.email)[:1].upper()
            role = member.role.value
            options = "".join(
                f'<option value="{e(r.value)}"{" selected" if r is member.role else ""}>{e(r.value)}</option>'
                for r in Role
            )
            items.append(f"""
          <div class="team-member" data-membership-id="{e(member.membership_id)}">
            <div class="team-person">
              <span class="team-avatar" aria-hidden="true">{e(initial)}</span>
              <div>
                <div class="team-name">{e(member.display_name)}</div>
                <div class="team-sub">{e(member.email)}</div>
              </div>
            </div>
            <label class="sr-only" for="papel-{e(member.membership_id)}">Papel de {e(member.display_name)}</label>
            <select class="input role-select" id="papel-{e(member.membership_id)}">{options}</select>
            {_member_status(member)}
            <div class="team-actions">
              <button class="btn btn-sm" type="button" data-member-action="role">Salvar papel</button>
              <button class="btn btn-sm btn-ghost" type="button" data-member-action="remove">Remover</button>
            </div>
          </div>""")
        rows = "".join(items) if items else f'<p class="team-empty">{_selo("idle", "○", "Nenhum membro cadastrado")}</p>'
        role_options = "".join(f'<option value="{e(r.value)}">{e(r.value)}</option>' for r in Role)
        controls = (
            '<div class="team-actions">'
            '<details class="team-add"><summary class="btn btn-sm">Adicionar membro</summary>'
            f'<form class="team-add-form" data-team-form="member" data-organization-id="{e(org_id)}">'
            '<div class="field"><label for="novo-membro-email">E-mail</label>'
            '<input class="input" type="email" id="novo-membro-email" name="email" maxlength="320" required></div>'
            '<div class="field"><label for="novo-membro-papel">Papel</label>'
            f'<select class="input" id="novo-membro-papel" name="role">{role_options}</select></div>'
            '<button class="btn btn-primary btn-sm" type="submit">Criar vínculo</button>'
            '</form></details>'
            '</div>'
        )
        footer = (
            '<p class="fine">A ação cria o vínculo como <b>convite pendente</b>; o e-mail de convite ainda '
            '<b>não é enviado</b>. A autorização é o papel do operador autenticado no domínio — um vínculo '
            '<i>viewer</i> recebe 403.</p>'
        )

    return f"""
      <section class="card" aria-labelledby="h-membros">
        <div class="spread">
          <div>
            <h2 id="h-membros">Membros</h2>
            <p class="dim" style="margin:0.3rem 0 0">Papéis por organização. Nome e e-mail são
              dado real do cadastro.</p>
          </div>
          {controls}
        </div>
        {rows}
        <div class="form-feedback" data-feedback="members" role="status" aria-live="polite"></div>
        {footer}
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
        {_permissions_matrix(view)}
      </section>"""


# Colunas da matriz de papéis (análise de Configurações 3.3). Cada coluna é **uma permissão real**
# do RBAC do domínio (`domain.saas.Permission`), não uma capacidade inventada.
_MATRIX_COLUMNS: tuple[tuple[str, Permission], ...] = (
    ("Editar / gerar", Permission.EDIT_VIDEO),
    ("Aprovar", Permission.APPROVE_PREVIEW),
    ("Publicar", Permission.PUBLISH),
)


def _permissions_matrix(view: TeamView) -> str:
    """Tabela Papel × permissão, gerada de `ROLE_PERMISSIONS` (dado real, sem inventar).

    O protótipo (`settingsTeam`, `prototype/index.html:629`) mostra a mesma matriz, mas de forma
    **ilustrativa** (Editor sem publicar). Aqui ela reflete o RBAC que o servidor aplica de verdade:
    Editor publica; Reviewer aprova e não publica; Viewer só lê.
    """
    header = "".join(f'<th scope="col">{e(label)}</th>' for label, _ in _MATRIX_COLUMNS)
    body = []
    for role, _description in view.roles:
        allowed = ROLE_PERMISSIONS.get(role, frozenset())
        cells = "".join(
            f'<td class="{"sim" if permission in allowed else "nao"}">'
            f'{"Sim" if permission in allowed else "Não"}</td>'
            for _label, permission in _MATRIX_COLUMNS
        )
        body.append(
            f'<tr><th scope="row"><span class="role-badge {e(role.value)}">{e(role.value)}</span></th>'
            f'{cells}</tr>'
        )
    return (
        '<div class="papeis-matriz-wrap">'
        '<table class="papeis-matriz">'
        '<caption>Permissões aplicadas pelo servidor, por papel.</caption>'
        f'<thead><tr><th scope="col">Papel</th>{header}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table></div>'
    )


def _keys_card(view: TeamView) -> str:
    if view.organization is None:
        body = f'<p class="team-empty">{_selo("idle", "○", "Nenhuma chave sem organização")}</p>'
        controls = (
            '<div class="team-actions">'
            '<button class="btn btn-sm" type="button" disabled '
            'title="Indisponível: sem organização cadastrada não há chave para gerir.">Adicionar chave</button>'
            '</div>'
        )
        footer = (
            '<p class="fine">Sem organização não há chave BYOK para gerir. Nenhum valor de chave é '
            'exibido depois de salvo.</p>'
        )
    else:
        org_id = view.organization.id
        controls = (
            '<div class="team-actions">'
            '<details class="team-add"><summary class="btn btn-sm">Adicionar chave</summary>'
            f'<form class="team-add-form" data-team-form="key" data-organization-id="{e(org_id)}">'
            '<div class="field"><label for="nova-chave-provider">Provider</label>'
            '<input class="input" type="text" id="nova-chave-provider" name="provider" maxlength="64" '
            'placeholder="ex.: elevenlabs" required></div>'
            '<div class="field"><label for="nova-chave-valor">Valor da chave</label>'
            '<input class="input" type="password" id="nova-chave-valor" name="value" autocomplete="off" required></div>'
            '<button class="btn btn-primary btn-sm" type="submit">Guardar no cofre</button>'
            '</form></details>'
            '</div>'
        )
        if not view.keys:
            body = (f'<p class="team-empty">{_selo("idle", "○", "Nenhuma chave BYOK cadastrada")}</p>'
                    '<p class="fine">O Studio usa as credenciais do ambiente até uma chave do tenant ser '
                    'cadastrada. Nenhum valor de chave é exibido depois de salvo.</p>')
        else:
            items = []
            for key in view.keys:
                rotation = (f"rotacionada {_age(view.now, key.rotated_at)}"
                            if key.rotated_at else "nunca rotacionada")
                items.append(f"""
          <div class="team-key" data-key-id="{e(key.id)}">
            <div>
              <div class="team-name">{e(key.provider)}</div>
              <div class="team-sub">Máscara <span class="mask">{e(key.mask)}</span> ·
                criada {_age(view.now, key.created_at)} · {e(rotation)}</div>
            </div>
            <span class="team-sub">{e(_usage_text(key.usage))}</span>
            {_key_status(key)}
            <div class="team-actions">
              <details class="team-add"><summary class="btn btn-sm btn-ghost">Rotacionar…</summary>
                <form class="team-add-form" data-key-action="rotate" data-organization-id="{e(org_id)}"
                      data-key-id="{e(key.id)}">
                  <div class="field"><label for="rot-{e(key.id)}">Novo valor da chave</label>
                  <input class="input" type="password" id="rot-{e(key.id)}" name="value"
                         autocomplete="off" required></div>
                  <button class="btn btn-primary btn-sm" type="submit">Trocar valor</button>
                </form></details>
              <button class="btn btn-sm btn-ghost" type="button" data-key-action="revoke"
                data-organization-id="{e(org_id)}" data-key-id="{e(key.id)}">Revogar</button>
            </div>
          </div>""")
            body = "".join(items)
        footer = (
            '<p class="fine">Máscara, status e consumo atribuído aparecem; o valor da chave nunca. '
            'Registrar, rotacionar e revogar são auditados com o ator (operador autenticado) no backend. '
            'Criptografia at-rest é a permissão do cofre (0700/0600); não há KMS/envelope.</p>'
        )
    return f"""
      <section class="card" aria-labelledby="h-chaves">
        <div class="spread">
          <div>
            <h2 id="h-chaves">Chaves BYOK</h2>
            <p class="dim" style="margin:0.3rem 0 0">Credencial própria do cliente, por tenant e
              provider. Só a máscara aparece; o valor fica no cofre com permissão restrita.</p>
          </div>
          {controls}
        </div>
        {body}
        <div class="form-feedback" data-feedback="keys" role="status" aria-live="polite"></div>
        {footer}
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


def render_team(view: TeamView, *, month: MonthCost | None = None,
                projects: list[tuple[str, str]] | None = None,
                project_id: str = "") -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    organization_state = (
        _selo("idle", "○", "Sem organização cadastrada") if view.organization is None
        else _selo("done", "✓", "Organização cadastrada")
    )
    cost_str = (
        f"Custo do mês: {month.text}"
        if month is not None and month.breakdown.calls > 0
        else "Não disponível: nenhuma chamada registrada neste mês."
    )
    content_html = f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Gestão de acesso e equipe</h2>
            <p class="dim" style="margin:4px 0 0">
              Ação primária: <b>gerir acesso</b>. Membros, papéis e BYOK são
              executados pela rota, autorizados pelo papel do operador autenticado; o isolamento de
              runtime por tenant segue mono-usuário.
            </p>
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

      <div class="card" aria-labelledby="h-indisp-equipe">
        <h2 id="h-indisp-equipe">O que ainda está indisponível</h2>
        <p class="muted" style="margin:0">{e(view.actions_note)}</p>
      </div>
      <div class="card" aria-labelledby="h-fronteira">
        <h2 id="h-fronteira">Fronteira de tenant</h2>
        <p class="muted" style="margin:0">Toda leitura e escrita do repositório recebe a
          organização do ator e a filtra no banco. O teste cross-tenant não acessa conteúdo nem
          credenciais de outra organização.</p>
      </div>
      <div class="card" aria-labelledby="h-correcao">
        <h2 id="h-correcao">Estado desta tela</h2>
        <p class="muted" style="margin:0">O F11 foi liberado em 2026-11-20 e as mutações passaram a
          ser executadas pela rota: o ator é o operador autenticado e o papel do vínculo aplica o
          RBAC. O que falta é a fonte de identidade por SSO/OIDC (F11-02), o envio do e-mail de
          convite, a cobrança e o isolamento de runtime por tenant — declarados, não fingidos.</p>
      </div>
    """
    body = shell_v3.render_settings_page_body(
        active_section="equipe",
        section_title="Equipe",
        content_html=content_html,
        project_id=project_id,
    )
    html = shell_v3.render_document(
        title="Faceless Studio — Equipe",
        active="equipe",
        crumb="Configurações / Equipe",
        body_html=body,
        nonce=nonce,
        projects=projects or [],
        project_id=project_id,
        cost_note=cost_str,
        page_js=TEAM_JS,
        extra_css=TEAM_CSS,
    )
    return html, shell._headers(nonce)