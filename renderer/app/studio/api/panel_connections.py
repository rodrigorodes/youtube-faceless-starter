"""Tela de Conexões (YT-04b) — conta Google → canais do YouTube, só com dado real do Studio.

A metade visual do fluxo que a YT-04a deixou pronta como serviço + API. A tela mostra a
hierarquia **conta → canais** (status por canal e **qual canal do estúdio publica ali**),
conecta uma conta (OAuth), **confirma o canal escolhido antes de vincular** (nome + id, §5.4),
deixa vincular/desvincular o canal do estúdio e revogar uma autorização **isoladamente**.

Regras que a tela respeita (§6/§7):

- o vazio **ensina** o próximo passo ("Nenhuma conta conectada" + o botão + o que será pedido);
- nada inventado: o que `GET /connections` não traz vira "não disponível" — sem preview, sem %;
- o vínculo do canal usa o `PATCH /channels/{profile_id}` já existente (nenhuma rota nova);
- ações destrutivas (revogar/desvincular) passam por um `<dialog>` nativo com o efeito explícito;
- os resultados aparecem num único `role="status" aria-live="polite"`.

Fonte de verdade: `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` §4/§5.4/§6/§7
e `docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md`.
"""
from __future__ import annotations

import html
import secrets

from ..domain.channel import ChannelProfile
from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

# (classe do estado, rótulo): o status vem do serviço, o texto é a leitura honesta dele.
_STATUS = {
    "CONNECTED": ("done", "✓", "Conectado"),
    "EXPIRED": ("active", "!", "Expirado"),
    "REVOKED": ("fail", "×", "Revogado"),
    "DISCONNECTED": ("idle", "·", "Sem credencial"),
    "ERROR": ("fail", "×", "Erro na autorização"),
}
# Escopos pedidos, em linguagem clara (§6: "o que será pedido").
_SCOPES_EXPLAINED = (
    ("youtube.upload", "Enviar (subir) os vídeos para o canal."),
    ("youtube.readonly", "Ler o canal e os vídeos — para conferir o destino antes de publicar."),
)

CONNECTIONS_CSS = """
.conn-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; }
.conn-note { margin-top: 0.9rem; }
.conn-account { border-top: 1px solid var(--border-soft); padding-top: 1rem; margin-top: 1rem; }
.conn-account:first-of-type { border-top: 0; padding-top: 0; margin-top: 0; }
.conn-account-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.6rem; }
.conn-email { font-weight: 700; }
.conn-channel {
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 0.85rem 1rem;
  margin-top: 0.75rem;
  background: #0e1524;
}
.conn-channel-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; }
.conn-name { font-weight: 600; }
.conn-id { color: var(--text-dim); font-size: 0.78rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.conn-meta { margin-top: 0.4rem; font-size: 0.78rem; color: var(--text-muted); }
.conn-dests { margin: 0.5rem 0 0; padding: 0; list-style: none; display: grid; gap: 0.4rem; }
.conn-dest { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; }
.conn-channel-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.65rem; align-items: center; }
.conn-link { margin-top: 0.6rem; }
.conn-link > summary { cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0; }
.conn-link > summary::-webkit-details-marker { display: none; }
.conn-link-body {
  margin-top: 0.6rem; padding: 0.85rem;
  border: 1px dashed var(--border-hover); border-radius: 10px;
  display: flex; flex-direction: column; gap: 0.75rem;
}
.conn-confirm {
  margin: 0; padding: 0.65rem 0.8rem;
  border-left: 3px solid var(--warn); background: var(--warn-bg);
  border-radius: 0 8px 8px 0; font-size: 0.82rem; line-height: 1.5;
}
.conn-status {
  min-height: 1.6rem; padding: 0.55rem 0.8rem; border-radius: 10px;
  background: var(--surface-raised); border: 1px solid var(--border);
  font-size: 0.82rem; color: var(--text-muted);
}
.conn-status[data-kind="bad"] { border-color: var(--bad); color: var(--text); background: var(--bad-bg); }
.conn-status[data-kind="ok"] { border-color: var(--success); color: var(--text); background: var(--success-surface); }
.conn-status:empty { display: none; }
.conn-scopes { margin: 0.5rem 0 0; padding-left: 1.1rem; font-size: 0.82rem; color: var(--text-muted); line-height: 1.6; }
.conn-scopes code { color: var(--text); }
dialog.confirm-dialog {
  border: 1px solid var(--border); border-radius: 14px; padding: 0; max-width: 30rem; width: calc(100% - 2rem);
  background: var(--surface); color: var(--text); box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}
dialog.confirm-dialog::backdrop { background: rgba(0, 0, 0, 0.62); }
dialog:modal { overscroll-behavior: contain; }
dialog::backdrop { overscroll-behavior: contain; }
.confirm-dialog-body { padding: 1.15rem 1.25rem; display: grid; gap: 0.75rem; }
.confirm-dialog h2 { font-size: 1rem; }
.confirm-dialog p { color: var(--text-muted); font-size: 0.85rem; line-height: 1.55; }
.confirm-dialog .confirm-actions { display: flex; justify-content: flex-end; gap: 0.6rem; }
.conn-cta-note { margin-top: 0.75rem; }
.conn-source {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.2rem 0.6rem; border: 1px solid var(--border); border-radius: 999px;
  font-size: 0.72rem; color: var(--text-dim);
}
@media (max-width: 820px) {
  .conn-channel-head { align-items: flex-start; }
  .conn-dest { flex-direction: column; align-items: flex-start; }
  .confirm-dialog .confirm-actions { flex-direction: column-reverse; }
  .confirm-dialog .confirm-actions .btn { width: 100%; }
}
"""

