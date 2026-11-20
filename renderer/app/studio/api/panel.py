"""Páginas HTML do painel do Studio (operacional e detalhe de vídeo).
Sem dependências externas; todo texto é escapado e a CSP é protegida por nonce.
"""
import html
import secrets

from ..application.panel import PanelView, VideoDetailView
from ..domain.panel import Stage, is_known_cost

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

CSS = """
:root {
  color-scheme: light dark;
  --bg: #0f0f0f;
  --sidebar: #0f0f0f;
  --sidebar-hover: #212121;
  --surface: #181818;
  --surface-alt: #212121;
  --surface-hover: #212121;
  --surface-elevated: #282828;
  --border: #282828;
  --border-hover: #383838;
  --text: #f1f1f1;
  --text-muted: #aaaaaa;
  --text-faint: #717171;
  --primary: #cc0000;
  --primary-hover: #ff0000;
  --primary-focus: rgba(204, 0, 0, 0.28);
  --input-bg: #121212;
  --input-focus-bg: #181818;
  --ok: #2ba640;
  --ok-bg: rgba(43, 166, 64, 0.14);
  --warn: #fbc02d;
  --warn-bg: rgba(251, 192, 45, 0.14);
  --bad: #ff4e45;
  --bad-bg: rgba(255, 78, 69, 0.14);
  --info: #3ea6ff;
  --info-bg: rgba(62, 166, 255, 0.14);
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
    --surface-elevated: #ffffff;
    --border: #dbe2ec;
    --border-hover: #cbd5e1;
    --text: #1a202c;
    --text-muted: #64748b;
    --text-faint: #94a3b8;
    --primary: #cc0000;
    --primary-hover: #b30000;
    --primary-focus: rgba(204, 0, 0, 0.22);
    --input-bg: #ffffff;
    --input-focus-bg: #ffffff;
    --ok: #1a7f37;
    --ok-bg: rgba(26, 127, 55, 0.12);
    --warn: #9a6700;
    --warn-bg: rgba(154, 103, 0, 0.12);
    --bad: #cf222e;
    --bad-bg: rgba(207, 34, 46, 0.12);
    --info: #0969da;
    --info-bg: rgba(9, 105, 218, 0.12);
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

h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.01em; }
h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.5rem; }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

label, .form-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

input, select, textarea {
  box-sizing: border-box;
}

input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]),
select,
textarea {
  width: 100%;
  display: block;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem 0.9rem;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text);
  line-height: 1.5;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
}
input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):hover,
select:hover,
textarea:hover {
  border-color: var(--border-hover);
}
input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
  background: var(--input-focus-bg);
}
input::placeholder, textarea::placeholder {
  color: var(--text-faint);
  opacity: 1;
}

select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238897a8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  padding-right: 2.25rem;
  cursor: pointer;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  min-height: 40px;
  min-width: 40px;
  line-height: 1.4;
  text-align: center;
  transition: all 0.15s ease;
  text-decoration: none;
}
.btn:hover {
  background: var(--surface-hover);
  border-color: var(--border-hover);
  text-decoration: none;
}
.btn-primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.btn-primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
  box-shadow: 0 2px 6px var(--primary-focus);
}
.btn:focus-visible { outline: 3px solid var(--primary); outline-offset: 2px; }

.grid-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
  margin-bottom: 1.75rem;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.card-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.04em;
  margin-bottom: 0.35rem;
}
.card-value {
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.card-sub {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.filter-bar {
  display: flex;
  gap: 0.35rem;
  align-items: center;
  font-size: 0.82rem;
  background: var(--input-bg);
  padding: 0.25rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.filter-link {
  padding: 0.3rem 0.75rem;
  border-radius: 6px;
  color: var(--text-muted);
  font-weight: 500;
  transition: all 0.15s ease;
  text-decoration: none;
}
.filter-link:hover {
  color: var(--text);
  text-decoration: none;
}
.filter-link.active {
  background: var(--surface-hover);
  color: var(--text);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 1.5rem;
}
th, td {
  padding: 0.85rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 0.875rem;
}
th {
  background: rgba(0,0,0,0.12);
  color: var(--text-muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.04em;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--surface-hover); }

.pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 12px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.pill-PENDING { background: var(--border); color: var(--text-muted); }
.pill-IN_PRODUCTION { background: var(--info-bg); color: var(--info); border: 1px solid var(--info); }
.pill-AWAITING_APPROVAL { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }
.pill-APPROVED { background: var(--ok-bg); color: var(--ok); border: 1px solid var(--ok); }
.pill-COMPLETED { background: var(--ok-bg); color: var(--ok); }
.pill-FAILED { background: var(--bad-bg); color: var(--bad); border: 1px solid var(--bad); }
.pill-REJECTED { background: var(--bad-bg); color: var(--bad); }

.warning {
  background: var(--warn-bg);
  color: var(--warn);
  padding: 0.85rem 1.15rem;
  border-radius: 8px;
  border: 1px solid rgba(227, 179, 65, 0.25);
  margin-bottom: 1.25rem;
  font-size: 0.85rem;
}
.empty {
  text-align: center;
  padding: 2.5rem 1rem;
  color: var(--text-muted);
}

.timeline { list-style: none; padding-left: 1.5rem; position: relative; }
.timeline-item { position: relative; margin-bottom: 1.25rem; }
.timeline-dot {
  position: absolute;
  left: -1.5rem;
  top: 0.25rem;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
}
.timeline-title { font-weight: 600; font-size: 0.875rem; }
.timeline-desc { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.15rem; }
.layout-detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1.25rem; }

details summary::-webkit-details-marker { display: none !important; }

/* Creation Form Section */
.new-video-section {
  margin-bottom: 1.75rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.new-video-section[open] {
  border-color: var(--primary);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
.new-video-summary {
  display: block;
  padding: 0.85rem 1.25rem;
  background: var(--surface);
  cursor: pointer;
  user-select: none;
  list-style: none;
}
.new-video-summary-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.new-video-section[open] .new-video-summary {
  border-bottom: 1px solid var(--border);
  background: var(--surface-hover);
}
.new-video-form {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem;
  width: 100%;
}
.form-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.25rem;
  flex-wrap: wrap;
}
.form-feedback {
  font-size: 0.85rem;
  font-weight: 500;
}

/* Trending Section */
.trends-card {
  margin-bottom: 1.75rem;
  background: linear-gradient(180deg, rgba(204, 0, 0, 0.04) 0%, var(--surface) 100%);
}
.trends-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.85rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.trends-title {
  font-weight: 700;
  font-size: 1.05rem;
  display: flex;
  align-items: center;
}
.trends-source {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--input-bg);
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.trend-item {
  background: #181818;
  border: 1px solid #282828;
  border-radius: 12px;
  padding: 1rem;
  margin-bottom: 0.85rem;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  transition: border-color 0.15s ease;
}
.trend-item:hover {
  border-color: #383838;
}
.trend-thumb-link {
  text-decoration: none;
  display: block;
  flex-shrink: 0;
}
.trend-thumb {
  width: 168px;
  height: 94px;
  border-radius: 8px;
  position: relative;
  overflow: hidden;
  background: #000;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.trend-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}
.trend-thumb:hover img {
  transform: scale(1.05);
}
.trend-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: #212121;
  color: #606060;
}
.thumb-play-overlay {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  font-size: 0.68rem;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 4px;
  line-height: 1.2;
}
.trend-content {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  flex: 1;
  min-width: 0;
}
.trend-top-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  width: 100%;
}
.trend-topic-name {
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  color: var(--text);
  line-height: 1.35;
}
.trend-title-link {
  text-decoration: none;
  color: #f1f1f1;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  word-break: break-word;
}
.trend-title-link:hover .trend-topic-name {
  text-decoration: underline;
  color: #ffffff;
}
.trend-external-icon {
  font-size: 0.82rem;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: transform 0.15s ease, color 0.15s ease;
}
.trend-title-link:hover .trend-external-icon {
  transform: translate(1px, -1px);
  color: #38bdf8;
}
.trend-badges {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  align-items: center;
}
.trend-meta-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.82rem;
  color: var(--text-muted);
  flex-wrap: wrap;
}
.trend-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
.trend-actions-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-top: 0.25rem;
}
.btn-watch-yt {
  background: #272727;
  color: #f1f1f1;
  border: 1px solid #383838;
  text-decoration: none;
  font-weight: 500;
  font-size: 0.82rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.btn-watch-yt:hover {
  background: #cc0000;
  border-color: #cc0000;
  color: #ffffff;
}
.badge-region-br {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
  font-weight: 600;
}
.badge-region-global {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.3);
  font-weight: 600;
}
.badge-pillar {
  background: #272727;
  color: #e5e5e5;
  border: 1px solid #383838;
  font-weight: 500;
}
@media (max-width: 640px) {
  .trend-item {
    flex-direction: column;
  }
  .trend-thumb {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
  }
}
.chip-metric {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.6rem;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.evidence-list {
  margin-top: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  width: 100%;
}
.evidence-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.55rem 0.85rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.82rem;
  width: 100%;
}
.evidence-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-views {
  color: var(--info);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  margin-left: 1.5rem;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Trends Actions and Category Pills */
.trends-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.cat-pills-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  margin: 0.85rem 0;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--border);
}
.cat-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 5px 14px;
  border-radius: 18px;
  background: #272727;
  border: 1px solid transparent;
  color: #f1f1f1;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}
.cat-pill:hover {
  background: #383838;
  color: #ffffff;
}
.cat-pill.active {
  background: #f1f1f1;
  border-color: transparent;
  color: #0f0f0f;
  font-weight: 600;
}
.cat-pill-btn {
  background: transparent;
  border: 1px dashed #3f3f3f;
  color: #aaa;
}
.cat-pill-btn:hover {
  border-style: solid;
  border-color: #f1f1f1;
  color: #f1f1f1;
  background: #272727;
}
.chip-category {
  background: var(--surface-elevated);
  border-color: var(--primary);
  color: var(--primary);
  font-weight: 600;
}

/* Category Management Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
  backdrop-filter: blur(2px);
}
.modal-content {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.modal-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 1.4rem;
  cursor: pointer;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  line-height: 1;
}
.modal-close:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.cat-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.cat-list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-elevated);
  gap: 0.75rem;
}
.cat-item-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.cat-item-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
}

/* Topic Groups / Videos Details */
.topic-group-card {
  margin-bottom: 1.25rem;
  padding: 0.85rem 1.15rem;
}
.topic-group-summary {
  display: block;
  cursor: pointer;
  margin-bottom: 0.75rem;
  user-select: none;
  list-style: none;
}
.topic-group-summary-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.topic-group-title {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.topic-group-label {
  font-size: 0.95rem;
  font-weight: 700;
}
.topic-group-cost {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 500;
}
.action-buttons {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.btn-compact {
  min-height: 32px;
  padding: 0.25rem 0.75rem;
  font-size: 0.8rem;
}

/* Inline loading spinner */
.spinner-inline {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 0.35rem;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Topic input pulse/glow highlight */
@keyframes topicPulse {
  0% {
    box-shadow: 0 0 0 0 rgba(204, 0, 0, 0.6);
    border-color: var(--primary);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(204, 0, 0, 0.2);
    border-color: var(--primary);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(204, 0, 0, 0);
    border-color: var(--border);
  }
}
.topic-pulse {
  animation: topicPulse 1.2s ease-out;
}
"""


