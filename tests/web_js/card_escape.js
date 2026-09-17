// Esc на карточке (TC-1335): настоящий `card.js` в node, без разметки - слушатель
// вешается один раз при загрузке файла, DOM карточки ему не нужен.
// Решает `tests/test_card_escape.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function pressEscape(pathname) {
  const calls = { back: 0 };
  const listeners = [];
  const document = {
    addEventListener: (name, handler) => {
      if (name === 'keydown') listeners.push(handler);
    },
  };
  const location = { pathname };
  const history = { back: () => { calls.back += 1; } };
  const context = { document, location, history, window: {} };
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8');
  vm.runInContext(source, context);
  for (const handler of listeners) handler({ key: 'Escape' });
  return calls.back;
}

process.stdout.write(JSON.stringify({
  onCard: pressEscape('/card/movie:sintel:2010'),
  onHome: pressEscape('/'),
  onPlay: pressEscape('/play'),
}) + '\n');