CONNECTIONS_SCRIPT = r"""
const statusRegion = document.getElementById('conexoes-status');
function announce(message, kind) {
  if (!statusRegion) return;
  statusRegion.textContent = message;
  if (kind) { statusRegion.dataset.kind = kind; } else { statusRegion.removeAttribute('data-kind'); }
}

async function postJson(url, method, body) {
  const response = await fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null
  });
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  return { ok: response.ok, status: response.status, data: data };
}

function detailOf(data, fallback) {
  return (data && typeof data.detail === 'string') ? data.detail : fallback;
}

const dialog = document.getElementById('confirm-dialog');
const dialogMessage = document.getElementById('confirm-message');
const dialogOk = document.getElementById('confirm-ok');
let pendingAction = null;

function askConfirm(options, action) {
  if (!dialog) { return; }  // sem suporte a <dialog>: nunca destrói num clique acidental
  pendingAction = action;
  if (dialogMessage) dialogMessage.textContent = options.message;
  if (dialogOk) dialogOk.textContent = options.confirmLabel || 'Confirmar';
  dialog.returnValue = '';
  dialog.showModal();
}

if (dialog) {
  dialog.addEventListener('close', () => {
    const choice = dialog.returnValue;
    dialog.returnValue = '';
    const run = pendingAction;
    pendingAction = null;
    if (choice === 'confirm' && run) { run(); }
  });
}

document.querySelectorAll('[data-connect]').forEach((button) => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    announce('Iniciando a autorização no Google…');
    try {
      const result = await postJson('/studio/connections/oauth/start', 'POST');
      if (result.ok && result.data.authorization_url) {
        window.location.assign(result.data.authorization_url);
        return;
      }
      announce('Não foi possível iniciar a conexão: ' + detailOf(result.data, 'tente novamente.'), 'bad');
    } catch (error) {
      announce('Falha de rede ao iniciar a conexão. Tente novamente.', 'bad');
    }
    button.disabled = false;
  });
});

document.querySelectorAll('[data-link]').forEach((button) => {
  button.addEventListener('click', () => {
    const youtubeId = button.getAttribute('data-youtube');
    const select = document.getElementById('sel-' + youtubeId);
    const profileId = select ? select.value : '';
    if (!profileId) {
      announce('Escolha o canal do estúdio antes de vincular.', 'bad');
      if (select) select.focus();
      return;
    }
    const option = select.selectedOptions && select.selectedOptions[0];
    const version = Number((option && option.getAttribute('data-version')) || '0');
    const name = (option && option.getAttribute('data-name')) || 'o canal do estúdio';
    askConfirm({
      message: 'Vincular "' + name + '" a este canal do YouTube? O canal do estúdio passa a publicar aqui.',
      confirmLabel: 'Vincular'
    }, async () => {
      announce('Vinculando…');
      try {
        const result = await postJson('/studio/channels/' + encodeURIComponent(profileId), 'PATCH',
          { expected_version: version, changes: { youtube_channel_id: youtubeId } });
        if (result.ok) {
          announce('Vinculado. Atualizando…', 'ok');
          setTimeout(() => window.location.reload(), 600);
        } else if (result.status === 409) {
          announce('Outra alteração venceu a corrida: recarregue a página e tente de novo.', 'bad');
        } else {
          announce('Não foi possível vincular: ' + detailOf(result.data, 'tente novamente.'), 'bad');
        }
      } catch (error) {
        announce('Falha de rede ao vincular. Tente novamente.', 'bad');
      }
    });
  });
});

document.querySelectorAll('[data-unlink]').forEach((button) => {
  button.addEventListener('click', () => {
    const profileId = button.getAttribute('data-profile');
    const name = button.getAttribute('data-name') || 'este canal do estúdio';
    const version = Number(button.getAttribute('data-version') || '0');
    askConfirm({
      message: 'Desvincular "' + name + '" deste canal do YouTube? O canal do estúdio deixa de publicar aqui. '
        + 'Nada é apagado no YouTube.',
      confirmLabel: 'Desvincular'
    }, async () => {
      announce('Desvinculando…');
      try {
        const result = await postJson('/studio/channels/' + encodeURIComponent(profileId), 'PATCH',
          { expected_version: version, changes: { youtube_channel_id: null } });
        if (result.ok) {
          announce('Desvinculado. Atualizando…', 'ok');
          setTimeout(() => window.location.reload(), 600);
        } else if (result.status === 409) {
          announce('Outra alteração venceu a corrida: recarregue a página e tente de novo.', 'bad');
        } else {
          announce('Não foi possível desvincular: ' + detailOf(result.data, 'tente novamente.'), 'bad');
        }
      } catch (error) {
        announce('Falha de rede ao desvincular. Tente novamente.', 'bad');
      }
    });
  });
});

document.querySelectorAll('[data-revoke]').forEach((button) => {
  button.addEventListener('click', () => {
    const grantId = button.getAttribute('data-grant');
    const youtubeId = button.getAttribute('data-youtube');
    const title = button.getAttribute('data-title') || 'este canal';
    askConfirm({
      message: 'Revogar a autorização de "' + title + '"? Este canal deixa de publicar e a autorização '
        + 'perde os tokens. As outras autorizações desta conta não são afetadas.',
      confirmLabel: 'Revogar'
    }, async () => {
      announce('Revogando…');
      try {
        const result = await postJson('/studio/connections/authorizations/'
          + encodeURIComponent(grantId) + '/' + encodeURIComponent(youtubeId) + '/revoke', 'POST');
        if (result.ok) {
          announce('Autorização revogada. Atualizando…', 'ok');
          setTimeout(() => window.location.reload(), 600);
        } else {
          announce('Não foi possível revogar: ' + detailOf(result.data, 'tente novamente.'), 'bad');
        }
      } catch (error) {
        announce('Falha de rede ao revogar. Tente novamente.', 'bad');
      }
    });
  });
});

// Retorno do Google/OAuth: a própria página trata o resultado (via query string) e conclui o
// consentimento pela API. Nenhum `code`/`state` é renderizado no HTML do servidor.
const params = new URLSearchParams(window.location.search);
const providerError = params.get('error') || params.get('erro');
const code = params.get('code');
const state = params.get('state');
const connected = params.get('conectado');

if (providerError) {
  announce('O Google não autorizou o acesso (' + providerError + '). Nenhum canal foi associado.', 'bad');
} else if (code && state) {
  (async () => {
    announce('Concluindo a autorização…');
    try {
      const result = await postJson('/studio/connections/oauth/callback', 'POST', { code: code, state: state });
      if (result.ok && result.data.channel) {
        window.location.replace('/studio/panel/conexoes?conectado='
          + encodeURIComponent(result.data.channel.youtube_channel_id));
        return;
      }
      announce('Não foi possível concluir a autorização: '
        + detailOf(result.data, 'a conexão precisa ser refeita.'), 'bad');
    } catch (error) {
      announce('Falha de rede ao concluir a autorização. Refaça a conexão.', 'bad');
    }
  })();
} else if (connected) {
  announce('Conta conectada. Confira o canal abaixo e confirme antes de vincular.', 'ok');
  const block = document.querySelector('[data-confirm-block="' + CSS.escape(connected) + '"]');
  if (block) { block.open = true; block.scrollIntoView({ block: 'start' }); }
}
"""


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------


