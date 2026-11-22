"""Tela Avançado (F02.T03): diagnóstico honesto do Estúdio, sem segredos e sem ação destrutiva.

É a sétima área de Configurações. Mostra só o que existe de verdade: a saúde do banco (o mesmo
`ping` da aplicação), o catálogo de providers com a disponibilidade medida e a configuração
efetiva do canal ativo (specs por tarefa, nunca chaves). Nenhum controle simula suporte: o que
não é editável aqui aparece como texto.

Não cria serviço novo: recebe um view model pronto da camada de aplicação/composição.
"""

from __future__ import annotations

import secrets
from html import escape as e

from . import panel as legacy
from . import shell_v3


# A view model vem da aplicação (`BuildAdvancedView`): a API só desenha.
from ..application.advanced_page import AdvancedPageView

AdvancedView = AdvancedPageView


def render_advanced(view: AdvancedView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.selected_project_id

    saude = ("Banco de dados: respondendo." if view.database_ok
             else "Banco de dados: sem resposta agora. As telas de dados ficam indisponíveis até voltar.")
    saude_cls = "ok" if view.database_ok else "erro"

    prov_rows = "".join(
        f"<tr><td>{e(p.kind)}</td><td>{e(p.name)}</td><td>{e(p.availability)}</td>"
        f"<td>{e(p.cost)}</td><td>{e(p.quality)}</td></tr>"
        for p in view.providers) or (
        '<tr><td colspan="5">Nenhum provider no catálogo desta instalação.</td></tr>')

    efetivas = "".join(
        f"<tr><th scope=\"row\">{e(kind)}</th><td>{e(spec)}</td></tr>"
        for kind, spec in view.effective) or (
        '<tr><td colspan="2">Nenhum canal ativo para resolver a configuração.</td></tr>')

    notas = "".join(f'<li>{e(note)}</li>' for note in view.notes)
    notas_bloco = f'<ul class="lista-avancado">{notas}</ul>' if notas else ""

    content = f"""
        <div class="card">
          <div class="spread">
            <div>
              <h2>Diagnóstico do Estúdio</h2>
              <p class="micro" style="margin:0">O que está ligado agora — sem chaves, sem tokens
              e sem botão que possa estragar a operação.</p>
            </div>
            <span class="selo">SOMENTE LEITURA</span>
          </div>
        </div>

        <div class="card">
          <h2>Saúde</h2>
          <p class="aviso" id="saude-banco" data-tipo="{saude_cls}" role="status">{e(saude)}</p>
          {notas_bloco}
        </div>

        <div class="card">
          <h2>Configuração efetiva do canal</h2>
          <p class="micro">O que a produção vai usar para este canal. A chave do provider nunca
            aparece aqui — só o nome e o modelo.</p>
          <table class="tabela-kv">
            <caption class="sr-only">Configuração efetiva por tarefa</caption>
            {efetivas}
          </table>
        </div>

        <div class="card">
          <h2>Providers disponíveis</h2>
          <p class="micro">Disponibilidade medida na composição, não presumida.</p>
          <table class="tabela">
            <caption class="sr-only">Catálogo de providers</caption>
            <thead><tr><th scope="col">Tarefa</th><th scope="col">Provider</th>
              <th scope="col">Disponibilidade</th><th scope="col">Custo</th>
              <th scope="col">Qualidade</th></tr></thead>
            <tbody>{prov_rows}</tbody>
          </table>
        </div>"""

    body = shell_v3.render_settings_page_body(
        active_section="avancado",
        section_title="Avançado",
        content_html=content,
        project_id=project_id or "",
    )

    html = shell_v3.render_document(
        title="Faceless Studio — Avançado",
        active="configuracoes",
        crumb="Avançado",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=project_id,
        cost_note="",
    )
    return html, legacy._headers(nonce)