// Шторм отказов дольше тишины: ряд «Продолжить» набирает обложки без перезагрузки.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Document } = require('./page.js');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');
const SHELVES = { fresh: [{ key: 'fresh', title: 'Fresh' }], popular: [] };

function row(poster, partial) {
  const items = [{ key: 'one', title: 'One', ...(poster ? { poster: 'p1' } : {}) }];
  items.partial = partial;
  return items;
}

async function run(answers) {
  const doc = new Document();
  const root = doc.createElement('main');
  root.id = 'tc-root';
  doc.body.appendChild(root);
  const pauses = [];
  const ctx = {
    document: doc, console, JSON, URLSearchParams,
    location: { pathname: '/', search: '' },
    history: { replaceState() {} }, sessionStorage: { setItem() {} },
    ResizeObserver: class { observe() {} },
    TC: { say: (key) => key, count: (key, n) => key + ':' + n, header: () => doc.createElement('div') },
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
  let asked = 0;
  ctx.TCApi = {
    history: async () => answers[Math.min(asked++, answers.length - 1)],
    shelves: async () => ({ ...SHELVES, partial: false, settling: false }),
  };
  await ctx.TCHome.mount(root);
  for (let spin = 0; spin < 400; spin += 1) await new Promise((done) => setImmediate(done));
  const tile = doc.querySelector('[data-tc-group="shelf-continue"]');
  return { asked, poster: tile ? tile.dataset.tcPoster || null : null, pauses: [...new Set(pauses)] };
}

// Обёртка сети читает ту же метку, что у полок, и кладёт её на сам массив.
async function wrapped(label) {
  const ctx = {
    window: {}, document: { cookie: '' }, console, JSON,
    fetch: async () => ({
      ok: true,
      json: async () => ({ items: [{ key: 'one' }] }),
      headers: { get: (name) => (name === 'X-Torrcast-Partial' ? label : null) },
    }),
  };
  vm.createContext(ctx);
  const code = fs.readFileSync(path.join(STATIC, 'api.js'), 'utf8') + '\nthis.TCApi = TCApi;';
  vm.runInContext(code, ctx, { filename: 'api.js' });
  const items = await ctx.TCApi.history();
  return { length: items.length, partial: items.partial };
}

async function main() {
  const filled = await run([row(false, true), row(false, true), row(true, false)]);
  const stuck = await run([row(false, true)]);
  const calm = await run([row(false, false)]);
  const api = { marked: await wrapped('1'), plain: await wrapped(null) };
  process.stdout.write(JSON.stringify({ filled, stuck, calm, api }) + '\n');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