def _status_badge(status: str) -> str:
    kind, icon, label = _STATUS.get(str(status).upper(), ("idle", "·", "Status não informado"))
    return (
        f'<span class="state s-{kind}" data-state="{kind}">'
        f'<span class="state-icon" aria-hidden="true">{icon}</span> <span>{e(label)}</span></span>'
    )


def _when(value: str | None) -> str:
    """Data ISO do canal como leitura curta; sem valor, diz que não há — nunca inventa."""
    if not value:
        return "validade não informada"
    text = str(value).replace("T", " ")
    return f"expira em {e(text[:16])} UTC" if len(text) >= 16 else f"expira em {e(text)}"


def _studio_options(profiles: list[ChannelProfile]) -> str:
    """Opções do `<select>`: todos os canais do estúdio, com o destino atual declarado."""
    options = []
    for profile in profiles:
        destination = (f"publica em {profile.youtube_channel_id}" if profile.youtube_channel_id
                       else "sem destino")
        archived = " (arquivado)" if profile.archived else ""
        label = f"{profile.name}{archived} — {destination}"
        options.append(
            f'<option value="{e(profile.id)}" data-version="{profile.version}" data-name="{e(profile.name)}">'
            f"{e(label)}</option>"
        )
    return "".join(options)


def _studio_destinations(channel: dict, profiles_by_id: dict[str, ChannelProfile]) -> str:
    """Quem publica neste canal do YouTube, com o controle de desvincular ao lado."""
    refs = channel.get("studio_channels") or []
    if not refs:
        return '<p class="conn-meta">Nenhum canal do estúdio publica aqui ainda.</p>'
    items = []
    for ref in refs:
        profile = profiles_by_id.get(ref.get("id"))
        version = profile.version if profile is not None else 0
        archived = " (arquivado)" if ref.get("archived") else ""
        items.append(
            f'<li class="conn-dest">'
            f'<span>{e(ref.get("name"))}{e(archived)}</span>'
            f'<button class="btn btn-sm btn-danger" type="button" data-unlink data-profile="{e(ref.get("id"))}" '
            f'data-name="{e(ref.get("name"))}" data-version="{version}">Desvincular</button>'
            f"</li>"
        )
    return (
        '<p class="conn-meta">Publica em:</p>'
        f'<ul class="conn-dests">{"".join(items)}</ul>'
    )


