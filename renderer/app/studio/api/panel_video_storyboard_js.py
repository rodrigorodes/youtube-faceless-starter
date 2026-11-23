"""JS do storyboard integrado (VE-08): modelo local + histórico + sincronização com o backend existente.

O servidor renderiza todos os `sceneCard` (HTML canônico do protótipo). Este script só preenche o que muda
(`fillCard`), mantém o histórico de Desfazer/Refazer e leva o estado ao backend pelos contratos que já
existem (`/script/scenes`, `/scenes/{id}/media`, `/scenes/{id}/broll`, `/production-runs`).
"""

STORYBOARD_JS = r"""
(function () {
  'use strict';
  var root = document.getElementById('storyboard');
  var dataEl = document.getElementById('storyboard-data');
  var cardsEl = document.getElementById('storyboard-cards');
  var tpl = document.getElementById('scene-card-template');
  if (!root || !dataEl || !cardsEl || !tpl) return;
  var D = {};
  try { D = JSON.parse(dataEl.textContent); } catch (err) { return; }
  var VID = D.video_id, editable = !!D.editable, structure = D.structure !== false, version = Number(D.version || 0);
  var fb = document.getElementById('storyboard-feedback');
  var MAX = 30;

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function say(text) { if (fb) fb.textContent = text; }
  function toast(text) {
    var t = document.createElement('div');
    t.className = 'toast'; t.setAttribute('role', 'status'); t.textContent = text;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2400);
  }
  function words(t) { return ((t || '').trim().match(/\S+/g) || []).length; }
  function secsOf(s) { return s.duration_s ? Math.round(s.duration_s) : Math.max(2, Math.round(words(s.narration) / 2.6)); }
  function countText(s) {
    var secs = s.duration_s ? (s.duration_s.toFixed(1) + 's') : ('~' + Math.max(2, Math.round(words(s.narration) / 2.6)) + 's');
    return words(s.narration) + ' palavras \u00b7 ' + secs;
  }
  function clock(n) { return '0:' + String(n).padStart(2, '0'); }
  function fmtT(total) { return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0'); }
  function norm(t) { return (t || '').trim(); }
  function validNarr(s) { var n = norm(s.narration).length; return n >= 5 && n <= 400; }
  function validPrompt(s) { var n = norm(s.image_prompt).length; return n >= 10 && n <= 500; }
  function assetUrl(s) { return '/studio/videos/' + encodeURIComponent(VID) + '/scenes/' + encodeURIComponent(s.id) + '/asset'; }

  var cidN = 0;
  function newCid() { cidN += 1; return 'c' + cidN; }
  var model = (D.scenes || []).map(function (s) { var m = clone(s); m.cid = newCid(); return m; });
  var server = clone(model);
  var undo = [], redo = [];
  var focusCid = model.length ? model[0].cid : null;
  var playing = null, audio = null;

  /* ---------------- render ---------------- */
  function thumbKey(s, i) {
    return s.asset_id ? ['m', s.id, s.asset_id, s.asset_tag, s.broll_enabled ? 1 : 0, secsOf(s)].join('|') : 'empty';
  }
  function thumbHtml(s, i) {
    if (!s.asset_id) {
      return '<div class="thumb" data-f="thumb" style="height:132px;background:var(--panel3);border-style:dashed;color:var(--muted);font-size:12px;text-align:center;padding:10px">Sem m\u00eddia ainda<br><span class="sample">Gere ou escolha uma imagem</span></div>';
    }
    var tag = (s.asset_tag || 'M\u00eddia') + (s.broll_enabled ? ' \u00b7 +B-roll' : '');
    return '<div class="thumb" data-f="thumb" style="height:132px;background:var(--panel3)"><img src="' + esc(assetUrl(s)) +
      '" alt="M\u00eddia da cena ' + (i + 1) + '" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"><span class="tag">' +
      esc(tag) + '</span><span class="time">' + clock(secsOf(s)) + '</span></div>';
  }
  var AUD = { ok: ['ok', '\u2713 \u00c1udio atual'], stale: ['warn', '\u00c1udio desatualizado'], none: ['bad', 'Sem \u00e1udio ainda'] };

  function fillCard(card, s, i, total) {
    var sid = s.id;
    card.dataset.sid = sid; card.dataset.cid = s.cid;
    card.querySelectorAll('[data-sid]').forEach(function (el) { el.dataset.sid = sid; });
    var cnt = card.querySelector('[data-count]'); cnt.dataset.count = sid; cnt.textContent = countText(s);
    var tx = card.querySelector('textarea[data-a="text"]');
    tx.id = 'tx-' + sid; tx.setAttribute('maxlength', '400');
    if (tx.value !== s.narration) tx.value = s.narration;
    var lab = card.querySelector('label.sr'); lab.setAttribute('for', 'tx-' + sid); lab.textContent = 'Texto da cena ' + (i + 1);
    var pr = card.querySelector('input[data-a="prompt"]');
    pr.id = 'pr-' + sid; pr.setAttribute('maxlength', '500');
    if (pr.value !== s.image_prompt) pr.value = s.image_prompt;
    var plab = pr.parentElement.querySelector('label'); plab.setAttribute('for', 'pr-' + sid);
    card.querySelector('.num').textContent = 'CENA ' + (i + 1) + ' \u00b7 ' + String(s.label || '').toUpperCase();
    // m\u00eddia
    var thumb = card.querySelector('[data-f="thumb"]'), key = thumbKey(s, i);
    if (thumb && thumb.dataset.k !== key) {
      thumb.insertAdjacentHTML('beforebegin', thumbHtml(s, i));
      var fresh = thumb.previousElementSibling; fresh.dataset.k = key; thumb.remove();
    } else if (thumb) { thumb.dataset.k = key; }
    var mediaBtn = card.querySelector('[data-a="media"]');
    mediaBtn.textContent = s.asset_id ? 'Trocar m\u00eddia' : 'Escolher m\u00eddia';
    // B-roll
    var br = card.querySelector('[data-a="broll"]');
    br.classList.toggle('ghost', !s.broll_enabled);
    br.style.cssText = s.broll_enabled ? 'border-color:var(--accent);color:var(--accent2)' : '';
    br.setAttribute('aria-pressed', s.broll_enabled ? 'true' : 'false');
    br.textContent = s.broll_enabled ? 'B-roll ativo' : '+ B-roll';
    var note = card.querySelector('input[data-a="brollnote"]');
    if (s.broll_enabled && !note) {
      br.parentElement.insertAdjacentHTML('afterend', '<input type="text" class="sample" style="margin-top:6px;font-size:12px" aria-label="Descri\u00e7\u00e3o do B-roll" data-a="brollnote" data-sid="' +
        esc(sid) + '" maxlength="200" placeholder="O que mostrar no B-roll?"' + (editable ? '' : ' readonly') + '>');
      note = card.querySelector('input[data-a="brollnote"]');
    } else if (!s.broll_enabled && note) { note.remove(); note = null; }
    if (note) { note.dataset.sid = sid; if (note.value !== (s.broll_note || '')) note.value = s.broll_note || ''; }
    // narra\u00e7\u00e3o
    var aud = AUD[s.audio_state] || AUD.none, pill = card.querySelector('[data-audpill]');
    pill.dataset.audpill = sid; pill.className = 'pill ' + aud[0]; pill.textContent = aud[1];
    var prog = card.querySelector('.prog'); prog.style.setProperty('--d', secsOf(s) + 's');
    prog.classList.toggle('run', playing === s.cid);
    var play = card.querySelector('[data-a="play"]');
    play.textContent = playing === s.cid ? '\u25a0 Parar' : '\u25b6 Ouvir trecho';
    play.disabled = s.audio_state === 'none';
    var regen = card.querySelector('[data-a="regen"]');
    regen.textContent = s.audio_state === 'none' ? 'Gerar \u00e1udio da cena' : 'Regenerar \u00e1udio da cena';
    var up = card.querySelector('[data-a="mv"][data-d="-1"]'), down = card.querySelector('[data-a="mv"][data-d="1"]');
    up.disabled = !editable || !structure || i === 0; down.disabled = !editable || !structure || i === total - 1;
  }

  function renderAll() {
    var byCid = {};
    cardsEl.querySelectorAll('.scene').forEach(function (c) { byCid[c.dataset.cid || ''] = c; });
    cardsEl.querySelectorAll('.scene').forEach(function (c) {
      if (!c.dataset.cid) {
        var idx = Array.prototype.indexOf.call(cardsEl.children, c);
        if (model[idx]) byCid[model[idx].cid] = c;
      }
    });
    var keep = {};
    model.forEach(function (s, i) {
      var card = byCid[s.cid];
      if (!card) card = tpl.content.firstElementChild.cloneNode(true);
      keep[s.cid] = true;
      fillCard(card, s, i, model.length);
      if (cardsEl.children[i] !== card) cardsEl.insertBefore(card, cardsEl.children[i] || null);
    });
    Array.prototype.slice.call(cardsEl.children).forEach(function (c) { if (!keep[c.dataset.cid]) c.remove(); });
    var empty = document.getElementById('storyboard-empty');
    if (!model.length && !empty && !document.getElementById('storyboard-vazio')) {
      cardsEl.insertAdjacentHTML('afterend', '<div class="card" id="storyboard-empty"><p class="sub">Sem cenas. Adicione a primeira cena.</p></div>');
    } else if (model.length && empty) { empty.remove(); }
    var full = document.getElementById('storyboard-fullscript');
    if (full) {
      full.innerHTML = model.map(function (s, i) {
        return '<p style="margin-top:12px"><b>' + (i + 1) + '. ' + esc(s.label) + '</b><br>' + esc(s.narration) + '</p>';
      }).join('');
      var sum = full.parentElement.querySelector('summary');
      if (sum) sum.textContent = 'Ver roteiro completo \u00b7 ' + model.length + ' cenas';
    }
    syncButtons(); updateDock();
  }

  function updateDock() {
    var cnt = document.getElementById('dock-count'), dur = document.getElementById('dock-dur');
    var total = model.reduce(function (a, s) { return a + Math.max(2, Math.round(words(s.narration) / 2.6)); }, 0);
    var missing = model.filter(function (s) { return !s.asset_id || s.audio_state !== 'ok'; }).length;
    if (cnt) cnt.textContent = model.length + ' cenas';
    if (dur) dur.textContent = '~' + fmtT(total) + ' \u00b7 estimativa de custo n\u00e3o dispon\u00edvel';
    var dock = document.getElementById('dock'), info = document.getElementById('dock-info');
    var warn = document.getElementById('dock-missing');
    if (dock && info) {
      var want = dock.dataset.needs === '1' && missing > 0;
      if (want && !warn) {
        warn = document.createElement('span'); warn.className = 'pill warn'; warn.id = 'dock-missing';
        info.insertBefore(warn, document.getElementById('run-feedback'));
      }
      if (warn) { if (want) warn.textContent = missing + ' cena(s) sem m\u00eddia ou \u00e1udio atual'; else warn.remove(); }
    }
    var n = document.getElementById('impact-n'); if (n) n.textContent = String(missing);
  }
  function syncButtons() {
    var u = document.getElementById('btn-undo-cenas'), r = document.getElementById('btn-redo-cenas');
    if (u) u.disabled = !undo.length; if (r) r.disabled = !redo.length;
  }

  /* ---------------- hist\u00f3rico (Desfazer/Refazer) ---------------- */
  function remember() { undo.push(clone(model)); if (undo.length > MAX) undo.shift(); redo = []; syncButtons(); }
  function adoptIds() {
    model.forEach(function (m) {
      var s = server.filter(function (x) { return x.cid === m.cid; })[0];
      m.id = s ? s.id : 'tmp-' + m.cid;
    });
  }
  function travel(from, to) {
    if (!from.length) return;
    to.push(clone(model));
    model = from.pop();
    adoptIds(); renderAll(); scheduleSync();
    toast('Edi\u00e7\u00e3o restaurada. Publica\u00e7\u00f5es e custos n\u00e3o s\u00e3o desfeitos.');
  }

  /* ---------------- sincroniza\u00e7\u00e3o com o backend ---------------- */
  var queue = Promise.resolve(), pending = false;
  function call(method, path, body, withKey) {
    var key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random();
    var payload = body ? (withKey ? Object.assign({ idempotency_key: key }, body) : body) : null;
    return fetch('/studio/videos/' + encodeURIComponent(VID) + path, {
      method: method, headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: payload ? JSON.stringify(payload) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) {
          var msg = window.StudioErro.texto(d, 'tente novamente.', r.status);
          throw new Error(msg);
        }
        return d;
      });
    });
  }
  function applyScript(res, cids) {
    version = res.script.version;
    var tags = {}; server.forEach(function (s) { tags[s.cid] = s.asset_tag; });
    server = res.scenes.map(function (sc, i) {
      return { cid: cids[i], id: sc.id, label: sc.label || '', caption: sc.caption || '', narration: sc.narration,
        image_prompt: sc.image_prompt, asset_id: sc.asset_id || null, asset_tag: tags[cids[i]] || '',
        duration_s: sc.duration_s || null, broll_enabled: !!sc.broll_enabled, broll_note: sc.broll_note || null };
    });
    adoptIds();
  }
  function has(list, cid) { return list.some(function (x) { return x.cid === cid; }); }
  var lastInvalid = '';

  async function reconcile() {
    var target = clone(model), i, k, cids, res, t, s;
    lastInvalid = '';
    for (i = server.length - 1; i >= 0; i--) {
      if (!has(target, server[i].cid)) {
        cids = server.map(function (x) { return x.cid; }); cids.splice(i, 1);
        res = await call('DELETE', '/script/scenes/' + i, { expected_version: version }, true);
        applyScript(res, cids);
      }
    }
    for (k = 0; k < target.length; k++) {
      t = target[k];
      if (has(server, t.cid)) continue;
      if (!validNarr(t) || !validPrompt(t)) { lastInvalid = 'A cena ' + (k + 1) + ' precisa de texto (5\u2013400 caracteres) e prompt (10\u2013500) para ser salva.'; continue; }
      var pos = Math.min(k, server.length);
      cids = server.map(function (x) { return x.cid; }); cids.splice(pos, 0, t.cid);
      res = await call('POST', '/script/scenes', { expected_version: version, position: pos, narration: norm(t.narration),
        image_prompt: norm(t.image_prompt), label: String(t.label || '').slice(0, 32), caption: String(t.caption || '').slice(0, 110) }, true);
      applyScript(res, cids);
    }
    var order = target.filter(function (x) { return has(server, x.cid); }).map(function (x) {
      return server.findIndex(function (y) { return y.cid === x.cid; }); });
    if (order.length === server.length && order.some(function (v, j) { return v !== j; })) {
      cids = target.filter(function (x) { return has(server, x.cid); }).map(function (x) { return x.cid; });
      res = await call('POST', '/script/scenes/reorder', { expected_version: version, order: order }, true);
      applyScript(res, cids);
    }
    for (k = 0; k < server.length; k++) {
      s = server[k]; t = target.filter(function (x) { return x.cid === s.cid; })[0];
      if (!t || (norm(t.narration) === norm(s.narration) && norm(t.image_prompt) === norm(s.image_prompt))) continue;
      if (!validNarr(t) || !validPrompt(t)) { lastInvalid = 'A cena ' + (k + 1) + ' precisa de texto (5\u2013400 caracteres) e prompt (10\u2013500) para ser salva.'; continue; }
      cids = server.map(function (x) { return x.cid; });
      res = await call('POST', '/script/scenes/' + k, { expected_version: version, narration: norm(t.narration), image_prompt: norm(t.image_prompt) }, true);
      applyScript(res, cids);
    }
    var cannotClear = false;
    for (k = 0; k < server.length; k++) {
      s = server[k]; t = target.filter(function (x) { return x.cid === s.cid; })[0];
      if (!t) continue;
      if (t.asset_id && t.asset_id !== s.asset_id) {
        res = await call('POST', '/scenes/' + encodeURIComponent(s.id) + '/media', { asset_id: t.asset_id, expected_version: version }, false);
        if (res.asset) { s.asset_id = res.asset.id; s.asset_tag = t.asset_tag; }
      } else if (!t.asset_id && s.asset_id) { cannotClear = true; }
      var tn = norm(t.broll_note) || null, sn = norm(s.broll_note) || null;
      if (!!t.broll_enabled !== !!s.broll_enabled || tn !== sn) {
        res = await call('POST', '/scenes/' + encodeURIComponent(s.id) + '/broll', { enabled: !!t.broll_enabled, note: tn }, false);
        s.broll_enabled = !!res.enabled; s.broll_note = res.note || null;
      }
    }
    // o servidor manda em id, dura\u00e7\u00e3o e \u00e1udio; a m\u00eddia s\u00f3 pode ser trocada, nunca removida
    model.forEach(function (m) {
      var sv = server.filter(function (x) { return x.cid === m.cid; })[0];
      if (!sv) return;
      m.id = sv.id; m.duration_s = sv.duration_s;
      if (cannotClear && !m.asset_id) { m.asset_id = sv.asset_id; m.asset_tag = sv.asset_tag; }
      m.audio_state = sv.duration_s ? 'ok' : (m.audio_state === 'stale' ? 'stale' : 'none');
      if (sv.duration_s === null && m.audio_state === 'ok') m.audio_state = 'none';
    });
    return { cannotClear: cannotClear };
  }
  function rollback(err) {
    model = clone(server); undo = []; redo = [];
    adoptIds(); renderAll();
    say('N\u00e3o foi poss\u00edvel salvar: ' + (err && err.message ? err.message : 'tente novamente.') + ' A tela voltou ao \u00faltimo estado salvo.');
  }
  function scheduleSync() {
    if (!editable) return;
    if (pending) return;
    pending = true;
    say('Salvando\u2026');
    queue = queue.then(async function () {
      pending = false;
      var out = await reconcile();
      renderAll();
      say(lastInvalid || (out.cannotClear ? 'Salvo. A m\u00eddia de uma cena s\u00f3 pode ser trocada, n\u00e3o removida.' : 'Altera\u00e7\u00f5es salvas.'));
    }).catch(function (err) { pending = false; rollback(err); });
  }
  window.__sbFlush = function () { return queue; };

  /* ---------------- a\u00e7\u00f5es ---------------- */
  function cardOf(el) { return el.closest('.scene'); }
  function sceneOf(el) { var c = cardOf(el); return c ? model.filter(function (m) { return m.cid === c.dataset.cid; })[0] : null; }
  function indexOf(m) { return model.indexOf(m); }

  function addScene() {
    if (!editable || !structure) return;
    remember();
    var m = { cid: newCid(), id: '', label: 'Nova cena', caption: '', narration: 'Escreva aqui o texto da narra\u00e7\u00e3o desta cena.',
      image_prompt: 'descreva a imagem desejada', duration_s: null, asset_id: null, asset_tag: '', audio_state: 'none',
      audio_history: [], broll_enabled: false, broll_note: null };
    m.id = 'tmp-' + m.cid;
    model.push(m); renderAll();
    var card = cardsEl.querySelector('.scene[data-cid="' + m.cid + '"]');
    if (card) { card.scrollIntoView({ block: 'nearest' }); var tx = card.querySelector('textarea'); if (tx) tx.focus(); }
    toast('Cena adicionada.'); scheduleSync();
  }
  function delScene(m) {
    if (!structure) return;
    if (model.length <= 1) { toast('O v\u00eddeo precisa de ao menos uma cena.'); return; }
    remember(); model.splice(indexOf(m), 1); renderAll(); toast('Cena exclu\u00edda.'); scheduleSync();
  }
  function moveScene(m, d) {
    if (!structure) return;
    var i = indexOf(m), j = i + d;
    if (j < 0 || j >= model.length) return;
    remember(); model[i] = model[j]; model[j] = m; renderAll(); scheduleSync();
  }
  function toggleBroll(m) {
    remember(); m.broll_enabled = !m.broll_enabled; renderAll();
    if (m.broll_enabled) {
      var c = cardsEl.querySelector('.scene[data-cid="' + m.cid + '"] input[data-a="brollnote"]'); if (c) c.focus();
    }
    scheduleSync();
  }

  /* edi\u00e7\u00e3o de texto/prompt/B-roll: um passo de hist\u00f3rico por foco, salvo ao sair do campo ou ap\u00f3s uma pausa */
  var snapAtFocus = null, committed = true, timer = null;
  cardsEl.addEventListener('focusin', function (ev) {
    var c = cardOf(ev.target); if (c) focusCid = c.dataset.cid;
    if (ev.target.matches('[data-a="text"],[data-a="prompt"],[data-a="brollnote"]')) { snapAtFocus = clone(model); committed = false; }
  });
  function commitText(m) {
    if (!m) return;
    var sv = server.filter(function (x) { return x.cid === m.cid; })[0];
    if (sv && (norm(m.narration) !== norm(sv.narration) || norm(m.image_prompt) !== norm(sv.image_prompt))) {
      m.asset_id = null; m.asset_tag = '';   // o backend limpa a m\u00eddia de uma cena cujo texto mudou
      if (m.audio_state === 'ok') m.audio_state = 'stale';
    }
    renderAll(); scheduleSync();
  }
  cardsEl.addEventListener('input', function (ev) {
    var el = ev.target, a = el.dataset && el.dataset.a;
    if (!/^(text|prompt|brollnote)$/.test(a || '')) return;
    var m = sceneOf(el); if (!m) return;
    if (!committed && snapAtFocus) { undo.push(snapAtFocus); if (undo.length > MAX) undo.shift(); redo = []; committed = true; syncButtons(); }
    if (a === 'text') { m.narration = el.value; var c = cardOf(el).querySelector('[data-count]'); if (c) c.textContent = countText(m); updateDock(); }
    if (a === 'prompt') m.image_prompt = el.value;
    if (a === 'brollnote') m.broll_note = el.value;
    clearTimeout(timer); timer = setTimeout(function () { commitText(m); }, 1500);
  });
  cardsEl.addEventListener('change', function (ev) {
    var a = ev.target.dataset && ev.target.dataset.a;
    if (!/^(text|prompt|brollnote)$/.test(a || '')) return;
    clearTimeout(timer); commitText(sceneOf(ev.target));
  });

  /* \u00e1udio real da cena */
  function stopAudio() {
    if (audio) { audio.pause(); audio = null; }
    if (playing) { playing = null; renderAll(); }
  }
  function playScene(m) {
    if (playing === m.cid) { stopAudio(); return; }
    stopAudio();
    audio = new Audio('/studio/videos/' + encodeURIComponent(VID) + '/scenes/' + encodeURIComponent(m.id) + '/narration.wav?t=' + Date.now());
    audio.addEventListener('ended', stopAudio);
    audio.addEventListener('error', function () { stopAudio(); say('N\u00e3o foi poss\u00edvel carregar o \u00e1udio desta cena.'); });
    audio.play().then(function () { playing = m.cid; renderAll(); }).catch(function () { stopAudio(); say('N\u00e3o foi poss\u00edvel tocar o \u00e1udio desta cena.'); });
  }
  async function regenScene(m, btn) {
    btn.disabled = true; say('Gerando o \u00e1udio da cena\u2026');
    try {
      await queue;
      var res = await call('POST', '/scenes/' + encodeURIComponent(m.id) + '/narration/regenerate', null, false);
      var sv = server.filter(function (x) { return x.cid === m.cid; })[0];
      m.audio_state = 'ok'; if (typeof res.duration_s === 'number') { m.duration_s = res.duration_s; if (sv) sv.duration_s = res.duration_s; }
      renderAll(); toast('\u00c1udio da cena gerado.'); say('\u00c1udio da cena atualizado.');
    } catch (err) { say('N\u00e3o foi poss\u00edvel gerar o \u00e1udio: ' + err.message); }
    btn.disabled = false;
  }

  /* modais */
  var dlgMedia = document.getElementById('dlg-media'), dlgHist = document.getElementById('dlg-audio-history');
  var mediaCid = null, mediaTab = 'video';
  function openDialog(d) { if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', ''); }
  function mediaBody() {
    var body = document.getElementById('media-body'), m = model.filter(function (x) { return x.cid === mediaCid; })[0];
    if (!m) return;
    dlgMedia.querySelectorAll('#media-tabs [data-a="media-tab"]').forEach(function (b) {
      var on = b.dataset.v === mediaTab; b.classList.toggle('primary', on);
    });
    if (mediaTab === 'video') {
      var seen = {}, opts = model.filter(function (x) { if (!x.asset_id || seen[x.asset_id]) return false; seen[x.asset_id] = 1; return true; });
      body.innerHTML = '<div class="grid3">' + (opts.map(function (x) {
        return '<button type="button" class="btn" data-a="pickmedia" data-asset="' + esc(x.asset_id) + '" data-tag="' + esc(x.asset_tag) +
          '" aria-label="Usar a m\u00eddia da cena ' + (indexOf(x) + 1) + '"><img src="' + esc(assetUrl(x)) +
          '" alt="" style="width:100%;height:64px;object-fit:cover;border-radius:6px"></button>';
      }).join('') || '<p>Nenhuma m\u00eddia dispon\u00edvel neste escopo.</p>') + '</div>';
    } else if (mediaTab === 'channel') {
      body.innerHTML = '<p>Nenhuma m\u00eddia dispon\u00edvel neste escopo.</p><p class="sample">A biblioteca de m\u00eddia do canal ainda n\u00e3o tem leitura no servidor.</p>';
    } else if (mediaTab === 'files') {
      body.innerHTML = '<p class="sub">Nenhum arquivo enviado. Importa\u00e7\u00e3o real depende do backend.</p><label class="field">Escolher arquivo<input type="file" disabled></label><p class="sample">O envio de arquivos ainda n\u00e3o existe no servidor.</p>';
    } else if (mediaTab === 'generate') {
      body.innerHTML = '<p class="sub">A imagem \u00e9 gerada a partir do prompt da cena durante a produ\u00e7\u00e3o. S\u00f3 o que falta \u00e9 gerado; o que j\u00e1 \u00e9 v\u00e1lido \u00e9 reaproveitado.</p><button type="button" class="btn primary small" data-a="genmissing-from-modal">Gerar tudo o que falta</button>';
    } else if (mediaTab === 'stock') {
      body.innerHTML = '<p class="sub">Buscando\u2026</p>';
      var wantCid = mediaCid;
      queue.then(function () { return call('GET', '/scenes/' + encodeURIComponent(m.id) + '/media/candidates', null, false); }).then(function (res) {
        if (mediaCid !== wantCid || mediaTab !== 'stock') return;
        var list = res.candidates || [];
        body.innerHTML = list.length ? '<div class="stack">' + list.map(function (c, i) {
          return '<div class="between card flat"><span>' + esc(c.attribution || c.author || c.media_type) + ' \u00b7 ' + esc(c.license) +
            (c.width ? ' \u00b7 ' + c.width + '\u00d7' + c.height : '') + '</span><button type="button" class="btn small" data-a="pickcandidate" data-i="' + i + '">Usar</button></div>';
        }).join('') + '</div>' : '<p>Nenhuma m\u00eddia dispon\u00edvel neste escopo.</p>';
        body._cands = list;
      }).catch(function (err) { if (mediaTab === 'stock') body.innerHTML = '<p class="sub">Busca de stock indispon\u00edvel: ' + esc(err.message) + '</p>'; });
    }
  }
  function openMedia(m) {
    if (m.id.indexOf('tmp-') === 0) { say('Aguarde a cena ser salva para escolher a m\u00eddia.'); queue.then(function () { openMedia(m); }); return; }
    mediaCid = m.cid; mediaTab = 'video';
    document.getElementById('media-scene').textContent = 'Cena ' + (indexOf(m) + 1) + ' \u00b7 ' + m.label;
    mediaBody(); openDialog(dlgMedia);
  }
  function pickAsset(assetId, tag) {
    var m = model.filter(function (x) { return x.cid === mediaCid; })[0]; if (!m) return;
    remember(); m.asset_id = assetId; m.asset_tag = tag || m.asset_tag;
    dlgMedia.close(); renderAll(); toast('M\u00eddia da cena atualizada.'); scheduleSync();
  }
  function pickCandidate(c) {
    var m = model.filter(function (x) { return x.cid === mediaCid; })[0]; if (!m) return;
    remember(); dlgMedia.close(); say('Aplicando a m\u00eddia\u2026');
    queue = queue.then(async function () {
      var res = await call('POST', '/scenes/' + encodeURIComponent(m.id) + '/media', { candidate: c, expected_version: version }, false);
      if (res.asset) {
        var lic = String(res.asset.license || ''); var tag = lic.indexOf('ai-generated') === 0 ? 'Arte IA' : (res.asset.kind === 'video' ? 'V\u00eddeo stock' : 'Imagem stock');
        m.asset_id = res.asset.id; m.asset_tag = tag;
        var sv = server.filter(function (x) { return x.cid === m.cid; })[0]; if (sv) { sv.asset_id = res.asset.id; sv.asset_tag = tag; }
      }
      renderAll(); toast('M\u00eddia da cena atualizada.'); say(res.changed ? 'M\u00eddia aplicada.' : (res.reason || 'Nada mudou.'));
    }).catch(function (err) { undo.pop(); syncButtons(); say('N\u00e3o foi poss\u00edvel trocar a m\u00eddia: ' + err.message); });
  }
  function openHistory() {
    var m = model.filter(function (x) { return x.cid === focusCid; })[0] || model[0];
    if (!m) { toast('Sem cenas.'); return; }
    document.getElementById('audio-history-scene').textContent = 'Cena ' + (indexOf(m) + 1) + ' \u00b7 ' + m.label;
    var hist = m.audio_history || [];
    document.getElementById('audio-history-list').innerHTML = hist.length ? hist.map(function (h, i) {
      return '<div class="card flat" style="margin-top:10px"><b>Gera\u00e7\u00e3o ' + (i + 1) + '</b><p class="sub">' + esc(h.text) + '</p></div>';
    }).join('') : '<p>Nenhuma gera\u00e7\u00e3o guardada ainda.</p>';
    openDialog(dlgHist);
  }

  /* delega\u00e7\u00e3o de cliques */
  root.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-a]'); if (!el || el.disabled) return;
    var a = el.dataset.a, m = el.closest('.scene') ? sceneOf(el) : null;
    if (m) focusCid = m.cid;
    if (a === 'addscene') addScene();
    else if (a === 'undo-v3') travel(undo, redo);
    else if (a === 'redo-v3') travel(redo, undo);
    else if (a === 'audio-history') openHistory();
    else if (a === 'media' && m) openMedia(m);
    else if (a === 'broll' && m) toggleBroll(m);
    else if (a === 'delscene' && m) delScene(m);
    else if (a === 'mv' && m) moveScene(m, Number(el.dataset.d));
    else if (a === 'play' && m) playScene(m);
    else if (a === 'regen' && m) regenScene(m, el);
    else if (a === 'media-tab') { mediaTab = el.dataset.v; mediaBody(); }
    else if (a === 'pickmedia') pickAsset(el.dataset.asset, el.dataset.tag);
    else if (a === 'pickcandidate') { var b = document.getElementById('media-body'); if (b._cands) pickCandidate(b._cands[Number(el.dataset.i)]); }
    else if (a === 'genmissing-from-modal') { dlgMedia.close(); var g = document.getElementById('btn-gerar-faltante'); if (g) g.click(); }
  });
  document.addEventListener('error', function (ev) {
    var img = ev.target;
    if (!img || img.tagName !== 'IMG' || !img.closest || !img.closest('.scene [data-f="thumb"]')) return;
    var card = img.closest('.scene'), m = model.filter(function (x) { return x.cid === card.dataset.cid; })[0];
    if (m) { var i = indexOf(m); var t = card.querySelector('[data-f="thumb"]'); t.insertAdjacentHTML('beforebegin', thumbHtml({ asset_id: null }, i)); var f = t.previousElementSibling; f.dataset.k = 'err'; t.remove(); }
  }, true);

  adoptIds(); renderAll();
})();
"""

