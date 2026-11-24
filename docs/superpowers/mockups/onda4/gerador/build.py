"""Mockups FIÉIS da Onda 4: telas reais renderizadas pelo próprio código + só o que será acrescentado, em destaque."""
import html as H
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import base  # noqa: E402
from app.studio.domain.contracts import VideoStatus  # noqa: E402

OUT = Path(sys.argv[1])

HL_CSS = """<style>
.mk-novo{outline:2px dashed #f5a524;outline-offset:4px;border-radius:10px;position:relative}
.mk-tag{white-space:nowrap;display:inline-block;background:#f5a524;color:#1a1200;font:700 10px/1 system-ui;letter-spacing:.06em;padding:3px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}
.mk-tag.abs{position:absolute;top:-11px;right:10px;margin:0}
.mk-chg{outline:2px dashed #38bdf8;outline-offset:4px;border-radius:10px;position:relative}
.mk-tag.chg{background:#38bdf8}
.mk-sw{width:56px;height:72px;border-radius:6px;flex:none;position:relative;overflow:hidden}
.mk-sw i{position:absolute;left:4px;bottom:3px;font:600 9px system-ui;color:#fff;background:rgba(0,0,0,.55);padding:1px 4px;border-radius:3px;font-style:normal}
.mk-shot{display:flex;gap:10px;align-items:center;background:var(--panel2,#16181f);border:1px solid var(--line,#2a2d38);border-radius:10px;padding:8px 10px;min-width:0}
.mk-shots{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:10px;align-items:stretch}
</style>"""


def tag(txt="NOVO", cls="", abs_=False):
    return f'<span class="mk-tag {cls} {"abs" if abs_ else ""}">{txt}</span>'


def sub(h, old, new, count=1):
    assert old in h, f"âncora ausente: {old[:70]!r}"
    return h.replace(old, new, count)


def svg(c1, c2, w=230, hh=132):
    s = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{hh}'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
         f"<stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/></linearGradient></defs>"
         f"<rect width='{w}' height='{hh}' fill='url(#g)'/></svg>")
    from urllib.parse import quote
    return "data:image/svg+xml;utf8," + quote(s)


def grad(c1, c2):
    return f"background:linear-gradient(135deg,{c1},{c2})"


def head_inject(h):
    return h.replace("</head>", HL_CSS + "</head>", 1)


def fix_images(h):
    pal = [("#6b4f2a", "#1b1410"), ("#3a3f5c", "#10121c"), ("#2d4a3e", "#0e1512")]
    for i, (c1, c2) in enumerate(pal, start=1):
        h = h.replace(f'src="/studio/videos/{"v"*32}/scenes/s{i}/asset"', f'src="{svg(c1, c2)}"')
    h = h.replace(f'poster="/studio/videos/{"v"*32}/thumbnail"', f'poster="{svg("#6b4f2a", "#1b1410", 270, 480)}"')
    return h


