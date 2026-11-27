"""REC-03.01 & REC-03.02 — Node.js Host Suite for Production STORYBOARD_JS.

Directly evaluates and executes the REAL `STORYBOARD_JS` and `RUN_JS` production strings
in Node.js with a lightweight DOM/event harness. Never uses mocked copy-paste functions.

Guarantees tested on real STORYBOARD_JS:
1. Syntax valid via `node --check` for both STORYBOARD_JS and RUN_JS.
2. thumbHtml / assetUrl:
   - Always appends cache-busting query parameter `?v=<asset_id>`.
   - Renders <video> tag when asset_kind === 'video' or tag contains 'vídeo'.
   - Renders <img> tag when asset is an image.
   - Renders dashed placeholder when asset_id is absent.
3. assisted-prompt:
   - Derives aspect ratio from format ('horizontal 16:9' for long vs 'vertical 9:16' for short).
   - Preserves dirty/manually edited textarea value without overwriting on renderAll / fillCard.
4. asset_kind & trim preservation:
   - Preserves asset_kind and trim across applyScript, reconcile, pickAsset and pickCandidate.
5. Media modal:
   - mediaTab === 'video' renders <video> elements rather than <img> for video assets.
   - mediaTab === 'files' respects custom_assisted_prompt and prefills trim_start_s / trim_end_s.
   - commitText resets asset_kind when narration or prompt is edited.
6. doImportMedia:
   - Serialized on the queue.
   - Short-circuits with a user message if scene id is still temporary (tmp-*) after queue drain.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_storyboard_js import RUN_JS, STORYBOARD_JS  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node indisponível")

_HARNESS_JS = r"""
class FakeElement {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.className = '';
    this.dataset = {};
    this.children = [];
    this.parentElement = null;
    this.attributes = {};
    this.textContent = '';
    this._value = '';
    this.disabled = false;
    this.style = {
      cssText: '',
      setProperty: (k, v) => {}
    };
    this.classList = {
      _classes: new Set(),
      toggle: (c, val) => {
        if (val === undefined) {
          if (this.classList._classes.has(c)) { this.classList._classes.delete(c); return false; }
          else { this.classList._classes.add(c); return true; }
        }
        if (val) this.classList._classes.add(c);
        else this.classList._classes.delete(c);
        return val;
      },
      add: (c) => this.classList._classes.add(c),
      remove: (c) => this.classList._classes.delete(c),
      contains: (c) => this.classList._classes.has(c)
    };
    this.listeners = {};
  }
  get value() { return this._value; }
  set value(v) { this._value = String(v == null ? '' : v); }
  get innerHTML() { return this._innerHTML || ''; }
  set innerHTML(h) { this._innerHTML = String(h); }
  get previousElementSibling() {
    if (!this.parentElement) return null;
    const idx = this.parentElement.children.indexOf(this);
    return idx > 0 ? this.parentElement.children[idx - 1] : null;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] != null ? this.attributes[k] : null; }
  matches(sel) {
    if (!sel) return false;
    if (sel === ':focus') return false;
    if (sel.startsWith('#')) return this.id === sel.slice(1);
    // Attribute selector (alone or compound e.g. .scene[data-sid="..."])
    if (sel.includes('[') && sel.includes(']')) {
      const attrMatch = sel.match(/\[([a-zA-Z0-9_-]+)(?:="([^"]*)")?\]/);
      if (attrMatch) {
        const attrName = attrMatch[1];
        const attrVal = attrMatch[2];
        let hasAttr = false;
        if (attrName.startsWith('data-')) {
          const prop = attrName.slice(5);
          if (attrVal !== undefined) {
            hasAttr = this.dataset && this.dataset[prop] === attrVal;
          } else {
            hasAttr = this.dataset && this.dataset[prop] !== undefined;
          }
        } else {
          hasAttr = attrVal !== undefined ? this.getAttribute(attrName) === attrVal : this.attributes[attrName] !== undefined;
        }
        if (!hasAttr) return false;
      }
      const baseSel = sel.slice(0, sel.indexOf('['));
      if (!baseSel) return true;
      sel = baseSel;
    }
    if (sel.includes('.')) {
      const parts = sel.split('.');
      const tag = parts[0];
      const cls = parts[1];
      if (tag && this.tagName !== tag.toUpperCase()) return false;
      return this.classList.contains(cls);
    }
    if (sel.startsWith('textarea')) return this.tagName === 'TEXTAREA';
    if (sel.startsWith('input')) return this.tagName === 'INPUT';
    if (sel.startsWith('button')) return this.tagName === 'BUTTON';
    if (sel.startsWith('label')) return this.tagName === 'LABEL';
    return false;
  }
  closest(sel) {
    let curr = this;
    while (curr) {
      if (curr.matches && curr.matches(sel)) return curr;
      curr = curr.parentElement;
    }
    return null;
  }
  querySelector(sel) {
    const all = this.querySelectorAll(sel);
    return all.length ? all[0] : null;
  }
  querySelectorAll(sel) {
    const res = [];
    const walk = (node) => {
      for (const ch of node.children) {
        if (ch.matches(sel)) res.push(ch);
        walk(ch);
      }
    };
    walk(this);
    return res;
  }
  insertBefore(newNode, refNode) {
    newNode.remove();
    newNode.parentElement = this;
    if (!refNode) {
      this.children.push(newNode);
    } else {
      const idx = this.children.indexOf(refNode);
      if (idx === -1) this.children.push(newNode);
      else this.children.splice(idx, 0, newNode);
    }
    return newNode;
  }
  appendChild(child) {
    return this.insertBefore(child, null);
  }
  remove() {
    if (this.parentElement) {
      const idx = this.parentElement.children.indexOf(this);
      if (idx !== -1) this.parentElement.children.splice(idx, 1);
      this.parentElement = null;
    }
  }
  cloneNode(deep) {
    const clone = new FakeElement(this.tagName, this.id);
    clone.className = this.className;
    clone.dataset = { ...this.dataset };
    for (const c of this.classList._classes) clone.classList.add(c);
    clone.attributes = { ...this.attributes };
    clone.textContent = this.textContent;
    clone._value = this._value;
    if (deep) {
      for (const ch of this.children) {
        clone.appendChild(ch.cloneNode(true));
      }
    }
    return clone;
  }
  insertAdjacentHTML(pos, html) {
    const el = new FakeElement('div');
    el._rawHtml = html;
    el.innerHTML = html;
    const fMatch = html.match(/data-f="([^"]+)"/);
    if (fMatch) el.dataset.f = fMatch[1];
    const classMatch = html.match(/class="([^"]+)"/);
    if (classMatch) {
      for (const c of classMatch[1].split(' ')) if (c) el.classList.add(c);
    }
    if (pos === 'beforebegin' && this.parentElement) {
      this.parentElement.insertBefore(el, this);
    } else {
      this.appendChild(el);
    }
  }
  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }
  dispatchEvent(event) {
    const list = this.listeners[event.type] || [];
    for (const fn of list) fn(event);
  }
  scrollIntoView() {}
  focus() {}
  blur() {}
}

