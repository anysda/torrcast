// Сценарии поиска на главной: печатают факты страницы одной строкой JSON на сценарий.
// Решает не этот файл, а `tests/test_home_search_js.py`: здесь только то, что видно на экране.
'use strict';

const { page } = require('./page.js');

const LIVE = '#tc-body [data-tc-tile][data-tc-focusable]';
const LATENCY = 30;

function hit(key, extra = {}) {
  return { key, title: 'T ' + key, year: 2000, kind: 'movie', ...extra };
}

// Картина плитки - ключ из пометки прогрева, с которым она и откроется: так же её читает щуп.
function picture(tile) {
  return JSON.parse(tile.dataset.tcWarmFacts || '{}').key;
}

function screen(p) {
  const here = p.doc.activeElement;
  const tiles = p.doc.querySelectorAll(LIVE);
  return {
    keys: tiles.map(picture),
    best: p.doc.querySelectorAll('#tc-body .tc-tile-best').length,
    searching: p.doc.querySelectorAll('#tc-body .tc-searching').length,
    dim: p.doc.querySelectorAll('#tc-body .is-dim').length,
    waiting: p.doc.querySelectorAll('#tc-body .tc-cap2').length,
    failed: p.doc.querySelectorAll('#tc-body .tc-search-retry').length,
    failedKeys: p.doc.querySelectorAll('#tc-body .tc-search-retry[data-tc-focusable]').length,
    text: p.doc.getElementById('tc-body').textContent,
    focus: here.dataset.tcTile ? picture(here) : here.tagName,
  };
}

function search(answer, text = 'тачки') {
  const p = page(answer, { latency: LATENCY });
  p.home._query = text;
  p.home._runSearch(text);
  return p;
}

function focusKey(p, key) {
  const tile = p.doc.querySelectorAll(LIVE).find((one) => picture(one) === key);
  if (tile) tile.focus();
}

const TEN = Array.from({ length: 10 }, (_, n) => hit('k' + n));

