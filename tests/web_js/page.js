// Страница без браузера: настоящие api.js, tile.js и home.js в `vm`, поддельные DOM, часы и
// сервер. Ровно то, чем пользуется выдача поиска; всё прочее тут отсутствует нарочно.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const STATIC = path.join(__dirname, '..', '..', 'web', 'static');

function kebab(name) {
  return name.replace(/[A-Z]/g, (ch) => '-' + ch.toLowerCase());
}

// Селектор из того, что зовут страница и щуп: тег, #id, .класс, [атрибут] и [атрибут="v"],
// потомок через пробел и перечисление через запятую.
function compound(el, part) {
  const tokens = part.match(/^[a-z]+|#[\w-]+|\.[\w-]+|\[[\w-]+(?:="[^"]*")?\]/gi) || [];
  if (tokens.join('') !== part) throw new Error('selector not supported: ' + part);
  return tokens.every((token) => {
    if (token[0] === '#') return el.id === token.slice(1);
    if (token[0] === '.') return el.className.split(/\s+/).includes(token.slice(1));
    if (token[0] === '[') {
      const [, name, value] = token.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
      const have = el.getAttribute(name);
      return value === undefined ? have !== null : have === value;
    }
    return el.tagName === token.toUpperCase();
  });
}

function matches(el, selector) {
  // Текстовый узел (``TextNode``) не тег - ни один селектор не берёт его тем же
  // путём, каким браузер обходит стороной обычный текст в ``querySelectorAll``.
  if (!el.tagName) return false;
  return selector.split(',').some((one) => {
    const parts = one.trim().split(/\s+/);
    if (!compound(el, parts[parts.length - 1])) return false;
    let at = el.parentNode;
    for (let i = parts.length - 2; i >= 0; i -= 1) {
      while (at && !(at.tagName && compound(at, parts[i]))) at = at.parentNode;
      if (!at) return false;
      at = at.parentNode;
    }
    return true;
  });
}

class Element {
  constructor(doc, tag) {
    this.ownerDocument = doc;
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = new Map();
    this.listeners = {};
    this.style = {};
    this.text = '';
    this.dataset = new Proxy({}, {
      get: (_, key) => (typeof key === 'string' ? this.getAttribute('data-' + kebab(key)) ?? undefined : undefined),
      // `String(value)` тут не описка, а сам браузер: `dataset.x = undefined` ставит
      // атрибут СТРОКОЙ «undefined», и признак остаётся на месте. Снимается он только
      // `delete`, и без этой ловушки снос уходил бы в пустышку Proxy, оставляя атрибут.
      set: (_, key, value) => { this.setAttribute('data-' + kebab(key), String(value)); return true; },
      deleteProperty: (_, key) => {
        if (typeof key === 'string') this.attrs.delete('data-' + kebab(key));
        return true;
      },
    });
  }

  get className() { return this.getAttribute('class') || ''; }
  set className(value) { this.setAttribute('class', value); }
  get id() { return this.getAttribute('id') || ''; }
  set id(value) { this.setAttribute('id', value); }
  get firstElementChild() { return this.children[0] || null; }
  get firstChild() { return this.children[0] || null; }
  // Минимальный ``classList``: читает/пишет через тот же ``className``, второго
  // источника правды не заводит - `player-panel.js`/`player.js` дёргают его на
  // готовых узлах (``toggle('is-paused', …)``), а не при постройке разметки.
  get classList() {
    const el = this;
    const names = () => el.className.split(/\s+/).filter(Boolean);
    return {
      add: (name) => { const set = new Set(names()); set.add(name); el.className = [...set].join(' '); },
      remove: (name) => { const set = new Set(names()); set.delete(name); el.className = [...set].join(' '); },
      contains: (name) => names().includes(name),
      toggle(name, on) {
        const want = on === undefined ? !this.contains(name) : !!on;
        if (want) this.add(name); else this.remove(name);
      },
    };
  }
  get textContent() { return this.text + this.children.map((c) => c.textContent).join(''); }
  set textContent(value) { this.children = []; this.text = String(value); }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  getAttribute(name) { return this.attrs.has(name) ? this.attrs.get(name) : null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, event = {}) {
    for (const fn of this.listeners[type] || []) fn({ preventDefault() {}, ...event });
  }

  appendChild(node) {
    if (node.parentNode) node.remove();
    node.parentNode = this;
    this.children.push(node);
    return node;
  }

  prepend(node) {
    if (node.parentNode) node.remove();
    node.parentNode = this;
    this.children.unshift(node);
    return node;
  }

  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  replaceChildren(...nodes) { this.children.slice().forEach((c) => c.remove()); this.append(...nodes); }

  remove() {
    if (!this.parentNode) return;
    const doc = this.ownerDocument;
    if (doc.activeElement && this.contains(doc.activeElement)) doc.activeElement = doc.body;
    this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
    this.parentNode = null;
  }

  replaceWith(node) {
    const parent = this.parentNode;
    const at = parent.children.indexOf(this);
    this.remove();
    if (node.parentNode) node.remove();
    node.parentNode = parent;
    parent.children.splice(at, 0, node);
  }

  contains(node) {
    for (let at = node; at; at = at.parentNode) if (at === this) return true;
    return false;
  }

  matches(selector) { return matches(this, selector); }

  querySelectorAll(selector) {
    const found = [];
    const walk = (el) => el.children.forEach((c) => { if (matches(c, selector)) found.push(c); walk(c); });
    walk(this);
    return found;
  }

  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }

  // Погашенную кнопку браузер не фокусирует вовсе: `focus()` по ней не делает ничего,
  // и фокус остаётся там, где был. Без этого мёртвая кнопка в кольце пульта читалась
  // бы тут как проходимая, а на живой странице стрелка упиралась бы в неё насмерть.
  focus() {
    if (this.disabled) return;
    if (this.getAttribute('data-tc-focusable') !== null && this.ownerDocument.body.contains(this)) {
      this.ownerDocument.activeElement = this;
    }
  }
}