# ----------------------------------------------------------------------------------------- 1. NOVO VÍDEO
def tela_novo_video():
    h = head_inject(base.new_video())
    h = sub(h, '<details class="diag" id="video-custom">', '<details class="diag" id="video-custom" open>')
    h = sub(h, '<select id="duracao-alvo" name="duration" style="width:auto"></select>',
            '<span class="mk-chg" style="display:inline-flex;align-items:center;gap:6px;padding:2px 4px"><select id="duracao-alvo" name="duration" style="width:auto">'
            '<option>30 s</option><option selected>60 s</option><option>3 min</option><option>5 min</option></select>'
            + tag("AGORA É ENVIADO", "chg") + '</span>')
    ritmo = (
        '<div class="mk-novo" style="margin:0 0 14px;padding:10px 12px">' + tag("NOVO", "", True) +
        '<p class="lbl" style="margin-bottom:6px">Ritmo de cortes</p>'
        '<div class="seg" role="group" style="display:inline-flex">'
        '<label class="seg-btn"><input type="radio" class="sr-only" name="pacing" value="dynamic" checked>⚡ Dinâmico</label>'
        '<label class="seg-btn"><input type="radio" class="sr-only" name="pacing" value="balanced">Balanceado</label>'
        '<label class="seg-btn"><input type="radio" class="sr-only" name="pacing" value="cinematic">Cinemático</label></div>'
        '<p class="sample" style="margin-top:6px">Dinâmico: um corte a cada ~2,5 s (1,5–3,5 s). Balanceado: ~3,5 s. Cinemático: ~5 s. '
        'Cena longa com uma só imagem é dividida em tomadas com zoom/pan alternados.</p></div>'
        '<div class="mk-novo" style="margin:0 0 14px;padding:10px 12px">' + tag("NOVO", "", True) +
        '<label class="lbl" for="teto-custo">Teto de custo deste vídeo (US$)</label>'
        '<input type="text" id="teto-custo" value="" placeholder="Opcional · padrão do servidor" style="max-width:260px">'
        '<p class="sample" style="margin-top:6px">A produção para antes de ultrapassar este valor.</p></div>')
    h = sub(h, '<p class="lbl" style="margin-bottom:6px">Voz do narrador', ritmo + '<p class="lbl" style="margin-bottom:6px">Voz do narrador')
    h = sub(h, '<b id="resumo-modo" style="color:var(--text)"></b>', '<b id="resumo-modo" style="color:var(--text)">Piloto automático</b>')
    h = sub(h, '<b id="resumo-formato" style="color:var(--text)"></b>', '<b id="resumo-formato" style="color:var(--text)">Short · 9:16</b>')
    extra = ('<div class="mk-novo" style="margin:6px 0">' + tag("NOVO", "", True) +
             '<div class="between sub"><span>Duração alvo</span><b style="color:var(--text)">60 s</b></div>'
             '<div class="between sub"><span>Ritmo de cortes</span><b style="color:var(--text)">Dinâmico</b></div>'
             '<div class="between sub"><span>Teto de custo</span><b style="color:var(--text)">padrão do servidor</b></div></div>')
    h = sub(h, '<div class="between sub"><span>Estimativa de custo</span>', extra + '<div class="between sub"><span>Estimativa de custo</span>')
    return h


# ----------------------------------------------------------------------------------------- navegação (todas as abas)
def com_aba_direcao(h, ativa=False):
    nav = '<nav class="abas-video" aria-label="Áreas do vídeo">'
    cls = "tab ativa aba" if ativa else "tab aba"
    cur = ' aria-current="page"' if ativa else ""
    new = (f'<a class="{cls} mk-novo" href="#"{cur}>Direção criativa{tag("NOVA ABA")}</a>')
    h = sub(h, nav, nav + new)
    return h


def desativa_aba(h, area):
    return sub(h, f'<a class="tab ativa aba" href="/studio/panel/videos/{"v"*32}/{area}" aria-current="page">',
               f'<a class="tab aba" href="/studio/panel/videos/{"v"*32}/{area}">')


