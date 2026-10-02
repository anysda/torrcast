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

// Когда какая плитка получила обложку в уже стоящую плитку, по виртуальным часам.
function paints(p) {
  const painted = [];
  const set = p.ctx.TCTile.setPoster;
  p.ctx.TCTile.setPoster = (tile, poster, title) => {
    if (tile && poster && tile.dataset.tcPoster !== poster) {
      painted.push({ key: picture(tile), at: p.time.now() });
    }
    return set.call(p.ctx.TCTile, tile, poster, title);
  };
  return painted;
}

// Плитки, что стоят с заглушкой «нет обложки».
function noArt(p) {
  return p.doc.querySelectorAll(LIVE)
    .filter((tile) => tile.querySelector('.tc-tile-noart')).map(picture);
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
    let swaps = 0;
    const swap = p.home._swapBody;
    p.home._swapBody = (next) => { swaps += 1; return swap(next); };
    await p.time.run(60000);
    return { polls: p.polls, swaps, timers: p.time.pending(), screen: screen(p) };
  },

  // Сервер держит первый ряд, пока ложатся его обложки: скелет стоит, ряд встаёт один раз.
  async heldFirstRow() {
    const p = page((n) => ({
      partial: n < 5, results: n < 3 ? [] : [hit('cars', { poster: 'cars.jpg' })], finalBy: 12,
    }), { latency: LATENCY });
    p.home._query = 'тачки';
    p.doc.getElementById('tc-body').replaceWith(p.home._searchLoading());
    let swaps = 0;
    const swap = p.home._swapBody;
    p.home._swapBody = (next) => { swaps += 1; return swap(next); };
    p.home._runSearch('тачки');
    await p.time.run(60000);
    return { polls: p.polls.length, swaps, screen: screen(p) };
  },

  // Скелет придержанного ряда уступает любому концу поиска: сбою, отказу или пустому финалу.
  async heldThenEnd() {
    const reason = { key: 'web.search.no_season_releases', values: { title: 'Wednesday', season: 9 } };
    const ends = {
      network: { reject: true },
      server: { status: 500 },
      refused: { status: 409, body: { error: 'search_refused', reason } },
      empty: { partial: false, results: [], finalBy: 12 },
    };
    const out = { reason };
    for (const [name, end] of Object.entries(ends)) {
      const p = page((n) => (n < 3 ? { partial: true, results: [], finalBy: 12 } : end),
        { latency: LATENCY });
      p.home._query = 'тачки';
      p.doc.getElementById('tc-body').replaceWith(p.home._searchLoading());
      p.home._runSearch('тачки');
      await p.time.run(60000);
      const skeletons = p.doc.querySelectorAll('#tc-body .tc-tile-skeleton').length;
      out[name] = { polls: p.polls.length, timers: p.time.pending(), skeletons, screen: screen(p) };
    }
    return out;
  },

  // Сервер твердит «обложки в пути» вечно: дозапрос кончается потолком сервера.
  async posterCap() {
    const p = search((_, at) => ({
      partial: false, postersPending: at < 20000, results: TEN,
      postersBy: Math.max(0, 20 - at / 1000),
    }));
    await p.time.run(120000);
    return { postersBy: 20, polls: p.polls, timers: p.time.pending() };
  },

  // Финал на 10-й секунде, сервер: до потолка ещё 20 с. Отсчёт идёт от ответа, не от начала.
  async posterCapFromFinal() {
    const p = search((_, at) => ({
      partial: at < 10000, postersPending: at >= 10000, results: TEN, finalBy: 12,
      postersBy: Math.max(0, 30 - at / 1000),
    }));
    await p.time.run(120000);
    return { capAt: 30000, polls: p.polls, timers: p.time.pending() };
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

  // Круг назвал причину ключом страницы и значениями: повторять тут нечего.
  async refused() {
    const reason = { key: 'web.search.no_season_releases', values: { title: 'Wednesday', season: 9 } };
    const p = search(() => ({ status: 409, body: { error: 'search_refused', reason } }), 'уэнсдэй 9 сезон');
    await p.time.run(1000);
    return { reason, polls: p.polls, screen: screen(p) };
  },

  // The deadline's empty snapshot remains on screen only until the running circle names why.
  async lateRefusal() {
    const reason = { key: 'web.search.franchise_no_number', values: {
      name: 'Cars', total: 2, index: 9, have: 'Cars (2006), Cars 2 (2011)', more: '',
    } };
    const p = search((n) => (n < 1
      ? { partial: true, results: [], finalBy: 12 }
      : n < 2 ? { partial: false, results: [], finalBy: 12, refusalPending: true }
        : { status: 409, body: { error: 'search_refused', reason } }), 'тачки 9');
    await p.time.run(60000);
    return { reason, polls: p.polls, timers: p.time.pending(), screen: screen(p) };
  },

  // An empty circle that missed indexers did not search the catalogue: the server says
  // the search failed, and the screen offers the retry, not «nothing» or another title.
  async cutEmpty() {
    const reason = { key: 'web.search.failed', values: {} };
    const p = search(() => ({ status: 409, body: { error: 'search_refused', reason } }), 'ubuntu');
    await p.time.run(1000);
    return { polls: p.polls, screen: screen(p) };
  },

  // The deadline's empty snapshot is kept listening to; a circle that ends cut says so late.
  async lateFailed() {
    const reason = { key: 'web.search.failed', values: {} };
    const p = search((n) => (n < 1
      ? { partial: false, results: [], finalBy: 12, refusalPending: true }
      : { status: 409, body: { error: 'search_refused', reason } }), 'ubuntu');
    await p.time.run(60000);
    const failed = screen(p);
    const asked = p.queries.length;
    const returned = p.home._askedBody('ubuntu');
    p.doc.getElementById('tc-body').replaceWith(returned);
    await p.time.run(1000);
    return { polls: p.polls, timers: p.time.pending(), screen: failed,
      askedAgain: p.queries.length - asked, returned: screen(p) };
  },

  // One torn poll while listening past the deadline does not end the listening.
  async tornListen() {
    const reason = { key: 'web.search.franchise_no_number', values: {
      name: 'Cars', total: 2, index: 9, have: 'Cars (2006), Cars 2 (2011)', more: '',
    } };
    const p = search((n) => (n < 1
      ? { partial: false, results: [], finalBy: 12, refusalPending: true }
      : n < 2 ? { status: 502 }
        : { status: 409, body: { error: 'search_refused', reason } }), 'тачки 9');
    await p.time.run(60000);
    return { reason, polls: p.polls, timers: p.time.pending(), screen: screen(p) };
  },

  // Every named refusal has its own page key. The screen must not collapse any of
  // them to the generic failure just because it arrived after a preview.
  async namedRefusals() {
    const reasons = [
      { key: 'web.search.nothing_parsed', values: { name: 'Matrix 9' } },
      { key: 'web.search.no_season_releases', values: { title: 'Wednesday', season: 9 } },
      { key: 'web.search.franchise_no_number', values: {
        name: 'Cars', total: 2, index: 9, have: 'Cars (2006), Cars 2 (2011)', more: '',
      } },
      { key: 'web.search.prowlarr_not_configured', values: {} },
    ];
    const screens = [];
    for (const reason of reasons) {
      const p = search(() => ({ status: 409, body: { error: 'search_refused', reason } }));
      await p.time.run(1000);
      screens.push(screen(p));
    }
    return { reasons, screens };
  },

  // A return to the query can reuse a preview, but must not replace the completed
  // refusal with a Best match tile.
  async returnAfterRefusal() {
    const reason = { key: 'web.search.no_season_releases', values: { title: 'Wednesday', season: 9 } };
    const p = search((n) => (n < 1
      ? { partial: true, results: [hit('wednesday')], finalBy: 12 }
      : { status: 409, body: { error: 'search_refused', reason } }), 'уэнсдэй 9 сезон');
    await p.time.run(5000);
    const refusal = screen(p);
    const returned = p.home._askedBody('уэнсдэй 9 сезон');
    p.doc.getElementById('tc-body').replaceWith(returned);
    return { reason, refusal, returned: screen(p) };
  },

  async retry() {
    const p = search((n) => n ? { partial: false, results: [], finalBy: 0 } : { status: 500 });
    await p.time.run(1000);
    p.doc.querySelector('.tc-search-retry').dispatch('click');
    await p.time.run(2000);
    return { polls: p.polls, queries: p.queries, screen: screen(p) };
  },

  // Картина каталога, которой круг не принёс раздач: пока круг идёт - ждёт под подписью,
  // в финале становится обычной плиткой. Клик у неё есть и там, и там; карточку она просит
  // по своему имени, а находка круга (`pick`) - по набранному тексту, раздачи которого ей
  // уже посчитаны. Греется весь экран одним набранным текстом.
  async waiting() {
    const p = search((n) => ({
      partial: n < 2,
      results: [hit('a', { pick: 0 }), hit('c', n < 2 ? { pending: true } : {})],
      finalBy: 12,
    }));
    await p.time.run(200);
    const during = screen(p);
    await p.time.run(60000);
    const tiles = p.doc.querySelectorAll(LIVE);
    const warm = tiles.map((tile) => tile.dataset.tcWarm);
    tiles.forEach((tile) => tile.dispatch('click'));
    return { during, after: screen(p), warm, opened: p.opened, cards: p.cards };
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

  // Обложки голых плиток приходят на разных опросах, а встают в плитки одной пачкой.
  async coversOnce() {
    const p = search((n) => ({
      partial: n < 5, postersPending: false, finalBy: 12,
      results: [
        hit('a', n >= 2 ? { poster: 'a.jpg' } : {}),
        hit('b', n >= 3 ? { poster: 'b.jpg' } : {}),
        hit('c', { poster: 'c.jpg' }),
      ],
    }));
    const painted = paints(p);
    await p.time.run(60000);
    return { painted, timers: p.time.pending(), screen: screen(p), noArt: noArt(p) };
  },

  // Одна обложка так и не пришла: пачка уходит к сроку, плитка без неё остаётся заглушкой.
  async coversDeadline() {
    const p = search((n, at) => ({
      partial: at < 8000, postersPending: false, finalBy: 12,
      results: [hit('a', at >= 4000 ? { poster: 'a.jpg' } : {}), hit('b', n >= 2 ? { poster: 'b.jpg' } : {})],
    }));
    const painted = paints(p);
    await p.time.run(60000);
    return { painted, screen: screen(p), noArt: noArt(p) };
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
