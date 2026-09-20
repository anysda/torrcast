// Отказ круга (409), пришедший на скелет превью: настоящий `card.js` в node, без
// разметки - тело подменяется поддельным `_show`, и сюда уезжает то, что встало на экран.
// Решает `tests/test_card_refused.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const KEY = 'movie:престиж:2006';
const SKELETON = {
  data: { title: 'Престиж', searching: true, releases: [], releases_count: 0 },
  partial: true, missing: false, refused: '',
};
const REFUSAL = { data: null, partial: false, missing: false, refused: 'Prowlarr не отвечает' };

async function lastShown(answers) {
  const shown = [];
  const context = {
    document: {
      addEventListener: () => {},
      body: { contains: () => true },
      getElementById: () => null,
      querySelector: () => null,
    },
    location: { pathname: '/card/' + KEY, search: '?query=Престиж&title=Престиж&year=2006&kind=movie' },
    sessionStorage: { getItem: () => null },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    TCKept: { mark: () => {}, stash: () => {} },
    TCRouter: { _card: KEY, _picture: '' },
    TC: { say: (name) => name },
    TCApi: { card: async () => answers.shift() || REFUSAL },
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  const card = vm.runInContext('TCCard', context);  // `const` живёт в лексике вставки
  card._show = (root, key, query, data) => { shown.push(data); };
  await card._load({}, KEY, 'Престиж', false, card._facts(), undefined);
  return shown[shown.length - 1] || null;
}

// Ключи всегда на месте: отсутствующий признак должен читаться словом, а не пропажей.
function told(data) {
  return {
    error: (data && data.error) || null,
    refused: (data && data.refused) || null,
    searching: (data && data.searching) || false,
    title: (data && data.title) || null,
  };
}

async function main() {
  const onSkeleton = await lastShown([SKELETON, REFUSAL]);
  const onEmpty = await lastShown([REFUSAL]);
  process.stdout.write(JSON.stringify({ onSkeleton: told(onSkeleton), onEmpty: told(onEmpty) }) + '\n');
}

main();