# ----------------------------------------------------------------------------------------- 2. DIREÇÃO CRIATIVA
def tela_direcao():
    h = head_inject(fix_images(base.workspace("cenas")))
    h = desativa_aba(h, "cenas")
    h = com_aba_direcao(h, ativa=True)
    start = h.index('<div id="progress-slot">')
    end = h.rindex("</section>")
    pill = lambda t, c="": f'<span class="pill {c}">{t}</span>'
    ta = lambda t, rows=3: f'<textarea rows="{rows}" style="width:100%">{H.escape(t)}</textarea>'
    cont = f"""
<div class="mk-novo" style="padding:0">{tag("TELA DA ABA NOVA", "", True)}
<div class="between" style="margin:14px 14px 16px"><div><h2>Direção criativa</h2>
<p class="sub">O briefing que guia roteiro, mídia, ritmo e música. Gerado a partir do tema; você pode ajustar antes de produzir.</p></div>
<div class="row"><span class="pill ok">✓ Briefing gerado</span><button class="btn small" type="button">↻ Regenerar briefing</button></div></div>
<div class="two" style="padding:0 14px 14px"><div class="stack">
 <div class="card"><h3 style="margin-bottom:8px">Gancho · primeiros 3 s</h3>
  {ta("Você teria coragem de viver numa cidade subterrânea com dezoito andares abaixo do solo, construída há mais de 2.000 anos?", 2)}
  <div class="field" style="margin-top:10px"><label>Objetivo narrativo</label>
  {ta("Mostrar como uma cidade inteira cabia sob a terra e por que ficou esquecida até 1963.", 2)}</div></div>
 <div class="card"><h3 style="margin-bottom:8px">Estrutura do conteúdo</h3>
  <ol style="margin:0 0 0 18px;line-height:1.9"><li>Gancho: a passagem encontrada em 1963</li><li>Descoberta e escala da cidade</li><li>Engenharia: ventilação, poços e portas de pedra</li><li>Como 20 mil pessoas viviam ali</li></ol></div>
 <div class="grid2">
  <div class="card"><h3 style="margin-bottom:6px">Tom</h3><input type="text" value="Misterioso e documental, voz calma"></div>
  <div class="card"><h3 style="margin-bottom:6px">Ritmo</h3><input type="text" value="Cortes rápidos no gancho, mais calmo na engenharia"></div>
  <div class="card"><h3 style="margin-bottom:6px">Direção visual</h3>{ta("Túneis de pedra com luz de tocha, poços verticais, portas circulares; paleta quente e sombria.", 3)}</div>
  <div class="card"><h3 style="margin-bottom:6px">Orientação de áudio</h3>{ta("Trilha ambiente grave e misteriosa, baixa sob a voz; sem batida.", 3)}</div>
 </div>
 <div class="card"><h3 style="margin-bottom:8px">Tipos de mídia recomendados</h3><div class="row">{pill("Imagem", "accent")}{pill("Vídeo stock", "accent")}{pill("Gráfico")}{pill("Texto")}</div>
  <div class="field" style="margin-top:10px"><label>Estratégia de legendas</label><input type="text" value="Curtas, uma ideia por linha, palavra ativa destacada"></div></div>
 <div class="card"><h3 style="margin-bottom:8px">Critérios de qualidade</h3>
  <ul style="margin:0 0 0 18px;line-height:1.9"><li>Nenhuma imagem repetida em cenas vizinhas</li><li>Voz sempre audível sobre a música</li><li>Legendas dentro da área segura do Shorts</li></ul></div>
</div>
<aside class="card" style="position:sticky;top:80px;align-self:start"><h3>Como o briefing é usado</h3>
 <p class="sub" style="margin:4px 0 12px">Cada decisão abaixo lê este briefing.</p>
 <div class="between sub"><span>Roteiro e cenas</span><b style="color:var(--text)">estrutura e gancho</b></div>
 <div class="between sub"><span>Busca de mídia</span><b style="color:var(--text)">direção visual + tipos</b></div>
 <div class="between sub"><span>Ritmo de cortes</span><b style="color:var(--text)">Dinâmico (do vídeo)</b></div>
 <div class="between sub"><span>Música</span><b style="color:var(--text)">orientação de áudio</b></div>
 <div class="between sub"><span>Teto de custo</span><b style="color:var(--text)">padrão do servidor</b></div>
 <div class="hr"></div>
 <button class="btn primary long" type="button">Salvar ajustes do briefing</button>
 <p class="sample" style="margin-top:8px">Salvar não refaz o que já foi renderizado; vale para as próximas gerações.</p>
</aside></div></div>"""
    return h[:start] + cont + h[end:]


