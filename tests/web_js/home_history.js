// Возврат главной: история приходит после карточки, а выдача остаётся на месте до Esc.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Document } = require('./page.js');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');
const OLD = [{ key: 'old', title: 'Old' }];
const NEW = [{ key: 'new', title: 'New' }, ...OLD];
const SHELVES = { fresh: [{ key: 'fresh', title: 'Fresh' }], popular: [] };

function picture(tile) {
  return tile ? tile.dataset.tcKey : '';
}

function make(partial = false) {
  const doc = new Document();
  const root = doc.createElement('main');
  root.id = 'tc-root';
  doc.body.appendChild(root);
  const input = doc.createElement('input');
  input.className = 'tc-search-input';
  const body = doc.createElement('div');
  body.id = 'tc-body';
  body.appendChild(doc.createElement('div')).className = 'search-was-kept';
  const kept = { nodes: [input, body] };
  const ctx = {
    document: doc, console, JSON, URLSearchParams,
    location: { pathname: '/', search: '?query=оно' },
    history: { replaceState() {} }, sessionStorage: { setItem() {} },
    ResizeObserver: class { observe() {} },
    TC: { say: (key) => key, count: (key, n) => key + ':' + n, header: () => doc.createElement('div') },
    TCKept: {
      take: () => kept,
      resume: (place, saved) => place.replaceChildren(...saved.nodes),
      mark() {},
    },
    TCRouter: { card() {} },
    setTimeout, clearTimeout,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['tile.js', 'home.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }
  ctx.TCHome._lastHistory = OLD;
  ctx.TCHome._lastShelves = SHELVES;
  ctx.TCHome._found = { query: 'оно', results: [] };
  ctx.TCHome._runSearch = () => {};
  ctx.TCHome._askSources = () => {};
  ctx.TCHome._stateLater = () => {};
  ctx.TCApi = {
    history: async () => NEW,
    shelves: async () => ({ ...SHELVES, partial }),
  };
  return { ctx, doc, root, input };
}

async function main() {
  const p = make();
  await p.ctx.TCHome.mount(p.root);
  await new Promise((done) => setImmediate(done));
  const kept = p.doc.getElementById('tc-body').querySelector('.search-was-kept') !== null;
  p.input.value = '';
  p.ctx.TCHome._onType({ target: p.input });
  const shown = p.doc.querySelector('[data-tc-group="shelf-continue"]');

  const body = p.ctx.TCHome._body([], SHELVES);
  p.doc.getElementById('tc-body').replaceWith(body);
  p.ctx.TCHome._wornContinue(NEW);
  const shelves = p.doc.getElementById('tc-body').children.map((node) => {
    const tile = node.querySelector('[data-tc-group]');
    return tile ? tile.dataset.tcGroup : '';
  });
  // Полки ещё собираются: новая история запоминается, но выдачу поиска не трогает.
  const q = make(true);
  q.ctx.TCHome._waitShelves = () => {};
  await q.ctx.TCHome.mount(q.root);
  await new Promise((done) => setImmediate(done));
  const found = q.doc.getElementById('tc-body');
  const partialKept = found.querySelector('.search-was-kept') !== null
    && found.querySelector('[data-tc-group="shelf-continue"]') === null
    && q.ctx.TCHome._lastHistory === NEW;

  process.stdout.write(JSON.stringify({ kept, key: picture(shown), shelves, partialKept }) + '\n');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
