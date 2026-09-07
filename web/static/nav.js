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
  // Бегущая анимация подписи под горящей плиткой: `<div class="tc-tile-cap">` → сама
  // функция кадра. Пока элемент - ключ карты, его цикл продолжается; исчез из карты -
  // прошлый `requestAnimationFrame` увидит чужой шаг и остановится сам, без отмены по id.
  _capAnim: new Map(),

  init() {
    document.addEventListener('keydown', TCNav._onKey);
    document.addEventListener('focusin', TCNav._onFocusIn);
    document.addEventListener('pointermove', TCNav._onPointer, { passive: true });
    document.addEventListener('pointerdown', TCNav._onPointer, { passive: true });
    // Колесо мыши крутит полку вбок. Работает только над полкой, которой правда есть
    // куда ехать (`scrollWidth > clientWidth`): пустая полка и весь остальной документ
    // вертикальное колесо не замечают и листаются как обычно. Боковое движение колеса
    // или трекпада (`deltaX`) сюда не попадает вовсе - у него уже есть родная прокрутка
    // через `overflow-x: auto`, и отбирать её незачем.
    document.addEventListener('wheel', TCNav._onWheel, { passive: false });
  },

  // Показ выделения переносится на новое место ЦЕЛИКОМ: сначала гаснет старое, потом
  // загорается новое, поэтому двух горящих мест разом не бывает даже на один кадр.
  light(place) {
    if (TCNav.lit === place) return;
    if (TCNav.lit) {
      TCNav.lit.classList.remove('is-lit');
      TCNav._stopCapScroll(TCNav.lit);
    }
    TCNav.lit = place;
    if (place) {
      place.classList.add('is-lit');
      TCNav._startCapScroll(place);
    }
  },

  // Полка едет разом на весь дельта колеса, без плавного разгона: `.tc-row` держит
  // `scroll-behavior: smooth` ради стрелок (`scrollIntoView`), а тот же переход у
  // `scrollLeft` только ЗАПИСЫВАЕТ движение в очередь браузера и не меняет свойство
  // немедленно - следующий тик колеса складывался бы с недоехавшим прошлым. Инлайновый
  // `auto` на миг перебивает класс ровно на один прыжок и тут же снимается, стрелкам
  // достаётся прежний плавный ход.
  _onWheel(event) {
    if (event.deltaX !== 0 || event.deltaY === 0) return;
    const row = event.target.closest && event.target.closest('.tc-row');
    if (!row || row.scrollWidth <= row.clientWidth) return;
    event.preventDefault();
    const was = row.style.scrollBehavior;
    row.style.scrollBehavior = 'auto';
    row.scrollLeft += event.deltaY;
    row.style.scrollBehavior = was;
  },

  // Подпись, не влезшая в отведённые две строки (`is-lit` разворачивает её в
  // `white-space: normal` внутри короба фиксированной высоты), едет вниз до конца и
  // обратно, пока плитка горит: место под текст не растёт ни на пиксель, а прочитать
  // остаток можно, просто задержавшись взглядом. `is-lit` уже применён строкой раньше,
  // так что `scrollHeight` меряет разложенный текст, а не однострочный обрезок.
  _startCapScroll(place) {
    const cap = place.querySelector && place.querySelector('.tc-tile-cap');
    if (!cap) return;
    const max = cap.scrollHeight - cap.clientHeight;
    if (max <= 0) return;
    const half = 1400;
    const started = performance.now();
    const step = (now) => {
      if (TCNav._capAnim.get(cap) !== step) return;
      const t = (now - started) % (half * 2);
      const phase = t < half ? t / half : 2 - t / half;
      cap.scrollTop = max * phase;
      requestAnimationFrame(step);
    };
    TCNav._capAnim.set(cap, step);
    requestAnimationFrame(step);
  },

  // Гаснущая плитка возвращает подпись на начало сразу, а не там, где её застало
  // выключение: следующий взгляд на неё в покое должен видеть тот же обрезок, что и до
  // наведения.
  _stopCapScroll(place) {
    const cap = place.querySelector && place.querySelector('.tc-tile-cap');
    if (!cap) return;
    TCNav._capAnim.delete(cap);
    cap.scrollTop = 0;
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