const scenarios = {
  // Сервер не отдаёт финала никогда: страница обязана бросить опрос сама, по сроку сервера.
  async endless() {
    const p = search(() => ({ partial: true, results: TEN.slice(0, 3), finalBy: 12 }));
    await p.time.run(120000);
    return { finalBy: 12, polls: p.polls, timers: p.time.pending(), screen: screen(p) };
  },

  // Финал на 18-й секунде при сроке сервера 20 с: страница его дожидается.
  async late() {
    const p = search((_, at) => ({ partial: at < 18000, results: TEN.slice(0, 3), finalBy: 20 }));
    await p.time.run(60000);
    return { polls: p.polls, screen: screen(p) };
  },

  // Шаг опроса: пустое превью - часто, с находками - реже, после финала - ни одного.
  async steps() {
    const p = search((n) => ({ partial: n < 6, results: n < 3 ? [] : TEN.slice(0, 2), finalBy: 12 }));
    await p.time.run(60000);
    return { latency: LATENCY, polls: p.polls, timers: p.time.pending() };
  },

  // Финал слово в слово равен последнему превью: плашка встаёт, строка «ищем» уходит.
  async equal() {
    const p = search((n) => ({ partial: n < 2, results: TEN.slice(0, 3), finalBy: 12 }));
    await p.time.run(60000);
    return { polls: p.polls.length, screen: screen(p) };
  },

  // Финал бывает без имён картинок: дозапрос идёт, пока сервер говорит «обложки в пути».
  async posterAfterFinal() {
    const p = search((n) => ({
      partial: false, postersPending: n < 2,
      results: [hit('cars', n > 1 ? { poster: 'cars.jpg' } : {})], finalBy: 2,
    }));
    await p.time.run(60000);
    return { polls: p.polls, timers: p.time.pending(), screen: screen(p) };
  },

  // Сервер твердит «обложки в пути» вечно: дозапрос кончается потолком сервера.
  async posterCap() {
    const p = search(() => ({ partial: false, postersPending: true, results: TEN, postersBy: 20 }));
    await p.time.run(120000);
    return { postersBy: 20, polls: p.polls, timers: p.time.pending() };
  },

  // Опрос, начатый до срока, застрял в очереди браузера на 3 с: финал всё равно встаёт.
  async held() {
    const p = search((n, at) => ({
      partial: at < 14000, results: TEN.slice(0, 3), finalBy: 12,
      delay: at >= 13000 && at < 14000 ? 3000 : undefined,
    }));
    await p.time.run(60000);
    return { polls: p.polls, screen: screen(p) };
  },

  // Один сорванный опрос посреди живого поиска: экрана сбоя нет, финал встаёт.
  async blip() {
    const p = search((n) => (n === 3 ? { status: 502 }
      : { partial: n < 5, results: TEN.slice(0, 3), finalBy: 12 }));
    await p.time.run(60000);
    return { polls: p.polls.length, screen: screen(p) };
  },

  // Сервер пропал посреди поиска: плитки на месте, повтор ищет снова, фокус на первой плитке.
  async lost() {
    let phase = 'up';
    const p = search((n) => {
      if (phase === 'down') return { reject: true };
      if (phase === 'final') return { partial: false, results: TEN.slice(0, 3), finalBy: 12 };
      if (n === 2) phase = 'down';
      return { partial: true, results: TEN.slice(0, 3), finalBy: 12 };
    });
    await p.time.run(5000);
    const failed = screen(p);
    const retry = p.doc.querySelector('.tc-search-retry');
    retry.focus();
    phase = 'final';
    retry.dispatch('click');
    await p.time.run(60000);
    return { failed, after: screen(p), timers: p.time.pending() };
  },

  async failedNetwork() {
    const p = search(() => ({ reject: true }));
    await p.time.run(1000);
    return { polls: p.polls, queries: p.queries, screen: screen(p) };
  },

  async failedServer() {
    const p = search(() => ({ status: 500 }));
    await p.time.run(1000);
    return { polls: p.polls, queries: p.queries, screen: screen(p) };
  },

  async retry() {
    const p = search((n) => n ? { partial: false, results: [], finalBy: 0 } : { status: 500 });
    await p.time.run(1000);
    p.doc.querySelector('.tc-search-retry').dispatch('click');
    await p.time.run(2000);
    return { polls: p.polls, queries: p.queries, screen: screen(p) };
  },

  // Картина каталога ждёт раздач, а в финале гаснет: подпись «ищу раздачи» уходит, клика нет.
  async dim() {
    const p = search((n) => ({
      partial: n < 2,
      results: [hit('a'), hit('c', n < 2 ? { pending: true } : { dim: true })],
      finalBy: 12,
    }));
    await p.time.run(200);
    const during = screen(p);
    await p.time.run(60000);
    const tiles = p.doc.querySelectorAll(LIVE);
    tiles.forEach((tile) => tile.dispatch('click'));
    return { during, after: screen(p), opened: p.opened };
  },

  // Фокус на плитке второго ряда: дописанное превью и переставленный финал его не уводят.
  async second() {
    const p = search((n, at) => {
      if (at < 1000) return { partial: true, results: TEN, finalBy: 12 };
      if (at < 2000) return { partial: true, results: TEN.concat([hit('k10')]), finalBy: 12 };
      return { partial: false, results: TEN.concat([hit('k10')]).reverse(), finalBy: 12 };
    });
    await p.time.run(200);
    focusKey(p, 'k8');
    const before = screen(p).focus;
    await p.time.run(1500);
    const added = screen(p).focus;
    await p.time.run(60000);
    return { before, added, after: screen(p) };
  },

  // Находка по раздаче садится в плитку каталога и меняет личность (`slot`), но не картину.
  async slot() {
    const p = search((n, at) => (at < 1000
      ? { partial: true, results: [hit('tt1', { pending: true }), hit('a'), hit('k')], finalBy: 12 }
      : { partial: false, results: [hit('k', { slot: 'tt1' }), hit('a')], finalBy: 12 }));
    await p.time.run(200);
    focusKey(p, 'k');
    const before = screen(p).focus;
    await p.time.run(60000);
    return { before, after: screen(p) };
  },
};

async function main() {
  const errors = [];
  process.on('unhandledRejection', (error) => errors.push(String(error)));
  const facts = {};
  for (const [name, run] of Object.entries(scenarios)) {
    errors.length = 0;
    try {
      facts[name] = await run();
    } catch (error) {
      facts[name] = { crashed: String(error && error.stack || error) };
    }
    await new Promise((done) => setImmediate(done));
    facts[name].errors = errors.slice();
  }
  process.stdout.write(JSON.stringify(facts) + '\n');
}

main();
