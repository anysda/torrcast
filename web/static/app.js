// Точка входа: словарь надписей, шапка с плашкой «сейчас идёт», числовые подписи и
// самый маленький маршрутизатор - без адресов, без правил, только путь в один из двух
// экранов (`home.js` / `card.js`). Сама логика экранов и D-pad живёт в СВОИХ файлах:
// этот держится коротким нарочно, а не потому что нечего было сказать.
'use strict';

const TC = {
  // Надписи страницы. Пока словарь не приехал, тут пусто, а не английский про запас:
  // запасной каталог живёт на стороне продукта (torrcast/domain/catalogs/web).
  phrases: {},

  // Надпись по ключу; неизвестный ключ виден сам собой, а не молча пропадает.
  say(key, values) {
    let line = TC.phrases[key];
    if (line === undefined) return '?' + key;
    if (values) for (const name of Object.keys(values)) {
      line = line.split('{' + name + '}').join(String(values[name]));
    }
    return line;
  },

  async load(lang) {
    const query = lang ? '?lang=' + encodeURIComponent(lang) : '';
    const answer = await fetch('/api/phrases' + query);
    TC.phrases = await answer.json();
    return TC.phrases;
  },

  // Шапка живёт только на главной; ``state`` - ответ ``/api/state`` (или ``null``,
  // пока он не приехал): плашка «сейчас идёт» появляется, только когда показ не в покое.
  header(state) {
    const brand = document.createElement('div');
    brand.className = 'tc-brand';
    const square = document.createElement('span');
    square.className = 'tc-brand-square';
    const name = document.createElement('span');
    name.textContent = 'Torrcast';
    const tail = document.createElement('span');
    tail.className = 'tc-brand-tail';
    tail.textContent = '_';
    brand.append(square, name, tail);

    const seat = document.createElement('div');
    seat.className = 'tc-seat';
    seat.textContent = TC.say('web.header.seat');

    const header = document.createElement('header');
    header.className = 'tc-header tc-safe';
    header.append(brand);
    header.append(state && state.state && state.state !== 'idle' ? TC._chip(state) : seat);
    return header;
  },

  // Договора о «показ идёт на ТВ, а не в браузере» в ``/api/state`` сегодня нет
  // (поле ``tv`` - имя настроенного телевизора, не флаг места показа): значок «На ТВ»
  // тут намеренно не рисуется, это честный пробел контракта, а не забытая строка.
  _chip(state) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'tc-now';
    chip.addEventListener('click', () => {
      if (window.TCPlayer && TCPlayer.open) TCPlayer.open();
    });
    const art = document.createElement('div');
    art.className = 'tc-now-art';
    if (state.image) {
      art.style.backgroundImage = 'url(' + state.image + ')';
      art.style.backgroundSize = 'cover';
      art.style.backgroundPosition = 'center';
    }
    const label = document.createElement('div');
    label.className = 'tc-now-label';
    label.textContent = TC.say('web.header.now_playing');
    const title = document.createElement('div');
    title.className = 'tc-now-title';
    title.textContent = state.shown_as || state.title || '';
    const time = document.createElement('div');
    time.className = 'tc-now-time';
    time.textContent = TCTime.clock(state.position) + ' / ' + TCTime.clock(state.duration);
    chip.append(art, label, title, time);
    return chip;
  },
};

// Числа страницы: часы читаются столбиком, и им нужен один и тот же формат везде -
// в шапке, на плитке «Продолжить» и на карточке, а не свой в каждом файле.
const TCTime = {
  clock(seconds) {
    if (seconds === null || seconds === undefined) return '--:--';
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const two = (n) => String(n).padStart(2, '0');
    return h > 0 ? h + ':' + two(m) + ':' + two(s) : m + ':' + two(s);
  },

  // Длительность фильма в словах каталога («2 h 49 min» / «38 min»); поле контракта
  // ``runtime`` идёт в секундах, как ``position``/``duration`` у показа.
  runtimeWords(seconds) {
    if (seconds === null || seconds === undefined) return '';
    const total = Math.round(seconds / 60);
    const h = Math.floor(total / 60);
    const m = total % 60;
    return h > 0 ? TC.say('web.detail.runtime_hm', { h, m }) : TC.say('web.detail.runtime_m', { m });
  },
};

// Два экрана, один корень: путь решает, кому его отдать. Ни правил, ни параметров -
// точный маршрут только у карточки (``/card/{key}``), остальное - главная.
const TCRouter = {
  go(path) {
    history.pushState({}, '', path);
    TCRouter.render();
  },

  // Ключ картины БЕЗ строки поиска ничей: ``/api/card/{key}`` ищет круг раздач тем же
  // запросом, что и выдача, и на пустой ``query`` отвечает 400. Значит адрес карточки
  // собирается одним местом и всегда вместе с запросом, иначе плитка ведёт на скелет.
  card(key, query) {
    const tail = query ? '?query=' + encodeURIComponent(query) : '';
    TCRouter.go('/card/' + encodeURIComponent(key) + tail);
  },

  render() {
    const root = document.getElementById('tc-root');
    const path = location.pathname;
    if (path.startsWith('/card/')) {
      const key = decodeURIComponent(path.slice('/card/'.length));
      TCCard.mount(root, key);
    } else if (path === '/play') {
      TCPlayer.mount(root);
    } else {
      TCHome.mount(root);
    }
  },
};

window.TC = TC;
window.TCTime = TCTime;
window.TCRouter = TCRouter;
window.addEventListener('popstate', TCRouter.render);

document.addEventListener('DOMContentLoaded', async () => {
  await TC.load();
  TCNav.init();
  TCRouter.render();
});
