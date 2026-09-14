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
      set: (_, key, value) => { this.setAttribute('data-' + kebab(key), String(value)); return true; },
    });
  }

  get className() { return this.getAttribute('class') || ''; }
  set className(value) { this.setAttribute('class', value); }
  get id() { return this.getAttribute('id') || ''; }
  set id(value) { this.setAttribute('id', value); }
  get firstElementChild() { return this.children[0] || null; }
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

  focus() {
    if (this.getAttribute('data-tc-focusable') !== null && this.ownerDocument.body.contains(this)) {
      this.ownerDocument.activeElement = this;
    }
  }
}

class Document {
  constructor() {
    this.documentElement = new Element(this, 'html');
    this.body = this.documentElement.appendChild(new Element(this, 'body'));
    this.activeElement = this.body;
  }

  createElement(tag) { return new Element(this, tag); }
  getElementById(id) { return this.documentElement.querySelector('#' + id); }
  querySelector(selector) { return this.documentElement.querySelector(selector); }
  querySelectorAll(selector) { return this.documentElement.querySelectorAll(selector); }
}

// Часы и таймеры страницы: время идёт только тогда, когда его двигает сценарий.
function clock() {
  const timers = [];
  let now = 0;
  let seq = 0;
  return {
    now: () => now,
    setTimeout: (fn, ms) => { seq += 1; timers.push({ at: now + (ms || 0), seq, fn }); return seq; },
    clearTimeout: (id) => { const at = timers.findIndex((t) => t.seq === id); if (at >= 0) timers.splice(at, 1); },
    // Двигать время до `limit`, отдавая промисам ход после каждого таймера; `steps` - предохранитель
    // от страницы, которая заводит таймеры без конца.
    async run(limit, steps = 20000) {
      for (let n = 0; n < steps; n += 1) {
        for (let i = 0; i < 20; i += 1) await new Promise((done) => setImmediate(done));
        timers.sort((a, b) => a.at - b.at || a.seq - b.seq);
        if (!timers.length || timers[0].at > limit) { now = Math.max(now, limit); return; }
        const timer = timers.shift();
        now = Math.max(now, timer.at);
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
    TCRouter: { card: (key) => opened.push(key) },
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
            'X-Torrcast-Final-By': String(said.finalBy ?? 12) })[name] ?? null },
          json: async () => ({ results: said.results }),
        });
      }, latency);
    }),
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const name of ['api.js', 'tile.js', 'home.js']) {
    vm.runInContext(fs.readFileSync(path.join(STATIC, name), 'utf8'), ctx, { filename: name });
  }
  ctx.TCApi.sources = async () => 0;
  return { doc, time, ctx, opened, polls, queries, home: ctx.TCHome };
}

module.exports = { page };