# ----------------------------------------------------------------------------------------- 3. CENAS (storyboard)
def tomadas(sid, linhas, vazio=False):
    if vazio:
        corpo = ('<p class="sample" style="margin:0">Sem tomadas ainda. Escolha a mídia da cena e o ritmo divide em tomadas.</p>')
    else:
        cards = "".join(
            f'<div class="mk-shot"><div class="mk-sw" style="{grad(c1, c2)}"><i>{n}</i></div>'
            f'<div style="font-size:12px;min-width:0"><b>{dur}</b><div class="sample" style="margin:0">{mov}</div>'
            f'<div style="font-size:10.5px;color:var(--ok)">{fonte}</div></div></div>'
            for n, dur, mov, fonte, c1, c2 in linhas)
        corpo = (f'<div class="mk-shots">{cards}<button type="button" class="btn small ghost" style="border-style:dashed;white-space:nowrap">+ Adicionar mídia</button></div>')
    n = 0 if vazio else len(linhas)
    return (
        '<div class="mk-novo" style="grid-column:1/-1;padding:12px;margin-top:2px">' + tag("NOVO NO CARD", "", True) +
        '<div class="between" style="margin-bottom:8px"><span class="lbl">TOMADAS DESTA CENA</span><span class="row">'
        + ('' if vazio else f'<span class="pill accent">⚡ Dinâmico · {n} tomadas</span>')
        + '<span class="sample">Ritmo:</span><select style="width:auto"><option>Herdar do vídeo (Dinâmico)</option><option>Balanceado</option><option>Cinemático</option></select></span></div>'
        + corpo + '</div>')


def tela_cenas():
    h = head_inject(fix_images(base.workspace("cenas")))
    h = com_aba_direcao(h)
    s1 = [("1", "2,2 s", "Zoom in", "Imagem · Pexels", "#6b4f2a", "#1b1410"),
          ("2", "2,2 s", "Vídeo (sem movimento)", "Vídeo · Pixabay", "#5a3d22", "#120d09"),
          ("3", "2,1 s", "Zoom out", "Imagem · Pexels", "#7a5a30", "#1f1710")]
    s2 = [("1", "2,3 s", "Pan para a esquerda", "Imagem · Pixabay", "#3a3f5c", "#10121c"),
          ("2", "2,3 s", "Zoom in", "Imagem · Pexels", "#2f3450", "#0d0f19"),
          ("3", "2,4 s", "Pan para a direita", "Imagem · Pexels", "#444a6e", "#141726")]
    for sid, dados, vazio in (("s1", s1, False), ("s2", s2, False), ("s3", None, True)):
        start = h.index(f'<div class="scene" data-sid="{sid}"')
        tail = 'Excluir</button></div></div></div>'
        pos = h.index(tail, start) + len('Excluir</button></div></div>')
        h = h[:pos] + tomadas(sid, dados, vazio) + h[pos:]
    h = sub(h, '<span class="sub" id="dock-dur">',
            '<span class="pill accent mk-novo" style="margin-left:4px">⚡ Dinâmico · 6 tomadas' + tag("NOVO") + '</span> <span class="sub" id="dock-dur">')
    return h