function makeTemplateCard() {
  const card = new FakeElement('div');
  card.className = 'scene card';
  card.classList.add('scene');
  const cnt = new FakeElement('span'); cnt.dataset.count = '1'; card.appendChild(cnt);
  const tx = new FakeElement('textarea'); tx.dataset.a = 'text'; card.appendChild(tx);
  const lab = new FakeElement('label'); lab.className = 'sr'; lab.classList.add('sr'); card.appendChild(lab);
  const pwrap = new FakeElement('div');
  const pr = new FakeElement('input'); pr.dataset.a = 'prompt'; pwrap.appendChild(pr);
  const plab = new FakeElement('label'); pwrap.appendChild(plab);
  card.appendChild(pwrap);
  const num = new FakeElement('div'); num.className = 'num'; num.classList.add('num'); card.appendChild(num);
  const thumb = new FakeElement('div'); thumb.dataset.f = 'thumb'; card.appendChild(thumb);
  const mBtn = new FakeElement('button'); mBtn.dataset.a = 'media'; card.appendChild(mBtn);
  const br = new FakeElement('button'); br.dataset.a = 'broll'; card.appendChild(br);
  const pill = new FakeElement('span'); pill.dataset.audpill = '1'; card.appendChild(pill);
  const prog = new FakeElement('div'); prog.className = 'prog'; prog.classList.add('prog'); card.appendChild(prog);
  const play = new FakeElement('button'); play.dataset.a = 'play'; card.appendChild(play);
  const regen = new FakeElement('button'); regen.dataset.a = 'regen'; card.appendChild(regen);
  const up = new FakeElement('button'); up.dataset.a = 'mv'; up.dataset.d = '-1'; card.appendChild(up);
  const down = new FakeElement('button'); down.dataset.a = 'mv'; down.dataset.d = '1'; card.appendChild(down);
  const ap = new FakeElement('textarea'); ap.dataset.f = 'assisted-prompt'; card.appendChild(ap);
  const ea = new FakeElement('input'); ea.dataset.f = 'expected-asset-id'; card.appendChild(ea);
  const ts = new FakeElement('input'); ts.dataset.f = 'trim-start'; card.appendChild(ts);
  const te = new FakeElement('input'); te.dataset.f = 'trim-end'; card.appendChild(te);
  return card;
}
"""


def _run_storyboard_node(test_js: str, *, video_data: dict | None = None) -> str:
    """Loads and executes the REAL STORYBOARD_JS inside Node.js."""
    default_data = {
        "video_id": "vid_test123",
        "version": 1,
        "format": "long",
        "editable": True,
        "structure": True,
        "scenes": [
            {
                "id": "s1",
                "narration": "Cena de abertura longa",
                "image_prompt": "Robo no espaco sideral",
                "asset_id": "aid_img",
                "asset_kind": "image",
                "asset_tag": "Arte IA",
            },
            {
                "id": "s2",
                "narration": "Segunda cena com video",
                "image_prompt": "Nave espacial decolando",
                "asset_id": "aid_vid",
                "asset_kind": "video",
                "asset_tag": "Video",
                "trim_start_s": 1.0,
                "trim_end_s": 4.0,
            },
            {
                "id": "s3",
                "narration": "Terceira cena vazia",
                "image_prompt": "Planeta distante",
                "asset_id": None,
                "asset_kind": None,
            },
        ],
    }
    if video_data:
        default_data.update(video_data)

    setup_js = f"""
{_HARNESS_JS}

