// Что человек ВИДИТ - то и греется: страница называет серверу запросы плиток в окне,
// и делает это заново на каждую прокрутку и на каждую перерисовку (`POST /api/warm`).
// Первые N по списку тут не годятся: полка длиннее экрана втрое, а греть то, до чего
// человек не долистал, значит занять индексеры вместо того, что у него перед глазами.
'use strict';

const TCWarm = {
  _last: '',
  _timer: null,
  // Экран пересматривается по прокрутке и по перерисовке, но не чаще этого: между
  // двумя кадрами прокрутки список видимого не меняется, а запрос стоил бы круга.
  _PAUSE: 400,

  start() {
    if (TCWarm._timer) return;
    TCWarm._timer = setInterval(TCWarm.look, TCWarm._PAUSE);
    document.addEventListener('scroll', TCWarm.look, true);
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