# ----------------------------------------------------------------------------------------- 4. COMPOSIÇÃO
def tela_composicao():
    h = head_inject(fix_images(base.workspace("composicao")))
    h = desativa_aba(h, "cenas") if False else h
    h = sub(h, f'<a class="tab ativa aba" href="/studio/panel/videos/{"v"*32}/cenas" aria-current="page">',
            f'<a class="tab aba" href="/studio/panel/videos/{"v"*32}/cenas">') if f'/{"v"*32}/cenas" aria-current="page"' in h else h
    h = com_aba_direcao(h)
    # linha do tempo
    h = sub(h, '<div class="track"><span>Música</span><div>bpm 122 · seed 7</div></div>',
            '<div class="track"><span>Música</span><div class="mk-chg">Sci-Fi Survival Dreamscape · CC0 · baixa sob a voz' + tag("MUDA", "chg") + '</div></div>')
    h = sub(h, '<div id="track-legendas">DejaVu Sans · Caixa discreta · base</div>',
            '<div id="track-legendas" class="mk-chg">DejaVu Sans · Destaque por palavra · área segura' + tag("MUDA", "chg") + '</div>')
    # estilo da legenda: opção que hoje é "em breve" passa a funcionar
    h = sub(h, '<option value="destaque" disabled>Destaque por palavra (em breve)</option></select>',
            '<option value="destaque" selected>Destaque por palavra (karaokê)</option></select>')
    h = sub(h, '<div class="field"><label for="composicao-caption-style">',
            '<div class="field mk-chg"><span style="position:absolute;top:-11px;right:10px">' + tag("EM BREVE → ATIVO", "chg") + '</span><label for="composicao-caption-style">')
    # volume + ducking deixam de ser "em breve"
    h = sub(h, '<div class="field"><label for="comp-music-vol">Volume da música <span class="pill pill-espera">Em breve</span></label><input type="range" id="comp-music-vol" min="0" max="60" value="20" disabled></div>',
            '<div class="field mk-chg"><span style="position:absolute;top:-11px;right:10px">' + tag("EM BREVE → ATIVO", "chg") + '</span><label for="comp-music-vol">Volume da música: <b>20</b></label><input type="range" id="comp-music-vol" min="0" max="60" value="20"></div>')
    h = sub(h, '<div class="field"><label class="tog"><input type="checkbox" id="comp-ducking" disabled><i></i>Abaixar a música quando houver voz <span class="pill pill-espera">Em breve</span></label></div>',
            '<div class="field mk-chg"><span style="position:absolute;top:-11px;right:10px">' + tag("EM BREVE → ATIVO", "chg") + '</span><label class="tog"><input type="checkbox" id="comp-ducking" checked><i></i>Abaixar a música quando houver voz</label>'
            '<p class="sample" style="margin-top:4px">Compressão sidechain: a música cai sob a narração e volta nas pausas; fade-out no final.</p></div>')
    # trilha escolhida + ritmo, antes de "Volume da música"
    novo = ('<div class="field mk-novo" style="padding:10px 12px">' + tag("NOVO", "", True) +
            '<span class="lbl">Trilha escolhida pelo Diretor de áudio</span>'
            '<select><option>Sci-Fi Survival Dreamscape · CC0 (sugerida pelo tom)</option><option>Ambient Music · CC0</option>'
            '<option>Electronic Minute No 258 · CC0</option><option>Sem música</option></select>'
            '<p class="sample" style="margin-top:4px">Só faixas CC0 do catálogo do estúdio; a licença aparece no relatório de entrega.</p></div>'
            '<div class="field mk-novo" style="padding:10px 12px">' + tag("NOVO", "", True) +
            '<span class="lbl">Ritmo de cortes</span><div class="seg" role="group">'
            '<label class="seg-btn"><input type="radio" class="sr-only" name="rp" checked>Dinâmico</label>'
            '<label class="seg-btn"><input type="radio" class="sr-only" name="rp">Balanceado</label>'
            '<label class="seg-btn"><input type="radio" class="sr-only" name="rp">Cinemático</label></div></div>')
    h = sub(h, '<div class="field mk-chg"><span style="position:absolute;top:-11px;right:10px">' + tag("EM BREVE → ATIVO", "chg") + '</span><label for="comp-music-vol">',
            novo + '<div class="field mk-chg"><span style="position:absolute;top:-11px;right:10px">' + tag("EM BREVE → ATIVO", "chg") + '</span><label for="comp-music-vol">')
    return h


