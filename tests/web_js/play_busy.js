// Голый 409 busy от /api/play обязан стать словами на обеих кнопках карточки.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

async function main() {
  const routes = [];
  let dropped = 0;
  const timers = [];
  const context = {
    fetch: async () => ({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ error: 'busy' }),
    }),
    document: { addEventListener: () => {}, querySelector: () => null },
    location: { pathname: '/card/movie:test:2000' },
    history: { back: () => {} },
    sessionStorage: { getItem: () => null },
    window: {},
    URLSearchParams, JSON, Date, Blob, Promise, console,
    setTimeout: (fire) => { timers.push(fire); },
    TCPlayerBox: {
      holdStale: async () => {},
      dropStale: () => { dropped += 1; },
    },
    TCRouter: { go: (where) => routes.push(where) },
    TC: { say: (key) => ({ 'web.player.already_starting': 'Показ уже запускается' })[key] || key },
  };
  vm.createContext(context);
  for (const name of ['api.js', 'card.js']) {
    const source = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'static', name), 'utf8');
    vm.runInContext(source, context);
  }
  const api = vm.runInContext('TCApi', context);
  const card = vm.runInContext('TCCard', context);
  const button = fakeNode(['Играть']);
  await card._playFrom(button, { title: 'Тест' }, 'movie:test:2000', 'Тест', [], false);
  const said = button.textContent;
  const row = fakeNode(['3', 'Сезон 1 · 3', '0:42:00']);
  card._showPlayRefusal(row, { ok: false, error: 'busy' });
  const rowSaid = row.textContent;
  for (const fire of timers.splice(0)) fire();
  const cast = await api.cast({ query: 'Тест' });
  let castWord = '';
  card._tvSay = (_key, phrase) => { castWord = context.TC.say(phrase); };
  api.state = async () => ({ state: 'idle' });
  await card._cast({ title: 'Тест' }, 'movie:test:2000', 'Тест', []);
  process.stdout.write(JSON.stringify({
    button: said, buttonLater: button.textContent, rowSaid, rowLater: row.childNodes,
    cast, castWord, routes, dropped,
  }) + '\n');
}

// Узел ровно настолько, насколько его трогает карточка: текст и дети.
function fakeNode(texts) {
  return {
    childNodes: texts.slice(),
    get textContent() { return this.childNodes.join(''); },
    set textContent(text) { this.childNodes = [text]; },
    replaceChildren(...kids) { this.childNodes = kids; },
  };
}

main();
