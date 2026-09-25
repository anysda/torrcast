// Ответ вкладки сезона, равный стоящему телу: настоящий `card.js` в node, тело
// подменяется поддельным `_show`. Решает `tests/test_card_season_answer.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const KEY = 'tv:футурама:1999';
const QUERY = 'Футурама';
// Одна раздача на все сезоны: ответ на любую вкладку совпадает с телом до байта.
const BODY = { title: 'Футурама', release: 'a'.repeat(40), seasons: [{ n: 1 }, { n: 7 }] };

async function redraws(season) {
  const shown = [];
  const context = {
    document: {
      addEventListener: () => {},
      body: { contains: () => true },
      getElementById: () => null,
      querySelector: () => null,
    },
    location: { pathname: '/card/' + KEY, search: '?query=' + QUERY },
    sessionStorage: { getItem: () => null },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    TCKept: { mark: () => {}, stash: () => {} },
    TCRouter: { _card: KEY, _picture: '' },
    TC: { say: (name) => name },
    TCApi: { card: async () => ({ data: BODY, partial: false, missing: false, refused: '' }) },
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  const card = vm.runInContext('TCCard', context);
  card._shown = { key: KEY, query: QUERY, data: BODY };
  card._show = (root, key, query, data) => { shown.push(data); };
  await card._load({}, KEY, QUERY, false, null, season);
  return shown.length;
}

async function main() {
  const tab = await redraws(1);
  const reload = await redraws(undefined);
  process.stdout.write(JSON.stringify({ tab, reload }) + '\n');
}

main();