// Текстовый узел: у ``player-panel.js`` секунда идёт первым ребёнком без тега
// (``time.appendChild(document.createTextNode(''))``), а не атрибутом соседнего span.
class TextNode {
  constructor(text) { this.text = text; this.parentNode = null; this.children = []; }
  get textContent() { return this.text; }
  set textContent(value) { this.text = String(value); }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
    this.parentNode = null;
  }
}

class Document {
  constructor() {
    this.documentElement = new Element(this, 'html');
    this.body = this.documentElement.appendChild(new Element(this, 'body'));
    this.activeElement = this.body;
  }

  // ``<video>`` - единственный тег со своим поведением: остальные разметке всё равно
  // какой ``Element`` держать (`player.js` ставит `currentTime`/зовёт `play()`, ни
  // одна карточка поиска так не делает - отсюда особый случай тут, а не отдельный класс).
  createElement(tag) {
    const el = new Element(this, tag);
    if (tag === 'video') {
      el.currentTime = 0;
      el.duration = 0;
      el.paused = true;
      el.ended = false;
      el.muted = false;
      el.volume = 1;
      el.playbackRate = 1;
      el.readyState = 4;
      el.buffered = { length: 0, start: () => 0, end: () => 0 };
      el.play = () => { el.paused = false; return Promise.resolve(); };
      el.pause = () => { el.paused = true; };
    }
    return el;
  }
  createTextNode(text) { return new TextNode(text); }
  getElementById(id) { return this.documentElement.querySelector('#' + id); }
  querySelector(selector) { return this.documentElement.querySelector(selector); }
  querySelectorAll(selector) { return this.documentElement.querySelectorAll(selector); }
  addEventListener() {}
}