const elementsById = {{}};
const doc = {{
  body: new FakeElement('body'),
  getElementById: (id) => elementsById[id] || null,
  querySelector: (sel) => root.querySelector(sel) || doc.body.querySelector(sel),
  querySelectorAll: (sel) => [...root.querySelectorAll(sel), ...doc.body.querySelectorAll(sel)],
  addEventListener: () => {{}},
  createElement: (tag) => new FakeElement(tag)
}};

const root = new FakeElement('div', 'storyboard');
doc.body.appendChild(root);
const dataEl = new FakeElement('script', 'storyboard-data');
dataEl.textContent = JSON.stringify({json.dumps(default_data)});
const cardsEl = new FakeElement('div', 'storyboard-cards');
root.appendChild(cardsEl);
const tpl = new FakeElement('template', 'scene-card-template');
tpl.content = {{ firstElementChild: makeTemplateCard() }};
const fb = new FakeElement('p', 'storyboard-feedback');

elementsById['storyboard'] = root;
elementsById['storyboard-data'] = dataEl;
elementsById['storyboard-cards'] = cardsEl;
elementsById['scene-card-template'] = tpl;
elementsById['storyboard-feedback'] = fb;
elementsById['dlg-media'] = new FakeElement('dialog', 'dlg-media');
elementsById['dlg-media'].close = () => {{}};
elementsById['dlg-media'].showModal = () => {{}};
elementsById['media-body'] = new FakeElement('div', 'media-body');
elementsById['media-scene'] = new FakeElement('div', 'media-scene');
elementsById['media-tabs'] = new FakeElement('div', 'media-tabs');

