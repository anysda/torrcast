// Что человек ВИДИТ - то и греется: страница называет серверу запросы плиток в окне,
// и делает это заново на каждую прокрутку и на каждую перерисовку (`POST /api/seen`).
// Первые N по списку тут не годятся: полка длиннее экрана втрое, а греть то, до чего
// человек не долистал, значит занять индексеры вместо того, что у него перед глазами.
'use strict';

const TCWarm = {
  _last: '',
  _timer: null,
  // Плитка под мышью или под пультом: её откроют раньше прочих видимых, и греется она
  // первой. Одна рука прогрева идёт по экрану около сорока секунд, и в порядке строк
  // плитка в конце экрана открывалась холодной (5.4 с на стенде `.104`).
  _first: '',
  // Экран пересматривается по прокрутке и по перерисовке, но не чаще этого: между
  // двумя кадрами прокрутки список видимого не меняется, а запрос стоил бы круга.
  _PAUSE: 400,

  start() {
    if (TCWarm._timer) return;
    TCWarm._timer = setInterval(TCWarm.look, TCWarm._PAUSE);
    document.addEventListener('scroll', TCWarm.look, true);
    for (const kind of ['pointerover', 'focusin']) {
      document.addEventListener(kind, TCWarm._aim, true);
    }
    TCWarm.look();
  },

  _aim(event) {
    const tile = event.target && event.target.closest ? event.target.closest('[data-tc-warm]') : null;
    if (!tile || tile.dataset.tcWarm === TCWarm._first) return;
    TCWarm._first = tile.dataset.tcWarm;
    TCWarm.look();
  },

  // Плитка видна, если её прямоугольник пересекается с окном: ровно то же правило, по
  // которому её видит человек, и никакой догадки про «наверное, долистает».
  seen() {
    const tiles = [];
    for (const node of document.querySelectorAll('[data-tc-warm]')) {
      const box = node.getBoundingClientRect();
      const inside = box.top < window.innerHeight && box.bottom > 0
        && box.left < window.innerWidth && box.right > 0;
      if (!inside || !box.width) continue;
      tiles.push(node.dataset.tcWarm);
    }
    // Первой - горящая плитка (`nav.js`), а не последняя под курсором: ряд под горящей
    // растёт, она уезжает из-под мыши, и курсор «наводится» на соседа, а жмут по горящей.
    const lit = window.TCNav && TCNav.lit && TCNav.lit.dataset ? TCNav.lit.dataset.tcWarm : '';
    const at = tiles.indexOf(lit || TCWarm._first);
    if (at > 0) tiles.unshift(tiles.splice(at, 1)[0]);
    return tiles;
  },

  look() {
    const tiles = TCWarm.seen();
    const mark = JSON.stringify(tiles);
    // Пустой экран (человек ушёл в поиск, результатов ещё нет) сообщается ровно один
    // раз: он снимает очередь прошлого экрана, чтобы фон не мешал живому кругу.
    if (mark === TCWarm._last) return;
    TCWarm._last = mark;
    TCApi.seen(tiles);
  },
};

window.TCWarm = TCWarm;