def _channel_block(channel: dict, profiles: list[ChannelProfile],
                   profiles_by_id: dict[str, ChannelProfile]) -> str:
    youtube_id = str(channel.get("youtube_channel_id") or "")
    title = str(channel.get("title") or youtube_id or "Canal sem nome")
    grant_id = str(channel.get("grant_id") or "")
    options = _studio_options(profiles)
    select_label = f"Canal do estúdio que publica em {title}"
    return f"""
      <section class="conn-channel" aria-labelledby="canal-{e(youtube_id)}">
        <div class="conn-channel-head">
          <span class="conn-name" id="canal-{e(youtube_id)}">{e(title)}</span>
          <span class="conn-id">{e(youtube_id)}</span>
          {_status_badge(channel.get("status"))}
        </div>
        <p class="conn-meta">{e(_when(channel.get("token_expires_at")))}</p>
        {_studio_destinations(channel, profiles_by_id)}
        <div class="conn-channel-actions">
          <button class="btn btn-sm btn-danger" type="button" data-revoke data-grant="{e(grant_id)}"
                  data-youtube="{e(youtube_id)}" data-title="{e(title)}">Revogar autorização</button>
        </div>
        <details class="conn-link" id="link-{e(youtube_id)}" data-confirm-block="{e(youtube_id)}">
          <summary class="btn btn-sm btn-ghost">Vincular um canal do estúdio</summary>
          <div class="conn-link-body">
            <p class="conn-confirm">
              Confira o destino antes de vincular — este é o canal do YouTube que vai receber as publicações:
              <b>{e(title)}</b> <code>{e(youtube_id)}</code>.
            </p>
            <div class="field">
              <label for="sel-{e(youtube_id)}">{e(select_label)}</label>
              <select id="sel-{e(youtube_id)}" data-link-select aria-describedby="sel-{e(youtube_id)}-hint">
                <option value="">Escolha um canal do estúdio…</option>
                {options}
              </select>
              <span class="hint" id="sel-{e(youtube_id)}-hint">O canal do estúdio passa a publicar no canal do YouTube confirmado acima.</span>
            </div>
            <div class="spread">
              <button class="btn btn-primary" type="button" data-link data-youtube="{e(youtube_id)}">Confirmar e vincular</button>
            </div>
          </div>
        </details>
      </section>
    """


