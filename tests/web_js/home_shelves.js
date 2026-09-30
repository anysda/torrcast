// Холодная главная: плитки встают по мере прихода, «Грузим_» держится ровно до полных полок.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Document } = require('./page.js');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');

function tiles(prefix, count) {
  return Array.from({ length: count }, (_, at) => ({ key: prefix + at, title: prefix + at }));
}

function make(answers) {
  const doc = new Document();
  const root = doc.createElement('main');
  root.id = 'tc-root';
  doc.body.appendChild(root);
  const header = doc.createElement('div');
  header.className = 'tc-header';
  doc.body.appendChild(header);
  const input = doc.createElement('input');
  input.className = 'tc-search-input';
  const pauses = [];
  const ctx = {
    document: doc, console, JSON, URLSearchParams,
    location: { pathname: '/', search: '' },
    history: { replaceState() {} }, sessionStorage: { setItem() {} },
    ResizeObserver: class { observe() {} },
    TC: {
      say: (key) => key,
      count: (key, n) => key + ':' + n,
      header: () => { const made = doc.createElement('div'); made.className = 'tc-header'; return made; },
    },
    TCKept: { take: () => null, resume() {}, mark() {} },
    TCRouter: { card() {} },
    setTimeout: (done, ms) => { pauses.push(ms); setImmediate(done); },
    clearTimeout,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['tile.js', 'home.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }
  ctx.TCHome._askSources = () => {};
  ctx.TCHome._stateLater = () => {};
  const steps = [];
  let asked = 0;
  ctx.TCApi = {
    history: async () => [],
    shelves: async () => {
      // The page's view of the previous answer, taken when it asks for the next one.
      if (asked > 0) steps.push(look(ctx, doc));
      const answer = answers[Math.min(asked, answers.length - 1)];
      asked += 1;
      return { fresh: [], popular: [], partial: false, settling: false, ...answer };
    },
  };
  root.appendChild(input);
  const body = doc.createElement('div');
  body.id = 'tc-body';
  root.appendChild(body);
  return { ctx, doc, root, steps, pauses, count: () => asked };
}

function look(ctx, doc) {
  const body = doc.getElementById('tc-body');
  const count = (group) => (body ? body.querySelectorAll(`[data-tc-group="${group}"]`).length : 0);
  return {
    fresh: count('shelf-new'),
    popular: count('shelf-popular'),
    skeleton: body ? body.querySelectorAll('.tc-tile-skeleton').length > 0 : false,
    empty: body ? body.querySelectorAll('.tc-shelf-empty').length : 0,
    loading: !!ctx.TCHome._assembling,
  };
}

async function settle(page) {
  for (let spin = 0; spin < 2000; spin += 1) await new Promise((done) => setImmediate(done));
}

async function main() {
  // Холодный заход: пусто, потом одни «Новинки», потом сорванный ответ, потом обе полки
  // полные (приговоры ещё идут), потом одна плитка сошла, и всё.
  const cold = make([
    { partial: true },
    { partial: true, fresh: tiles('f', 12) },
    { torn: true },
    { partial: true, fresh: tiles('f', 30), popular: tiles('p', 4) },
    { settling: true, fresh: tiles('f', 30), popular: tiles('p', 30) },
    { fresh: tiles('f', 29), popular: tiles('p', 30) },
  ]);
  await cold.ctx.TCHome.mount(cold.root);
  await settle(cold);
  const coldFinal = look(cold.ctx, cold.doc);

  // Долгая сборка: пятьдесят недоехавших ответов - это не повод бросить опрос.
  const slow = make([...Array.from({ length: 50 }, () => ({ partial: true })),
    { fresh: tiles('f', 2), popular: tiles('p', 2) }]);
  await slow.ctx.TCHome.mount(slow.root);
  await settle(slow);

  process.stdout.write(JSON.stringify({
    coldSteps: cold.steps,
    coldFinal,
    coldAsked: cold.count(),
    firstPause: cold.pauses[0],
    slowAsked: slow.count(),
    slowFinal: look(slow.ctx, slow.doc),
  }) + '\n');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
