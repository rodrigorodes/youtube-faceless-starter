# Arquivo verbatim — preview.py antes da casca compartilhada (feat/preview-shell)

Extraído de `git show f57dae2:renderer/app/studio/api/preview.py` (base do main no momento da fatia).
Estes blocos foram **removidos** de `renderer/app/studio/api/preview.py`; nada abaixo existe mais na página.

## 1) CSS duplicado do design system (linhas 10–287 do original)

```css
CSS = """
:root {
  color-scheme: light dark;
  --bg: #0f0f0f;
  --sidebar: #0f0f0f;
  --sidebar-hover: #212121;
  --surface: #181818;
  --surface-alt: #212121;
  --surface-hover: #212121;
  --border: #282828;
  --border-hover: #383838;
  --text: #f1f1f1;
  --text-muted: #aaaaaa;
  --primary: #cc0000;
  --primary-hover: #ff0000;
  --primary-focus: rgba(204, 0, 0, 0.28);
  --input-bg: #121212;
  --input-focus-bg: #181818;
  --ok: #2ba640;
  --ok-bg: rgba(43, 166, 64, 0.14);
  --bad: #ff4e45;
  --bad-bg: rgba(255, 78, 69, 0.14);
  --warn: #fbc02d;
  --warn-bg: rgba(251, 192, 45, 0.14);
  --gap: 1.5rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f5f7fb;
    --sidebar: #ffffff;
    --sidebar-hover: #edf2f7;
    --surface: #ffffff;
    --surface-alt: #f0f0f0;
    --surface-hover: #f7fafc;
    --border: #dbe2ec;
    --border-hover: #cbd5e1;
    --text: #1a202c;
    --text-muted: #64748b;
    --primary: #cc0000;
    --primary-hover: #b30000;
    --primary-focus: rgba(204, 0, 0, 0.22);
    --input-bg: #ffffff;
    --input-focus-bg: #ffffff;
    --ok: #1a7f37;
    --ok-bg: rgba(26, 127, 55, 0.12);
    --bad: #cf222e;
    --bad-bg: rgba(207, 34, 46, 0.12);
    --warn: #9a6700;
    --warn-bg: rgba(154, 103, 0, 0.12);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); min-height: 100vh; }

.app-layout {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 250px;
  background: var(--sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 1.25rem 1rem;
  flex-shrink: 0;
  z-index: 10;
}
@media (max-width: 860px) {
  .app-layout { flex-direction: column; }
  .sidebar { width: 100%; height: auto; position: static; border-right: none; border-bottom: 1px solid var(--border); }
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.25rem;
}
.brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary) 0%, #990000 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  box-shadow: 0 2px 6px rgba(204, 0, 0, 0.3);
}
.brand-title {
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
  line-height: 1.2;
}
.brand-sub {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.55rem 0.75rem;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.15s ease;
  text-decoration: none;
}
.nav-item svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 2;
  fill: none;
  flex-shrink: 0;
}
.nav-item:hover {
  background: var(--sidebar-hover);
  color: var(--text);
  text-decoration: none;
}
.nav-item.active {
  background: var(--surface-hover);
  color: var(--primary);
  font-weight: 600;
}

.sidebar-footer {
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--text-muted);
}
.budget-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  margin-bottom: 0.75rem;
}
.budget-bar {
  background: var(--border);
  border-radius: 4px;
  height: 6px;
  overflow: hidden;
  margin: 0.35rem 0 0.25rem;
}
.budget-fill {
  background: var(--primary);
  height: 100%;
}

.main-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.75rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  gap: 1rem;
  flex-wrap: wrap;
}
.content-body {
  padding: 1.75rem;
  max-width: 80rem;
  width: 100%;
}

header { margin-bottom: 1.25rem; }
h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0.35rem; }
h2 { font-size: 1.05rem; font-weight: 600; margin: 1.25rem 0 0.5rem; color: var(--text); }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

.layout { display: grid; gap: var(--gap); grid-template-columns: minmax(18rem, 26rem) 1fr; align-items: start; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
}

video { width: 100%; max-height: 80vh; background: #000; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.25); }

.badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; background: var(--surface); border: 1px solid var(--border); margin-right: 0.35rem; }
.ok { color: var(--ok); }
.bad { color: var(--bad); }

label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-top: 0.85rem; margin-bottom: 0.25rem; }
.hint { font-weight: 400; font-size: 0.78rem; opacity: 0.8; }

input, textarea {
  width: 100%;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem 0.85rem;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text);
  transition: border-color 0.15s, box-shadow 0.15s, background-color 0.15s;
}
input:hover, textarea:hover { border-color: var(--border-hover); }
input:focus-visible, textarea:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
  background: var(--input-focus-bg);
}

button {
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.55rem 1.25rem;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  min-height: 42px;
  margin-top: 0.85rem;
  margin-right: 0.5rem;
  transition: all 0.15s ease;
}
button#approve {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
button#approve:hover {
  background: var(--primary-hover);
  box-shadow: 0 2px 6px var(--primary-focus);
}
button#reject {
  background: var(--surface);
  color: var(--bad);
  border-color: var(--border);
}
button#reject:hover {
  background: var(--bad-bg);
  border-color: var(--bad);
}
button:focus-visible { outline: 3px solid var(--primary); outline-offset: 2px; }

table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 0.5rem; }
th, td { text-align: start; padding: 0.45rem 0.85rem; font-size: 0.82rem; border-bottom: 1px solid var(--border); }
th { color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; font-weight: 600; }
tr:last-child th, tr:last-child td { border-bottom: none; }

ol, ul { padding-left: 1.25rem; font-size: 0.875rem; color: var(--text); }
li { margin-bottom: 0.35rem; }

section[aria-label="Detalhes"] { display: flex; flex-direction: column; gap: 1rem; }
section[aria-label="Detalhes"] .card-panel { margin-top: 0 !important; }
.card-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
"""

```

## 2) `<aside class="sidebar">` hardcoded com a navegação antiga (linhas 373–423 do original)

```html
    sidebar_html = """
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-icon">🎬</div>
        <div>
          <div class="brand-title">FACELESS STUDIO</div>
          <div class="brand-sub">Pipeline de Vídeos</div>
        </div>
      </div>
      <nav class="nav-menu">
        <a class="nav-item" href="/studio/panel">
          <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          <span>Painel</span>
        </a>
        <a class="nav-item" href="/studio/panel#trending-section">
          <svg viewBox="0 0 24 24"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>
          <span>Temas em Alta</span>
        </a>
        <a class="nav-item" href="/studio/panel#videos-section">
          <svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg>
          <span>Vídeos</span>
        </a>
        <a class="nav-item" href="/studio/panel#new-video-section">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
          <span>+ Novo Vídeo</span>
        </a>
        <a class="nav-item" href="/docs" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          <span>API Docs</span>
        </a>
        <a class="nav-item" href="http://localhost:5678" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
          <span>n8n Workflows</span>
        </a>
      </nav>
      <div class="sidebar-footer">
        <div class="budget-card">
          <div style="font-weight: 600; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">TETO MENSAL</div>
          <div style="font-size: 0.85rem; font-weight: 700; margin-top: 0.15rem;">Definido no Painel</div>
          <div class="budget-bar">
            <div class="budget-fill" style="width: 100%;"></div>
          </div>
          <div style="font-size: 0.7rem; color: var(--text-muted);"><a href="/studio/panel">Ver no Painel &rarr;</a></div>
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.72rem;">
          <span style="color: var(--ok); font-size: 0.85rem;">●</span>
          <span>Docker Local / Saudável</span>
        </div>
      </div>
    </aside>
    """

```