// Часы и таймеры страницы: время идёт только тогда, когда его двигает сценарий.
// ``setInterval``/``clearInterval`` живут в той же очереди, что и ``setTimeout`` -
// повторный таймер просто сам кладёт себя обратно после срабатывания
// (`player-next.js` считает свою плашку через ``setInterval``, поиск на главной
// таких вовсе не заводит - отсюда раньше очередь знала только один вид таймера).
function clock() {
  const timers = [];
  let now = 0;
  let seq = 0;
  const schedule = (fn, ms, repeat) => {
    seq += 1;
    timers.push({ id: seq, at: now + (ms || 0), ms: ms || 0, repeat, fn });
    return seq;
  };
  const cancel = (id) => { const at = timers.findIndex((t) => t.id === id); if (at >= 0) timers.splice(at, 1); };
  return {
    now: () => now,
    setTimeout: (fn, ms) => schedule(fn, ms, false),
    clearTimeout: cancel,
    setInterval: (fn, ms) => schedule(fn, ms, true),
    clearInterval: cancel,
    // Двигать время до `limit`, отдавая промисам ход после каждого таймера; `steps` - предохранитель
    // от страницы, которая заводит таймеры без конца.
    async run(limit, steps = 20000) {
      for (let n = 0; n < steps; n += 1) {
        for (let i = 0; i < 20; i += 1) await new Promise((done) => setImmediate(done));
        timers.sort((a, b) => a.at - b.at || a.id - b.id);
        if (!timers.length || timers[0].at > limit) { now = Math.max(now, limit); return; }
        const timer = timers.shift();
        now = Math.max(now, timer.at);
        if (timer.repeat) { timer.at = now + timer.ms; timers.push(timer); }
        timer.fn();
      }
    },
    pending: () => timers.length,
  };
}

function page(answer, { latency = 30 } = {}) {
  const doc = new Document();
  const time = clock();
  const opened = [];
  // Имя, с которым карточку открыли: плитка выдачи обязана спросить раздачи ПО СВОЕЙ
  // картине, а не по набранному тексту, иначе круг молчит о половине экрана.
  const cards = [];
  const polls = [];
  const queries = [];
  const header = doc.createElement('div');
  header.className = 'tc-header';
  const body = doc.createElement('div');
  body.id = 'tc-body';
  doc.body.append(header, body);
  const ctx = {
    document: doc,
    console,
    JSON,
    Date: { now: time.now },
    setTimeout: time.setTimeout,
    clearTimeout: time.clearTimeout,
    location: { pathname: '/', search: '' },
    history: { replaceState() {} },
    sessionStorage: { setItem() {} },
    ResizeObserver: class { observe() {} },
    TC: { say: (key) => key, count: (key, n) => key + ':' + n, header: () => header },
    TCKept: { mark() {}, take: () => null },
    TCRouter: { card(key, query) { opened.push(key); cards.push([key, query]); } },
    fetch: (url, init) => new Promise((done, fail) => {
      const began = time.now();
      const body = JSON.parse(init.body);
      polls.push(began);
      queries.push(body.query);
      const said = answer(polls.length - 1, began, body.query);
      time.setTimeout(() => {
        if (said.reject) {
          fail(new Error('network down'));
          return;
        }
        const status = said.status || 200;
        done({
          ok: status >= 200 && status < 300,
          status,
          headers: { get: (name) => ({ 'X-Torrcast-Partial': said.partial ? '1' : '0',
            'X-Torrcast-Final-By': String(said.finalBy ?? 12),
            'X-Torrcast-Posters-Pending': said.postersPending ? '1' : '0',
            'X-Torrcast-Posters-By': String(said.postersBy ?? 60) })[name] ?? null },
          json: async () => said.body || { results: said.results },
        });
      }, said.delay ?? latency);
    }),
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['api.js', 'tile.js', 'home.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }
  ctx.TCApi.sources = async () => 0;
  return { doc, time, ctx, opened, cards, polls, queries, home: ctx.TCHome };
}

module.exports = { page, Element, TextNode, Document, clock, matches };