RUN_JS = r"""
(function () {
  'use strict';
  var slot = document.getElementById('progress-slot');
  var tpl = document.getElementById('progress-card-template');
  var fb = document.getElementById('run-feedback') || document.getElementById('storyboard-feedback');
  var starting = false, timer = null;
  function vidOf() {
    var el = document.querySelector('[data-video-id]'); return el ? el.getAttribute('data-video-id') : '';
  }
  var video = vidOf();
  var labels = {}; try { labels = JSON.parse((tpl && tpl.dataset.labels) || '{}'); } catch (e) { labels = {}; }
  function say(t) { if (fb) fb.textContent = t; }
  function toast(t) {
    var el = document.createElement('div'); el.className = 'toast'; el.setAttribute('role', 'status'); el.textContent = t;
    document.body.appendChild(el); setTimeout(function () { el.remove(); }, 2600);
  }
  function sayWaiting(runId) {
    // Pausa humana: leva direto à execução, onde est\u00e1 o "Continuar" (em vez de s\u00f3 mandar procurar).
    if (!fb) return;
    fb.textContent = 'A produ\u00e7\u00e3o aguarda voc\u00ea. ';
    var a = document.createElement('a'); a.className = 'btn small primary';
    a.href = '/studio/panel/videos/' + encodeURIComponent(video) + '/production-runs/' + encodeURIComponent(runId);
    a.textContent = 'Continuar na execu\u00e7\u00e3o'; fb.appendChild(a);
  }
  var TONE = { SUCCEEDED: ['ok', '\u2713'], RUNNING: ['accent', '\u2026'], WAITING_HUMAN: ['accent', '\u2026'], FAILED: ['bad', '\u2715'] };
  function ensureCard(runId) {
    var card = document.getElementById('progress-card');
    if (!card && tpl && slot) {
      card = tpl.content.firstElementChild.cloneNode(true);
      card.id = 'progress-card'; slot.appendChild(card);
    }
    if (card) { card.dataset.runId = runId; card.dataset.videoId = video; }
    return card;
  }
  function paint(card, stages) {
    var done = stages.filter(function (s) { return s.state === 'SUCCEEDED'; }).length, total = stages.length;
    card.querySelector('[data-f="count"]').textContent = done + '/' + total + ' etapas';
    card.querySelector('[data-f="bar"]').style.width = (total ? Math.round(done / total * 100) : 0) + '%';
    var pills = card.querySelector('[data-f="pills"]'); pills.textContent = '';
    stages.forEach(function (s) {
      var tone = TONE[s.state] || ['', '\u25cb'], p = document.createElement('span');
      p.className = 'pill ' + tone[0]; p.textContent = tone[1] + ' ' + (labels[s.stage] || s.stage); pills.appendChild(p);
    });
  }
  function busyButtons(on) {
    ['btn-render', 'btn-gerar-faltante'].forEach(function (id) {
      var b = document.getElementById(id); if (!b) return;
      b.disabled = on; if (on) b.setAttribute('aria-busy', 'true'); else b.removeAttribute('aria-busy');
    });
    var r = document.getElementById('btn-render'); if (r && on) r.textContent = '\u26a1 Produ\u00e7\u00e3o em andamento\u2026';
  }
  function poll(runId) {
    clearInterval(timer);
    var tick = function () {
      if (document.hidden) return;
      fetch('/studio/videos/' + encodeURIComponent(video) + '/production-runs/' + encodeURIComponent(runId))
        .then(function (r) { return r.ok ? r.json() : null; }).then(function (run) {
          if (!run) return;
          var card = ensureCard(runId); if (card) paint(card, run.stages);
          if (run.state === 'SUCCEEDED' || run.state === 'FAILED' || run.state === 'CANCELLED') {
            clearInterval(timer);
            try { sessionStorage.setItem('run-toast-' + video, run.state); } catch (e) {}
            location.reload();
          } else if (run.state === 'WAITING_HUMAN') { clearInterval(timer); sayWaiting(runId); }
        }).catch(function () {});
    };
    tick(); timer = setInterval(tick, 2500);
  }
  async function startRun() {
    if (starting) return; starting = true; busyButtons(true); say('Iniciando a produ\u00e7\u00e3o\u2026');
    try {
      if (window.__sbFlush) await window.__sbFlush();
      var key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      var r = await fetch('/studio/videos/' + encodeURIComponent(video) + '/production-runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: '{}' });
      var d = await r.json().catch(function () { return {}; });
      if (r.ok && d.run_id) {
        ensureCard(d.run_id); say(d.created === false ? 'J\u00e1 havia uma produ\u00e7\u00e3o em andamento; acompanhando.' : 'Produ\u00e7\u00e3o iniciada.');
        poll(d.run_id);
      } else {
        say('N\u00e3o foi poss\u00edvel iniciar: ' + (window.StudioErro.texto(d, 'resposta inv\u00e1lida do servidor.')));
        starting = false; busyButtons(false);
      }
    } catch (err) { say('Falha de rede ao iniciar a produ\u00e7\u00e3o. Tente novamente.'); starting = false; busyButtons(false); }
  }
  var dlg = document.getElementById('dlg-impacto');
  function askImpact(kind) {
    var missing = Number((document.getElementById('impact-n') || {}).textContent || 0);
    if (kind === 'missing' && !missing) { toast('Nada faltando.'); return; }
    if (dlg && typeof dlg.showModal === 'function') dlg.showModal(); else startRun();
  }
  var btnRender = document.getElementById('btn-render');
  if (btnRender && !btnRender.disabled) btnRender.addEventListener('click', function () { askImpact('render'); });
  var btnGen = document.getElementById('btn-gerar-faltante');
  if (btnGen) btnGen.addEventListener('click', function () { askImpact('missing'); });
  var confirm = document.getElementById('btn-confirmar-render');
  if (confirm) confirm.addEventListener('click', function () { dlg.close(); startRun(); });

  // Estado vazio: o roteiro nasce das fontes (POST /script, já existente). Sem isso o Diretor ficava sem saída.
  var btnRoteiro = document.getElementById('btn-gerar-roteiro');
  if (btnRoteiro) btnRoteiro.addEventListener('click', async function () {
    var out = document.getElementById('roteiro-feedback') || fb;
    btnRoteiro.disabled = true; btnRoteiro.setAttribute('aria-busy', 'true');
    if (out) out.textContent = 'Gerando o roteiro a partir das fontes\u2026';
    try {
      var r = await fetch('/studio/videos/' + encodeURIComponent(video) + '/script', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      var d = await r.json().catch(function () { return {}; });
      if (r.ok) { if (out) out.textContent = 'Roteiro gerado. Abrindo as cenas\u2026'; location.reload(); return; }
      if (out) out.textContent = 'N\u00e3o foi poss\u00edvel gerar o roteiro: ' + window.StudioErro.texto(d, 'tente novamente.', r.status);
    } catch (err) { if (out) out.textContent = 'Falha de rede ao gerar o roteiro. Tente novamente.'; }
    btnRoteiro.disabled = false; btnRoteiro.removeAttribute('aria-busy');
  });
  // Aviso deixado pela tela de criação (ex.: a produção não pôde iniciar), mostrado uma vez.
  try {
    var flash = sessionStorage.getItem('flash-' + video);
    if (flash) { sessionStorage.removeItem('flash-' + video); toast(flash); say(flash); }
  } catch (e) {}

  var live = document.getElementById('progress-card');
  if (live && live.dataset.runId) { starting = true; busyButtons(true); poll(live.dataset.runId); }
  try {
    var done = sessionStorage.getItem('run-toast-' + video);
    if (done) {
      sessionStorage.removeItem('run-toast-' + video);
      toast(done === 'SUCCEEDED' ? 'Produ\u00e7\u00e3o conclu\u00edda. Abra a aprova\u00e7\u00e3o.' : done === 'FAILED' ? 'A produ\u00e7\u00e3o falhou. Veja o progresso / diagn\u00f3stico.' : 'Produ\u00e7\u00e3o cancelada.');
    }
  } catch (e) {}
})();
"""
