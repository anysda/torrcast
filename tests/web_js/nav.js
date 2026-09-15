// Стрелка вниз с поля поиска на выложенном экране: печатает, куда встал фокус, одной строкой JSON.
// Решает `tests/test_nav_search_field.py`; раскладка - прямоугольники экрана 1600 точек шириной.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function element(name, box, parent, classes = []) {
  return {
    name,
    parentElement: parent,
    offsetParent: {},
    matches: (selector) => classes.some((one) => selector === '.' + one),
    closest: () => null,
    getBoundingClientRect: () => ({ ...box, right: box.left + box.width, bottom: box.top + box.height }),
  };
}

function landing(withRetry) {
  const form = { name: 'form' };
  const body = { name: 'body' };
  const grid = { name: 'grid' };
  const field = element('field', { left: 0, top: 0, width: 1600, height: 70 }, form, ['tc-search-input']);
  const shown = [field];
  if (withRetry) shown.push(element('retry', { left: 0, top: 210, width: 220, height: 56 }, body));
  const top = withRetry ? 320 : 120;
  for (let n = 0; n < 8; n += 1) {
    shown.push(element('tile' + n, { left: n * 200, top, width: 190, height: 300 }, grid));
    shown.push(element('low' + n, { left: n * 200, top: top + 330, width: 190, height: 300 }, grid));
  }
  const document = { querySelectorAll: () => shown };
  const context = { document, window: {} };
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'static', 'nav.js'), 'utf8');
  vm.runInContext(source + '\nwindow.TCNav = TCNav;', context);
  const there = context.window.TCNav.nearest(field, 'down');
  return there ? there.name : null;
}

process.stdout.write(JSON.stringify({ failed: landing(true), results: landing(false) }) + '\n');
