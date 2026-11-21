"""Página de retorno do consentimento OAuth do Google (F8-05 + ligação L1).

O Google redireciona para o `redirect_uri` configurado (`/studio/oauth/callback` por padrão) com
`?code=...&state=...`. A página só conhece o `state`, que carrega o id do projeto; ela então chama
`POST /studio/projects/{project_id}/youtube-oauth/callback` para trocar o código pelo canal
associado e mostra o resultado. Nenhum token, client secret ou código de autorização é renderizado
no HTML do servidor: o `code` e o `state` são lidos da própria URL pelo browser.
"""
from __future__ import annotations

import html
import secrets

from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

CALLBACK_CSS = """
.callback-card { max-width: 640px; }
.callback-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 1rem; align-items: center; }
.callback-feedback { font-size: 0.9rem; line-height: 1.5; }
.callback-feedback a { color: var(--info); }
"""


def _side_card() -> str:
    return (
        '<div class="side-card"><h2>O que acontece aqui</h2>'
        '<p>O Google devolve o código de autorização para esta página. O servidor troca o código '
        'pelo canal associado e guarda os tokens no secret store. Nenhum segredo volta ao browser.</p>'
        "</div>"
    )


def _page_shell(nonce: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark light">
  <title>Faceless Studio — Consentimento do YouTube</title>
  <style nonce="{nonce}">{shell.CSS}{CALLBACK_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#oauth-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="canais", channels_href="/studio/canais", side_card_html=_side_card(), nonce=nonce)}
    <main class="main-content" id="oauth-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="oauth-heading">Consentimento do YouTube</h1>
            <p class="page-goal" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem">
              Conclusão do retorno do Google ao Studio.
            </p>
          </div>
          <span class="screen-no dim">Configuração · Canais</span>
        </div>
      </div>
      {body}
    </main>
  </div>
</body>
</html>"""


def _back_link(project_id: str | None) -> str:
    href = "/studio/canais" + (f"?project_id={e(project_id)}" if project_id else "")
    return f'<a class="btn btn-primary" href="{href}">Voltar para Canais</a>'


def render_oauth_callback(project_id: str | None, *, provider_error: str | None = None,
                          ) -> tuple[str, dict[str, str]]:
    """Página de callback: conclui a autorização quando há projeto reconhecido.

    `provider_error` é o `error` devolvido pelo Google (ex.: `access_denied`). Ele é renderizado
    pelo servidor, então a recusa é honesta mesmo sem JavaScript. Sem projeto reconhecido, a página
    explica que a conexão precisa ser refeita a partir da tela de Canais — sem beco sem saída.
    """
    nonce = secrets.token_urlsafe(16)
    if project_id is None:
        body = f"""
      <div class="card callback-card" role="alert">
        <h2>Não foi possível identificar o canal deste consentimento</h2>
        <p class="callback-feedback">O retorno do Google trouxe um <code>state</code> que não corresponde a
        nenhum consentimento iniciado pelo Studio. Nada foi associado. Refaça a conexão a partir da tela
        de Canais.</p>
        <div class="callback-actions">{_back_link(None)}</div>
      </div>"""
        return _page_shell(nonce, body), shell._headers(nonce)

    if provider_error:
        body = f"""
      <div class="card callback-card" role="alert">
        <h2>O Google não autorizou o acesso</h2>
        <p class="callback-feedback">O consentimento foi recusado ou interrompido no Google
        (<code>{e(provider_error)}</code>). Nenhum canal foi associado e nenhum token foi guardado.
        Você pode tentar de novo quando quiser.</p>
        <div class="callback-actions">{_back_link(project_id)}</div>
      </div>"""
        return _page_shell(nonce, body), shell._headers(nonce)

    complete_path = f"/studio/projects/{project_id}/youtube-oauth/callback"
    back_href = f"/studio/canais?project_id={e(project_id)}"
    body = f"""
      <div class="card callback-card" id="oauth-complete" data-complete-path="{e(complete_path)}"
           data-project-id="{e(project_id)}" data-back-href="{back_href}">
        <h2>Concluindo a autorização</h2>
        <p class="callback-feedback" id="oauth-feedback" role="status" aria-live="polite">
          Trocando o código de autorização pelo canal associado&hellip;
        </p>
        <div class="callback-actions">{_back_link(project_id)}</div>
        <p class="fine">Os tokens ficam no secret store do servidor. Nenhum valor de credencial
        (access token, refresh token ou client secret) é exibido nesta página.</p>
      </div>
      <script nonce="{nonce}">
        const card = document.getElementById('oauth-complete');
        const feedback = document.getElementById('oauth-feedback');
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code') || '';
        const state = params.get('state') || '';
        const providerError = params.get('error') || '';
        if (providerError) {{
          if (feedback) feedback.textContent = 'O Google recusou a autorização (' + providerError
            + '). Nenhum canal foi associado.';
        }} else if (!code || !state) {{
          if (feedback) feedback.textContent = 'A resposta do Google não trouxe código e estado. '
            + 'Nenhum canal foi associado; repita a conexão em Canais.';
        }} else {{
          fetch(card.getAttribute('data-complete-path'), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ code: code, state: state }})
          }}).then(async (response) => {{
            const data = await response.json().catch(() => ({{}}));
            if (response.ok) {{
              const title = (data && data.title) ? data.title : 'canal do YouTube';
              if (feedback) feedback.textContent = 'Canal associado: ' + title
                + '. Redirecionando para Canais...';
              setTimeout(() => {{ window.location.href = card.getAttribute('data-back-href'); }}, 1200);
            }} else {{
              const detail = (data && typeof data.detail === 'string')
                ? data.detail : 'o servidor recusou a troca do código.';
              if (feedback) feedback.textContent = 'Não foi possível concluir: ' + detail
                + ' Nenhum canal foi associado.';
            }}
          }}).catch(() => {{
            if (feedback) feedback.textContent = 'Falha de rede ao concluir a autorização. '
              + 'Nenhum canal foi associado; tente de novo em Canais.';
          }});
        }}
      </script>"""
    return _page_shell(nonce, body), shell._headers(nonce)