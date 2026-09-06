// Заготовка страницы: словарь надписей и шапка. Экраны, полки и D-pad - соседний заход,
// и живут они в ЭТОМ файле, чтобы плееру (player.js) не пришлось его открывать.
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

  header() {
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
    header.append(brand, seat);
    return header;
  },

  async start() {
    await TC.load();
    const root = document.getElementById('tc-root');
    root.replaceChildren(TC.header());
  },
};

window.TC = TC;
document.addEventListener('DOMContentLoaded', () => { TC.start(); });
