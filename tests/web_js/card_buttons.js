// Кольцо пульта на карточке: настоящий `card.js` в node поверх игрушечного DOM
// (`page.js`), сюда уезжает только то, что осталось проходимым. Решает
// `tests/test_card_buttons.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const { Document } = require('./page.js');

const KEY = 'movie:интерстеллар:2014';

function card(doc) {
  const context = {
    document: doc,
    location: { pathname: '/card/' + KEY, search: '' },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    TC: { say: (name) => name, count: (name, n) => name + ':' + n },
    TCKept: { mark: () => {}, take: () => null },
    TCRouter: { _card: KEY, _picture: '' },
    TCApi: {},
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  return vm.runInContext('TCCard', context);  // `const` живёт в лексике вставки
}

// Что видит пульт и куда он уезжает с «Назад»: кольцо меряется ходьбой, а не одним
// признаком - атрибут на месте, а фокус не двигается, и наоборот.
function ring(data) {
  const doc = new Document();
  const back = doc.createElement('button');
  back.className = 'tc-back';
  back.dataset.tcFocusable = '1';
  const row = card(doc)._buttons(data, KEY, '', false);
  doc.body.append(back, row);
  const play = row.querySelector('[data-tc-play]');
  back.focus();
  const walked = [];
  for (const el of doc.querySelectorAll('[data-tc-focusable]')) {
    el.focus();
    walked.push(doc.activeElement === el ? el.className : null);
  }
  return {
    play_text: play.textContent,
    play_disabled: !!play.disabled,
    play_focus_attr: play.getAttribute('data-tc-focusable'),
    play_in_ring: play.matches('[data-tc-focusable]'),
    ring: doc.querySelectorAll('[data-tc-focusable]').map((el) => el.className),
    reachable: walked.filter((name) => name !== null),
  };
}

const EMPTY = { releases_count: 0, searching: false, voices: [], tv: false };

process.stdout.write(JSON.stringify({
  noReleases: ring(EMPTY),
  searching: ring({ ...EMPTY, searching: true }),
  found: ring({ ...EMPTY, releases_count: 73 }),
}) + '\n');