def _account_card(account: dict, profiles: list[ChannelProfile],
                  profiles_by_id: dict[str, ChannelProfile]) -> str:
    email = str(account.get("email") or "")
    display_name = str(account.get("display_name") or "").strip()
    heading = display_name or email or "Conta sem e-mail"
    channels = account.get("channels") or []
    if channels:
        body = "".join(_channel_block(channel, profiles, profiles_by_id) for channel in channels)
    else:
        body = ('<p class="conn-meta">Nenhum canal autorizado nesta conta ainda. '
                'Conecte de novo para autorizar um canal.</p>')
    secondary = f'<span class="conn-id">{e(email)}</span>' if (display_name and email) else ""
    return f"""
      <section class="conn-account" aria-labelledby="conta-{e(account.get('id'))}">
        <div class="conn-account-head">
          <h3 class="conn-email" id="conta-{e(account.get('id'))}">{e(heading)}</h3>
          {secondary}
          <span class="conn-source">{len(channels)} canal(is)</span>
        </div>
        {body}
      </section>
    """


def _scopes_card() -> str:
    rows = "".join(
        f"<li><code>{e(scope)}</code> — {e(purpose)}</li>" for scope, purpose in _SCOPES_EXPLAINED
    )
    return f"""
      <div class="card">
        <h2>O que será pedido</h2>
        <p class="muted" style="font-size:0.85rem">
          Ao conectar uma conta do Google, o Studio pede permissão para:
        </p>
        <ul class="conn-scopes">{rows}</ul>
        <p class="fine">Os tokens ficam no cofre do servidor. Nenhum valor de credencial é exibido nesta página.</p>
      </div>
    """


def _empty_card() -> str:
    return """
      <div class="card empty" id="conexoes-vazio">
        <h2>Nenhuma conta conectada</h2>
        <p class="muted">Conecte uma conta do Google para autorizar os canais do YouTube em que o estúdio publica.</p>
        <p class="fine">Cada canal do YouTube precisa da própria autorização. Conectar uma conta não publica nada
        sozinho: o canal só entra no ar quando você vincular um canal do estúdio a ele.</p>
      </div>
    """


