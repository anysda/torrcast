// D-pad по-геометрии: ни одной библиотеки, только getBoundingClientRect() и оценка
// «кто ближе в нажатую сторону». Тут же живёт и ПОКАЗ выделения: гореть на кадре
// должно ровно одно место, и какое - решает последнее действие человека.
'use strict';

const TCNav = {
  // Чем человек трогал страницу последним: 'key' или 'mouse'. Начинается с клавиш -
  // так страницу открывает всякий, кто пришёл с пультом и мыши не касался.
  input: 'key',
  // Единственное горящее место на кадре или ``null``, если не горит ничего.
  lit: null,
  // Где стоит указатель (координаты окна) или ``null``, если он ушёл со страницы.
  // Прокрутка под неподвижной мышью событий мыши не рождает, и `_onScroll` ищет
  // плитку под этой точкой сам.
  _pointer: null,
  _relight: 0,
  // Бегущая анимация подписи под горящей плиткой: `<div class="tc-tile-cap">` → сама
  // функция кадра. Пока элемент - ключ карты, его цикл продолжается; исчез из карты -
  // прошлый `requestAnimationFrame` увидит чужой шаг и остановится сам, без отмены по id.
  _capAnim: new Map(),

  init() {
    document.addEventListener('keydown', TCNav._onKey);
    document.addEventListener('focusin', TCNav._onFocusIn);
    document.addEventListener('pointermove', TCNav._onPointer, { passive: true });
    document.addEventListener('pointerdown', TCNav._onPointer, { passive: true });
    document.addEventListener('pointerout', TCNav._onPointerOut, { passive: true });
    // Прокрутка не всплывает: и полку, и страницу слышно только на погружении.
    document.addEventListener('scroll', TCNav._onScroll, { capture: true, passive: true });
    // Вертикальное колесо листает СТРАНИЦУ, над полкой тоже, и сюда не попадает. Вбок
    // полку везут боковое колесо и трекпад (родная прокрутка), кнопки над полкой и
    // Shift+колесо - последнее ловится здесь.
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

  // Shift+колесо везёт полку вбок там, где браузер сам не превращает его в боковое
  // движение. Полка едет разом на весь шаг: инлайновый `auto` на миг перебивает
  // `scroll-behavior: smooth`, иначе тики колеса копились бы в очереди плавного хода.
  _onWheel(event) {
    if (!event.shiftKey || event.deltaX !== 0 || event.deltaY === 0) return;
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
    const under = event.target.closest && event.target.closest('[data-tc-focusable]');
    // Указатель вне интерактивного места не отменяет последнее действие с клавиатуры:
    // иначе один уход мыши в угол гасит фокус ещё до scroll, хотя прокручивать можно
    // колесом в любой части страницы. Над плиткой остаётся мышиный режим, чтобы
    // неподвижный указатель после прокрутки сразу зажигал новую плитку под собой.
    if (!under && TCNav.input === 'key') return;
    TCNav.input = 'mouse';
    TCNav._pointer = { x: event.clientX, y: event.clientY };
    TCNav.light(under || null);
  },

  _onPointerOut(event) {
    if (!event.relatedTarget) TCNav._pointer = null;
  },

  // Полка или страница проехала под неподвижной мышью: гореть должно то, что теперь под
  // указателем, а не то, что было под ним до прокрутки. Раз в кадр, а не на каждый тик;
  // бегущая подпись крутит свой `scrollTop` сама и в счёт не идёт.
  _onScroll(event) {
    const moved = event.target;
    if (moved && moved.classList && moved.classList.contains('tc-tile-cap')) return;
    if (TCNav.input !== 'mouse' || !TCNav._pointer || TCNav._relight) return;
    TCNav._relight = requestAnimationFrame(() => {
      TCNav._relight = 0;
      const spot = TCNav._pointer;
      if (TCNav.input !== 'mouse' || !spot) return;
      const at = document.elementFromPoint(spot.x, spot.y);
      TCNav.light((at && at.closest('[data-tc-focusable]')) || null);
    });
  },

  _onFocusIn() {
    if (TCNav.input === 'key') TCNav.light(TCNav._focused());
  },

  _focused() {
    const here = document.activeElement;
    return here && here.matches && here.matches('[data-tc-focusable]') ? here : null;
  },

  _typing() {
    const here = document.activeElement;
    return !!here && (here.tagName === 'INPUT' || here.tagName === 'TEXTAREA');
  },

  _onKey(event) {
    // Голый модификатор (Shift и так далее) не значит «человек перешёл на клавиатуру» -
    // он же нужен мышиному Shift+колесу для бокового хода полки, и без этой отсечки его
    // keydown гасил мышиный режим за миг до события scroll, которое должно было зажечь
    // плитку под курсором.
    if (event.key === 'Shift' || event.key === 'Control' || event.key === 'Alt' || event.key === 'Meta') return;
    const way = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' }[event.key];
    // Мышь последней указала место: стрелка идёт от него, а не от фокуса, оставшегося там,
    // где человек был до мыши. Каретку поля ввода влево и вправо у него не отнимаем.
    const pointed = TCNav.input === 'mouse' ? TCNav.lit : null;
    TCNav.input = 'key';
    const caret = TCNav._typing() && (way === 'left' || way === 'right');
    if (way && pointed && pointed.isConnected && pointed !== document.activeElement && !caret) {
      pointed.focus({ preventScroll: true });
    }
    TCNav.light(TCNav._focused());
    if (!way) return;
    const here = document.activeElement;
    if (!here || !here.matches || !here.matches('[data-tc-focusable]')) return TCNav._wake(event);
    const there = TCNav.nearest(here, way);
    if (!there) {
      // На краю полки стрелка стоит, но и странице не достаётся: та увезла бы полку вбок.
      if (here.closest('.tc-row')) event.preventDefault();
      return;
    }
    event.preventDefault();
    there.focus({ preventScroll: true });
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

  // С плитки полки: влево и вправо - только по своей полке, вверх и вниз - на соседнюю
  // линию. Всё прочее (поле поиска, кнопки карточки, плеер) судит общий счёт.
  nearest(from, way) {
    if (!from.closest('.tc-row')) return TCNav._geometric(from, way);
    return way === 'left' || way === 'right' ? TCNav._along(from, way) : TCNav._across(from, way);
  },

  // Соседняя плитка той же полки; на краю - ``null``: в чужую полку вбок не прыгаем.
  _along(from, way) {
    let next = from;
    do next = way === 'left' ? next.previousElementSibling : next.nextElementSibling;
    while (next && !next.matches('[data-tc-focusable]'));
    return next;
  },

  // Ближайшая линия в нажатую сторону (соседняя полка, поле поиска), а в ней - то, что
  // ближе всех по колонке экрана. Линию меряют КРАЯ, а не центры: плитка своей полки не
  // «ниже» соседки, как бы ни разошлись их высоты.
  _across(from, way) {
    const start = from.getBoundingClientRect();
    const mid = start.left + start.width / 2;
    const found = [];
    for (const el of TCNav._candidates()) {
      if (el.parentElement === from.parentElement) continue;
      const rect = el.getBoundingClientRect();
      const gap = way === 'down' ? rect.top - start.bottom : start.top - rect.bottom;
      if (gap >= -1) found.push({ el, gap, cross: Math.abs(rect.left + rect.width / 2 - mid) });
    }
    if (!found.length) return null;
    const line = Math.min(...found.map((c) => c.gap)) + start.height / 2;
    let best = null;
    for (const c of found) {
      if (c.gap <= line && (!best || c.cross < best.cross)) best = c;
    }
    return best.el;
  },

  // Общий счёт: ближе в нажатую сторону, крест весит вдвое - ровно поперёк оси лучший
  // кандидат, наискось хуже.
  _geometric(from, way) {
    const start = from.getBoundingClientRect();
    const startMid = { x: start.left + start.width / 2, y: start.top + start.height / 2 };
    let best = null;
    let bestScore = Infinity;
    for (const el of TCNav._candidates()) {
      if (el === from) continue;
      const rect = el.getBoundingClientRect();
      const mid = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
      const primary = TCNav._primary(startMid, mid, way);
      if (primary <= 0) continue;
      const score = primary + Math.abs(TCNav._cross(startMid, mid, way)) * 2;
      if (score < bestScore) {
        bestScore = score;
        best = el;
      }
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
