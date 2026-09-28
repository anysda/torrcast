// Скелет карточки в миг клика по плитке: настоящий `card.js` в node на поддельных узлах,
// сюда уезжают тексты того, что встало до первого ответа сервера.
// Решает `tests/test_card_shell_year.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const KEY = 'tv:клиника:2001';

function node(tag) {
  return {
    tag, className: '', textContent: '', children: [], dataset: {},
    setAttribute() {}, addEventListener() {},
    style: { setProperty() {} },
    appendChild(child) { this.children.push(child); return child; },
    append(...kids) { this.children.push(...kids); },
  };
}

function texts(root) {
  const out = [];
  const walk = (at) => {
    if (at.textContent) out.push([at.className, at.textContent]);
    (at.children || []).forEach(walk);
  };
  walk(root);
  return out;
}

function shell(tile) {
  const context = {
    document: {
      addEventListener: () => {},
      createElement: node,
      getElementById: () => null,
      querySelector: () => null,
    },
    location: { pathname: '/card/' + KEY, search: '' },
    sessionStorage: { getItem: () => (tile ? JSON.stringify(tile) : null) },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    TCKept: { mark: () => {}, stash: () => {} },
    TCRouter: { _card: KEY, _picture: '' },
    TC: { say: (name) => name },
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  const card = vm.runInContext('TCCard', context);  // `const` живёт в лексике вставки
  card._posterBlock = () => node('div');  // обложка плитки проверяется не здесь
  return texts(card._shell(KEY));
}

process.stdout.write(JSON.stringify({
  fromTile: shell({ title: 'Клиника', year: 2001, poster: null }),
  noYear: shell({ title: 'Клиника', year: null, poster: null }),
}) + '\n');