# ----------------------------------------------------------------------------------------- 5. QUALIDADE / ENTREGA
def tela_qualidade():
    h = head_inject(fix_images(base.workspace("qualidade", VideoStatus.RENDERED)))
    h = com_aba_direcao(h)
    btn = ('<span class="mk-novo" style="display:inline-block;margin-left:10px">' + tag("NOVO", "", True) +
           '<a class="btn primary small" href="#">⬇ Baixar vídeo (.mp4)</a></span>')
    h = sub(h, '>Abrir prévia completa</a></p>', '>Abrir prévia completa</a>' + btn +
            '</p><p class="sample" style="text-align:center;margin-top:6px">MP4 H.264 + AAC · 14,8 MB · 1080×1920 · 25 fps</p>')
    resumo = ('<div class="card mk-novo" style="margin-top:14px">' + tag("NOVO CARTÃO", "", True) +
              '<h3 style="margin-bottom:8px">Resumo audiovisual desta versão</h3>'
              '<div class="between sub"><span>Duração</span><b style="color:var(--text)">0:48</b></div>'
              '<div class="between sub"><span>Cortes / tomadas</span><b style="color:var(--text)">16 · ritmo Dinâmico</b></div>'
              '<div class="between sub"><span>Música</span><b style="color:var(--text)">Sci-Fi Survival Dreamscape · CC0</b></div>'
              '<div class="between sub"><span>Mixagem</span><b style="color:var(--text)">música baixa sob a voz · fade-out</b></div>'
              '<div class="between sub"><span>Legendas</span><b style="color:var(--text)">destaque por palavra · área segura</b></div>'
              '<div class="between sub"><span>Mídias</span><b style="color:var(--text)">Pexels · Pixabay</b></div>'
              '<p class="sample" style="margin-top:8px">Licenças: música CC0 1.0; mídias sob as licenças de uso do Pexels e do Pixabay.</p></div>')
    # após o cartão "Pronto para sua revisão"
    h = sub(h, '<details class="diag"><summary>Ver todas as verificações técnicas</summary>',
            resumo + '<details class="diag" style="margin-top:14px"><summary>Ver todas as verificações técnicas</summary>')
    return h


TELAS = [
    ("1 · Novo vídeo", tela_novo_video, 1500, "Tela existente: <code>Criar vídeo</code>. Abri o bloco já existente «Personalizar este vídeo».",
     ["<b>Ritmo de cortes</b> (Dinâmico / Balanceado / Cinemático): hoje não existe na tela.",
      "<b>Teto de custo do vídeo</b> (opcional): hoje é só configuração do servidor.",
      "<b>Duração alvo</b>: o seletor já existe, mas o valor não é enviado ao criar. Passa a ser enviado.",
      "<b>Resumo</b> (lateral): ganha 3 linhas (duração, ritmo, teto). Nada mais muda."]),
    ("2 · Direção criativa (aba nova)", tela_direcao, 1760, "Mesmo workspace do vídeo. A única adição estrutural: <b>uma aba nova</b> na barra de áreas.",
     ["Aba <b>Direção criativa</b> ao lado das 5 abas atuais. As outras abas e o destino padrão de cada vídeo não mudam.",
      "Mostra o briefing criativo do vídeo (gancho, estrutura, tom, ritmo, direção visual, áudio, tipos de mídia, legendas, critérios) com edição e «Regenerar».",
      "O briefing alimenta roteiro, busca de mídia, ritmo e música (painel lateral)."]),
    ("3 · Cenas & Storyboard", tela_cenas, 1850, "Tela existente, com os 3 cartões de cena reais. Cada cartão ganha uma faixa de tomadas.",
     ["<b>Faixa «Tomadas desta cena»</b> dentro de cada cartão: duração, movimento e origem de cada tomada, geradas pelo ritmo.",
      "<b>+ Adicionar mídia</b> abre o mesmo modal «Mídia para esta cena» que já existe (Deste vídeo / Do canal / Meus arquivos / Stock / Gerar).",
      "<b>Ritmo por cena</b> (herda do vídeo ou sobrescreve).",
      "<b>Rodapé</b> ganha a pílula «Dinâmico · 6 tomadas». Texto, prompt, narração, B-roll e voz seguem como estão."]),
    ("4 · Composição & Legendas", tela_composicao, 1720, "Tela existente. Aqui três controles que hoje aparecem como «Em breve» passam a funcionar.",
     ["<b>Volume da música</b> e <b>Abaixar a música quando houver voz</b>: hoje desabilitados («Em breve»), passam a atuar na mixagem.",
      "<b>Estilo da legenda → Destaque por palavra</b>: hoje «(em breve)», vira karaokê.",
      "<b>Trilha escolhida</b> (catálogo CC0) e <b>Ritmo de cortes</b>: campos novos.",
      "<b>Linha do tempo</b>: as linhas Música e Legendas mostram a trilha e o estilo reais."]),
    ("5 · Qualidade & Aprovação", tela_qualidade, 1350, "Tela existente (prévia + aprovação). Duas adições.",
     ["<b>⬇ Baixar vídeo (.mp4)</b> ao lado de «Abrir prévia completa».",
      "<b>Resumo audiovisual</b>: duração, cortes, música e licença, mixagem, legendas e origem das mídias.",
      "Aprovação, pontos de revisão e verificações técnicas não mudam."]),
]


