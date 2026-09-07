// D-pad по-геометрии: ни одной библиотеки, только getBoundingClientRect() и оценка
// «кто ближе в нажатую сторону». Тут же живёт и ПОКАЗ выделения: гореть на кадре
// должно ровно одно место, и какое - решает последнее действие человека.
'use strict';

const TCNav = {
  // Полка помнит, на какой своей плитке стояли в последний раз: Map «имя полки» → элемент.
  remembered: new Map(),
  // Чем человек трогал страницу последним: 'key' или 'mouse'. Начинается с клавиш -
  // так страницу открывает всякий, кто пришёл с пультом и мыши не касался.
  input: 'key',
  // Единственное горящее место на кадре или ``null``, если не горит ничего.
  lit: null,

  init() {
    document.addEventListener('keydown', TCNav._onKey);
    document.addEventListener('focusin', TCNav._onFocusIn);
    document.addEventListener('pointermove', TCNav._onPointer, { passive: true });
    document.addEventListener('pointerdown', TCNav._onPointer, { passive: true });
  },

  // Показ выделения переносится на новое место ЦЕЛИКОМ: сначала гаснет старое, потом
  // загорается новое, поэтому двух горящих мест разом не бывает даже на один кадр.
  light(place) {
    if (TCNav.lit === place) return;
    if (TCNav.lit) TCNav.lit.classList.remove('is-lit');
    TCNav.lit = place;
    if (place) place.classList.add('is-lit');
  },

  // Фокус НЕ снимается вместе с показом: он нужен и навигации, и чтению с экрана.
  // Мышь гасит только ПОКАЗ клавиатурного выделения, а не сам фокус.
  _onPointer(event) {
    TCNav.input = 'mouse';
    const under = event.target.closest && event.target.closest('[data-tc-focusable]');
    TCNav.light(under || null);
  },

  _onFocusIn(event) {
    const holder = event.target.closest && event.target.closest('[data-tc-group]');
    if (holder) TCNav.remembered.set(holder.dataset.tcGroup, holder);
    if (TCNav.input === 'key') TCNav.light(TCNav._focused());
  },

  _focused() {
    const here = document.activeElement;
    return here && here.matches && here.matches('[data-tc-focusable]') ? here : null;
  },

  _onKey(event) {
    TCNav.input = 'key';
    TCNav.light(TCNav._focused());
    const way = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' }[event.key];
    if (!way) return;
    const here = document.activeElement;
    if (!here || !here.matches || !here.matches('[data-tc-focusable]')) return TCNav._wake(event);
    const there = TCNav.nearest(here, way);
    if (!there) return;
    event.preventDefault();
    there.focus();
    there.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  },

  // 🔴 Фокус НИГДЕ - обычное состояние экрана, а не сбой: так страница открывается у
  // всякого, кто пришёл с пультом и мыши не касался, и так же она остаётся после того,
  // как карточка доехала фоном и подменила своё тело вместе с элементом под фокусом.
  // Стрелка отсюда не делала НИЧЕГО, и выйти из этого положения клавишами было нельзя
  // вовсе: `document.activeElement` - `<body>`, а он не помечен.
  _wake(event) {
    const first = TCNav._candidates()[0];
    if (!first) return;
    event.preventDefault();
    first.focus();
    first.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  },

  // Кандидаты - всё видимое и помеченное; спрятанное (``display:none`` или чужая полка,
  // ушедшая за экран) не мешает счёту, потому что его не измерить осмысленно.
  _candidates() {
    return Array.from(document.querySelectorAll('[data-tc-focusable]'))
      .filter((el) => el.offsetParent !== null);
  },

  nearest(from, way) {
    const start = from.getBoundingClientRect();
    const startMid = { x: start.left + start.width / 2, y: start.top + start.height / 2 };
    let best = null;
    let bestScore = Infinity;
    let bestGroup = null;
    for (const el of TCNav._candidates()) {
      if (el === from) continue;
      const rect = el.getBoundingClientRect();
      const mid = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
      const primary = TCNav._primary(startMid, mid, way);
      if (primary <= 0) continue;
      const cross = TCNav._cross(startMid, mid, way);
      // Крест весит вдвое: ровно поперёк оси - лучший кандидат, наискось - хуже.
      const score = primary + Math.abs(cross) * 2;
      if (score < bestScore) {
        bestScore = score;
        best = el;
        bestGroup = el.dataset.tcGroup;
      }
    }
    if (!best) return null;
    const fromGroup = from.dataset.tcGroup;
    if (bestGroup && bestGroup !== fromGroup) {
      const kept = TCNav.remembered.get(bestGroup);
      if (kept && kept !== best && kept.offsetParent !== null) return kept;
    }
    return best;
  },

  _primary(from, to, way) {
    if (way === 'right') return to.x - from.x;
    if (way === 'left') return from.x - to.x;
    if (way === 'down') return to.y - from.y;
    return from.y - to.y;
  },

  _cross(from, to, way) {
    return way === 'left' || way === 'right' ? to.y - from.y : to.x - from.x;
  },
};

window.TCNav = TCNav;
