'use strict';
// Отказ подъёма и медленный поиск следующей серии на настоящем ``player.js``: сервер
// отвечает так, как отвечает ``payload()`` (``has_next`` = ``null`` на ``starting`` и
// ``idle``), время виртуальное и абсолютное (``time.run(t)`` идёт ДО метки ``t``).
const { player } = require('./player_page.js');

const REASON = 'source_did_not_answer';

function gone(p) {
  return p.calls.routerGo.length + p.calls.historyBack;
}

function refusedFacts(p) {
  const screen = p.overlay().querySelector('.tc-refused');
  return { left: gone(p), refused: !!screen, line: screen ? screen.textContent : '' };
}

// Подъём картины кончился отказом: ``starting`` без ящика, потом ``idle`` с причиной.
async function refusedStart(first) {
  let st = { state: 'starting', has_next: null, start: { waited: 3 }, refusal: null, last_error: null };
  const p = player({ box: () => null, state: () => st });
  p.ctx.TC.phrases['web.player.refused_' + REASON] = 'the source did not answer';
  p.mount();
  await p.time.run(6000);
  st = { state: 'idle', has_next: null, start: null, refusal: first.refusal, last_error: first.error };
  await p.time.run(12000);
  return refusedFacts(p);
}

// Серия кончилась, юнит нашёл следующую, но поднять её не смог и погас с отказом.
async function refusedNext() {
  let st = { state: 'playing', has_next: true, season: 8, episode: 1 };
  const box = { key: 'k1', url: 'http://stand/a.m3u8', at: 0 };
  const p = player({ box: () => box, state: () => st });
  p.ctx.TC.phrases['web.player.refused_' + REASON] = 'the source did not answer';
  p.mount();
  await p.time.run(200);
  p.video.duration = 100;
  p.tick(95);
  await p.time.run(11000);
  p.ended();
  st = { state: 'starting', has_next: null, start: { waited: 2 } };
  await p.time.run(30000);
  st = { state: 'idle', has_next: null, start: null, refusal: REASON, last_error: 'no answer' };
  await p.time.run(36000);
  return refusedFacts(p);
}

// Юнит жив ещё минуту после ``ended`` (поиск медленный), потом кладёт ящик ``k2``.
async function slowFound(first, midState) {
  let st = { state: 'playing', has_next: first, season: 8, episode: 1 };
  let box = { key: 'k1', url: 'http://stand/a.m3u8', at: 0 };
  const p = player({ box: () => box, state: () => st,
    position: (said) => (said.key === box.key ? 200 : 409) });
  p.mount();
  await p.time.run(200);
  p.video.duration = 100;
  p.tick(95);
  await p.time.run(11000);
  p.ended();
  st = { state: midState, has_next: first, season: 8, episode: 1 };
  await p.time.run(71000);
  const whileSearching = gone(p);
  box = { key: 'k2', url: 'http://stand/b.m3u8', at: 0 };
  st = { state: 'starting', has_next: null };
  await p.time.run(79000);
  st = { state: 'playing', has_next: true, season: 8, episode: 2 };
  await p.time.run(87000);
  const T = p.ctx.TCPlayer;
  return { whileSearching, afterBox: gone(p), key: T._key, url: T._url, pending: !!T._pendingBox };
}

async function main() {
  const facts = {
    film: await refusedStart({ refusal: REASON, error: 'no answer' }),
    episode: await refusedStart({ refusal: null, error: 'nothing parsed' }),
    next: await refusedNext(),
    slow: {},
  };
  for (const first of [true, null]) {
    for (const mid of ['playing', 'paused', 'starting']) {
      facts.slow[`${first}/${mid}`] = await slowFound(first, mid);
    }
  }
  process.stdout.write(JSON.stringify(facts) + '\n');
  process.exit(0);
}

main();
