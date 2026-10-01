// «Отмена» на плашке следующей серии во вкладке (TC-1390, решение владельца по TC-1394):
// серия доигрывает, на её конце - карточка сериала, следующая серия не начинается.
// Печатает факты одной строкой JSON на сценарий; решает `tests/test_player_cancel.py`.
'use strict';

const { player } = require('./player_page.js');

const CARD = '.tc-next';
const TITLE = 'Рик и Морти';
const HISTORY = [{
  key: 'rick', title: 'Rick and Morty', query: 'rick and morty', shown: TITLE,
  kind: 'series', year: 2013, label: 's1e3', pos: 0, dur: 0,
}];

// Сервер одного показа: ящик, снимок и ответ на доклад позиции меняет сценарий.
function stand(firstBox) {
  const live = {
    box: firstBox,
    state: { state: 'playing', has_next: true, season: 1, episode: 2, title: TITLE },
    refuse: false,
  };
  const p = player({
    box: () => live.box,
    state: () => live.state,
    position: () => (live.refuse ? 409 : 204),
    history: () => HISTORY,
  });
  const go = (ms) => p.time.run(p.time.now() + ms);
  // Показ кончился на сервере: ящик снят, отметка «Отмены» (если была) жива, юнит погас.
  const closed = (last) => {
    live.box = last ? { tv: false, last } : { tv: false };
    live.state = { state: 'idle', has_next: false };
  };
  const end = () => {
    p.video.currentTime = 100;
    p.video.ended = true;
    p.ended();
  };
  return { p, live, go, closed, end };
}

function shown(p) {
  return !!p.doc.querySelector(CARD);
}

function cancel(p) {
  p.doc.querySelectorAll(CARD + ' button')[1].dispatch('click');
}

function outcome(p) {
  return {
    card: p.calls.card,
    back: p.calls.historyBack + p.calls.routerGo.length,
    stops: p.calls.control.filter(([cmd]) => cmd === 'stop').length,
    nextCalls: p.calls.next.length,
    key: p.ctx.TCPlayer._key,
  };
}

const scenarios = {
  // Обычная «Отмена» за несколько секунд до конца: слово серверу уходит сразу, серия
  // доигрывает без плашки, на её конце - карточка сериала, а не шаг назад.
  async cancelInTheTab() {
    const { p, go, closed, end } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0 });
    p.mount();
    await go(200);
    p.video.duration = 100;
    p.tick(91);
    const mounted = shown(p);
    const before = p.calls.position.length;
    cancel(p);
    await go(50);
    const saidAtOnce = p.calls.position.slice(before).some((one) => one.last === true);
    p.tick(95);
    p.tick(99);
    await go(3000);
    const plaqueBack = shown(p);
    const leftBeforeTheEnd = p.calls.card.length + p.calls.historyBack + p.calls.routerGo.length;
    end();
    await go(600);
    const ended = p.calls.position.filter((one) => one.phase === 'ended');
    closed('k1');
    await go(5000);
    return {
      mounted, saidAtOnce, plaqueBack, leftBeforeTheEnd,
      endedReports: ended.length, endedAllLast: ended.every((one) => one.last === true),
      ...outcome(p),
    };
  },

  // Серия кончилась раньше, чем вкладка успела сказать: сервер уже закрыл показ без
  // отметки и заводит следующую серию. Её ящик вкладка не играет - снимает показ и
  // открывает карточку сериала.
  async cancelAfterTheServerMovedOn() {
    const { p, live, go, end } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0 });
    p.mount();
    await go(200);
    p.video.duration = 100;
    p.tick(91);
    await go(200);
    end();
    live.box = { tv: false };
    live.refuse = true;
    live.state = { state: 'starting', has_next: null, title: TITLE };
    await go(300);
    const mountedAtClick = shown(p);
    cancel(p);
    await go(300);
    live.box = { key: 'k2', url: 'http://stand/b.m3u8', at: 0, tv: false };
    await go(2000);
    return { mountedAtClick, ...outcome(p) };
  },

  // Перезагрузка вкладки после «Отмены»: ящик называет ключ отмеченным, плашки нет,
  // доклады несут отметку, конец - карточка сериала.
  async reloadAfterCancel() {
    const { p, go, closed, end } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0, last: 'k1' });
    p.mount();
    await go(200);
    p.video.duration = 100;
    p.tick(91);
    await go(2500);
    const plaque = shown(p);
    const reportsLast = p.calls.position.length > 0 && p.calls.position.every((one) => one.last === true);
    end();
    await go(600);
    closed('k1');
    await go(5000);
    return { plaque, reportsLast, ...outcome(p) };
  },

  // Вторая вкладка того же показа «Отмену» не видела: её плашка досчитала, а показ
  // погас без новой серии. Ключ «Отмены» в ящике ведёт и её в карточку сериала.
  async secondTabFollowsTheCancel() {
    const { p, go, closed, end } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0 });
    p.mount();
    await go(200);
    p.video.duration = 100;
    p.tick(91);
    end();
    await go(1500);
    closed('k1');
    await go(5000);
    const sentLast = p.calls.position.some((one) => one.last === true);
    return { sentLast, ...outcome(p) };
  },

  // Без «Отмены» погасший показ - прежний уход назад, карточка сериала не открывается.
  async noCancelLeavesAsBefore() {
    const { p, go, closed, end } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0 });
    p.mount();
    await go(200);
    p.video.duration = 100;
    p.tick(91);
    end();
    await go(1500);
    closed('');
    await go(5000);
    const sentLast = p.calls.position.some((one) => one.last === true);
    return { sentLast, ...outcome(p) };
  },

  // Счёт плашки - реальные секунды видео: лента вдруг короче обещанного (осталось 3 с) -
  // и счёт тут же 3, а не 8, и переход по нулю приходит с концом ленты.
  async countFollowsTheRealRemainder() {
    const { p, go } = stand({ key: 'k1', url: 'http://stand/a.m3u8', at: 0 });
    p.ctx.TC.say = (key, vars) => (vars && vars.n !== undefined ? String(vars.n) : key);
    p.mount();
    await go(200);
    p.video.duration = 100;
    const badge = () => {
      const node = p.doc.querySelector('.tc-next-badge');
      return node ? node.textContent : null;
    };
    const seen = [];
    p.tick(90.5);
    seen.push(badge());
    await go(1000);
    seen.push(badge());
    p.tick(97);
    for (let i = 0; i < 4; i += 1) {
      await go(1000);
      seen.push(badge());
    }
    return { seen };
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
      facts[name] = { crashed: String((error && error.stack) || error) };
    }
    await new Promise((done) => setImmediate(done));
    facts[name].errors = errors.slice();
  }
  process.stdout.write(JSON.stringify(facts) + '\n');
}

main();
