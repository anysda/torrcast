// An episode row pressed in the early answer of the card: the real `card.js` and
// `card-series.js` in node, bodies faked by the rows they hold. Judged by
// `tests/test_card_early_press.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const KEY = 'tv:x:2010';
const STATIC = path.join(__dirname, '..', '..', 'web', 'static');

function page() {
  const context = {
    document: { addEventListener: () => {}, getElementById: () => null, querySelector: () => null },
    location: { pathname: '/card/' + KEY, search: '' },
    sessionStorage: { getItem: () => null },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    TCKept: { mark: () => {}, take: () => null },
    TCRouter: {},
    TC: { say: (name) => name },
  };
  vm.createContext(context);
  for (const file of ['card.js', 'card-series.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, file), 'utf8'), context);
  }
  const card = vm.runInContext('TCCard', context);
  card._load = () => {};
  card._shell = () => ({ querySelector: () => ({ focus: () => {} }) });
  return { card, series: vm.runInContext('TCCardSeries', context) };
}

// A body holding one row `s1e3`: a live one counts its clicks, a grey one has no click to run.
function body(rows) {
  return { querySelector: (sel) => rows.find((row) => sel.includes(row.dataset.tcEpisode)) || null };
}

function row(live, clicks) {
  return { dataset: { tcEpisode: 's1e3' }, click: () => { if (live) clicks.push('s1e3'); } };
}

// Press s1e3 in the early answer, then let the card meet each body in turn.
function run(bodies, { leave = false, key = KEY } = {}) {
  const { card, series } = page();
  const root = { replaceChildren: () => {}, appendChild: () => {} };
  card.mount(root, KEY);
  const clicks = [];
  series._wait(KEY, row(true, clicks));
  if (leave) card.mount(root, KEY);
  for (const [searching, live] of bodies) {
    const rows = live === null ? [] : [row(live, clicks)];
    card._pressAgain(body(rows), key, { searching });
  }
  return { clicks: clicks.length, kept: card._pressed !== null };
}

const result = {
  // The viewer left the card before its release came, and opened it again.
  back: run([[false, true]], { leave: true }),
  // The full body holds the row live: it plays, once, even if more bodies follow.
  plays: run([[true, true], [false, true], [false, true]]),
  // The full body holds the row grey: nothing starts, the row stays grey.
  grey: run([[false, false], [false, true]]),
  // The full body is a refusal or an empty card: no row, and nothing waits for a later one.
  refused: run([[false, null], [false, true]]),
  // Still searching: the press waits for the body that names the release.
  searching: run([[true, true]]),
  // Another card's body does not settle this card's press.
  other: run([[false, true]], { key: 'tv:y:2011' }),
};
process.stdout.write(JSON.stringify(result) + '\n');
