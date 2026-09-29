// Новый заход карточки обрывает висящий запрос прежнего: настоящий `card.js` в node.
// Решает `tests/test_card_tab_abort.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const KEY = 'tv:рик-и-морти:2013';
const BODY = { title: 'Рик и Морти', seasons: [{ n: 1 }, { n: 2 }] };

async function main() {
  const asked = [];
  const context = {
    document: {
      addEventListener: () => {},
      body: { contains: () => true },
      getElementById: () => null,
      querySelector: () => null,
    },
    location: { pathname: '/card/' + KEY, search: '' },
    sessionStorage: { getItem: () => null },
    history: { back: () => {} },
    window: {},
    URLSearchParams, AbortController, JSON, Date, setTimeout, Promise, console,
    TCKept: { mark: () => {}, stash: () => {} },
    TCRouter: { _card: KEY, _picture: '' },
    TC: { say: (name) => name },
    // Первая вкладка висит на доборе дорожек, пока её не оборвут; вторая отвечает сразу.
    TCApi: {
      card: (key, query, wait, facts, season, voices, signal) => {
        asked.push({ season, signal });
        if (season === 2) return Promise.resolve({ data: BODY, partial: false });
        return new Promise((done) => {
          signal.addEventListener('abort', () => done({ data: null, partial: false }));
        });
      },
    },
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  const card = vm.runInContext('TCCard', context);
  card._show = () => {};
  const first = card._load({}, KEY, '', false, null, 1);
  const second = card._load({}, KEY, '', false, null, 2);
  const ended = await Promise.race([
    Promise.all([first, second]).then(() => true),
    new Promise((done) => setTimeout(() => done(false), 1000)),
  ]);
  process.stdout.write(JSON.stringify({ aborted: asked[0].signal.aborted, ended }) + '\n');
}

main();