def _accounts_card(accounts: list[dict], profiles: list[ChannelProfile],
                   profiles_by_id: dict[str, ChannelProfile]) -> str:
    body = "".join(_account_card(account, profiles, profiles_by_id) for account in accounts)
    return f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>Contas e canais</h2>
            <p class="dim" style="margin:4px 0 0;font-size:12.5px">
              A conta agrupa; cada canal tem a própria autorização e o próprio status. Reconectar um canal
              não toca nas autorizações dos outros.
            </p>
          </div>
          <span class="chip-metric">{len(accounts)} conta(s)</span>
        </div>
        <div style="margin-top:14px">{body}</div>
      </div>
    """


def _confirm_dialog() -> str:
    return """
      <dialog id="confirm-dialog" class="confirm-dialog" aria-labelledby="confirm-title">
        <div class="confirm-dialog-body">
          <h2 id="confirm-title">Confirmar ação</h2>
          <p id="confirm-message"></p>
          <form method="dialog" class="confirm-actions">
            <button value="cancel" class="btn" autofocus>Cancelar</button>
            <button value="confirm" class="btn btn-danger" id="confirm-ok">Confirmar</button>
          </form>
        </div>
      </dialog>
    """


def _rail(accounts: list[dict], profiles: list[ChannelProfile]) -> str:
    channels = sum(len(account.get("channels") or []) for account in accounts)
    with_destination = sum(1 for profile in profiles if profile.youtube_channel_id)
    return f"""
      <aside class="rail" aria-label="Resumo">
        <section class="card" aria-labelledby="h-conexoes">
          <h2 id="h-conexoes">As conexões</h2>
          <div class="kv"><span>Contas conectadas</span><span>{len(accounts)}</span></div>
          <div class="kv"><span>Canais autorizados</span><span>{channels}</span></div>
          <div class="kv"><span>Canais do estúdio com destino</span><span>{with_destination}</span></div>
          <p class="fine">O status de cada canal vem da credencial real no cofre e do vínculo validado — nunca
          de um campo digitado.</p>
        </section>
        <section class="card" aria-labelledby="h-isolada">
          <h2 id="h-isolada">Reconexão isolada</h2>
          <p class="fine">Revogar ou reconectar um canal não mexe nas autorizações dos outros. Se a mesma
          autorização servir dois canais, revogar um não derruba o outro.</p>
        </section>
      </aside>
    """


def _sidebar_card(accounts: list[dict]) -> str:
    channels = sum(len(account.get("channels") or []) for account in accounts)
    return f"""
        <div class="side-card">
          <h2>Contas do YouTube</h2>
          <div class="kv"><span>Contas</span><span>{len(accounts)}</span></div>
          <div class="kv"><span>Canais</span><span>{channels}</span></div>
        </div>
    """


def render_connections(board: dict, profiles: list[ChannelProfile]) -> tuple[str, dict[str, str]]:
    """Página de Conexões: casca aprovada + conta → canais real + conectar/confirmar/revogar."""
    nonce = secrets.token_urlsafe(16)
    accounts = list(board.get("accounts") or [])
    profiles = list(profiles or [])
    profiles_by_id = {profile.id: profile for profile in profiles}
    body = _accounts_card(accounts, profiles, profiles_by_id) if accounts else _empty_card()
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark light">
  <title>Faceless Studio — Conexões</title>
  <style nonce="{nonce}">{shell.CSS}{CONNECTIONS_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#conexoes-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="conexoes", base_href="/studio/panel", side_card_html=_sidebar_card(accounts), channels_href="/studio/canais", nonce=nonce)}
    <main class="main-content" id="conexoes-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="conexoes-heading">Conexões</h1>
            <p class="page-goal" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem">
              Ação primária: <b>conectar a conta e escolher o canal</b>. Confirme o canal do YouTube antes de
              vincular — errar de canal custa segundos para evitar e horas para consertar.
            </p>
          </div>
          <span class="screen-no dim">Configuração · Conexões</span>
        </div>
        <div class="conn-actions conn-note">
          <button class="btn btn-primary" type="button" data-connect>Conectar conta Google</button>
          <span class="dim" style="font-size:0.82rem">Adiciona uma conta (ou mais canais de uma conta que já existe).</span>
        </div>
      </div>
      <div class="conn-status" id="conexoes-status" role="status" aria-live="polite"></div>
      {body}
      {_scopes_card()}
      {_confirm_dialog()}
    </main>
    {_rail(accounts, profiles)}
  </div>
  <script nonce="{nonce}">{CONNECTIONS_SCRIPT}</script>
</body>
</html>"""
    return page, shell._headers(nonce)
