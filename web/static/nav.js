// D-pad по-геометрии: ни одной библиотеки, только getBoundingClientRect() и оценка
// «кто ближе в нажатую сторону». Ссылка на приём и её причину - SPEC.md §4.6.
'use strict';

const TCNav = {
  // Полка помнит, на какой своей плитке стояли в последний раз: Map «имя полки» → элемент.
  remembered: new Map(),

  init() {
    document.addEventListener('keydown', TCNav._onKey);
    document.addEventListener('focusin', TCNav._onFocusIn);
  },

  _onFocusIn(event) {
    const holder = event.target.closest && event.target.closest('[data-tc-group]');
    if (holder) TCNav.remembered.set(holder.dataset.tcGroup, holder);
  },

  _onKey(event) {
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
  // вовсе: `document.activeElement` - `<body>`, а он не помечен (замер на стенде `.104`
  // 07-09-2026, пункт 11 приёмки: 12 нажатий, фокус остался на `BODY`).
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
