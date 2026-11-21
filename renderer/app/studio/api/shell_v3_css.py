"""CSS da UX V3 — gerado a partir de `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html`.

Fonte da verdade visual aprovada pelo dono. Não editar à mão: mudanças de aparência entram primeiro
na proposta e depois aqui (extensões próprias do produto ficam em `shell_v3.PRODUCT_CSS`).
"""

V3_CSS = """
/* =========================================================================
   Tokens. Padrão do projeto (modern-web-guidance › dark-mode):
   color-scheme em :root + light-dark(); fallback por prefers-color-scheme
   para navegador que tem color-scheme mas não tem light-dark().
   ========================================================================= */
:root {
  color-scheme: light dark;

  /* pares crus: claro primeiro, escuro depois */
  --bg-l:#f7f7fa;        --bg-d:#0c0d10;
  --side-l:#ffffff;      --side-d:#111216;
  --panel-l:#ffffff;     --panel-d:#15171c;
  --panel2-l:#f2f1f7;    --panel2-d:#1c1e24;
  --line-l:#e3e0ea;      --line-d:#2c2e37;
  --txt-l:#1b1a21;       --txt-d:#f3f3f7;
  --muted-l:#5c5966;     --muted-d:#a3a6b4;   /* ≥4.5:1 sobre panel/bg */
  --sub-l:#6a6773;       --sub-d:#90939f;     /* ≥4.5:1 sobre panel/bg */
  --accent-l:#6a4bc4;    --accent-d:#b9a3ff;  /* texto de acento lavável */
  --accentfill-l:#6b4cd6; --accentfill-d:#8f6ef7;
  --onaccent-l:#ffffff;  --onaccent-d:#14101f;
  --good-l:#1d6b48;      --good-d:#7fd0a8;
  --warn-l:#7a5312;      --warn-d:#ecc27a;
  --soft-l:#ece7fb;      --soft-d:#221d33;
  --shadow-l:0 10px 30px rgba(24,16,44,.10);
  --shadow-d:0 20px 55px rgba(0,0,0,.35);
  --hero-l:linear-gradient(120deg,#ece7fb,#f8f7fb 70%);
  --hero-d:linear-gradient(120deg,#1e1b2d,#16161e 68%);

  /* fallback: default claro; escuro pela preferência do sistema */
  --bg:var(--bg-l); --side:var(--side-l); --panel:var(--panel-l); --panel2:var(--panel2-l);
  --line:var(--line-l); --txt:var(--txt-l); --muted:var(--muted-l); --sub:var(--sub-l);
  --accent:var(--accent-l); --accentfill:var(--accentfill-l); --onaccent:var(--onaccent-l);
  --good:var(--good-l); --warn:var(--warn-l); --soft:var(--soft-l); --shadow:var(--shadow-l);
  --hero:var(--hero-l);

  @media (prefers-color-scheme: dark) {
    --bg:var(--bg-d); --side:var(--side-d); --panel:var(--panel-d); --panel2:var(--panel2-d);
    --line:var(--line-d); --txt:var(--txt-d); --muted:var(--muted-d); --sub:var(--sub-d);
    --accent:var(--accent-d); --accentfill:var(--accentfill-d); --onaccent:var(--onaccent-d);
    --good:var(--good-d); --warn:var(--warn-d); --soft:var(--soft-d); --shadow:var(--shadow-d);
    --hero:var(--hero-d);
  }

  /* moderno: uma declaração por token, seguindo o color-scheme computado */
  @supports (color: light-dark(white, black)) {
    --bg:light-dark(var(--bg-l),var(--bg-d));
    --side:light-dark(var(--side-l),var(--side-d));
    --panel:light-dark(var(--panel-l),var(--panel-d));
    --panel2:light-dark(var(--panel2-l),var(--panel2-d));
    --line:light-dark(var(--line-l),var(--line-d));
    --txt:light-dark(var(--txt-l),var(--txt-d));
    --muted:light-dark(var(--muted-l),var(--muted-d));
    --sub:light-dark(var(--sub-l),var(--sub-d));
    --accent:light-dark(var(--accent-l),var(--accent-d));
    --accentfill:light-dark(var(--accentfill-l),var(--accentfill-d));
    --onaccent:light-dark(var(--onaccent-l),var(--onaccent-d));
    --good:light-dark(var(--good-l),var(--good-d));
    --warn:light-dark(var(--warn-l),var(--warn-d));
    --soft:light-dark(var(--soft-l),var(--soft-d));
    --shadow:light-dark(var(--shadow-l),var(--shadow-d));
    --hero:light-dark(var(--hero-l),var(--hero-d));
  }

  accent-color:var(--accentfill);            /* controles nativos acompanham o tema */
  scrollbar-color:var(--line) transparent;
}

* { box-sizing:border-box; }
/* hidden precisa vencer o display de qualquer classe (ex.: .btn usa inline-flex) */
[hidden] { display:none !important; }
/* Tipografia do protótipo V3: Inter (usada no mockup original) primeiro; se não
   estiver instalada, cai no MESMO fallback do original, para não mudar de fonte. */
body {
  margin:0; background:var(--bg); color:var(--txt);
  font:14px/1.5 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
button,input,select,textarea { font:inherit; color:inherit; }
a { color:var(--accent); }
h1,h2,h3 { letter-spacing:-.3px; }
:where(a,button,input,select,textarea,[tabindex]):focus-visible {
  outline:2px solid var(--accent); outline-offset:2px; border-radius:6px;
}
.sr-only {
  position:absolute; width:1px; height:1px; padding:0; margin:-1px;
  overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0;
}
.skip { position:absolute; left:-9999px; top:0; background:var(--panel); color:var(--txt);
  padding:10px 14px; z-index:50; border:1px solid var(--line); }
.skip:focus { left:8px; top:8px; }

/* ---------- estrutura ---------- */
.app { display:flex; min-height:100vh; }
.side {
  position:sticky; top:0; width:240px; min-width:240px; height:100vh; background:var(--side);
  border-right:1px solid var(--line); padding:25px 16px; display:flex; flex-direction:column;
}
.brand { display:flex; align-items:center; gap:11px; padding:3px 10px 34px; font-weight:780;
  font-size:16px; letter-spacing:-.6px; }
.brand-logo { width:33px; height:33px; border-radius:11px; background:var(--accentfill);
  color:var(--onaccent); display:grid; place-items:center; font-size:18px; font-weight:900;
  box-shadow:0 5px 22px color-mix(in srgb, var(--accentfill) 25%, transparent); }
.brand small { display:block; color:var(--sub); font-weight:500; font-size:10px;
  letter-spacing:2px; margin-top:-2px; }
.side-caption { font-size:10px; text-transform:uppercase; letter-spacing:1.5px;
  color:var(--sub); font-weight:700; margin:8px 12px 10px; }   /* era 4.02:1 */
.nav-list { list-style:none; margin:0; padding:0; }
.nav-list a {
  display:flex; gap:13px; align-items:center; padding:12px 13px; border:1px solid transparent;
  border-left:3px solid transparent; border-radius:10px; color:var(--txt);
  text-decoration:none; font-weight:560; margin:2px 0;
}
/* ícones do protótipo: traço 1.8, 18×18, herdando a cor do item */
.nav-list svg { width:18px; height:18px; flex:0 0 18px; stroke-width:1.8; }
.nav-list a:hover { background:var(--panel2); color:var(--accent); }
/* Indicador de página ativa: forma (barra + peso), não só cor — sobrevive ao alto contraste */
.nav-list a[aria-current="page"] {
  background:var(--soft); color:var(--accent); border-color:var(--line);
  border-left-color:var(--accentfill); font-weight:750;
}
.side-bottom { margin-top:auto; border-top:1px solid var(--line); padding-top:12px; }
.side-note { display:flex; gap:10px; align-items:center; color:var(--muted); font-size:12px;
  padding:10px 11px; }
.avatar { width:30px; height:30px; border-radius:50%; background:var(--soft); color:var(--accent);
  display:grid; place-items:center; font-weight:800; }
.mock-flag { font-size:11px; color:var(--muted); padding:6px 10px; margin:0; }

.main { flex:1; min-width:0; display:flex; flex-direction:column; }
.top { min-height:78px; border-bottom:1px solid var(--line); display:flex; align-items:center;
  justify-content:space-between; gap:20px; padding:12px 52px; flex-wrap:wrap; }
.crumb { color:var(--muted); font-size:13px; }
.crumb b { color:var(--txt); font-weight:650; }
.tools { display:flex; align-items:center; gap:10px; }
.canal-select { border:1px solid var(--line); background:var(--panel); border-radius:11px;
  padding:9px 12px; font-size:12px; min-width:185px; }
.icon-btn { background:transparent; border:1px solid var(--line); border-radius:10px;
  width:36px; height:36px; display:grid; place-items:center; cursor:pointer; color:var(--muted); }
.icon-btn:hover { background:var(--panel2); color:var(--txt); }
.content { padding:43px 52px 100px; max-width:1240px; width:100%; margin:0 auto; }
.pagina[hidden] { display:none; }
.eyebrow { text-transform:uppercase; color:var(--accent); font-weight:750; letter-spacing:2px;
  font-size:10px; margin-bottom:12px; }
.h1 { font-size:35px; line-height:1.2; letter-spacing:-1.3px; font-weight:730; margin:0 0 10px; }
.lead { color:var(--muted); margin:0; }
.secao { margin-top:36px; }
.secao-cab { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:16px; }
.secao h2 { font-size:17px; margin:0; }
.muted { color:var(--muted); }
.micro { font-size:12px; color:var(--muted); }
.link-btn { background:none; border:0; color:var(--accent); font-weight:650; font-size:12px;
  padding:8px; cursor:pointer; text-decoration:underline; }

/* ---------- botões ---------- */
.btn { border:1px solid var(--line); background:var(--panel2); color:var(--txt); border-radius:10px;
  padding:11px 17px; font-weight:650; cursor:pointer; display:inline-flex; align-items:center;
  justify-content:center; gap:8px; }
.btn:hover { background:var(--panel); }
.btn-primario { background:var(--accentfill); color:var(--onaccent); border-color:var(--accentfill); }
.btn-primario:hover { filter:brightness(1.08); }
.btn[disabled] { opacity:.55; cursor:not-allowed; }

/* ---------- início ---------- */
.hero { padding:38px 42px 36px; background:var(--hero); border:1px solid var(--line);
  border-radius:19px; }
.hero h1 { font-size:32px; letter-spacing:-1.2px; line-height:1.2; margin:0 0 9px; }
.hero p { color:var(--muted); margin:0 0 20px; }
.campo-tema { display:flex; flex-direction:column; gap:7px; }
.campo-tema label { font-size:13px; font-weight:650; }
.campo-tema input { border:1px solid var(--line); background:var(--panel); border-radius:10px;
  padding:13px; width:100%; }
.hero-linha { display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap; }
.hero-linha .campo-tema { flex:1 1 320px; }
.formatos { border:0; padding:0; margin:16px 0 0; display:flex; gap:9px; flex-wrap:wrap; }
.formatos legend { font-size:12px; color:var(--muted); margin-bottom:6px; padding:0; }
.formato { display:inline-flex; align-items:center; gap:8px; border:1px solid var(--line);
  background:var(--panel); border-radius:9px; padding:9px 12px; font-size:13px; cursor:pointer; }
.formato:has(input:checked) { border-color:var(--accentfill); background:var(--soft);
  color:var(--accent); font-weight:650; }
.formato input { accent-color:var(--accentfill); }

.grade { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:15px; }
.cartao-projeto { border:1px solid var(--line); background:var(--panel); border-radius:14px;
  overflow:hidden; }
.cartao-projeto a { display:block; text-decoration:none; color:inherit; border-radius:14px; }
.cartao-projeto a:hover { border-color:var(--accentfill); }
.miniatura { height:145px; display:flex; align-items:flex-end; padding:15px;
  background:linear-gradient(135deg,#2a2340,#12121d); }
.miniatura b { font-size:10px; letter-spacing:1.4px; text-transform:uppercase;
  color:#e5e5f5; font-weight:750; }
.cartao-corpo { padding:15px; }
.cartao-corpo h3 { font-size:14px; margin:0 0 7px; }
.linha-meta { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:var(--muted); }
.situacao { display:inline-flex; align-items:center; gap:7px; font-weight:600; font-size:11px;
  color:var(--txt); }
.situacao i { width:8px; height:8px; border-radius:50%; background:var(--accentfill); }
.situacao.ok i { background:var(--good); }
.situacao.espera i { background:var(--warn); }
.situacao.parado i { background:var(--muted); }
.etapa-atual { font-size:12px; color:var(--muted); margin-top:8px; }

/* ---------- tendências (com evidência) ---------- */
.grade-tendencias { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.cartao-tendencia { border:1px solid var(--line); background:var(--panel); border-radius:13px; padding:17px; }
.origem { display:inline-block; border:1px solid var(--line); background:var(--panel2);
  color:var(--accent); border-radius:5px; padding:4px 7px; font-size:10px; font-weight:700; }
.cartao-tendencia h3 { font-size:15px; margin:13px 0 10px; }
.evidencias { list-style:none; margin:0 0 12px; padding:0; font-size:12px; color:var(--muted); }
.evidencias li { padding:4px 0; border-bottom:1px solid var(--line); display:flex; gap:8px;
  justify-content:space-between; }
.evidencias li span:last-child { color:var(--txt); font-weight:600; text-align:right;
  overflow-wrap:anywhere; min-width:0; }   /* URL longa quebra em vez de estourar o cartão */
/* link com área de toque de 24px de altura (WCAG 2.5.8) sem deixar de quebrar a URL */
.evidencias a { display:inline-block; max-width:100%; padding:5px 0; overflow-wrap:anywhere; }
.pilha { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

/* ---------- pilares (filtro e gestão) — espelha a UX atual ---------- */
.barra-pilares { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 18px; }
.chip-filtro { border:1px solid var(--line); background:var(--panel); color:var(--txt);
  border-radius:30px; padding:8px 13px; font-size:12px; font-weight:600; cursor:pointer; }
.chip-filtro:hover { background:var(--panel2); }
/* pressionado: fundo + borda + PESO (não só cor) e aria-pressed para o leitor de tela */
.chip-filtro[aria-pressed="true"] { background:var(--soft); border-color:var(--accentfill);
  color:var(--accent); font-weight:750; }
.chip-filtro.novo { border-style:dashed; color:var(--accent); }
.chip-pilar { display:inline-block; border:1px solid var(--line); background:var(--panel2);
  color:var(--accent); border-radius:5px; padding:4px 7px; font-size:10px; font-weight:700; }

/* ---------- diálogo de pilares (nativo, sem role/aria-modal) ---------- */
dialog { border:1px solid var(--line); background:var(--panel); color:var(--txt);
  border-radius:16px; padding:0; width:min(620px, calc(100vw - 32px)); box-shadow:var(--shadow); }
dialog::backdrop { background:rgba(8,6,16,.6); overflow:hidden; overscroll-behavior:contain; }
dialog:modal { overscroll-behavior:contain; }
.dialogo-cab { display:flex; align-items:flex-start; justify-content:space-between; gap:14px;
  padding:22px 24px 0; }
.dialogo-cab h2 { font-size:18px; margin:0; letter-spacing:-.4px; }
.dialogo-corpo { padding:10px 24px 24px; max-height:min(72vh,640px); overflow:auto; }
.lista-pilares { list-style:none; margin:14px 0 22px; padding:0; }
.lista-pilares li { display:flex; gap:12px; align-items:flex-start; justify-content:space-between;
  padding:12px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
.lista-pilares b { display:block; font-size:13px; }
.lista-pilares small { color:var(--muted); display:block; margin-top:3px; }
.acoes-linha { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.form-pilar { border-top:1px solid var(--line); padding-top:18px; }
.form-pilar h3 { font-size:14px; margin:0 0 4px; }
.form-pilar .acoes { justify-content:flex-end; }

/* ---------- novo vídeo ---------- */
.passos { list-style:none; display:flex; gap:10px; align-items:center; padding:0; margin:0 0 22px;
  font-size:12px; color:var(--muted); flex-wrap:wrap; }
.passos li { display:flex; align-items:center; gap:7px; }
.passos b { width:22px; height:22px; border:1px solid var(--line); border-radius:50%;
  display:grid; place-items:center; font-size:11px; }
.passos li[aria-current="step"] { color:var(--accent); font-weight:700; }
.passos li[aria-current="step"] b { background:var(--soft); border-color:var(--accentfill);
  border-width:2px; }
.passos li.feito { color:var(--good); }
.passos li.feito b { border-color:var(--good); }
.passos .risco { width:14px; height:1px; background:var(--line); }
.grade-criar { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:20px; align-items:start; }
.painel { border:1px solid var(--line); background:var(--panel); border-radius:14px; padding:25px; }
.painel h3 { font-size:16px; font-weight:690; letter-spacing:-.3px; margin:0 0 6px; }
.painel > p { color:var(--muted); margin:0 0 22px; font-size:12px; }
.campo { margin-bottom:20px; }
.campo > label, .campo > .rotulo { display:block; font-size:13px; font-weight:650; margin-bottom:8px; }
.campo input[type="text"], .campo input[type="url"], .campo input[type="search"],
.campo textarea, .campo select, select.campo {
  width:100%; border:1px solid var(--line); background:var(--panel2); border-radius:9px; padding:12px;
}
.campo textarea { min-height:120px; resize:vertical; }
.dica { font-size:12px; color:var(--muted); margin:7px 0 0; }
.pills { border:0; padding:0; margin:0; display:flex; gap:8px; flex-wrap:wrap; }
.pills legend { font-size:13px; font-weight:650; margin-bottom:8px; padding:0; }
.pill { display:inline-flex; align-items:center; gap:7px; border:1px solid var(--line);
  background:var(--panel2); border-radius:9px; padding:9px 12px; font-size:13px; cursor:pointer; }
.pill:has(input:checked) { border-color:var(--accentfill); background:var(--soft); color:var(--accent);
  font-weight:650; }
.tabela-kv { width:100%; font-size:13px; border-collapse:collapse; }
.tabela-kv th, .tabela-kv td { text-align:left; padding:11px 0; border-bottom:1px solid var(--line);
  font-weight:500; }
.tabela-kv th { color:var(--muted); font-weight:500; width:48%; }
.tabela-kv td { font-weight:650; text-align:right; }
.acoes { display:flex; gap:9px; align-items:center; justify-content:space-between; flex-wrap:wrap;
  margin-top:18px; }
.aviso { border:1px solid var(--line); border-left:3px solid var(--accentfill); background:var(--soft);
  border-radius:9px; padding:13px 15px; font-size:13px; }

/* ---------- filtros/busca ---------- */
.linha-busca { display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap; margin-bottom:18px; }
.linha-busca .campo { margin:0; flex:1 1 260px; }
.filtros { border:0; padding:0; margin:0; }
.filtros legend { font-size:13px; font-weight:650; margin-bottom:8px; padding:0; }
.vazio { padding:28px; text-align:center; color:var(--muted); border:1px dashed var(--line);
  border-radius:11px; }

/* ---------- desempenho ---------- */
.estatisticas { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:13px; }
.estat { border:1px solid var(--line); background:var(--panel); border-radius:12px; padding:18px; }
.estat span { color:var(--muted); font-size:12px; }
.estat strong { display:block; font-size:26px; margin:8px 0 3px; }
.grafico { display:flex; align-items:flex-end; gap:10px; height:180px; padding:14px 4px 0;
  border-bottom:1px solid var(--line); }
.barra { flex:1; border-radius:4px 4px 0 0; background:var(--accentfill); }
.rotulos { display:flex; gap:10px; color:var(--muted); font-size:11px; padding:9px 4px; }
.rotulos span { flex:1; text-align:center; }
.selo { display:inline-block; border:1px solid var(--line); background:var(--panel2);
  color:var(--accent); border-radius:6px; padding:3px 8px; font-size:11px; font-weight:700; }

/* ---------- configurações (rotas, não abas) ---------- */
.grade-config { display:grid; grid-template-columns:210px minmax(0,1fr); gap:20px; align-items:start; }
.menu-config { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:4px; }
.menu-config a { display:block; padding:11px 12px; border:1px solid transparent;
  border-left:3px solid transparent; border-radius:9px; color:var(--txt); text-decoration:none;
  font-weight:600; font-size:13px; }
.menu-config a:hover { background:var(--panel2); }
.menu-config a[aria-current="page"] { background:var(--soft); color:var(--accent);
  border-color:var(--line); border-left-color:var(--accentfill); font-weight:750; }
.item-config { display:flex; justify-content:space-between; gap:14px; align-items:center;
  padding:16px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
.item-config:last-child { border-bottom:0; }
.item-config b { display:block; font-size:13px; }
.item-config small { color:var(--muted); }
.galeria { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:11px; }
.cartao-estilo { border:1px solid var(--line); background:var(--panel2); border-radius:11px;
  overflow:hidden; text-align:left; padding:0 0 11px; cursor:pointer; }
.cartao-estilo:has(input:checked) { border-color:var(--accentfill); border-width:2px; }
.cartao-estilo .amostra { height:82px; display:grid; place-items:center; font-weight:800;
  letter-spacing:-.6px; color:#f4f2fb; background:linear-gradient(135deg,#4a3b78,#1a1a2b); }
/* o rádio fica junto do nome, onde pertence — não solto sobre a amostra */
.cartao-rodape { display:flex; align-items:center; gap:8px; margin:10px 11px 0;
  font-size:13px; font-weight:700; }
.cartao-estilo:has(input:checked) .cartao-rodape { color:var(--accent); }

/* ---------- workspace do vídeo ---------- */
.cab-video { display:flex; justify-content:space-between; gap:16px; align-items:flex-start;
  flex-wrap:wrap; margin-bottom:22px; }
.grade-video { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(280px,.85fr); gap:20px;
  align-items:start; }
.player { aspect-ratio:16/9; border:1px solid var(--line); border-radius:12px;
  background:linear-gradient(135deg,#232437,#0d0e17); display:grid; place-items:center; gap:10px;
  color:#e8e6f2; padding:18px; text-align:center; }
.cenas { list-style:none; margin:0; padding:0; }
.cenas li { display:flex; gap:12px; align-items:flex-start; padding:12px 0;
  border-bottom:1px solid var(--line); }
.cenas li:last-child { border-bottom:0; }
.cena-n { width:28px; height:28px; flex:0 0 28px; border-radius:8px; background:var(--soft);
  color:var(--accent); display:grid; place-items:center; font-size:11px; font-weight:700; }
.cenas small { display:block; color:var(--muted); }
.checklist { list-style:none; margin:0; padding:0; }
.checklist li { display:flex; gap:11px; align-items:center; padding:13px 0;
  border-bottom:1px solid var(--line); }
.checklist li:last-child { border-bottom:0; }
.checklist b { width:20px; height:20px; flex:0 0 20px; border-radius:50%; border:1px solid var(--line);
  display:grid; place-items:center; font-size:11px; }
.checklist li[data-estado="concluido"] { color:var(--txt); }
.checklist li[data-estado="concluido"] b { background:var(--good); border-color:var(--good);
  color:var(--bg); }
.checklist li[data-estado="atual"] { font-weight:700; }
.checklist li[data-estado="atual"] b { border-color:var(--accentfill); border-width:2px; }
.checklist li[data-estado="falhou"] { font-weight:700; }
.checklist li[data-estado="falhou"] b { background:var(--warn); border-color:var(--warn); color:var(--bg); }
/* gate humano: não é falha, mas é você quem destrava */
.checklist li[data-estado="aguardando"] { font-weight:700; }
.checklist li[data-estado="aguardando"] b { background:var(--warn); border-color:var(--warn); color:var(--bg); }
.checklist .estado { margin-left:auto; font-size:11px; color:var(--muted); font-weight:600; }
/* erro: escondido por padrão; o script revela junto com aria-invalid, para o estado
   visual e o programático nunca discordarem (e nada ser lido antes da interação) */
.campo-erro { display:none; font-size:12px; color:var(--warn); font-weight:600; margin-top:6px; }
.campo-erro.visivel { display:block; }
.campo [aria-invalid="true"] { border-color:var(--warn); }

/* ---------- aviso (região viva, existe desde o carregamento) ---------- */
.aviso-toast { position:fixed; right:22px; bottom:22px; max-width:380px; z-index:40;
  background:var(--panel); border:1px solid var(--accentfill); border-left-width:4px;
  border-radius:11px; padding:13px 16px; box-shadow:var(--shadow); display:none; }
.aviso-toast.visivel { display:block; }

/* ---------- responsivo: uma árvore de navegação, sem gaveta ---------- */
@media (max-width:1080px) {
  .content { padding:35px 28px 80px; }
  .top { padding:12px 28px; }
  .grade, .estatisticas { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .grade-criar, .grade-video, .grade-config { grid-template-columns:1fr; }
}
@media (max-width:820px) {
  .app { flex-direction:column; }
  .side { position:static; width:auto; min-width:0; height:auto; border-right:0;
    border-bottom:1px solid var(--line); padding:14px; }
  .brand { padding-bottom:12px; }
  .nav-list { flex-direction:row; overflow-x:auto; gap:4px; }
  .nav-list a { white-space:nowrap; border-left-width:1px; border-bottom:3px solid transparent; }
  .nav-list a[aria-current="page"] { border-left-color:var(--line); border-bottom-color:var(--accentfill); }
  .side-bottom { margin-top:12px; }
  .content { padding:28px 18px 65px; }
  .top { padding:10px 18px; }
  .grade, .grade-tendencias, .estatisticas, .galeria { grid-template-columns:1fr; }
}

/* ---------- sem animação quando o sistema pede ---------- */
@media (prefers-reduced-motion: reduce) {
  * { transition:none !important; animation:none !important; }
}

/* ---------- alto contraste: forma e cores de sistema ---------- */
@media (forced-colors: active) {
  .nav-list a[aria-current="page"],
  .menu-config a[aria-current="page"] {
    border-left-color:Highlight; background:Canvas; color:Highlight; forced-color-adjust:none;
  }
  .situacao i, .passos b, .checklist b, .cena-n { border-color:CanvasText; forced-color-adjust:none; }
  .hero, .miniatura, .player, .cartao-estilo .amostra {
    background:Canvas !important; border-color:CanvasText;
  }
  .barra { background:Highlight; forced-color-adjust:none; }
  .btn, .btn-primario { border-color:ButtonText; }
  .chip-filtro[aria-pressed="true"] { border-color:Highlight; color:Highlight; forced-color-adjust:none; }
}
"""
