// Плашка главной: настоящие app.js/home.js, виртуальные часы и ответы состояния.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Document, clock } = require('./page.js');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');
const POINTS = [0, 5000, 10000, 20000];

function line(doc) {
  const chip = doc.querySelector('.tc-now');
  if (!chip) return '';
  return ['.tc-now-label', '.tc-now-title', '.tc-now-time']
    .map((selector) => chip.querySelector(selector).textContent).join(' / ');
}

function page(stateAt) {
  const doc = new Document();
  const time = clock();
  const root = doc.createElement('main');
  root.id = 'tc-root';
  doc.body.appendChild(root);
  doc.hidden = false;
  let calls = 0;
  let opened = 0;
  const ctx = {
    document: doc,
    console,
    JSON,
    URLSearchParams,
    Date: { now: time.now },
    setTimeout: time.setTimeout,
    clearTimeout: time.clearTimeout,
    location: { pathname: '/', search: '' },
    history: { pushState() {}, replaceState() {} },
    sessionStorage: { getItem: () => null, setItem() {} },
    navigator: {},
    Blob: class {},
    fetch: async () => { throw new Error('unexpected fetch'); },
    addEventListener() {},
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['api.js', 'app.js', 'home.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }
  ctx.TC.phrases = {
    'web.header.now_playing': 'NOW PLAYING ▶',
    'web.header.on_tv': 'ON TV ▶',
    'web.player.preparing': 'PREPARING…',
  };
  ctx.TCPlayer = { open: () => { opened += 1; } };
  ctx.TCApi.state = async () => { calls += 1; return stateAt(time.now()); };
  ctx.TCApi.box = async () => ({ tv: false });
  root.appendChild(ctx.TC.header(null, false, null));
  ctx.TCHome._shelfPoll = 1;
  ctx.TCHome._stateLater(root);
  return { ctx, doc, time, calls: () => calls, opened: () => opened };
}

function playing(at) {
  return {
    state: 'playing', title: 'ВАСАБИ', position: 3051 + Math.floor(at / 1000), duration: 5630,
  };
}

async function watch(stateAt) {
  const p = page(stateAt);
  const seen = {};
  for (const at of POINTS) {
    await p.time.run(at);
    seen['+' + at / 1000] = line(p.doc);
  }
  const chip = p.doc.querySelector('.tc-now');
  if (chip) chip.dispatch('click');
  return { seen, calls: p.calls(), opens: p.opened() };
}

async function main() {
  const removed = await watch((at) => (at < 2000 ? playing(at) : { state: 'idle' }));
  const ended = await watch((at) => (at < 2000 ? playing(at) : { state: 'idle' }));
  const started = await watch((at) => (at < 2000 ? { state: 'idle' } : playing(at)));
  const live = await watch(playing);

  const hidden = page(playing);
  await hidden.time.run(0);
  hidden.doc.hidden = true;
  await hidden.time.run(20000);
  const callsWhileHidden = hidden.calls();
  hidden.doc.hidden = false;
  await hidden.time.run(22000);

  process.stdout.write(JSON.stringify({
    removed, ended, started, live,
    hidden: { callsWhileHidden, callsAfterVisible: hidden.calls(), line: line(hidden.doc) },
  }));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
