/* Прототип екрана гравця. Лише фронтенд: усі дані сценарні (data.js), без мережі. */
(() => {
  'use strict';
  const D = window.DATA;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };

  let pace = parseFloat(new URLSearchParams(location.search).get('pace')) || 1; // множник затримок
  const NPC_MS = 300;   // мс на слово NPC (темп мовлення)
  const NARR_MS = 130;  // мс на слово опису

  const S = {
    paused: false, waiters: [], run: null, running: false, turn: 0, minutes: D.scene.startMinutes, day: D.scene.day,
    logN: 0, veilNext: false, errorNotes: [], lastNpc: null, lastOut: null, speaking: null, draft: null, fbMode: null,
    outCount: 0, reactN: 0,
  };

  /* ---------- утиліти ---------- */
  const sleep = (ms, run) => new Promise((res) => {
    const t = setTimeout(res, ms * pace);
    if (run) run.wake = () => { clearTimeout(t); res(); };
  });
  async function gate() { while (S.paused) await new Promise((r) => S.waiters.push(r)); }
  function autoscroll(force) {
    const s = $('#story');
    if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 180) s.scrollTop = s.scrollHeight;
  }
  const fmtClock = () => {
    const h = Math.floor(S.minutes / 60) % 24, m = S.minutes % 60;
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  };
  function updateClock() { $('#clock').textContent = `день ${S.day} · ${fmtClock()}`; }

  /* ---------- журнал фонових суджень (debug) ---------- */
  const TAGS = { jev: 'Jev', llm: 'LLM', npc: 'NPC', code: 'Код', check: 'Перевірка', extractor: 'Екстрактор', roll: 'Відкат', ui: 'UI' };
  function log(kind, text, opts = {}) {
    S.logN++;
    const row = el('div', 'le k-' + kind + (opts.draft ? ' draft' : ''));
    row.append(el('span', 't', `${fmtClock()} #${String(S.logN).padStart(3, '0')}`), el('span', 'tag', TAGS[kind] || kind), document.createTextNode(text));
    const list = $('#logList');
    list.append(row);
    list.scrollTop = list.scrollHeight;
  }

  /* ---------- розмітка тексту ---------- */
  function tokenize(text) {
    const re = /\[([^\]|]+)\|(\w+)\]/g;
    const toks = [];
    const plain = (s) => {
      const parts = s.match(/\S+/g) || [];
      let i = 0;
      const prev = toks[toks.length - 1];
      if (prev && prev.ent && /^\S/.test(s) && parts.length) { prev.after = parts[0]; i = 1; }
      for (; i < parts.length; i++) toks.push({ w: parts[i] });
    };
    let last = 0, m;
    while ((m = re.exec(text))) {
      plain(text.slice(last, m.index));
      m[1].split(' ').forEach((w) => toks.push({ w, ent: m[2], after: '' }));
      last = re.lastIndex;
    }
    plain(text.slice(last));
    return toks;
  }
  function wordNode(tok, i) {
    const s = el('span', 'w');
    s.dataset.i = i;
    if (tok.ent) {
      const e = el('span', 'ent', tok.w);
      e.dataset.ent = tok.ent;
      e.dataset.kind = D.ents[tok.ent].kind;
      s.append(e);
      if (tok.after) s.append(tok.after);
    } else s.textContent = tok.w;
    return s;
  }
  const wordDelay = (w, base) => base * (/[.!?…]$/.test(w) ? 2.4 : /[,;:—]$/.test(w) ? 1.6 : 1);

  async function streamInto(box, toks, base, run) {
    for (let i = 0; i < toks.length; i++) {
      await gate();
      if (run.signal) return false;
      if (i > 0) box.append(' ');
      box.append(wordNode(toks[i], i));
      autoscroll();
      await sleep(wordDelay(toks[i].w, base), run);
    }
    return !run.signal;
  }

  /* ---------- dock ---------- */
  function setDock(mode, who) {
    ['Speak', 'Narr', 'Cut', 'Idle'].forEach((n) => { $('#dock' + n).hidden = n.toLowerCase() !== mode; });
    if (mode === 'speak') $('#speakWho').textContent = `${D.ents[who].nom} говорить…`;
    S.running = mode === 'speak' || mode === 'narr';
  }

  /* ---------- відтворення виводу світу ---------- */
  async function narr(group, text, run) {
    setDock('narr');
    const p = el('p', 'narr');
    group.append(p);
    autoscroll(true);
    return streamInto(p, tokenize(text), NARR_MS, run);
  }

  async function npcBeat(group, b, run) {
    setDock('speak', b.who);
    const box = el('div', 'npc');
    box.dataset.who = b.who;
    const say = el('span', 'say');
    box.append(el('span', 'who', D.ents[b.who].nom), say);
    say.append('«');
    group.append(box);
    autoscroll(true);
    const utt = { box, say, who: b.who, toks: tokenize(b.text), cut: false };
    S.speaking = utt;
    const done = await streamInto(say, utt.toks, NPC_MS, run);
    S.speaking = null;
    S.lastNpc = utt;
    const shown = $$('.w', say).length;
    if (done) {
      say.append('»');
      log('npc', `${D.ents[b.who].nom}: репліка доставлена гравцю (${shown} слів)`);
    } else if (run.signal === 'interrupt') {
      utt.cut = true;
      utt.shown = shown;
      say.append(el('span', 'cutmark', ' —'), '»');
    } else {
      say.append('…»');
      S.lastNpc = null;
    }
    return { done, utt, shown };
  }

  function logBeatsOf(out) { out.log.forEach(([k, t]) => log(k, t)); }

  async function playOutput(out, beats, opts = {}) {
    removeFooters();
    const group = opts.group || el('div', 'out');
    if (!opts.group) $('#feed').append(group);
    const run = S.run = { signal: null, wake: null };
    S.lastOut = { out, group };
    S.lastNpc = null;
    S.outCount++;

    if (opts.regen) {
      group.append(el('div', 'badge', '↻ Перегенеровано з урахуванням вашого пояснення'));
    }
    if (S.errorNotes.length && !opts.regen) log('llm', `У промпт додано пояснень помилок кампанії: ${S.errorNotes.length}`);

    if (S.veilNext) {
      S.veilNext = false;
      setVeilUI();
      group.append(el('div', 'sysnote veil', D.veilText));
      log('code', 'Завіса: вивід світу не показано гравцю; стан оновлено так само');
      logBeatsOf(out);
      return finishOutput(out, group);
    }

    let interrupted = null;
    for (const b of beats) {
      if (run.signal) break;
      if (b.t === 'narr') await narr(group, b.text, run);
      else {
        const r = await npcBeat(group, b, run);
        if (!r.done && run.signal === 'interrupt') { interrupted = { ...r, who: b.who }; break; }
      }
    }

    const sig = run.signal;
    S.run = null;
    if (sig === 'interrupt') {
      handleCut(interrupted.utt, interrupted.shown, false);
      await reactionNarr(group, interrupted.who);
    } else if (sig === 'skip') {
      trailOff(group);
      group.append(el('div', 'sysnote', '⏭ ' + out.summary));
      log('code', 'Пропуск: сцена минула одним реченням; подія записана');
      logBeatsOf(out);
    } else if (sig === 'veil') {
      trailOff(group);
      group.append(el('div', 'sysnote veil', D.veilText));
      log('code', 'Завіса: решту виводу сховано; стан оновлено');
      logBeatsOf(out);
    } else {
      logBeatsOf(out);
    }
    finishOutput(out, group);
  }

  function trailOff(group) {
    const last = group.lastElementChild;
    if (last && last.classList.contains('narr')) last.append('…');
  }

  function finishOutput(out, group) {
    setDock('idle');
    S.running = false;
    addFooter(group);
    autoscroll(true);
    updateIdle();
  }

  async function reactionNarr(group, who) {
    const run = S.run = { signal: null, wake: null };
    const out = S.lastOut.out;
    await narr(group, out.interrupt[who] || out.interrupt.horst, run);
    S.run = null;
  }

  function removeFooters() { $$('.outfoot').forEach((f) => f.remove()); }
  function addFooter(group) {
    removeFooters();
    const f = el('div', 'outfoot');
    const u = S.lastNpc;
    if (u && !u.cut && group.contains(u.box)) {
      const b = el('button', 'btn cutbtn', '✂ Перебити в останній репліці');
      b.id = 'btnCut';
      f.append(b);
    }
    const e = el('button', 'btn', '⚠ Помилка моделі');
    e.id = 'btnModelErr';
    f.append(e);
    group.append(f);
  }

  /* ---------- переривання ---------- */
  function handleCut(utt, shown, retro, remaining) {
    const last = $$('.w', utt.say)[shown - 1];
    const lastWord = last ? last.textContent.replace(/[«»]/g, '') : '';
    const name = D.ents[utt.who].nom;
    const total = utt.toks.length;
    log('code', `Подія: гравець перебив ${D.ents[utt.who].acc} на слові ${shown}/${total} «${lastWord}»${retro ? ' (заднім числом, вікно: остання репліка NPC)' : ''}. Видима всім присутнім за звичайним сприйняттям`);
    log('roll', 'Все після точки обриву не було сказано. Записи, витягнені з відрізаного тексту, і похідні від них видалено');
    const rest = remaining || utt.toks.slice(shown).map((t) => t.w + (t.after || '')).join(' ');
    log('npc', `${name} зберіг недосказане як приватний намір: «${rest.split(' ').slice(0, 9).join(' ')}…»`);
    log('jev', `${name} зрозумів, що його перебили? так · p=0.99`);
  }

  function applyCutRetro(utt, idx) {
    const words = $$('.w', utt.say);
    const target = words[idx];
    const nodes = [];
    for (let n = target.nextSibling; n; n = n.nextSibling) nodes.push(n);
    const remaining = words.slice(idx + 1).map((w) => w.textContent).join(' ');
    const wrap = el('span', 'gone');
    nodes.forEach((n) => wrap.append(n));
    const mark = el('span', 'cutmark', ' —');
    utt.say.append(mark, wrap, '»');
    utt.cut = true;
    setTimeout(() => wrap.classList.add('fade'), 1100);
    setTimeout(() => wrap.remove(), 2100);
    return remaining;
  }

  /* ---------- режим ретроактивного переривання ---------- */
  function enterCutMode() {
    const u = S.lastNpc;
    if (!u || u.cut) return;
    $('#feed').classList.add('cutmode');
    const ws = $$('.w', u.say);
    ws.slice(0, -1).forEach((w) => w.classList.add('cuttable'));
    u.box.classList.add('cut-glow');
    u.box.scrollIntoView({ block: 'center' });
    setDock('cut');
    hideConfirm();
  }
  function exitCutMode() {
    $('#feed').classList.remove('cutmode');
    $$('.cuttable, .will-gone, .sel').forEach((w) => w.classList.remove('cuttable', 'will-gone', 'sel'));
    $$('.cut-glow').forEach((b) => b.classList.remove('cut-glow'));
    hideConfirm();
    setDock('idle');
    updateIdle();
  }
  function askCut(wordEl) {
    const u = S.lastNpc;
    const idx = +wordEl.dataset.i;
    $$('.w', u.say).forEach((w) => {
      w.classList.toggle('will-gone', +w.dataset.i > idx);
      w.classList.toggle('sel', w === wordEl);
    });
    const c = $('#confirm');
    c.replaceChildren();
    const p = el('p');
    p.append('Перебити після «', el('b', null, wordEl.textContent.replace(/[«»]/g, '')), '»?');
    const row = el('div', 'row');
    const ok = el('button', 'go', 'Перебити');
    ok.id = 'cutOk';
    const no = el('button', null, 'Ні');
    no.id = 'cutNo';
    row.append(ok, no);
    c.append(p, row);
    placeMenu(c, wordEl);
    c.hidden = false;
    ok.onclick = async () => {
      const remaining = applyCutRetro(u, idx);
      hideConfirm();
      $('#feed').classList.remove('cutmode');
      $$('.cuttable, .will-gone, .sel').forEach((w) => w.classList.remove('cuttable', 'will-gone', 'sel'));
      u.box.classList.remove('cut-glow');
      handleCut(u, idx + 1, true, remaining);
      removeFooters();
      const group = S.lastOut.group;
      await reactionNarr(group, u.who);
      finishOutput(S.lastOut.out, group);
    };
    no.onclick = () => { $$('.w', u.say).forEach((w) => w.classList.remove('will-gone', 'sel')); hideConfirm(); };
  }
  function hideConfirm() { $('#confirm').hidden = true; }

  /* ---------- меню сутностей ---------- */
  function placeMenu(m, anchor) {
    m.hidden = false;
    const r = anchor.getBoundingClientRect();
    const mw = m.offsetWidth, mh = m.offsetHeight;
    let left = Math.min(Math.max(8, r.left + r.width / 2 - mw / 2), innerWidth - mw - 8);
    let top = r.bottom + 8;
    if (top + mh > innerHeight - 8) top = Math.max(8, r.top - mh - 8);
    m.style.left = left + 'px';
    m.style.top = top + 'px';
  }
  function entActions(id) {
    const e = D.ents[id];
    if (e.kind === 'person') return [
      ['Придивитись', `Уважно дивлюсь на ${e.acc}.`, ''],
      ['Заговорити', `Повертаюсь до ${e.gen}.`, ''],
      ['Запитати прямо', `Дивлюсь ${e.gen} в очі.`, 'Що ви від мене приховуєте?'],
    ];
    if (e.kind === 'place') return [
      ['Розпитати', '', `Розкажіть мені про ${e.acc}.`],
      ['Піти туди', `Прямую до ${e.gen}.`, ''],
    ];
    return [
      ['Оглянути', `Оглядаю ${e.acc}.`, ''],
      ['Взяти', `Беру ${e.acc}.`, ''],
      ['Показати іншим', `Показую ${e.acc} усім за столом.`, ''],
    ];
  }
  function openEntMenu(entEl) {
    hideConfirm();
    const id = entEl.dataset.ent, e = D.ents[id];
    const m = $('#menu');
    m.replaceChildren();
    const h = el('div', 'mh');
    h.append(el('b', null, e.nom[0].toUpperCase() + e.nom.slice(1)), e.note);
    m.append(h);
    entActions(id).forEach(([label, act, say]) => {
      const b = el('button', null, label);
      b.onclick = () => {
        m.hidden = true;
        $('#fAct').value = act;
        $('#fSay').value = say;
        clearDraft();
        fitAll();
        updateIdle();
        log('ui', `Чернетка з меню «${label}» → ${e.nom} (поза журналом, доки не надіслано)`, { draft: true });
        if (!S.running) $(say && !act ? '#fSay' : '#fAct').focus();
      };
      m.append(b);
    });
    placeMenu(m, entEl);
  }

  /* ---------- швидкі реакції ---------- */
  function buildReactions() {
    const box = $('#reacts');
    D.reactions.forEach((r) => {
      const b = el('button', 'btn', r.label);
      b.dataset.react = r.id;
      b.onclick = () => {
        const u = S.speaking;
        if (!u) return;
        u.say.append(' ', el('span', 'react', r.marker));
        autoscroll();
        const p = [0.91, 0.87, 0.95, 0.72][S.reactN++ % 4];
        log('code', `Подія: ${r.log} під час репліки ${D.ents[u.who].gen}; спостережувана, її сприймають усі присутні`);
        log('jev', `${D.ents[u.who].nom} помітив і відреагує? так · p=${p.toFixed(2)}`);
      };
      box.append(b);
    });
  }

  /* ---------- хід гравця ---------- */
  const fAct = $('#fAct'), fSay = $('#fSay');
  function fit(t) { t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight + 2, 120) + 'px'; }
  function fitAll() { fit(fAct); fit(fSay); }
  function updateIdle() {
    $('#btnSend').disabled = !(fAct.value.trim() || fSay.value.trim());
    $('#lockAct').hidden = $('#lockSay').hidden = $('#draftTools').hidden = !S.draft;
    $('.composer').classList.toggle('has-draft', !!S.draft);
    $('#draftNote').hidden = !S.draft;
  }
  function clearDraft() {
    S.draft = null; S.fbMode = null;
    $('#fbBox').hidden = true;
    ['Act', 'Say'].forEach((k) => { $('#lock' + k).setAttribute('aria-pressed', 'false'); $('#f' + k).closest('.field').classList.remove('locked'); });
    updateIdle();
  }
  [fAct, fSay].forEach((t) => t.addEventListener('input', () => { fit(t); updateIdle(); }));

  function submitTurn() {
    const act = fAct.value.trim(), say = fSay.value.trim();
    if (!act && !say) return;
    removeFooters();
    const me = el('div', 'me');
    me.append(el('span', 'who', 'Рагнар'));
    if (act) me.append(el('p', 'act', act));
    if (say) me.append(el('p', 'sayline', '«' + say + '»'));
    $('#feed').append(me);
    log('code', `Хід гравця записано в журнал: дія=${act ? 'є' : '—'}, слова=${say ? 'є' : '—'}. Чернетки до цього моменту в журнал не потрапляли`);
    fAct.value = fSay.value = '';
    clearDraft();
    fitAll();
    S.turn++;
    S.minutes += 7;
    updateClock();
    const out = nextOutput();
    playOutput(out, out.beats);
  }
  function nextOutput() {
    const idx = S.turn === 0 ? 0 : S.turn % 2 === 1 ? 1 : 2;
    nextOutput.cur = D.outputs[idx];
    return nextOutput.cur;
  }

  /* ---------- помічник ходу ---------- */
  function openAssist() {
    const set = D.assist[Math.min(S.turn, D.assist.length - 1)];
    const body = $('#assistBody');
    body.replaceChildren(el('div', 'skel'), el('div', 'skel'), el('div', 'skel'), el('div', 'skel'));
    openSheet('assistSheet');
    log('ui', 'Помічник ходу: контекст = лише знання Рагнара; 4 варіанти (поза журналом)', { draft: true });
    setTimeout(() => {
      body.replaceChildren();
      set.forEach((o, i) => {
        const b = el('button', 'opt');
        b.dataset.opt = i;
        b.append(el('b', null, o.title), el('i', null, o.act), el('span', null, '«' + o.say + '»'));
        b.onclick = () => applyOption(set, i);
        body.append(b);
      });
    }, 650 * pace);
  }
  function applyOption(set, i) {
    const o = set[i];
    fAct.value = o.act;
    fSay.value = o.say;
    S.draft = { set, i, title: o.title };
    ['Act', 'Say'].forEach((k) => { $('#lock' + k).setAttribute('aria-pressed', 'false'); $('#f' + k).closest('.field').classList.remove('locked'); });
    $('#fbBox').hidden = true;
    $('#draftNote').textContent = `Чернетка помічника: «${o.title}». Вона не потрапить у журнал, доки ви не надішлете.`;
    closeSheets();
    fitAll();
    updateIdle();
  }
  function toggleLock(k) {
    const b = $('#lock' + k), on = b.getAttribute('aria-pressed') !== 'true';
    b.setAttribute('aria-pressed', on);
    $('#f' + k).closest('.field').classList.toggle('locked', on);
    log('ui', `Гравцю сподобалось: ${k === 'Act' ? 'дія' : 'слова'} ${on ? 'зафіксовано дослівно' : 'знято з фіксації'}`, { draft: true });
  }
  function openFeedback(mode) {
    S.fbMode = mode;
    const box = $('#fbBox');
    box.hidden = false;
    $('#fbLabel').textContent = mode === 'dislike' ? 'Що не так з цим варіантом?' : 'Як змінити цей варіант?';
    $('#fbText').placeholder = mode === 'dislike' ? 'Напишіть кілька слів' : 'Наприклад: м’якше, без погроз';
    $('#fbText').value = '';
    $('#fbText').focus();
  }
  function sendFeedback() {
    const txt = $('#fbText').value.trim();
    if (!txt || !S.draft) return;
    const lockedAct = $('#lockAct').getAttribute('aria-pressed') === 'true';
    const lockedSay = $('#lockSay').getAttribute('aria-pressed') === 'true';
    if (S.fbMode === 'dislike') {
      S.draft.i = (S.draft.i + 1) % S.draft.set.length;
      const o = S.draft.set[S.draft.i];
      if (!lockedAct) fAct.value = o.act;
      if (!lockedSay) fSay.value = o.say;
      S.draft.title = o.title;
      $('#draftNote').textContent = `Новий варіант: «${o.title}» (з урахуванням «${txt}»). Зафіксовані частини лишились дослівно.`;
      log('ui', `Зворотний зв’язок «${txt}» → інший варіант; зафіксовано: ${[lockedAct && 'дія', lockedSay && 'слова'].filter(Boolean).join(', ') || 'нічого'}`, { draft: true });
    } else {
      if (!lockedAct) fAct.value = fAct.value.replace(/\.$/, '') + ` [${txt}].`;
      if (!lockedSay) fSay.value = fSay.value + ` [${txt}]`;
      $('#draftNote').textContent = `Варіант змінено за вашою вказівкою: «${txt}». Зафіксовані частини лишились дослівно. (Імітація: справжня модель перепише лише вільні частини.)`;
      log('ui', `Зміна варіанта «${txt}»; зафіксовані частини не чіпаємо`, { draft: true });
    }
    $('#fbBox').hidden = true;
    fitAll();
    updateIdle();
  }

  /* ---------- шторки ---------- */
  const sheets = ['charPanel', 'assistSheet', 'errSheet'];
  function openSheet(id) {
    closeSheets();
    const s = document.getElementById(id);
    s.classList.add('open');
    s.setAttribute('aria-hidden', 'false');
    $('#scrim').hidden = false;
    $('#menu').hidden = true;
    hideConfirm();
  }
  function closeSheets() {
    sheets.forEach((id) => { const s = document.getElementById(id); s.classList.remove('open'); s.setAttribute('aria-hidden', 'true'); });
    $('#scrim').hidden = true;
  }
  function buildChar() {
    const body = $('#charBody');
    D.panel.forEach((c) => {
      const card = el('section', 'card');
      card.dataset.sec = c.id;
      card.append(el('h3', null, c.title));
      const chips = el('div', 'chips');
      c.chips.forEach(([t, vis]) => {
        const ch = el('span', 'chip');
        ch.append(el('i', 'dot' + (vis ? ' on' : '')), t);
        chips.append(ch);
      });
      card.append(chips, el('p', null, c.prose));
      body.append(card);
    });
  }

  /* ---------- зміст: пауза, завіса, пропуск ---------- */
  function setPause(on) {
    S.paused = on;
    $('#pauseOv').hidden = !on;
    $('#btnPause').setAttribute('aria-pressed', on);
    if (!on) { S.waiters.splice(0).forEach((r) => r()); }
    log('code', on ? 'Пауза: світ зупинено' : 'Пауза знята: світ іде далі');
  }
  function setVeilUI() {
    $('#btnVeil').setAttribute('aria-pressed', S.veilNext);
    $('#veilTag').hidden = !S.veilNext;
  }
  function signal(s) { if (S.run) { S.run.signal = s; S.run.wake && S.run.wake(); } }

  function skipIdle() {
    removeFooters();
    S.turn++;
    S.minutes += 15;
    updateClock();
    const out = nextOutput();
    const g = el('div', 'out');
    g.append(el('div', 'sysnote', '⏭ ' + out.summary));
    $('#feed').append(g);
    S.lastNpc = null;
    S.lastOut = { out, group: g };
    log('code', 'Пропуск: сцена минула одним реченням (хід без дії гравця); подія записана');
    logBeatsOf(out);
    finishOutput(out, g);
  }

  /* ---------- помилка моделі ---------- */
  async function regenerate(note) {
    const { out, group } = S.lastOut;
    S.errorNotes.push(note);
    log('roll', `Помилка моделі: «${note}». Перегенерується лише останній вивід світу; хід гравця лишається. Записи, похідні від старого тексту, видалено`);
    log('llm', `Пояснення збережено в кампанії (${S.errorNotes.length}) і додається до наступних промптів`);
    group.replaceChildren();
    S.lastNpc = null;
    await playOutput(out, out.alt, { group, regen: true });
  }

  /* ---------- події ---------- */
  function bind() {
    $('#sceneTitle').textContent = D.scene.title;
    $('#btnChar').onclick = () => openSheet('charPanel');
    $('#charClose').onclick = closeSheets;
    $('#assistClose').onclick = closeSheets;
    $('#errClose').onclick = closeSheets;
    $('#scrim').onclick = closeSheets;
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeSheets(); $('#menu').hidden = true; hideConfirm(); } });

    $('#btnDebug').onclick = () => {
      const on = $('#debugPanel').hidden;
      $('#debugPanel').style.top = $('.strip').getBoundingClientRect().bottom + 'px';
      $('#debugPanel').hidden = !on;
      $('#btnDebug').setAttribute('aria-pressed', on);
    };
    $$('.chip-sm[data-pace]').forEach((b) => b.onclick = () => {
      pace = parseFloat(b.dataset.pace);
      $$('.chip-sm[data-pace]').forEach((x) => x.classList.toggle('on', x === b));
    });

    $('#btnPause').onclick = () => setPause(true);
    $('#btnResume').onclick = () => setPause(false);
    $('#btnVeil').onclick = () => {
      if (S.running) { signal('veil'); return; }
      S.veilNext = !S.veilNext;
      setVeilUI();
      log('code', S.veilNext ? 'Завіса: наступна сцена буде за кадром' : 'Завіса скасована');
    };
    $('#btnSkip').onclick = () => { if (S.running) signal('skip'); else skipIdle(); };

    $('#btnInterrupt').onclick = () => signal('interrupt');
    $('#btnCutCancel').onclick = exitCutMode;
    $('#btnAssist').onclick = openAssist;
    $('#btnSend').onclick = submitTurn;
    $('#lockAct').onclick = () => toggleLock('Act');
    $('#lockSay').onclick = () => toggleLock('Say');
    $('#btnDislike').onclick = () => openFeedback('dislike');
    $('#btnModify').onclick = () => openFeedback('modify');
    $('#btnHand').onclick = () => { $('#draftNote').textContent = 'Правте руками. Текст нижче вже ваш, помічник його не чіпає.'; fAct.focus(); };
    $('#btnOwn').onclick = () => { fAct.value = fSay.value = ''; clearDraft(); fitAll(); updateIdle(); fAct.focus(); };
    $('#fbSend').onclick = sendFeedback;
    $('#fbText').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendFeedback(); });

    $('#errText').addEventListener('input', () => { $('#errSend').disabled = $('#errText').value.trim().length < 6; });
    $('#errSend').onclick = () => {
      const note = $('#errText').value.trim();
      if (note.length < 6) return;
      $('#errText').value = '';
      $('#errSend').disabled = true;
      closeSheets();
      regenerate(note);
    };

    // делегування кліків у стрічці
    $('#feed').addEventListener('click', (e) => {
      const t = e.target;
      if (t.closest('#btnCut')) return enterCutMode();
      if (t.closest('#btnModelErr')) return openSheet('errSheet');
      const w = t.closest('.cuttable');
      if (w && $('#feed').classList.contains('cutmode')) return askCut(w);
      const ent = t.closest('.ent');
      if (ent) { e.stopPropagation(); return openEntMenu(ent); }
    });
    document.addEventListener('pointerdown', (e) => {
      if (!e.target.closest('#menu') && !e.target.closest('.ent')) $('#menu').hidden = true;
      if (!e.target.closest('#confirm') && !e.target.closest('.cuttable')) hideConfirm();
    });

    // свайп: вліво відкриває панель персонажа, вправо закриває
    let sx = 0, sy = 0, st = 0;
    const start = (e) => { sx = e.clientX; sy = e.clientY; st = Date.now(); };
    $('#story').addEventListener('pointerdown', start);
    $('#story').addEventListener('pointerup', (e) => {
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (dx < -70 && Math.abs(dy) < 50 && Date.now() - st < 700) openSheet('charPanel');
    });
    $('#charPanel').addEventListener('pointerdown', start);
    $('#charPanel').addEventListener('pointerup', (e) => {
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (dx > 70 && Math.abs(dy) < 50 && Date.now() - st < 700) closeSheets();
    });
  }

  /* ---------- старт ---------- */
  function boot() {
    buildReactions();
    buildChar();
    bind();
    updateClock();
    log('code', `Сесію ініціалізовано: ${D.scene.place}, день ${D.scene.day}. Журнал подій append-only`);
    log('code', 'Режим часу: покроковий (світ чекає на гравця); у фоні застосунку світ стоїть');
    nextOutput.cur = D.outputs[0];
    playOutput(D.outputs[0], D.outputs[0].beats);
  }
  boot();
})();