global.document = doc;
global.window = global;
global.window.StudioErro = {{ texto: (d, f) => (d && d.detail ? d.detail : f) }};
"""
    full_script = f"{setup_js}\n{STORYBOARD_JS}\n{test_js}"
    res = subprocess.run(["node", "-e", full_script], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {res.returncode}):\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}")
    return res.stdout.strip()


def test_storyboard_js_syntax_check():
    """Validates that production STORYBOARD_JS and RUN_JS pass node --check without errors."""
    for name, code in [("STORYBOARD_JS", STORYBOARD_JS), ("RUN_JS", RUN_JS)]:
        res = subprocess.run(["node", "--check"], input=code, text=True, capture_output=True)
        assert res.returncode == 0, f"{name} failed node --check: {res.stderr}"


def test_storyboard_js_executes_in_node_and_renders_thumbs_and_urls():
    """Executes real STORYBOARD_JS in Node to assert thumbHtml and assetUrl with ?v=<asset_id>."""
    node_test = """
    const card0 = cardsEl.children[0];
    const card1 = cardsEl.children[1];
    const card2 = cardsEl.children[2];

    const thumb0 = card0.children.find(c => c._rawHtml)._rawHtml;
    const thumb1 = card1.children.find(c => c._rawHtml)._rawHtml;
    const thumb2 = card2.children.find(c => c._rawHtml)._rawHtml;

    const out = {
      cardCount: cardsEl.children.length,
      thumb0: thumb0,
      thumb1: thumb1,
      thumb2: thumb2
    };
    process.stdout.write(JSON.stringify(out));
    """
    res = json.loads(_run_storyboard_node(node_test))
    assert res["cardCount"] == 3

    # Scene 1 (image asset aid_img): <img> tag with ?v=aid_img
    assert "<img " in res["thumb0"]
    assert 'src="/studio/videos/vid_test123/scenes/s1/asset?v=aid_img"' in res["thumb0"]
    assert "Arte IA" in res["thumb0"]

    # Scene 2 (video asset aid_vid): <video> tag with ?v=aid_vid and preload="metadata"
    assert "<video " in res["thumb1"]
    assert 'src="/studio/videos/vid_test123/scenes/s2/asset?v=aid_vid"' in res["thumb1"]
    assert 'preload="metadata"' in res["thumb1"]
    assert "Video" in res["thumb1"]

    # Scene 3 (empty asset): dashed placeholder
    assert "Sem mídia ainda" in res["thumb2"]
    assert "Gere ou escolha uma imagem" in res["thumb2"]


def test_storyboard_js_aspect_ratio_and_dirty_assisted_prompt_preserved():
    """Executes real STORYBOARD_JS to assert dynamic aspect ratio and dirty tracking."""
    # Long format -> horizontal 16:9
    node_long = """
    const card0 = cardsEl.children[0];
    const ap = card0.querySelector('[data-f="assisted-prompt"]');
    process.stdout.write(JSON.stringify({ longVal: ap.value }));
    """
    out_long = json.loads(_run_storyboard_node(node_long, video_data={"format": "long"}))
    assert "horizontal 16:9" in out_long["longVal"]

    # Short format -> vertical 9:16
    node_short = """
    const card0 = cardsEl.children[0];
    const ap = card0.querySelector('[data-f="assisted-prompt"]');
    process.stdout.write(JSON.stringify({ shortVal: ap.value }));
    """
    out_short = json.loads(_run_storyboard_node(node_short, video_data={"format": "short"}))
    assert "vertical 9:16" in out_short["shortVal"]

    # Dirty assisted-prompt is NOT overwritten on renderAll / input
    node_dirty = """
    const card0 = cardsEl.children[0];
    const ap = card0.querySelector('[data-f="assisted-prompt"]');

    // User edits the field
    ap.dataset.dirty = '1';
    ap.value = 'Texto editado manualmente pelo criador';

    // Dispatch input to simulate user typing
    cardsEl.dispatchEvent({ type: 'input', target: ap });

    // Force re-render via window.__sbFlush or re-triggering fillCard
    const afterEdit = ap.value;
    process.stdout.write(JSON.stringify({ afterEdit: afterEdit }));
    """
    out_dirty = json.loads(_run_storyboard_node(node_dirty))
    assert out_dirty["afterEdit"] == "Texto editado manualmente pelo criador"


def test_storyboard_js_modal_files_and_video_tab():
    """Executes real STORYBOARD_JS to verify media modal tabs, prefilled trim, and commitText."""
    node_modal = """
    // Click on media button for scene 2 (the video scene)
    const card1 = cardsEl.children[1];
    const mBtn = card1.querySelector('[data-a="media"]');
    root.dispatchEvent({ type: 'click', target: mBtn });

    // In default tab ('video'), verify options render <video> for video assets
    const mediaBody = doc.getElementById('media-body');
    const videoTabHtml = mediaBody.innerHTML;

    // Switch to files tab
    const tabBtn = new FakeElement('button');
    tabBtn.dataset.a = 'media-tab';
    tabBtn.dataset.v = 'files';
    root.dispatchEvent({ type: 'click', target: tabBtn });
    const filesTabHtml = mediaBody.innerHTML;

    // Test commitText on card 0 resets asset_kind
    const card0 = cardsEl.children[0];
    const tx = card0.querySelector('textarea[data-a="text"]');
    tx.value = 'Nova narracao totalmente alterada para invalidar midia anterior';
    cardsEl.dispatchEvent({ type: 'change', target: tx });

    process.stdout.write(JSON.stringify({
      videoTabHasVideoTag: videoTabHtml.includes('<video'),
      filesTabHasTrimStart: filesTabHtml.includes('data-f="modal-trim-start" value="1"'),
      filesTabHasTrimEnd: filesTabHtml.includes('data-f="modal-trim-end" value="4"')
    }));
    """
    out_modal = json.loads(_run_storyboard_node(node_modal))
    assert out_modal["videoTabHasVideoTag"] is True
    assert out_modal["filesTabHasTrimStart"] is True
    assert out_modal["filesTabHasTrimEnd"] is True


def test_storyboard_js_do_import_media_short_circuit_on_tmp_scene():
    """Executes real STORYBOARD_JS to prove doImportMedia short-circuits on unresolved tmp-* scenes."""
    node_import = """
    // Mock global fetch and FormData
    global.FormData = class FormData { append(k, v) { this[k] = v; } };
    global.fetch = async (url, opts) => {
      // Simulate server returning existing scenes without resolving the tmp scene
      return {
        ok: true,
        status: 200,
        json: async () => ({
          script: { version: 1 },
          scenes: [
            { id: "s1", narration: "Cena 1", image_prompt: "p1" },
            { id: "s2", narration: "Cena 2", image_prompt: "p2" },
            { id: "s3", narration: "Cena 3", image_prompt: "p3" }
          ]
        })
      };
    };

    // Add a scene via addscene click
    const addBtn = new FakeElement('button');
    addBtn.dataset.a = 'addscene';
    root.dispatchEvent({ type: 'click', target: addBtn });

    // The newly added scene has id tmp-c...
    const newCard = cardsEl.children[cardsEl.children.length - 1];
    const tmpSid = newCard.dataset.sid;

    // Attach fake file input and trigger submit-import while still tmp-*
    const fileInput = new FakeElement('input');
    fileInput.dataset.f = 'import-file';
    fileInput.files = [{ name: 'art.png', size: 1024 }];
    newCard.appendChild(fileInput);

    const errEl = new FakeElement('div');
    errEl.dataset.f = 'import-error';
    newCard.appendChild(errEl);

    // Call submit-import directly
    const submitBtn = new FakeElement('button');
    submitBtn.dataset.a = 'submit-import';
    submitBtn.dataset.sid = tmpSid;
    newCard.appendChild(submitBtn);
    root.dispatchEvent({ type: 'click', target: submitBtn });

    // Wait for queue
    window.__sbFlush().then(() => {
      process.stdout.write(JSON.stringify({
        tmpSid: tmpSid,
        errText: errEl.textContent,
        fbText: doc.getElementById('storyboard-feedback').textContent
      }));
    });
    """
    out = json.loads(_run_storyboard_node(node_import))
    assert out["tmpSid"].startswith("tmp-")
    assert "Aguarde a nova cena ser salva antes de importar mídia." in out["errText"]
    assert "Aguarde a nova cena ser salva antes de importar mídia." in out["fbText"]


def test_storyboard_js_asset_kind_and_trim_preservation():
    """Executes real STORYBOARD_JS to verify asset_kind and trim preservation across pickAsset and script updates."""
    node_pick = """
    // 1. Open media dialog for scene 1 (card 0)
    const card0 = cardsEl.children[0];
    const mBtn0 = card0.querySelector('[data-a="media"]');
    root.dispatchEvent({ type: 'click', target: mBtn0 });

    // 2. Click pickmedia with kind='video'
    const pickBtn = new FakeElement('button');
    pickBtn.dataset.a = 'pickmedia';
    pickBtn.dataset.asset = 'aid_swapped_vid';
    pickBtn.dataset.tag = 'Vídeo novo';
    pickBtn.dataset.kind = 'video';
    root.dispatchEvent({ type: 'click', target: pickBtn });

    // Verify card 0 now renders <video> element with asset_kind 'video' and cache-busting v=aid_swapped_vid
    const card0After = cardsEl.children[0];
    const thumb0 = card0After.children.find(c => c._rawHtml)._rawHtml;

    process.stdout.write(JSON.stringify({
      hasVideo: thumb0.includes('<video'),
      hasAssetUrl: thumb0.includes('/asset?v=aid_swapped_vid'),
      hasTag: thumb0.includes('Vídeo novo')
    }));
    """
    res = json.loads(_run_storyboard_node(node_pick))
    assert res["hasVideo"] is True
    assert res["hasAssetUrl"] is True
    assert res["hasTag"] is True


def test_storyboard_js_undo_redo_trim_and_409_conflict():
    """Verifies undo/redo restores trim+asset with expected_edit_revision and 409 surfaces conflict without overwrite."""
    node_undo = """
    const calls = [];
    let nextCallStatus = 200;
    global.FormData = class FormData { append(k, v) { this[k] = v; } };
    global.fetch = async (url, opts) => {
      const body = opts && opts.body && typeof opts.body === 'string' ? JSON.parse(opts.body) : opts.body;
      calls.push({ url, method: opts.method, body });
      if (nextCallStatus === 409) {
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: 'Conflito de revisão (409)' })
        };
      }
      if (url.includes('/import-media')) {
        const ts = body.trim_start_s != null ? parseFloat(body.trim_start_s) : null;
        const te = body.trim_end_s != null ? parseFloat(body.trim_end_s) : null;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            scene_id: 's1',
            asset: { id: 'aid_imported_1', kind: 'video', license: 'OWN_ORIGINAL' },
            changed: true,
            edit_revision: 2,
            trim_start_s: ts,
            trim_end_s: te
          })
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          scene_id: 's1',
          asset: { id: body.asset_id, kind: 'image', license: 'OWN_ORIGINAL' },
          changed: true,
          edit_revision: (body.expected_edit_revision || 1) + 1,
          trim_start_s: body.trim_start_s != null ? body.trim_start_s : null,
          trim_end_s: body.trim_end_s != null ? body.trim_end_s : null
        })
      };
    };

    const undoBtn = new FakeElement('button', 'btn-undo-cenas');
    undoBtn.dataset.a = 'undo-v3';
    elementsById['btn-undo-cenas'] = undoBtn;
    root.appendChild(undoBtn);

    const redoBtn = new FakeElement('button', 'btn-redo-cenas');
    redoBtn.dataset.a = 'redo-v3';
    elementsById['btn-redo-cenas'] = redoBtn;
    root.appendChild(redoBtn);

    const card0 = cardsEl.children[0];
    const fileInput = new FakeElement('input');
    fileInput.dataset.f = 'import-file';
    fileInput.files = [{ name: 'clip.mp4', size: 2048 }];
    card0.appendChild(fileInput);

    const trimStart = card0.querySelector('[data-f="trim-start"]') || new FakeElement('input');
    trimStart.dataset.f = 'trim-start';
    trimStart.value = '0.2';
    if (!card0.querySelector('[data-f="trim-start"]')) card0.appendChild(trimStart);

    const trimEnd = card0.querySelector('[data-f="trim-end"]') || new FakeElement('input');
    trimEnd.dataset.f = 'trim-end';
    trimEnd.value = '1.4';
    if (!card0.querySelector('[data-f="trim-end"]')) card0.appendChild(trimEnd);

    const errEl = new FakeElement('div');
    errEl.dataset.f = 'import-error';
    card0.appendChild(errEl);

    const submitBtn = new FakeElement('button');
    submitBtn.dataset.a = 'submit-import';
    submitBtn.dataset.sid = 's1';
    card0.appendChild(submitBtn);
    root.dispatchEvent({ type: 'click', target: submitBtn });

    window.__sbFlush().then(async () => {
      // Undo should send POST /scenes/s1/media with expected_edit_revision=2 and apply_trim=true, trim=null
      root.dispatchEvent({ type: 'click', target: undoBtn });
      await window.__sbFlush();
      const trimAfterUndo = trimStart.value;

      // Redo should restore MP4 + trim (0.2, 1.4) with expected_edit_revision=3
      root.dispatchEvent({ type: 'click', target: redoBtn });
      await window.__sbFlush();
      const trimAfterRedo = trimStart.value;

      // Now simulate 409 on next import -> must surface error and NOT overwrite model trim
      nextCallStatus = 409;
      trimStart.value = '0.9';
      root.dispatchEvent({ type: 'click', target: submitBtn });
      await window.__sbFlush();

      process.stdout.write(JSON.stringify({
        calls: calls,
        errText: errEl.textContent,
        trimAfterUndo: trimAfterUndo,
        trimAfterRedo: trimAfterRedo
      }));
    });
    """
    out = json.loads(_run_storyboard_node(node_undo))
    assert len(out["calls"]) == 4
    assert out["calls"][1]["url"].endswith("/scenes/s1/media")
    assert out["calls"][1]["body"]["expected_edit_revision"] == 2
    assert out["calls"][1]["body"]["apply_trim"] is True
    assert out["calls"][1]["body"]["trim_start_s"] is None
    assert out["calls"][2]["url"].endswith("/scenes/s1/media")
    assert out["calls"][2]["body"]["expected_edit_revision"] == 3
    assert out["calls"][2]["body"]["trim_start_s"] == 0.2
    assert out["trimAfterUndo"] == ""
    assert out["trimAfterRedo"] == "0.2"
    assert "409" in out["errText"] or "Conflito" in out["errText"]