def main():
    blocos, indice = [], []
    for i, (titulo, fn, alt, descr, mudancas) in enumerate(TELAS):
        doc = fn(); (Path(__file__).parent / f"doc{i}.html").write_text(doc)
        lis = "".join(f"<li>{m}</li>" for m in mudancas)
        indice.append(f'<a href="#t{i}">{H.escape(titulo)}</a>')
        blocos.append(
            f'<section id="t{i}" class="bloco"><h2>{H.escape(titulo)}</h2><p class="d">{descr}</p>'
            f'<ul class="chg">{lis}</ul>'
            f'<div class="fr" style="height:{int(alt*0.72)}px"><iframe srcdoc="{H.escape(doc, quote=True)}" '
            f'style="width:1440px;height:{alt}px"></iframe></div></section>')
    page = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Onda 4 · mockups fiéis</title>
<style>
body{{margin:0;background:#0b0c10;color:#e8e8ee;font:14px/1.5 system-ui}}
header{{position:sticky;top:0;background:#0b0c10ee;border-bottom:1px solid #2a2d38;padding:12px 24px;z-index:9}}
header a{{color:#a78bfa;margin-right:16px;text-decoration:none;font-weight:600}}
.leg{{padding:14px 24px;color:#c9c9d4}}
.leg b.o{{color:#f5a524}} .leg b.b{{color:#38bdf8}}
.bloco{{padding:8px 24px 28px}} h2{{margin:20px 0 4px}} .d{{color:#a8a8b8;margin:0 0 8px}}
.chg{{margin:0 0 14px 20px;line-height:1.7}} code{{background:#1b1d26;padding:1px 5px;border-radius:4px}}
.fr{{width:{int(1440*0.72)}px;border:1px solid #2a2d38;border-radius:10px;overflow:hidden}}
iframe{{border:0;transform:scale(.72);transform-origin:0 0;background:#0b0c10}}
</style></head><body>
<header>{"".join(indice)}</header>
<div class="leg"><b>Como ler:</b> cada tela abaixo é a <b>tela real do estúdio</b>, renderizada pelo próprio código atual
(mesmo HTML e CSS), com dados de exemplo. Só o que será acrescentado ou alterado está destacado:
<b class="o">contorno laranja tracejado = NOVO</b> · <b class="b">contorno azul tracejado = muda algo que já existe</b>.
O resto da tela é exatamente o que existe hoje.</div>
{"".join(blocos)}</body></html>"""
    OUT.write_text(page)
    print("ok", len(page))


main()
