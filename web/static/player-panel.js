// Панель плеера, идущего показа (экран 4.5/A, /F): шапка с названием и серией, полоса
// перемотки, ряд управления и подсказка клавиш. Строит DOM один раз (:func:`mount`),
// дальше только правит числа и классы (:func:`update`) - клавиатурный фокус и открытая
// выпадашка не должны переживаться пересборкой узлов.
'use strict';

const TCPlayerPanel = {
  //: Подсказка клавиш (§4.6): колпачок и слово под ним, ключом каталога.
  KEYS: [
    ['SPACE', 'web.keys.pause'],
    ['← →', 'web.keys.seek'],
    ['↑ ↓', 'web.keys.volume'],
    ['F', 'web.keys.fullscreen'],
    ['ESC', 'web.keys.back'],
  ],

  // ``on`` - обработчики нажатий; названия и числа заполняет первый же :func:`update`
  // из ``player.js`` - тут только пустые узлы, чтобы не ждать первого ответа сервера
  // ради самого первого кадра.
  mount(root, on) {
    const frame = document.createElement('div');
    frame.className = 'tc-player-frame';

    const top = document.createElement('div');
    top.className = 'tc-player-top';
    const left = document.createElement('div');
    left.style.display = 'flex';
    left.style.alignItems = 'baseline';
    left.style.gap = '1rem';
    const name = document.createElement('span');
    name.className = 'tc-player-title';
    const ep = document.createElement('span');
    ep.className = 'tc-player-ep';
    ep.hidden = true;
    left.append(name, ep);
    const badge = document.createElement('div');
    badge.className = 'tc-ontv-badge';
    badge.textContent = TC.say('web.player.on_tv');
    badge.hidden = true;
    // Почему вкладка молчит: звук снимается вместе с уходом показа на ТВ, и без этой
    // строки человек читал это как поломку звука (TC-1184).
    const mutedNote = document.createElement('div');
    mutedNote.className = 'tc-ontv-note';
    mutedNote.textContent = TC.say('web.player.muted');
    mutedNote.hidden = true;
    // 🔴 TC-1210. Показ во вкладке пульту не по силам - сервер отказал словом
    // (``no_remote``), а нажатие не вправе остаться немым: короткая надпись говорит,
    // почему перемотка/пауза не взялись, и гасится сама (:func:`flashRefused`).
    const remoteNote = document.createElement('div');
    remoteNote.className = 'tc-ontv-note';
    remoteNote.textContent = TC.say('web.player.no_remote');
    remoteNote.hidden = true;
    top.append(left, mutedNote, remoteNote, badge);

    const keys = document.createElement('div');
    keys.className = 'tc-keys';
    for (const [cap, word] of TCPlayerPanel.KEYS) {
      const key = document.createElement('div');
      key.className = 'tc-key';
      const capEl = document.createElement('div');
      capEl.className = 'tc-key-cap';
      capEl.textContent = cap;
      const whatEl = document.createElement('div');
      whatEl.className = 'tc-key-what';
      whatEl.textContent = TC.say(word);
      key.append(capEl, whatEl);
      keys.appendChild(key);
    }

    const seek = document.createElement('div');
    seek.className = 'tc-seek';
    const bufferedBar = document.createElement('div');
    bufferedBar.className = 'tc-seek-packed';
    const playedBar = document.createElement('div');
    playedBar.className = 'tc-seek-played';
    const head = document.createElement('div');
    head.className = 'tc-seek-head';
    const mark = document.createElement('div');
    mark.className = 'tc-seek-mark';
    seek.append(bufferedBar, playedBar, head, mark);
    seek.addEventListener('click', (event) => {
      const rect = seek.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      on.onSeekTo(frac);
    });

    const controls = document.createElement('div');
    controls.className = 'tc-player-controls';
    const controlsLeft = document.createElement('div');
    controlsLeft.className = 'tc-bar';

    const playpause = document.createElement('button');
    playpause.type = 'button';
    playpause.className = 'tc-playpause';
    playpause.append(document.createElement('i'), document.createElement('i'));
    playpause.tabIndex = 0;
    playpause.dataset.tcFocusable = '1';
    playpause.dataset.tcGroup = 'player';
    playpause.addEventListener('click', on.onToggle);

    const back10 = TCPlayerPanel._btn('web.player.back_ten', 'secondary', () => on.onSeekBy(-10));
    const fwd10 = TCPlayerPanel._btn('web.player.forward_ten', 'secondary', () => on.onSeekBy(10));

    const time = document.createElement('div');
    time.className = 'tc-time';
    const timeTotal = document.createElement('span');
    timeTotal.className = 'tc-time-total';
    time.appendChild(document.createTextNode(''));
    time.appendChild(timeTotal);

    const volWrap = document.createElement('div');
    volWrap.style.display = 'flex';
    volWrap.style.alignItems = 'center';
    volWrap.style.gap = '.75rem';
    volWrap.style.marginLeft = '1.375rem';
    const volLabel = document.createElement('span');
    volLabel.className = 'tc-vol-label';
    volLabel.textContent = TC.say('web.player.volume');
    const vol = document.createElement('div');
    vol.className = 'tc-vol';
    const volFill = document.createElement('i');
    vol.appendChild(volFill);
    volWrap.append(volLabel, vol);

    controlsLeft.append(playpause, back10, fwd10, time, volWrap);

    const actions = document.createElement('div');
    actions.className = 'tc-player-actions';
    const audio = document.createElement('div');
    audio.className = 'tc-btn tc-btn--secondary';
    audio.dataset.tcAudioOption = '1';
    audio.textContent = sessionStorage.getItem('tc-voice') || TC.say('web.player.audio');
    const next = TCPlayerPanel._btn('web.player.next_episode', 'secondary', on.onNext);
    next.hidden = true;
    const tv = TCPlayerPanel._btn('web.player.play_on_tv', 'primary', on.onToggleTv);
    const full = TCPlayerPanel._btn(null, 'secondary', on.onFullscreen, '⤢');
    full.classList.add('tc-btn--square');
    const close = TCPlayerPanel._btn(null, 'secondary', on.onClose, '✕');
    close.classList.add('tc-btn--square');
    close.setAttribute('aria-label', TC.say('web.player.back'));
    actions.append(audio, next, tv, full, close);

    controls.append(controlsLeft, actions);

    const panel = document.createElement('div');
    panel.className = 'tc-player-panel';
    panel.append(seek, controls);

    const bottom = document.createElement('div');
    bottom.className = 'tc-player-bottom';
    bottom.append(keys, panel);

    frame.append(top, bottom);
    root.appendChild(frame);

    return {
      frame,
      name,
      ep,
      badge,
      mutedNote,
      remoteNote,
      time,
      timeTotal,
      playpause,
      bufferedBar,
      playedBar,
      head,
      mark,
      volFill,
      volLabel,
      next,
      tv,
    };
  },

  // 🔴 TC-1210. Отказ пульта показывается на пару секунд и гасится сам - живёт короче
  // надёжной надписи «на ТВ» (:attr:`mutedNote`), потому что относится к ОДНОМУ нажатию,
  // а не к состоянию показа.
  flashRefused(nodes) {
    clearTimeout(TCPlayerPanel._refusedTimer);
    nodes.remoteNote.hidden = false;
    TCPlayerPanel._refusedTimer = setTimeout(() => { nodes.remoteNote.hidden = true; }, 3000);
  },

  _btn(key, kind, handler, text) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tc-btn tc-btn--' + kind;
    button.textContent = key ? TC.say(key) : text;
    button.tabIndex = 0;
    button.dataset.tcFocusable = '1';
    button.dataset.tcGroup = 'player';
    button.addEventListener('click', handler);
    return button;
  },

  // Числа и классы на живом узле: пересборка DOM тут потеряла бы открытую выпадашку и
  // клавиатурный фокус, поэтому :func:`mount` зовётся один раз на сеанс показа.
  //
  // ``snap.packagedPct`` - поле ``warm`` из ``/api/state`` (0..100, ``null`` пока
  // неизвестно): это и есть «докуда упаковано», которое из самого плейлиста не
  // вычислить (лента снята полносеточным VOD с первой секунды). Продукт отдаёт его
  // готовым процентом - конвертировать тут нечего.
  update(nodes, snap) {
    nodes.name.textContent = snap.title;
    nodes.ep.textContent = snap.episode || '';
    nodes.ep.hidden = !snap.episode;
    nodes.time.firstChild.textContent = TCTime.clock(snap.pos);
    nodes.timeTotal.textContent = ' / ' + TCTime.clock(snap.dur);
    nodes.playpause.classList.toggle('is-paused', snap.paused);
    const playedPct = snap.dur > 0 ? (100 * Math.min(snap.pos, snap.dur)) / snap.dur : 0;
    const packagedPct = typeof snap.packagedPct === 'number' ? snap.packagedPct : playedPct;
    nodes.playedBar.style.width = playedPct + '%';
    nodes.bufferedBar.style.width = Math.max(playedPct, packagedPct) + '%';
    nodes.head.style.left = playedPct + '%';
    nodes.mark.style.left = Math.max(playedPct, packagedPct) + '%';
    nodes.mark.textContent = TC.say(snap.onTv ? 'web.player.tv_position' : 'web.player.packaged');
    nodes.mark.classList.toggle('is-tv', snap.onTv);
    nodes.volFill.style.width = Math.round(100 * snap.volume) + '%';
    nodes.volLabel.textContent = TC.say(snap.onTv ? 'web.player.tv_volume' : 'web.player.volume');
    nodes.volLabel.classList.toggle('tc-ontv-vol', snap.onTv);
    nodes.next.hidden = !snap.hasNext;
    nodes.badge.hidden = !snap.onTv;
    // Звук снят с самого нажатия «На ТВ» (``player.js``, ``onToggleTv``), а не с ответа
    // приёмника: всё время подъёма каста (``toTv``) вкладка уже молчит, и объяснение
    // стоит на экране ровно столько же, сколько снят звук.
    nodes.mutedNote.hidden = !snap.onTv && !snap.toTv;
    // Переход на ТВ идёт секундами (рукопожатие и подъём показа на приёмнике), и всё
    // это время кнопка говорит «Готовим…», а не зовёт нажать себя второй раз.
    nodes.tv.textContent = snap.toTv ? TC.say('web.player.preparing')
      : TC.say(snap.onTv ? 'web.player.back_to_browser' : 'web.player.play_on_tv');
    nodes.tv.classList.toggle('tc-btn--primary', !snap.onTv);
    nodes.tv.classList.toggle('tc-btn--secondary', snap.onTv);
  },
};

window.TCPlayerPanel = TCPlayerPanel;