def _headers(nonce: str) -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            f"default-src 'none'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "img-src 'self' data: https://i.ytimg.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def render_panel(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    days = view.days

    filters_html = "".join(
        f'<a class="filter-link {"active" if d == days else ""}" href="/studio/panel?days={d}">{d} dias</a>'
        for d in (7, 14, 30)
    )

    warning_html = (
        '<div class="warning">Aviso: exibindo os 500 vídeos mais recentes do período selecionado.</div>'
        if view.truncated else ""
    )

    project_options = "".join(f'<option value="{e(p[0])}">{e(p[1])}</option>' for p in view.projects)
    create_form_html = f"""
      <details class="new-video-section" id="new-video-section">
        <summary class="new-video-summary">
          <div class="new-video-summary-inner">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <span class="btn btn-primary btn-compact">+ Novo Vídeo</span>
              <span style="font-size: 0.85rem; color: var(--text-muted);">Criar vídeo a partir de tema ou tendência</span>
            </div>
            <span style="font-size: 0.8rem; color: var(--text-muted);">Clique para expandir</span>
          </div>
        </summary>
        <form id="create-video-form" class="new-video-form">
          <div class="form-grid-2">
            <div>
              <label for="new-video-project">Projeto</label>
              <select id="new-video-project" name="project_id" required>
                {project_options}
              </select>
            </div>
            <div>
              <label for="new-video-format">Formato</label>
              <select id="new-video-format" name="format">
                <option value="short">Short (vertical 1080x1920)</option>
                <option value="long">Long (horizontal 1920x1080)</option>
              </select>
            </div>
          </div>
          <div>
            <label for="topic">Tema <span style="font-weight: 400; opacity: 0.75;">(3 a 300 caracteres)</span></label>
            <input type="text" id="topic" name="topic" class="new-video-topic" minlength="3" maxlength="300" placeholder="Ex: ADE Lineup 2026 Revelado" required>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="btn-create-video">Criar Vídeo</button>
            <div id="create-video-feedback" class="form-feedback"></div>
          </div>
        </form>
      </details>
    """

    current_project_id = view.project_id or (view.projects[0][0] if view.projects else "")

    total_trends = len(view.trends)
    br_count = sum(1 for t in view.trends if t.region == "BR")
    global_count = sum(1 for t in view.trends if t.region == "GLOBAL")

    pills = [
        f'<button type="button" class="cat-pill active" data-filter-type="all">🔥 Todas ({total_trends})</button>',
        f'<button type="button" class="cat-pill" data-filter-type="region" data-region-code="BR">🇧🇷 Em Alta Brasil ({br_count})</button>',
        f'<button type="button" class="cat-pill" data-filter-type="region" data-region-code="GLOBAL">🌍 Em Alta Mundo ({global_count})</button>',
    ]
    for cat in view.categories:
        cat_count = sum(1 for t in view.trends if t.category_id == cat.id)
        pills.append(
            f'<button type="button" class="cat-pill" data-filter-type="category" data-cat-id="{e(cat.id)}" data-category-id="{e(cat.id)}">🏷️ {e(cat.name)} ({cat_count})</button>'
        )
    pills.append('<button type="button" class="cat-pill cat-pill-btn" id="btn-open-categories-modal">+ Novo Pilar</button>')
    cat_pills_html = f'<div class="cat-pills-bar">{"".join(pills)}</div>'

    action_buttons_html = f"""
      <div class="trends-actions">
        <button type="button" class="btn btn-compact" id="btn-refresh-trends" data-project-id="{e(current_project_id)}">🔄 Buscar Agora</button>
        <button type="button" class="btn btn-compact" id="btn-manage-categories" data-project-id="{e(current_project_id)}">⚙️ Gerenciar Categorias ({len(view.categories)})</button>
      </div>
    """

    if view.trends_status == "never_collected" or not view.trends:
        trends_html = f"""
          <div class="card trends-card" style="margin-bottom: 1.75rem;" id="trending-section">
            <div class="trends-header">
              <div class="trends-title">
                <span>🔥 Temas em Alta nos Últimos {days} Dias</span>
              </div>
              {action_buttons_html}
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            <div class="empty" style="padding: 1.5rem 1rem;">Ainda não há coleta de tendências registrada para o período selecionado. Clique em <strong>Buscar Agora</strong> para atualizar.</div>
          </div>
        """
    else:
        last_dt_str = view.last_collected_at.strftime("%d/%m %H:%M") if view.last_collected_at else ""
        stale_badge = ' <span class="pill pill-FAILED" style="margin-left: 0.5rem;">Desatualizado</span>' if view.trends_status == "stale" else ""
        items_html = []
        for t in view.trends:
            ev_list = []
            for ev in t.evidence:
                ev_title = e(ev.get("title", ""))
                ev_chan = e(ev.get("channel", ""))
                ev_views = f"{int(ev['views']):,} views".replace(",", ".") if ev.get("views") is not None else ""
                ev_list.append(
                    f"<div role='listitem' class='evidence-item'>"
                    f"<div class='evidence-title'><span style='color: var(--primary); font-size: 0.75rem; flex-shrink: 0;'>▶</span> <strong style='color: var(--text);'>{ev_title}</strong> <span style='color: var(--text-muted);'>· {ev_chan}</span></div>"
                    f"<div class='evidence-views'>{ev_views}</div>"
                    f"</div>"
                )
            ev_html = f'<div role="list" class="evidence-list">{"".join(ev_list)}</div>' if ev_list else ""

            # Thumbnail markup
            if t.thumbnail_url:
                thumb_inner = f'<img src="{e(t.thumbnail_url)}" alt="{e(t.topic)}" loading="lazy" class="trend-thumb-img" /><span class="thumb-play-overlay">▶</span>'
            else:
                thumb_inner = (
                    '<div class="trend-thumb-placeholder">'
                    '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#606060" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<rect x="2" y="4" width="20" height="16" rx="4"></rect>'
                    '<polygon points="10 8 16 12 10 16 10 8" fill="#606060"></polygon>'
                    '</svg>'
                    '</div>'
                )

            if t.video_url:
                thumb_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-thumb-link" aria-label="Assistir {e(t.topic)} no YouTube">'
                    f'<div class="trend-thumb">{thumb_inner}</div>'
                    f'</a>'
                )
            else:
                thumb_html = f'<div class="trend-thumb">{thumb_inner}</div>'

            # Badges row
            badges_parts = []
            if t.region == "BR":
                badges_parts.append('<span class="chip-metric badge-region-br">🇧🇷 Em Alta Brasil</span>')
            elif t.region == "GLOBAL":
                badges_parts.append('<span class="chip-metric badge-region-global">🌍 Em Alta Mundo</span>')

            if t.category_name:
                badges_parts.append(f'<span class="chip-metric chip-category badge-pillar">🏷️ {e(t.category_name)}</span>')

            if t.metric_text:
                badges_parts.append(f'<span class="chip-metric" style="color: var(--info); font-weight: 600;">📊 {e(t.metric_text)}</span>')

            completed_count = t.counts.get(Stage.COMPLETED, 0)
            in_prod_count = t.counts.get(Stage.IN_PRODUCTION, 0)
            badges_parts.append(f'<span class="chip-metric">🎬 {completed_count} concluídos · {in_prod_count} em produção</span>')
            badges_parts.append(f'<span class="chip-metric">💰 Custo: {e(t.cost_text)}</span>')

            badges_html = f'<div class="trend-badges">{"".join(badges_parts)}</div>'

            # Title
            if t.video_url:
                title_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-title-link">'
                    f'<span class="trend-topic-name">{e(t.topic)}</span>'
                    f'<span class="trend-external-icon">↗</span>'
                    f'</a>'
                )
            else:
                title_html = f'<div class="trend-topic-name">{e(t.topic)}</div>'

            # Channel & metadata
            views_str = None
            if t.evidence and t.evidence[0].get("views") is not None:
                views_str = f"{int(t.evidence[0]['views']):,} views".replace(",", ".")
            elif t.metric_text:
                views_str = t.metric_text

            meta_parts = [f'<span class="trend-meta-item">📺 {e(t.channel_title or "Canal")}</span>']
            if views_str:
                meta_parts.append(f'<span class="trend-meta-item">👁️ {e(views_str)}</span>')
            if t.published_text:
                meta_parts.append(f'<span class="trend-meta-item">⏱️ {e(t.published_text)}</span>')
            meta_html = f'<div class="trend-meta-row">{" · ".join(meta_parts)}</div>'

            # Action buttons
            action_buttons = []
            if t.video_url:
                action_buttons.append(
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-compact btn-watch-yt">▶️ Assistir no YouTube</a>'
                )
            if t.create_action:
                action_buttons.append(
                    f'<button type="button" class="btn btn-primary btn-create-from-trend" data-topic="{e(t.topic)}" style="white-space: nowrap;">✨ Criar Vídeo deste Tema</button>'
                )
            actions_html = f'<div class="trend-actions-row">{"".join(action_buttons)}</div>' if action_buttons else ""

            items_html.append(f"""
              <div class="trend-item" data-category-id="{e(t.category_id or '')}" data-region="{e(t.region or '')}">
                {thumb_html}
                <div class="trend-content">
                  {badges_html}
                  {title_html}
                  {meta_html}
                  {actions_html}
                  {ev_html}
                </div>
              </div>
            """)

        trends_html = f"""
          <div class="card trends-card" id="trending-section">
            <div class="trends-header">
              <div class="trends-title">
                <span>🔥 Temas em Alta nos Últimos {days} Dias</span>{stale_badge}
              </div>
              <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
                <div class="trends-source">
                  Fonte: <a href="{e(view.trends[0].source_url)}" target="_blank" rel="noopener noreferrer">{e(view.trends[0].source_name)}</a> · Consulta: {last_dt_str}
                </div>
                {action_buttons_html}
              </div>
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            {''.join(items_html)}
          </div>
        """

    if not view.topics:
        body_html = '<div class="card empty">Nenhum vídeo no período selecionado.</div>'
    else:
        topic_blocks = []
        for g in view.topics:
            rows = []
            for v in g.videos:
                actions_html = []
                if "preview" in v.actions:
                    actions_html.append(f'<a class="btn btn-primary btn-compact" href="/studio/videos/{e(v.id)}/preview">Ver Prévia</a>')
                if "progress" in v.actions:
                    actions_html.append(f'<a class="btn btn-compact" href="/studio/panel/videos/{e(v.id)}">Ver Progresso</a>')

                date_str = v.updated_at.strftime("%d/%m %H:%M")
                rows.append(f"""
                  <tr>
                    <td><strong>{e(v.topic)}</strong></td>
                    <td><span class="pill pill-{e(v.stage.value)}">{e(v.stage.value)}</span></td>
                    <td style="font-variant-numeric: tabular-nums;">{e(v.cost_text)}</td>
                    <td style="color: var(--text-muted); font-size: 0.82rem;">{date_str}</td>
                    <td><div class="action-buttons">{' '.join(actions_html)}</div></td>
                  </tr>
                """)

            table_html = f"""
              <table>
                <thead>
                  <tr>
                    <th scope="col" style="width: 40%;">Tema</th>
                    <th scope="col">Etapa</th>
                    <th scope="col">Custo</th>
                    <th scope="col">Atualizado</th>
                    <th scope="col">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                </tbody>
              </table>
            """
            topic_blocks.append(f"""
              <details open class="card topic-group-card">
                <summary class="topic-group-summary">
                  <div class="topic-group-summary-inner">
                    <div class="topic-group-title">
                      <span class="topic-group-label">{e(g.label)}</span>
                      <span class="chip-metric" style="font-size: 0.72rem;">{len(g.videos)} vídeo{'s' if len(g.videos) > 1 else ''}</span>
                    </div>
                    <span class="topic-group-cost">{e(g.cost_text)}</span>
                  </div>
                </summary>
                {table_html}
              </details>
            """)
        body_html = "".join(topic_blocks)

    cat_items = []
    if not view.categories:
        categories_list_html = '<div class="empty" style="padding: 1rem; font-size: 0.85rem;" id="empty-cat-msg">Nenhum pilar cadastrado ainda. Preencha o formulário abaixo para adicionar o primeiro.</div>'
    else:
        for c in view.categories:
            queries_str = ", ".join(c.queries)
            queries_disp = e(queries_str) if c.queries else "Nenhum termo definido"
            cat_items.append(f"""
              <div class="cat-list-item" data-category-id="{e(c.id)}">
                <div class="cat-item-info">
                  <strong style="color: var(--text);">{e(c.name)}</strong>
                  <span style="color: var(--text-muted); font-size: 0.78rem;">Termos: {queries_disp}</span>
                </div>
                <div class="cat-item-actions">
                  <button type="button" class="btn btn-compact btn-edit-category" data-id="{e(c.id)}" data-name="{e(c.name)}" data-queries="{e(queries_str)}">Editar</button>
                  <button type="button" class="btn btn-compact btn-delete-category" data-id="{e(c.id)}" data-name="{e(c.name)}" style="color: var(--bad); border-color: var(--bad);">Excluir</button>
                </div>
              </div>
            """)
        categories_list_html = "".join(cat_items)

    modal_html = f"""
      <div class="modal-overlay" id="categories-modal" role="dialog" aria-modal="true" aria-labelledby="modal-categories-title">
        <div class="modal-content">
          <div class="modal-header">
            <div class="modal-title" id="modal-categories-title">Gerenciar Categorias (Pilares de Conteúdo)</div>
            <button type="button" class="modal-close" id="btn-close-modal" aria-label="Fechar">&times;</button>
          </div>
          <div class="modal-body">
            <div>
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.5rem;">Pilares Cadastrados</div>
              <div class="cat-list" id="modal-categories-list">
                {categories_list_html}
              </div>
            </div>

            <div style="border-top: 1px solid var(--border); padding-top: 1rem;">
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.65rem;" id="category-form-title">Novo Pilar de Conteúdo</div>
              <form id="form-category" style="display: flex; flex-direction: column; gap: 0.85rem;">
                <input type="hidden" id="category-id" name="id" value="">
                <div>
                  <label for="category-name">Nome do Pilar</label>
                  <input type="text" id="category-name" name="name" minlength="1" maxlength="100" placeholder="Ex: Tecnologia e IA" required>
                </div>
                <div>
                  <label for="category-queries">Termos de Busca <span style="font-weight: 400; opacity: 0.75;">(separados por vírgula, máx 10)</span></label>
                  <input type="text" id="category-queries" name="queries" placeholder="Ex: IA, inteligência artificial, ChatGPT">
                </div>
                <div class="form-actions">
                  <button type="submit" class="btn btn-primary" id="btn-save-category">Salvar Pilar</button>
                  <button type="button" class="btn btn-compact" id="btn-cancel-edit-category" style="display: none;">Cancelar</button>
                  <div id="category-form-feedback" class="form-feedback"></div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    """

    pct_width = min(100.0, max(0.0, view.month.percent or 0.0))

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Faceless Studio — Painel</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-icon">🎬</div>
        <div>
          <div class="brand-title">FACELESS STUDIO</div>
          <div class="brand-sub">Pipeline de Vídeos</div>
        </div>
      </div>
      <nav class="nav-menu">
        <a class="nav-item active" href="/studio/panel">
          <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          <span>Painel</span>
        </a>
        <a class="nav-item" href="#trending-section">
          <svg viewBox="0 0 24 24"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>
          <span>Temas em Alta</span>
        </a>
        <a class="nav-item" href="#videos-section">
          <svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg>
          <span>Vídeos</span>
        </a>
        <a class="nav-item" href="#new-video-section" id="nav-btn-new-video">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
          <span>Novo Vídeo</span>
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
          <div style="font-weight: 600; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Teto Mensal</div>
          <div style="font-size: 0.85rem; font-weight: 700; margin-top: 0.15rem;">{e(view.month.text)}</div>
          <div class="budget-bar">
            <div class="budget-fill" style="width: {pct_width:.1f}%;"></div>
          </div>
          <div style="font-size: 0.7rem; color: var(--text-muted);">Teto: US$ {view.month.cap_usd:.2f}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.72rem;">
          <span style="color: var(--ok); font-size: 0.85rem;">●</span>
          <span>Docker Local / Saudável</span>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <h1>Painel Operacional</h1>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Produção, validação editorial e custos</div>
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <div class="filter-bar">
            <span style="padding-left: 0.4rem; color: var(--text-muted);">Período:</span>
            {filters_html}
          </div>
        </div>
      </header>

      <div class="content-body">
        <div class="grid-summary">
          <div class="card">
            <div class="card-label">Em Produção</div>
            <div class="card-value" style="color: var(--info);">{view.totals.get(Stage.IN_PRODUCTION, 0)}</div>
            <div class="card-sub">Jobs de render/mídia ativos</div>
          </div>
          <div class="card">
            <div class="card-label">Aguardando Aprovação</div>
            <div class="card-value" style="color: var(--warn);">{view.totals.get(Stage.AWAITING_APPROVAL, 0)}</div>
            <div class="card-sub">Exigem revisão humana</div>
          </div>
          <div class="card">
            <div class="card-label">Concluídos</div>
            <div class="card-value" style="color: var(--ok);">{view.totals.get(Stage.COMPLETED, 0)}</div>
            <div class="card-sub">No período selecionado</div>
          </div>
          <div class="card">
            <div class="card-label">Gasto no Mês vs Teto</div>
            <div class="card-value">{e(view.month.text)}</div>
            <div class="card-sub">Teto mensal: US$ {view.month.cap_usd:.2f}</div>
          </div>
        </div>

        {create_form_html}

        {trends_html}

        {warning_html}

        <h2 id="videos-section">Vídeos</h2>
        {body_html}
      </div>
    </main>
  </div>
  {modal_html}
  <script nonce="{nonce}">
    const form = document.getElementById('create-video-form');
    if (form) {{
      form.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const btn = document.getElementById('btn-create-video');
        const feedback = document.getElementById('create-video-feedback');
        const project_id = document.getElementById('new-video-project').value;
        const topicInput = document.getElementById('topic') || document.getElementById('new-video-topic');
        const topic = topicInput ? topicInput.value.trim() : '';
        const format = document.getElementById('new-video-format').value;
        if (!topic) return;
        if (btn) btn.disabled = true;
        feedback.textContent = 'Criando vídeo...';
        try {{
          const res = await fetch('/studio/videos', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ project_id, topic, format }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            feedback.textContent = 'Vídeo criado com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            feedback.textContent = 'Erro ao criar: ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
            if (btn) btn.disabled = false;
          }}
        }} catch (err) {{
          feedback.textContent = 'Falha de rede: ' + err.message;
          if (btn) btn.disabled = false;
        }}
      }});
    }}
    document.querySelectorAll('.btn-create-from-trend').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const topic = btn.getAttribute('data-topic') || btn.dataset.topic || '';
        const details = document.getElementById('new-video-section');
        const form = document.getElementById('create-video-form');
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if (details) details.open = true;
        if (input) {{
          input.value = topic;
          input.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          input.classList.remove('topic-pulse');
          void input.offsetWidth;
          input.classList.add('topic-pulse');
          setTimeout(() => input.focus(), 100);
          setTimeout(() => input.classList.remove('topic-pulse'), 1500);
        }} else if (form) {{
          form.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
      }});
    }});
    const navBtnNew = document.getElementById('nav-btn-new-video');
    if (navBtnNew) {{
      navBtnNew.addEventListener('click', (ev) => {{
        ev.preventDefault();
        const details = document.getElementById('new-video-section');
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if (details) {{
          details.open = true;
          details.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
        if (input) {{
          setTimeout(() => input.focus(), 200);
        }}
      }});
    }}

    // Pill Filtering (Region, Category & All)
    const filterPills = document.querySelectorAll('.cat-pill[data-filter-type]');
    const trendItems = document.querySelectorAll('.trend-item');
    filterPills.forEach((pill) => {{
      pill.addEventListener('click', () => {{
        filterPills.forEach((p) => p.classList.remove('active'));
        pill.classList.add('active');
        const filterType = pill.getAttribute('data-filter-type');
        trendItems.forEach((item) => {{
          if (filterType === 'all') {{
            item.style.display = '';
          }} else if (filterType === 'region') {{
            const regCode = pill.getAttribute('data-region-code');
            if (item.getAttribute('data-region') === regCode) {{
              item.style.display = '';
            }} else {{
              item.style.display = 'none';
            }}
          }} else if (filterType === 'category') {{
            const catId = pill.getAttribute('data-cat-id') || pill.getAttribute('data-category-id');
            if (item.getAttribute('data-category-id') === catId) {{
              item.style.display = '';
            }} else {{
              item.style.display = 'none';
            }}
          }}
        }});
      }});
    }});

    // Modal Open & Close
    const modal = document.getElementById('categories-modal');
    const btnManage = document.getElementById('btn-manage-categories');
    const btnAddPillarPill = document.getElementById('btn-open-categories-modal') || document.getElementById('btn-add-pillar-pill');
    const btnCloseModal = document.getElementById('btn-close-modal');

    function openCatModal() {{
      if (modal) {{
        modal.style.display = 'flex';
        resetCategoryForm();
      }}
    }}
    function closeCatModal() {{
      if (modal) modal.style.display = 'none';
    }}

    if (btnManage) btnManage.addEventListener('click', openCatModal);
    if (btnAddPillarPill) btnAddPillarPill.addEventListener('click', openCatModal);
    if (btnCloseModal) btnCloseModal.addEventListener('click', closeCatModal);
    if (modal) {{
      modal.addEventListener('click', (ev) => {{
        if (ev.target === modal) closeCatModal();
      }});
    }}
    document.addEventListener('keydown', (ev) => {{
      if (ev.key === 'Escape' && modal && modal.style.display === 'flex') {{
        closeCatModal();
      }}
    }});

    // Category Form Reset & Edit
    const catForm = document.getElementById('form-category');
    const catFormTitle = document.getElementById('category-form-title');
    const catIdInput = document.getElementById('category-id');
    const catNameInput = document.getElementById('category-name');
    const catQueriesInput = document.getElementById('category-queries');
    const btnSaveCat = document.getElementById('btn-save-category');
    const btnCancelEdit = document.getElementById('btn-cancel-edit-category');
    const catFeedback = document.getElementById('category-form-feedback');

    function resetCategoryForm() {{
      if (catIdInput) catIdInput.value = '';
      if (catNameInput) catNameInput.value = '';
      if (catQueriesInput) catQueriesInput.value = '';
      if (catFormTitle) catFormTitle.textContent = 'Novo Pilar de Conteúdo';
      if (btnSaveCat) {{
        btnSaveCat.textContent = 'Salvar Pilar';
        btnSaveCat.disabled = false;
      }}
      if (btnCancelEdit) btnCancelEdit.style.display = 'none';
      if (catFeedback) catFeedback.textContent = '';
    }}

    if (btnCancelEdit) {{
      btnCancelEdit.addEventListener('click', resetCategoryForm);
    }}

    document.querySelectorAll('.btn-edit-category').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const id = btn.dataset.id || '';
        const name = btn.dataset.name || '';
        const queries = btn.dataset.queries || '';
        if (catIdInput) catIdInput.value = id;
        if (catNameInput) {{
          catNameInput.value = name;
          catNameInput.focus();
        }}
        if (catQueriesInput) catQueriesInput.value = queries;
        if (catFormTitle) catFormTitle.textContent = 'Editar Pilar: ' + name;
        if (btnSaveCat) btnSaveCat.textContent = 'Atualizar Pilar';
        if (btnCancelEdit) btnCancelEdit.style.display = '';
        if (catFeedback) catFeedback.textContent = '';
      }});
    }});

    // Category Form Submit
    const activeProjectId = "{e(current_project_id)}";
    if (catForm) {{
      catForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const id = (catIdInput && catIdInput.value.trim()) || null;
        const name = catNameInput ? catNameInput.value.trim() : '';
        if (!name) return;

        const rawQueries = catQueriesInput ? catQueriesInput.value : '';
        const queries = rawQueries
          .split(',')
          .map((q) => q.trim())
          .filter((q) => q.length > 0);

        if (btnSaveCat) btnSaveCat.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Salvando pilar...';

        try {{
          const payload = {{ name: name, queries: queries }};
          if (id) payload.id = id;

          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar salvo com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else if (res.status === 409) {{
            if (catFeedback) catFeedback.textContent = 'Já existe um pilar com este nome no projeto.';
            if (btnSaveCat) btnSaveCat.disabled = false;
          }} else {{
            const errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (catFeedback) catFeedback.textContent = 'Erro: ' + errMsg;
            if (btnSaveCat) btnSaveCat.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          if (btnSaveCat) btnSaveCat.disabled = false;
        }}
      }});
    }}

    // Category Delete
    document.querySelectorAll('.btn-delete-category').forEach((btn) => {{
      btn.addEventListener('click', async () => {{
        const catId = btn.dataset.id;
        const catName = btn.dataset.name || 'este pilar';
        if (!catId) return;
        if (!confirm('Deseja excluir o pilar "' + catName + '"?')) return;

        btn.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Excluindo pilar...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories/' + encodeURIComponent(catId), {{
            method: 'DELETE'
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar excluído com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else {{
            const errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (catFeedback) catFeedback.textContent = 'Erro ao excluir: ' + errMsg;
            btn.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          btn.disabled = false;
        }}
      }});
    }});

    // Refresh Trends
    const btnRefresh = document.getElementById('btn-refresh-trends');
    const refreshFeedback = document.getElementById('trends-refresh-feedback');
    if (btnRefresh) {{
      btnRefresh.addEventListener('click', async () => {{
        btnRefresh.disabled = true;
        const origText = btnRefresh.textContent;
        btnRefresh.textContent = ' Consultando YouTube...';
        const spinner = document.createElement('span');
        spinner.className = 'spinner-inline';
        btnRefresh.prepend(spinner);
        if (refreshFeedback) refreshFeedback.textContent = 'Consultando YouTube Data API com seus pilares de conteúdo...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/trends/refresh', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{}})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            const count = typeof data.stored === 'number' ? data.stored : 0;
            if (refreshFeedback) refreshFeedback.textContent = 'Coleta concluída (' + count + ' temas encontrados)! Atualizando...';
            setTimeout(() => location.reload(), 500);
          }} else {{
            const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (refreshFeedback) refreshFeedback.textContent = 'Erro na coleta: ' + msg;
            btnRefresh.disabled = false;
            btnRefresh.textContent = origText;
          }}
        }} catch (err) {{
          if (refreshFeedback) refreshFeedback.textContent = 'Falha de rede: ' + err.message;
          btnRefresh.disabled = false;
          btnRefresh.textContent = origText;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def render_video(view: VideoDetailView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = view.video

    steps_html = []
    if not view.steps:
        steps_html.append('<li class="timeline-item"><div class="timeline-desc">Nenhum passo executado ainda.</div></li>')
    else:
        for s in view.steps:
            err_html = f'<div style="color: var(--bad); font-size: 0.8rem; margin-top: 0.2rem;">{e(s.error_message)}</div>' if s.error_message else ""
            steps_html.append(f"""
              <li class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-title">{e(s.step)} (tentativa {s.attempt}): {e(s.status)}</div>
                <div class="timeline-desc">{s.started_at.strftime("%d/%m %H:%M:%S")}{err_html}</div>
              </li>
            """)

    usage_html = []
    if not view.usage:
        usage_html.append('<tr><td colspan="4" class="empty">Sem registro de uso de IA para este vídeo.</td></tr>')
    else:
        for u in view.usage:
            if is_known_cost(u.provider, u.model, u.cost_usd):
                cost_str = "US$ 0,00 (gratuito)" if u.cost_usd == 0.0 else f"US$ {u.cost_usd:.4f}"
            else:
                cost_str = '<span style="color: var(--warn);">Não informado</span>'
            usage_html.append(f"""
              <tr>
                <td>{e(u.step)}</td>
                <td>{e(u.provider)}</td>
                <td>{e(u.model)}</td>
                <td>{cost_str}</td>
              </tr>
            """)

    render_err_html = f'<div class="warning" style="margin-top: 1rem;"><strong>Erro de Renderização:</strong> {e(view.render_error)}</div>' if view.render_error else ""

    pub_status_html = ""
    if view.publication:
        pub_err = f'<div style="color: var(--bad);">{e(view.publication.error)}</div>' if view.publication.error else ""
        pub_status_html = f"""
          <div class="card" style="margin-top: 1.25rem;">
            <div class="card-label">Publicação</div>
            <div>Status: <span class="pill pill-{e(view.publication.status.value)}">{e(view.publication.status.value)}</span> (tentativa {view.publication.attempt})</div>
            {pub_err}
          </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Faceless Studio — Detalhe do Vídeo</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <div class="app-layout">
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
        <a class="nav-item active" href="#">
          <svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line></svg>
          <span>Detalhe do Vídeo</span>
        </a>
        <a class="nav-item" href="/studio/videos/{e(v.id)}/preview">
          <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
          <span>Abrir Prévia</span>
        </a>
        <a class="nav-item" href="/docs" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          <span>API Docs</span>
        </a>
      </nav>
      <div class="sidebar-footer">
        <div style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.25rem;">ID do Vídeo:</div>
        <div style="font-family: monospace; font-size: 0.72rem; word-break: break-all; color: var(--text);">{e(v.id)}</div>
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <div style="font-size: 0.8rem; margin-bottom: 0.25rem;"><a href="/studio/panel">&larr; Voltar ao Painel</a></div>
          <h1>{e(v.topic)}</h1>
          <div style="margin-top: 0.25rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            <span class="pill pill-{e(view.stage.value)}">{e(view.stage.value)}</span>
            <span style="font-size: 0.85rem; color: var(--text-muted);">Custo do vídeo: {e(view.cost_text)}</span>
          </div>
        </div>
        <div>
          <a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia e Aprovar</a>
        </div>
      </header>

      <div class="content-body">
        <div class="layout-detail">
          <div class="card">
            <h2>Linha do Tempo dos Passos</h2>
            <ul class="timeline">
              {''.join(steps_html)}
            </ul>
            {render_err_html}
            {pub_status_html}
          </div>

          <div class="card">
            <h2>Registro de Uso de Modelos</h2>
            <table>
              <thead>
                <tr>
                  <th scope="col">Passo</th>
                  <th scope="col">Provedor</th>
                  <th scope="col">Modelo</th>
                  <th scope="col">Custo</th>
                </tr>
              </thead>
              <tbody>
                {''.join(usage_html)}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  </div>
</body>
</html>"""
    return html_content, _headers(nonce)
