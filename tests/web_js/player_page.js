// Экран показа без браузера: настоящие player.js, player-box.js, player-next.js,
// player-panel.js и player-screens.js в `vm`, поддельные DOM/часы/hls.js/TCApi. Тот же
// приём, что и у `page.js` (поиск на главной) - ДОМ и часы делит с ним, а не заводит
// свои: `require('./page.js')` даёт `Element`/`Document`/`clock`, тут достроен только
// стенд, которого поиску не было нужно (``<video>``, ``Hls``, ящик показа).
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Document, clock } = require('./page.js');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');

// ``Hls`` настоящего hls.js тут не участвует (сеть - не предмет этого сторожа): манифест
// «разбирается» одним тиком виртуальных часов после ``attachMedia`` - как и настоящий,
// не в тот же синхронный вызов, что и ``_attach()`` (`player.js`).
function hlsStub(time) {
  function Hls(opts) {
    this.opts = opts;
    this.handlers = {};
  }
  Hls.prototype.on = function on(event, fn) { this.handlers[event] = fn; };
  Hls.prototype.loadSource = function loadSource(url) { this.url = url; };
  Hls.prototype.attachMedia = function attachMedia(el) {
    this.video = el;
    time.setTimeout(() => {
      const parsed = this.handlers.MANIFEST_PARSED;
      if (parsed) parsed();
    }, 0);
  };
  Hls.prototype.destroy = function destroy() {};
  Hls.isSupported = () => true;
  Hls.Events = { MANIFEST_PARSED: 'MANIFEST_PARSED', ERROR: 'ERROR' };
  return Hls;
}

// Стенд ``/play``: собирает контекст ``vm``, грузит НАСТОЯЩИЕ файлы плеера и отдаёт
// сценарию ручки на живое состояние - без них сценарий не смог бы толкать таймлайн.
//
// ``server`` - три функции, отвечающие ровно так, как отвечает мост (:mod:`hass.bridge`):
// ``box()`` - текущий ящик показа (``null``, пока не готов), ``state()`` - снимок
// ``/api/state`` (``has_next``, серия, отказ), ``position(phase, pos, dur)`` - код ответа
// на отчёт позиции (``409`` - ящик сменился, сигнал для ``rebox()``).
function player(server) {
  const doc = new Document();
  const time = clock();
  const latency = 20;
  const overlayRoot = doc.body;
  const calls = {
    next: [], control: [], position: [], left: [], boxPolls: 0, statePolls: 0,
    routerGo: [], historyBack: 0,
  };

  const ctx = {
    document: doc,
    console,
    JSON,
    Math,
    URL,
    Date: { now: time.now },
    setTimeout: time.setTimeout,
    clearTimeout: time.clearTimeout,
    setInterval: time.setInterval,
    clearInterval: time.clearInterval,
    location: { pathname: '/play', href: 'http://stand/play', hostname: 'stand' },
    history: { state: null, length: 1, back() { calls.historyBack += 1; } },
    sessionStorage: (() => {
      const store = new Map();
      return {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key),
      };
    })(),
    addEventListener() {},
    TC: { say: (key) => key, phrases: {} },
    TCTime: { clock: (s) => String(s) },
    TCRouter: { go(path) { calls.routerGo.push(path); }, card() {} },
    Hls: hlsStub(time),
    TCApi: {
      async box() {
        calls.boxPolls += 1;
        await new Promise((done) => time.setTimeout(done, latency));
        return server.box();
      },
      async state() {
        calls.statePolls += 1;
        await new Promise((done) => time.setTimeout(done, latency));
        return server.state();
      },
      async position(said) {
        calls.position.push(said);
        await new Promise((done) => time.setTimeout(done, latency));
        return server.position ? server.position(said) : 200;
      },
      left(said) { calls.left.push(said); },
      async next(ended) { calls.next.push(ended); return true; },
      async control(cmd, arg) { calls.control.push([cmd, arg]); return { ok: true }; },
      async toTv() { return true; },
      async toWeb() { return true; },
    },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['player-panel.js', 'player-screens.js', 'player-next.js', 'player-box.js', 'player.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }

  const self = {
    doc, time, ctx, calls, video: null,
    // ``mount()`` строит ``<video>`` заново (``player.js``, ``TCPlayer.mount``) - своя
    // ссылка на него берётся ПОСЛЕ, тем же способом, каким её берёт сам продукт
    // (``TCPlayer._video``), а не заводится параллельным узлом мимо разметки.
    mount() { ctx.TCPlayer.mount(overlayRoot); self.video = ctx.TCPlayer._video; },
    overlay() { return ctx.TCPlayer._overlay; },
    // Кадр без реального времени: ставит место и зовёт тот же обработчик, что и
    // настоящий ``<video>`` при ходе плёнки (`player.js`: `video.addEventListener
    // ('timeupdate', …)`), а не выдумывает свой отдельный путь мимо него.
    tick(pos) { self.video.currentTime = pos; self.video.dispatch('timeupdate'); },
    ended() { self.video.dispatch('ended'); },
  };
  return self;
}

// Одна ``player-next.js`` без остального стенда: в сборке `_playNext()`/`_cancelNext()`
// (`player.js`) сразу следом заменяют весь оверлей (`overlay.replaceChildren()` у ЛЮБОГО
// экрана `player-screens.js`) - это маскирует поломку `card.remove()` внутри `stop()`
// (пробa «(д)»: убери его - карточка всё равно пропадёт, потому что её сносит СЛЕДУЮЩИЙ
// вызов, а не сам счётчик). У ``player-next.js`` свой контракт - карточка исчезает САМА,
// а не полагается на то, что вызвавший её код сейчас же перерисует всё заново.
function next(onPlay, onCancel) {
  const doc = new Document();
  const time = clock();
  const ctx = {
    document: doc,
    console,
    setTimeout: time.setTimeout,
    clearTimeout: time.clearTimeout,
    setInterval: time.setInterval,
    clearInterval: time.clearInterval,
    TC: { say: (key) => key },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(
    fs.readFileSync(path.join(STATIC, 'player-next.js'), 'utf8'), ctx, { filename: 'player-next.js' },
  );
  const root = doc.body;
  ctx.TCPlayerNext.mount(root, onPlay, onCancel);
  return { root, time, card: () => root.querySelector('.tc-next') };
}

module.exports = { player, next };
