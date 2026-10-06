// hls.js грузится показом, а не страницей: настоящий `player.js` в node, `_attach` до и
// после загрузки файла. Решает `tests/test_player_hls_lazy.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');

function hlsStub(made) {
  function Hls(opts) { this.opts = opts; made.push(this); }
  Hls.prototype.on = function on() {};
  Hls.prototype.loadSource = function loadSource(url) { this.url = url; };
  Hls.prototype.attachMedia = function attachMedia() {};
  Hls.prototype.destroy = function destroy() {};
  Hls.isSupported = () => true;
  Hls.Events = { MANIFEST_PARSED: 'MANIFEST_PARSED', ERROR: 'ERROR' };
  return Hls;
}

// `sources` - какие конструкторы MSE есть у браузера: по умолчанию настольный `MediaSource`.
function stand(sources = { MediaSource: function MediaSource() {} }) {
  const tags = [];
  const ctx = {
    console,
    addEventListener() {},
    ...sources,
    document: {
      addEventListener() {},
      head: { appendChild(tag) { tags.push(tag); return tag; } },
      createElement(name) {
        const heard = {};
        return {
          name, src: '', heard,
          addEventListener(event, fn) { (heard[event] = heard[event] || []).push(fn); },
        };
      },
    },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(STATIC, 'player.js'), 'utf8'), ctx, { filename: 'player.js' });
  const player = vm.runInContext('TCPlayer', ctx);
  player._video = { src: '', addEventListener() {} };
  return { ctx, tags, player };
}

const settle = () => new Promise((done) => setImmediate(done));

async function loaded() {
  const { ctx, tags, player } = stand();
  const made = [];
  player._attach('/hls/first.m3u8', 0);
  player._attach('/hls/second.m3u8', 7);
  const before = { tags: tags.map((t) => t.src), made: made.length };
  ctx.Hls = hlsStub(made);
  tags.forEach((t) => (t.heard.load || []).forEach((fn) => fn()));
  await settle();
  return {
    before,
    after: made.map((h) => [h.url, h.opts.startPosition]),
    tags: tags.length,
  };
}

async function failed() {
  const { tags, player } = stand();
  player._attach('/hls/only.m3u8', 0);
  tags.forEach((t) => (t.heard.error || []).forEach((fn) => fn()));
  await settle();
  return { tags: tags.length, src: player._video.src };
}

// iPhone с iOS 17.1+: `MediaSource` нет, есть только `ManagedMediaSource` - hls.js
// с ним играет, значит файл обязан грузиться. Без всякого MSE файл не тянется.
function managed() {
  const { tags, player } = stand({ ManagedMediaSource: function ManagedMediaSource() {} });
  player._attach('/hls/phone.m3u8', 42);
  return { tags: tags.map((t) => t.src), src: player._video.src };
}

function bare() {
  const { tags, player } = stand({});
  player._attach('/hls/old.m3u8', 0);
  return { tags: tags.length, src: player._video.src };
}

// Вкладка при «На ТВ» метит запросы раздаче как зеркало, без каста - как есть.
function mirror() {
  const { ctx, player } = stand();
  const made = [];
  ctx.Hls = hlsStub(made);
  player._attach('/hls/cast.m3u8', 0);
  const setup = made[0].opts.xhrSetup || (() => {});
  const asked = (onTv, url) => {
    const opened = [];
    player._onTv = onTv;
    setup({ open: (...args) => opened.push(args) }, url);
    return opened;
  };
  return {
    tab: asked(false, '/hls/v5.m4s'),
    tv: asked(true, '/hls/v5.m4s'),
    query: asked(true, '/hls/v5.m4s?a=1'),
  };
}

(async () => {
  process.stdout.write(JSON.stringify({
    loaded: await loaded(), failed: await failed(), managed: managed(), bare: bare(),
    mirror: mirror(),
  }));
})();
