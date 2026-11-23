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


_PERFIS = (("ECONOMY", "⚡ Econômico", "Prioriza custo conhecido. Rápido e simples.", "Econômico"),
           ("BALANCED", "⚖ Equilibrado", "Equilibra custo e qualidade elegível.", "Equilibrado"),
           ("PREMIUM", "💎 Premium", "Prioriza qualidade. Exige providers de alta qualidade.", "Premium"))

_WIZARD_JS = """
(function () {
  var form = document.getElementById('new-channel-form');
  if (!form) return;
  var hid = function (id) { return document.getElementById(id); };
  var estado = { estilo: '', formato: 'short', modo: 'piloto', perfil: 'ECONOMY' };
  var ROT = { piloto: 'Piloto automático', diretor: 'Modo Diretor', ECONOMY: 'Econômico', BALANCED: 'Equilibrado', PREMIUM: 'Premium' };
  function marcar(grupo, valor) {
    estado[grupo] = valor;
    form.querySelectorAll('[data-wset="' + grupo + '"]').forEach(function (el) {
      var on = el.getAttribute('data-v') === valor;
      if (el.classList.contains('btn')) { el.classList.toggle('primary', on); }
      el.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var alvo = { estilo: 'novo-canal-estilo', formato: 'novo-canal-formato', modo: 'novo-canal-modo', perfil: 'novo-canal-perfil-economico' }[grupo];
    if (hid(alvo)) hid(alvo).value = valor;
    var resumo = hid('wiz-resumo');
    if (resumo) resumo.textContent = 'Voz padrão do estúdio · ' + ROT[estado.perfil] + ' · ' + ROT[estado.modo];
    var rp = hid('wiz-perfil-rotulo');
    if (rp) rp.textContent = ROT[estado.perfil];
  }
  form.addEventListener('click', function (ev) {
    var el = ev.target.closest ? ev.target.closest('[data-wset]') : null;
    if (!el) return;
    ev.preventDefault();
    marcar(el.getAttribute('data-wset'), el.getAttribute('data-v'));
  });
  form.querySelectorAll('input[type=range][data-out]').forEach(function (r) {
    var saida = hid(r.getAttribute('data-out'));
    var fmt = function () {
      var v = Number(r.value);
      var txt = r.getAttribute('data-pre') ? r.getAttribute('data-pre') + (r.step && r.step.indexOf('.') >= 0 ? v.toFixed(2).replace('.', ',') : v) : v + (r.getAttribute('data-suf') || '');
      if (saida) saida.textContent = txt;
    };
    r.addEventListener('input', fmt);
  });
  var pil = hid('novo-canal-pilares');
  if (pil) pil.addEventListener('input', function () {
    var caixa = hid('wiz-pilares');
    if (!caixa) return;
    var itens = pil.value.split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    caixa.textContent = '';
    if (!itens.length) { var vazio = document.createElement('span'); vazio.className = 'sample'; vazio.textContent = 'Nenhum pilar ainda.'; caixa.appendChild(vazio); return; }
    itens.forEach(function (t) { var p = document.createElement('span'); p.className = 'pill accent'; p.textContent = t; caixa.appendChild(p); });
  });
})();
"""


def _seg(grupo, opcoes, atual):
    botoes = "".join(f'<button type="button" aria-pressed="{"true" if v == atual else "false"}" data-wset="{grupo}" data-v="{v}">{e(t)}</button>'
                     for v, t in opcoes)
    return f'<div class="seg" role="group">{botoes}</div>'


def _hidden(key, value):
    return f'<input type="hidden" id="novo-canal-{key}" value="{e(value)}">'


