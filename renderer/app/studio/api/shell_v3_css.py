"""CSS da UX V3 — extraído fielmente do protótipo aprovado:
`docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html`.

Tema 100% dark mode nativo com acento roxo (`#8f6ef7`, `#0c0d10`, painéis `#15171c`, linhas `#2c2e37`, Inter).
"""

V3_CSS = """
/* =========================================================================
   Tokens e CSS do Protótipo V4/V3 (docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html)
   Compatibilidade: light-dark(var(--txt-d), var(--txt-d))
   ========================================================================= */
:root {
  color-scheme: dark;
  --bg: #0c0d10;
  --panel: #15171c;
  --panel2: #111216;
  --panel3: #1c1e24;
  --line: #2c2e37;
  --line2: #3b3353;
  --text: #f3f3f7;
  --txt: #f3f3f7;
  --muted: #a3a6b4;
  --sub: #90939f;
  --accent: #8f6ef7;
  --accent2: #b9a3ff;
  --accentbg: #221d33;
  --accentfill: #8f6ef7;
  --onaccent: #14101f;
  --ok: #7fd0a8;
  --okbg: #1d6b48;
  --good: #7fd0a8;
  --warn: #ecc27a;
  --bad: #f08a8a;
  --err: #f08a8a;
  --radius: 12px;
  --hero: linear-gradient(120deg, #1e1b2d, #16161e 68%);
  --soft: #221d33;
}

* { box-sizing: border-box; }
html, body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color-scheme: dark;
}
button, input, select, textarea { font: inherit; color: inherit; }
h1, h2, h3, h4, p { margin: 0; }
a { color: var(--accent2); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Grid e Casca Principal */
.app { display: grid; grid-template-columns: 232px 1fr; min-height: 100vh; }
.side {
  background: var(--panel2);
  border-right: 1px solid var(--line);
  padding: 18px 12px;
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.logo { display: flex; align-items: center; gap: 10px; padding: 4px 10px 16px; font-weight: 780; font-size: 16px; color: var(--text); }
.logo i { font-style: normal; color: var(--accent2); font-size: 20px; }
.side nav { display: flex; flex-direction: column; gap: 2px; }
.side nav ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.side nav li { margin: 0; padding: 0; }
.side nav a, .side nav button {
  all: unset;
  cursor: pointer;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 9px 12px;
  border-radius: 9px;
  color: var(--muted);
  font-weight: 560;
  text-decoration: none;
}
.side nav a svg, .side nav button svg {
  width: 16px;
  height: 16px;
  min-width: 16px;
  min-height: 16px;
  max-width: 16px;
  max-height: 16px;
  flex-shrink: 0;
  display: inline-block;
  vertical-align: middle;
}
.side nav a span[aria-hidden="true"], .side nav button span[aria-hidden="true"] {
  font: inherit;
}
.side nav a:hover, .side nav button:hover { background: var(--panel3); color: var(--text); text-decoration: none; }
.side nav a[aria-current=page], .side nav button[aria-current=page] {
  background: var(--accentbg);
  color: var(--accent2);
  box-shadow: inset 0 0 0 1px var(--line2);
}
.side nav a:focus-visible, .side nav button:focus-visible, .btn:focus-visible, .tab:focus-visible {
  outline: 2px solid var(--accent2);
  outline-offset: 2px;
}
.side .sp { flex: 1; }
.budget {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
  font-size: 12px;
  color: var(--muted);
  margin-top: auto;
}
.bar { height: 6px; background: var(--panel3); border-radius: 4px; overflow: hidden; margin-top: 6px; }
.bar > b { display: block; height: 100%; background: var(--accent); border-radius: 4px; }

/* Topbar */
.main { min-width: 0; display: flex; flex-direction: column; }
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 28px;
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  background: rgba(12, 13, 16, 0.92);
  backdrop-filter: blur(8px);
  z-index: 20;
}
.top .l, .top .r { display: flex; align-items: center; gap: 10px; }
.top .crumb { font-size: 13px; color: var(--muted); margin: 0; }
.top .crumb b { color: var(--text); }
.content { padding: 26px 28px 120px; max-width: 1240px; width: 100%; margin: 0 auto; }

/* Tipografia e Títulos */
.eyebrow { font-size: 11px; font-weight: 750; letter-spacing: 0.8px; text-transform: uppercase; color: var(--accent2); }
h1 { font-size: 26px; font-weight: 780; letter-spacing: -0.3px; color: var(--text); }
h2 { font-size: 19px; font-weight: 720; color: var(--text); }
h3 { font-size: 15px; font-weight: 700; color: var(--text); }
.sub { color: var(--muted); font-size: 13px; }
.head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 22px; flex-wrap: wrap; }

/* Aliases das classes legadas: telas que ainda usam o vocabulário antigo herdam a tipografia do protótipo */
.h1 { font-size: 26px; font-weight: 780; letter-spacing: -0.3px; color: var(--text); }
.lead, .vazio { color: var(--muted); font-size: 13px; }
.micro, .dica { font-size: 11.5px; color: var(--muted); }
.secao-cab { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 22px; flex-wrap: wrap; }
.pilha { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }

/* Cards, Grids e Layout */
.hero {
  background: var(--hero);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 26px;
  margin-bottom: 24px;
}
.card, .painel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px;
}
.card.flat { background: var(--panel2); }
.stack { display: flex; flex-direction: column; gap: 16px; }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.between { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.two { display: grid; grid-template-columns: 1.5fr 1fr; gap: 20px; align-items: start; }

/* Botões */
.btn {
  cursor: pointer;
  background: var(--panel3);
  border: 1px solid var(--line);
  color: var(--text);
  padding: 8px 14px;
  border-radius: 9px;
  font-weight: 600;
  font-size: 13px;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  text-align: center;
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s;
}
.btn:hover { border-color: var(--accent); text-decoration: none; }
.btn.primary, .btn-primary, .btn-primario {
  background: var(--accent);
  border-color: var(--accent);
  color: #14101f !important;
  font-weight: 760;
  box-shadow: 0 4px 16px rgba(143, 110, 247, 0.28);
}
.btn.primary:hover, .btn-primary:hover, .btn-primario:hover { filter: brightness(1.08); }
.btn.ok { background: var(--okbg); border-color: var(--okbg); color: #fff; font-weight: 740; }
.btn.danger, .btn-danger { background: transparent; border-color: rgba(240, 138, 138, 0.45); color: var(--bad); font-weight: 650; }
.btn.danger:hover, .btn-danger:hover { background: rgba(240, 138, 138, 0.12); border-color: var(--bad); }
.acoes { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 2px 0 14px; }
.campo-rejeicao { margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line); }
.btn.ghost, .btn-ghost { background: transparent; border-color: var(--line); }
.btn.ghost:hover, .btn-ghost:hover { background: var(--panel3); }
.btn.small, .btn-sm { padding: 4px 10px; font-size: 12px; border-radius: 7px; }
.btn.long { width: 100%; }
.choice { cursor: pointer; background: var(--panel2); border: 1px solid var(--line); border-radius: 12px; padding: 14px; text-align: left; display: block; width: 100%; color: var(--text); font: inherit; font-size: 14px; line-height: 1.5; }
.choice[aria-pressed=true] { border: 2px solid var(--accent); background: var(--accentbg); padding: 13px; }
.btn[disabled], .btn:disabled { opacity: 0.45; cursor: not-allowed; filter: none; pointer-events: none; }

/* Pílulas (Pills) e Badges */
.pill {
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--panel3);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 3px 11px;
  font-size: 12px;
  color: var(--text);
}
.pill.accent { background: var(--accentbg); border-color: var(--accent); color: var(--accent2); font-weight: 650; }
.pill.ok, .pill.good, .pill-good, .pill-ok { background: rgba(127, 208, 168, 0.13); border-color: rgba(127, 208, 168, 0.35); color: var(--ok); }
.pill.warn, .pill.espera, .pill-espera, .pill-warn { background: rgba(236, 194, 122, 0.12); border-color: rgba(236, 194, 122, 0.35); color: var(--warn); }
.pill.bad, .pill-bad, .pill-FAILED, .pill-REJECTED { background: rgba(240, 138, 138, 0.12); border-color: rgba(240, 138, 138, 0.35); color: var(--bad); }
.pill.info, .pill-info { background: var(--accentbg); border-color: var(--line2); color: var(--accent2); }
.pill.btnlike { cursor: pointer; }
.pill.btnlike:hover { border-color: var(--accent); }

/* Avisos e Notas */
.note, .aviso {
  background: rgba(236, 194, 122, 0.09);
  border: 1px solid rgba(236, 194, 122, 0.28);
  color: var(--warn);
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 12.5px;
}
.note.info, .aviso.info, .aviso-info { background: var(--accentbg); border-color: var(--line2); color: var(--accent2); }
.note.okn, .aviso.ok, .aviso-ok { background: rgba(127, 208, 168, 0.1); border-color: rgba(127, 208, 168, 0.3); color: var(--ok); }

/* Abas (Tabs) */
.tabs, .abas-video {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
}
.tab, .aba, .aba-link {
  all: unset;
  cursor: pointer;
  padding: 10px 14px;
  color: var(--muted);
  font-weight: 600;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
  text-decoration: none;
}
.tab:hover, .aba:hover, .aba-link:hover { color: var(--text); text-decoration: none; }
.tab[aria-current=page], .aba[aria-current=page], .aba.ativa, .tab.ativa {
  color: var(--accent2);
  border-bottom-color: var(--accent);
}
.tab .dot, .aba .dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-left: 6px;
  background: var(--warn);
}

/* Campos e Inputs */
.field, .campo { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.field > label, .campo > label, .lbl, .rotulo { font-size: 12px; color: var(--muted); font-weight: 600; }
input[type=text], input[type=url], input[type=datetime-local], input[type=number], input.input, select, textarea {
  background: var(--panel3);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  width: 100%;
  outline: none;
  color: var(--text);
}
input:focus, select:focus, textarea:focus { border-color: var(--accent); }
textarea { resize: vertical; line-height: 1.55; }
input[type=range] { accent-color: var(--accent); width: 100%; }
input[type=checkbox], input[type=radio] { accent-color: var(--accent); }

/* Segmented Controls (Pills selector) */
.seg {
  display: inline-flex;
  background: var(--panel3);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 2px;
}
.seg button, .seg .seg-btn {
  all: unset;
  cursor: pointer;
  padding: 5px 12px;
  border-radius: 18px;
  font-size: 12.5px;
  color: var(--muted);
  font-weight: 600;
}
.seg button[aria-pressed=true], .seg .seg-btn[aria-pressed=true], .seg button.on {
  background: var(--accentbg);
  color: var(--accent2);
  box-shadow: inset 0 0 0 1px var(--accent);
}

/* Cartões de Modo e Escolha */
.modecard {
  cursor: pointer;
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px;
  text-align: left;
  display: block;
  width: 100%;
}
.modecard[aria-pressed=true] {
  border: 2px solid var(--accent);
  background: var(--accentbg);
  padding: 17px;
}
.modecard h3 { margin: 6px 0 4px; }

/* Storyboard, Mídia e Cenas */
.thumb {
  border-radius: 9px;
  display: grid;
  place-items: center;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
}
.thumb .tag {
  position: absolute;
  top: 6px;
  left: 6px;
  background: rgba(0, 0, 0, 0.66);
  padding: 1px 7px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 650;
}
.thumb .time {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0, 0, 0, 0.66);
  color: var(--accent2);
  padding: 1px 7px;
  border-radius: 5px;
  font-size: 10px;
}
.scene {
  display: grid;
  grid-template-columns: 230px 1fr 210px;
  gap: 16px;
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px;
  align-items: start;
}
.scene.active { border-color: var(--line2); }
.scene .num { font-size: 11px; font-weight: 750; color: var(--accent2); letter-spacing: 0.5px; }
.scene textarea { background: var(--bg); font-size: 13.5px; }
.player { background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 10px; }
.prog { height: 4px; background: var(--panel3); border-radius: 3px; overflow: hidden; margin: 8px 0; }
.prog b { display: block; height: 100%; width: 0; background: var(--accent2); }

/* Dock Flutuante */
.dock {
  position: fixed;
  left: calc(232px + 28px);
  right: 28px;
  bottom: 18px;
  max-width: 1184px;
  margin: 0 auto;
  background: rgba(21, 23, 28, 0.96);
  border: 1px solid var(--line2);
  border-radius: 14px;
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.55);
  z-index: 25;
  backdrop-filter: blur(8px);
  flex-wrap: wrap;
}

/* Gates e Verificações */
.gate {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 10px 14px;
  align-items: center;
}
.gate small { display: block; color: var(--muted); font-size: 11.5px; }

/* Tabela de Vídeos */
.vtable, .tabela-lista { width: 100%; border-collapse: collapse; }
.vtable th, .tabela-lista th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--muted);
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
}
.vtable td, .tabela-lista td { padding: 12px; border-bottom: 1px solid var(--line); vertical-align: middle; }
.vtable tr.click { cursor: pointer; }
.vtable tr.click:hover td { background: var(--panel); }

/* Frame de Prévia e Composição */
.frame {
  background: #000;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  position: relative;
  margin: 0 auto;
  display: grid;
  place-items: center;
}
.frame.r169 { aspect-ratio: 16/9; width: 100%; }
.frame.r916 { aspect-ratio: 9/16; width: 230px; }
.frame .bg { position: absolute; inset: 0; animation: ken 12s ease-in-out infinite alternate; }
@keyframes ken { from { transform: scale(1); } to { transform: scale(1.08); } }
.frame.static .bg { animation: none; }
.toast { position: fixed; right: 22px; top: 70px; background: var(--panel); border: 1px solid var(--accent); color: var(--text); padding: 10px 16px; border-radius: 10px; z-index: 80; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5); font-size: 13px; max-width: 360px; }
.chart { display: flex; align-items: flex-end; gap: 8px; height: 130px; padding-top: 10px; }
.chart div { flex: 1; background: linear-gradient(180deg, var(--accent), #4a3a8a); border-radius: 5px 5px 0 0; min-height: 4px; position: relative; }
.chart div span { position: absolute; bottom: -20px; left: 0; right: 0; text-align: center; font-size: 10px; color: var(--muted); }
.cap {
  position: absolute;
  left: 8%;
  right: 8%;
  text-align: center;
  font-weight: 750;
  text-shadow: 0 2px 6px #000;
  padding: 4px 8px;
  border-radius: 6px;
}
.track { display: flex; align-items: center; gap: 10px; font-size: 11.5px; margin-bottom: 6px; }
.track > span { width: 70px; color: var(--muted); flex: none; }
.track > div {
  flex: 1;
  height: 22px;
  border-radius: 5px;
  border: 1px solid var(--line);
  display: flex;
  align-items: center;
  padding: 0 9px;
  background: var(--panel3);
  overflow: hidden;
  white-space: nowrap;
}

/* Modais e Diálogos */
dialog, dialog.modal, .modal {
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 16px;
  padding: 22px;
  width: min(560px, 100%);
  max-height: 88vh;
  overflow: auto;
  color: var(--text);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.65);
}
dialog::backdrop { background: rgba(5, 5, 8, 0.72); overflow: hidden; overscroll-behavior: contain; }
.modal-header, .dialogo-cab {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.modal-header h2, .modal-header h3, .dialogo-cab h2, .dialogo-cab h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 750;
  color: var(--txt);
}
.modal-close, button[data-fechar-dialogo] {
  background: transparent;
  border: 0;
  color: var(--muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px 8px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}
.modal-close:hover, button[data-fechar-dialogo]:hover {
  background: var(--panel2);
  color: var(--txt);
}
.modal-footer {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  align-items: center;
}

/* Utilitários */
.skip { position: absolute; left: -9999px; }
.skip:focus { left: 12px; top: 12px; z-index: 100; background: var(--panel); padding: 10px; }
.canal-select { width: auto; min-width: 210px; max-width: 100%; }
.seg .seg-btn:has(input:checked) { background: var(--accentbg); color: var(--accent2); box-shadow: inset 0 0 0 1px var(--accent); }
.seg .seg-btn:focus-within, .modecard:focus-within { outline: 2px solid var(--accent2); outline-offset: 2px; }
.tog { display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none; }
.tog input { position:absolute;opacity:0; }
.tog i { width:34px;height:20px;border-radius:12px;background:var(--panel3);border:1px solid var(--line);position:relative;flex:none;pointer-events:none;transition:0.15s; }
.tog i:after { content:"";position:absolute;left:2px;top:2px;width:14px;height:14px;border-radius:50%;background:var(--muted);transition:0.15s; }
.tog input:checked+i { background:var(--accentbg);border-color:var(--accent); }
.tog input:checked+i:after { left:16px;background:var(--accent2); }
.tog input:focus-visible+i { outline:2px solid var(--accent2);outline-offset:2px; }
.feedback:empty { display: none; }
.feedback.erro { color: var(--bad); }
.hr { border: 0; border-top: 1px solid var(--line); margin: 14px 0; }
.sr, .sr-only { position: absolute; left: -9999px; }
.mono { font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: var(--muted); }
.sample { font-size: 11.5px; color: var(--muted); }
.prog.run b { animation: fill var(--d, 4s) linear forwards; }
@keyframes fill { to { width: 100%; } }
.step { display: flex; gap: 12px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid var(--line); }
.step:last-child { border: 0; }
.ic { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 800; flex: none; background: var(--panel3); border: 1px solid var(--line); color: var(--muted); }
.ic.ok { background: var(--okbg); border-color: var(--okbg); color: #fff; }
.ic.run { border-color: var(--accent); color: var(--accent2); animation: pulse 1s infinite; }
.ic.fail { background: #6b1d1d; border-color: #6b1d1d; color: #fff; }
@keyframes pulse { 50% { box-shadow: 0 0 0 5px rgba(143, 110, 247, 0.25); } }
details.diag { background: var(--panel2); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
details.diag summary { cursor: pointer; font-weight: 650; color: var(--muted); }

/* Responsividade */
@media (max-width: 1000px) {
  .app { grid-template-columns: 1fr; }
  .side { position: static; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; }
  .side nav, .side nav ul { flex-direction: row; flex-wrap: wrap; }
  .grade, .grade-tendencias { grid-template-columns: minmax(0, 1fr); }
  .pill { max-width:100%; }
  .top .l, .top .r, .row, .between { min-width:0; }
  .cartao-tendencia, .cartao-projeto { min-width:0; overflow-wrap:anywhere; }
  .side .budget, .side .sp { display: none; }
  .scene, .two, .grid2, .grid3, .grid4 { grid-template-columns: 1fr; }
  .two > *, .scene > * { min-width: 0; }  /* o protótipo estoura a largura aqui (trilhas nowrap); não repetimos o defeito */
  .dock { left: 12px; right: 12px; bottom: 64px; }
  .content { padding: 18px 14px 150px; }
  .top { padding: 12px 14px; flex-wrap: wrap; }
  .top .l, .top .r { flex-wrap: wrap; }
  #chstyle { display: none; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
"""
