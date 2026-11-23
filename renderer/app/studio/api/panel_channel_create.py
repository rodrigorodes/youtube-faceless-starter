"""Progressive channel form, using the existing transactional channel endpoint."""
import secrets
from html import escape as e

from . import panel_channels, panel_shell, shell_v3


def field(key, label, *, value="", kind="text", extra=""):
    return (f'<div class="field"><label for="novo-canal-{key}">{label}</label>'
            f'<input id="novo-canal-{key}" type="{kind}" value="{e(str(value))}" {extra}></div>')


def select(key, label, options):
    return (f'<div class="field"><label for="novo-canal-{key}">{label}</label>'
            f'<select id="novo-canal-{key}">'
            + "".join(f'<option value="{e(value)}">{e(text)}</option>' for value, text in options)
            + '</select></div>')


def render_channel_create(view):
    nonce = secrets.token_urlsafe(16)
    project_id = view.project.id if view.project else ""
    styles = [("", "Padrão do estúdio")] + [(style.id, style.name) for style in view.styles]
    body = f"""
    <section id="pagina-criar-canal">
      <div class="head"><div><p class="eyebrow">Canais / Novo canal</p><h1>Criar canal</h1>
        <p class="sub">Comece com o essencial. Todos os ajustes continuam disponíveis quando precisar.</p>
      </div><a class="btn ghost small" href="/studio/configuracoes/canais">Cancelar</a></div>
      <form id="new-channel-form">
        <div class="grid2">
          <div class="card"><h3 style="margin-bottom:12px">Quem é este canal?</h3>
            {field("nome", "Nome do canal *", extra='required maxlength="120" placeholder="Ex.: Curiosidades Históricas"')}
            {field("nicho", "Nicho editorial", extra='maxlength="200" placeholder="Ex.: História e mistérios"')}
            {select("idioma", "Idioma", [("pt-BR", "Português (BR)"), ("en-US", "English"), ("es-ES", "Español")])}
            {field("publico", "Público", extra='maxlength="500" placeholder="Ex.: curiosos por história e mistérios"')}
          </div>
          <div class="card"><h3>Como isso é usado</h3>
            <p class="sub" style="margin-top:6px">O nome identifica o canal no menu. Nicho, idioma e público orientam o roteiro, as sugestões de tendência e o tom do texto.</p>
            <div class="note info" style="margin-top:14px">Só o nome é obrigatório. O resto pode ser ajustado depois em Configurações.</div>
          </div>
        </div>
        <div class="card" style="margin-top:16px"><h3>Predefinição do canal</h3>
          <div style="margin-top:12px">{select("estilo", "Estilo visual", styles)}</div>
          <p class="sub">Voz padrão do estúdio · Equilibrado · Piloto automático</p>
        </div>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Estratégia</summary>
          <div class="grid2" style="margin-top:16px"><div class="card"><h3>Linha editorial</h3>
            {field("estrategia", "Estratégia", extra='maxlength="500"')}
            {field("pilares", "Pilares editoriais (separados por vírgula)", extra='maxlength="600"')}
            {field("narrativa", "Estilo narrativo", extra='maxlength="4000"')}
            {field("cta", "Chamada para ação padrão", extra='maxlength="500"')}
            {field("duracao", "Duração padrão (segundos)", value=60, kind="number", extra='min="1" max="36000"')}
          </div><div class="card"><h3>Pilares viram ideias</h3><p class="sub">Os pilares orientam a estratégia editorial do canal.</p></div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Visual e voz</summary>
          <div class="grid2" style="margin-top:16px"><div class="card">
            {select("formato", "Formato padrão", [("short", "Short · 9:16"), ("long", "Vídeo · 16:9")])}
            {select("modo", "Modo padrão de criação", [("piloto", "Piloto automático"), ("diretor", "Modo Diretor")])}
          </div><div class="card"><p class="sub">Voz e legendas podem ser personalizadas em Marca e estilo após criar o canal.</p></div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Produção</summary>
          <div class="grid2" style="margin-top:16px"><div class="card">
            {select("perfil-economico", "Perfil de produção", [("BALANCED", "Equilibrado"), ("FRUGAL", "Econômico"), ("PREMIUM", "Premium")])}
          </div><div class="card"><h3>Limites e saída</h3>
            {field("teto-mensal", "Teto mensal (US$)", value=100, kind="number", extra='min="0" step="0.01"')}
            {field("teto-video", "Teto por vídeo (US$)", value=10, kind="number", extra='min="0" step="0.01"')}
          </div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Providers e YouTube</summary>
          <div class="grid2" style="margin-top:16px"><div class="card"><h3>Providers do canal</h3>
            <p class="sub">O roteamento usa o perfil de produção. Disponibilidade e conexões podem ser verificadas depois de criar o canal.</p>
          </div><div class="card"><h3>Canal do YouTube</h3><p class="sub">Conectar o YouTube é opcional agora; necessário só para publicar.</p></div></div>
        </details>
        <div class="between" style="margin-top:20px"><p class="sub">Criar o canal não gera vídeos nem cobra nada. YouTube é opcional agora.</p>
          <button class="btn primary" type="submit" id="btn-criar-canal">✦ Criar canal</button></div>
        <p id="new-channel-feedback" class="feedback" role="status"></p>
      </form>
    </section>"""
    html = shell_v3.render_document(title="Faceless Studio — Criar canal", active="configuracoes",
        crumb="Criar canal", body_html=body, nonce=nonce, projects=list(view.projects),
        project_id=project_id, page_js=panel_channels._channels_page_js(project_id))
    return html, panel_shell._headers(nonce)