def render_channel_create(view):
    nonce = secrets.token_urlsafe(16)
    project_id = view.project.id if view.project else ""
    styles = [("", "Padrão do estúdio", "")] + [(style.id, style.name, style) for style in view.styles]
    chips = "".join(
        f'<button type="button" class="btn {"primary " if not sid else ""}small" aria-pressed="{"true" if not sid else "false"}" '
        f'data-wset="estilo" data-v="{e(sid)}">{e(nome)}</button>' for sid, nome, _ in styles)
    galeria = "".join(
        f'<button type="button" class="choice" aria-pressed="{"true" if not sid else "false"}" data-wset="estilo" data-v="{e(sid)}">'
        f'<div class="thumb" style="height:60px;background:linear-gradient(135deg,#2b2540,#15171c);margin-bottom:8px"><span style="font-size:24px">🎨</span></div>'
        f'<b style="font-size:12.5px">{e(nome)}</b></button>' for sid, nome, _ in styles)
    perfis = "".join(
        f'<button type="button" class="choice" aria-pressed="{"true" if v == "ECONOMY" else "false"}" data-wset="perfil" data-v="{v}">'
        f'<b>{t}</b><p class="sub">{d}</p></button>' for v, t, d, _ in _PERFIS)
    body = f"""
    <section id="pagina-criar-canal">
      <div class="head"><div><p class="eyebrow">Canais / Novo canal</p><h1>Criar canal</h1>
        <p class="sub">Comece com o essencial. Todos os ajustes continuam disponíveis quando precisar.</p>
      </div><a class="btn ghost small" href="/studio/configuracoes/canais">Cancelar</a></div>
      <form id="new-channel-form">
        {_hidden("estilo", "")}{_hidden("formato", "short")}{_hidden("modo", "piloto")}{_hidden("perfil-economico", "ECONOMY")}
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
          <div class="row" style="margin-top:12px">{chips}</div>
          <p class="sub" id="wiz-resumo" style="margin-top:12px">Voz padrão do estúdio · Econômico · Piloto automático</p>
        </div>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Estratégia</summary>
          <div class="grid2" style="margin-top:16px"><div class="card"><h3 style="margin-bottom:12px">Linha editorial</h3>
            <div class="field"><label for="novo-canal-estrategia">Estratégia</label><textarea id="novo-canal-estrategia" rows="3" maxlength="500" placeholder="O que o canal entrega e como se diferencia"></textarea></div>
            {field("pilares", "Pilares editoriais (separados por vírgula)", extra='maxlength="600" placeholder="Ex.: História, Mistérios, Arqueologia"')}
            {field("narrativa", "Estilo narrativo", extra='maxlength="4000" placeholder="Ex.: Didático e envolvente"')}
            {field("cta", "Chamada para ação padrão", extra='maxlength="500" placeholder="Ex.: Qual tema você quer ver no próximo vídeo?"')}
            <div class="field"><label for="novo-canal-duracao">Duração padrão: <b id="w9v">45 s</b></label><input type="range" id="novo-canal-duracao" min="15" max="600" step="5" value="45" data-out="w9v" data-suf=" s"></div>
          </div><div class="card"><h3>Pilares viram ideias</h3><p class="sub" style="margin-top:6px">Os pilares alimentam Tendências e ideias e a estrutura de roteiro sugerida ao criar um vídeo.</p><div class="row" id="wiz-pilares" style="margin-top:12px"><span class="sample">Nenhum pilar ainda.</span></div></div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Visual e voz</summary>
          <div class="stack" style="margin-top:16px"><div class="card"><h3 style="margin-bottom:6px">Estilo visual (da Biblioteca)</h3><p class="sub" style="margin-bottom:12px">Todo vídeo novo herda este estilo. Dá para trocar por vídeo.</p><div class="grid3">{galeria}</div></div>
          <div class="grid2"><div class="card"><h3 style="margin-bottom:10px">Voz do narrador</h3><p class="sub">A voz do canal é definida em Marca & Editorial depois de criar o canal.</p></div>
          <div class="card"><h3 style="margin-bottom:10px">Legendas, formato e modo</h3>
            <div class="field"><span class="lbl">Formato padrão</span>{_seg("formato", [("short", "Short · 9:16"), ("long", "Vídeo · 16:9")], "short")}</div>
            <div class="field"><span class="lbl">Modo padrão de criação</span>{_seg("modo", [("piloto", "⚡ Piloto automático"), ("diretor", "🎬 Modo Diretor")], "piloto")}</div>
          </div></div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Produção</summary>
          <div class="grid2" style="margin-top:16px"><div class="card"><h3 style="margin-bottom:12px">Perfil de produção</h3><div class="stack" style="gap:10px">{perfis}</div></div>
          <div class="card"><h3 style="margin-bottom:12px">Limites e saída</h3>
            <div class="field"><label for="novo-canal-teto-mensal">Teto mensal: <b id="w13v">US$ 20</b></label><input type="range" id="novo-canal-teto-mensal" min="5" max="100" value="20" data-out="w13v" data-pre="US$ "></div>
            <div class="field"><label for="novo-canal-teto-video">Teto por vídeo: <b id="w14v">US$ 1,50</b></label><input type="range" id="novo-canal-teto-video" min="0.2" max="5" step="0.1" value="1.5" data-out="w14v" data-pre="US$ "></div>
            <p class="sample">Nunca troca a voz de identidade nem excede o teto sem avisar.</p>
          </div></div>
        </details>
        <details class="diag" style="margin-top:12px"><summary>Personalizar · Providers e YouTube</summary>
          <div class="two" style="margin-top:16px"><div class="card"><h3>Providers que este canal usaria</h3>
            <p class="sub">Escolha automática pelo perfil <span id="wiz-perfil-rotulo">Econômico</span>. Você pode fixar outro depois em Configurações.</p>
            <p class="sample" style="margin-top:10px">A disponibilidade de cada tarefa só pode ser verificada depois que o canal existe.</p></div>
          <div class="stack"><div class="card"><h3>Canal do YouTube</h3><p class="pill warn" style="margin:8px 0">○ Desconectado</p><p class="sub">Sem vínculo. Você pode criar e aprovar vídeos normalmente, mas só publica depois de conectar.</p></div>
          <div class="note info">Conectar o YouTube agora é opcional. Dá para criar e aprovar vídeos e conectar só na hora de publicar.</div></div></div>
        </details>
        <div class="between" style="margin-top:20px"><p class="sub">Criar o canal não gera vídeos nem cobra nada. YouTube é opcional agora.</p>
          <button class="btn primary" type="submit" id="btn-criar-canal">✦ Criar canal</button></div>
        <p id="new-channel-feedback" class="feedback" role="status"></p>
      </form>
    </section>"""
    html = shell_v3.render_document(title="Faceless Studio — Criar canal", active="configuracoes",
        crumb="Criar canal", body_html=body, nonce=nonce, projects=list(view.projects),
        project_id=project_id, page_js=panel_channels._channels_page_js(project_id) + _WIZARD_JS)
    return html, panel_shell._headers(nonce)
