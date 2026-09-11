// Точка входа: словарь надписей, шапка с плашкой «сейчас идёт», числовые подписи и
// самый маленький маршрутизатор - без адресов, без правил, только путь в один из двух
// экранов (`home.js` / `card.js`). Сама логика экранов и D-pad живёт в СВОИХ файлах:
// этот держится коротким нарочно, а не потому что нечего было сказать.
'use strict';

const TC = {
  // Надписи страницы. Пока словарь не приехал, тут пусто, а не английский про запас:
  // запасной каталог живёт на стороне продукта (torrcast/domain/catalogs/web).
  phrases: {},
  language: 'en',

  // Сколько имён в одной ленте бегущей строки. Лента обязана быть ШИРЕ шапки, иначе
  // на стыке двух лент открылась бы дыра; восемь имён шире окна в любую ширину, потому
  // что размер знака сам считается от ширины окна.
  BRAND_COPIES: 8,

  // Надпись по ключу; неизвестный ключ виден сам собой, а не молча пропадает.
  say(key, values) {
    let line = TC.phrases[key];
    if (line === undefined) return '?' + key;
    if (values) for (const name of Object.keys(values)) {
      line = line.split('{' + name + '}').join(String(values[name]));
    }
    return line;
  },

  // Число и существительное - одна надпись: английскому хватает one/other, русский
  // различает one, few (2-4) и many (включая 11-14). Дроби и отрицательные не бывают
  // в счётчиках продукта; для них честно берётся other, а не притворная русская форма.
  count(key, number) {
    const n = Number(number);
    let form = 'other';
    if (Number.isInteger(n) && n >= 0) {
      if (TC.language === 'ru') {
        const last = n % 10;
        const lastTwo = n % 100;
        form = last === 1 && lastTwo !== 11 ? 'one'
          : last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'few' : 'many';
      } else if (n === 1) {
        form = 'one';
      }
    }
    return TC.say(key + '.' + form, { n: number });
  },

  async load(lang) {
    const query = lang ? '?lang=' + encodeURIComponent(lang) : '';
    const answer = await fetch('/api/phrases' + query);
    TC.phrases = await answer.json();
    TC.language = lang === 'ru' ? 'ru' : 'en';
    return TC.phrases;
  },

  // Шапка живёт только на главной; ``state`` - ответ ``/api/state`` (или ``null``,
  // пока он не приехал): плашка «сейчас идёт» появляется, только когда показ не в покое.
  // ``loading`` - главная ещё собирает полки, а ``box`` называет место показа.
  header(state, loading, box) {
    const header = document.createElement('header');
    header.className = 'tc-header tc-safe';
    header.append(TC._marquee());
    if (state && state.state && state.state !== 'idle') header.append(TC._chip(state, !!(box && box.tv)));
    else if (loading) header.append(TC._loading());
    return header;
  },

  // Слот шапки на время сборки полок (экран 4.1): пока главная ждёт ответы, в нём
  // стоит «Грузим_», и он уходит вместе с приходом полок. Место то же, что у плашки
  // «сейчас идёт», и занять их обе разом нельзя: показ идёт - плашка старше.
  _loading() {
    const line = document.createElement('div');
    line.className = 'tc-now-label';
    line.dataset.tcLoading = '1';
    line.textContent = TC.say('web.shelf.loading');
    return line;
  },

  // Имя продукта идёт по шапке бегущей строкой без конца. Лент ровно ДВЕ и они
  // одинаковые: пока первая уезжает на свою же ширину, вторая стоит ровно на её месте,
  // поэтому конца у строки не видно и «дорисовать ещё копию» никогда не требуется.
  _marquee() {
    const marquee = document.createElement('div');
    marquee.className = 'tc-marquee';
    const track = document.createElement('div');
    track.className = 'tc-marquee-track';
    for (let band = 0; band < 2; band += 1) {
      const strip = document.createElement('div');
      strip.className = 'tc-marquee-band';
      for (let copy = 0; copy < TC.BRAND_COPIES; copy += 1) strip.appendChild(TC._brand());
      track.appendChild(strip);
    }
    marquee.appendChild(track);
    return marquee;
  },

  _brand() {
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
    return brand;
  },

  _chip(state, onTv) {
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
    label.textContent = TC.say(onTv ? 'web.header.on_tv' : 'web.header.now_playing');
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
  TCWarm.start();
});
