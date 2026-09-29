'use strict';
// Экран вкладки между ящиком и первым кадром на настоящем ``player.js``: сервер отвечает
// так, как отвечает ``payload()`` (``start`` со ``here``/``packed`` из
// :mod:`torrcast.usecases.start_progress`), время виртуальное и абсолютное.
const { player } = require('./player_page.js');

const BOX = { key: 'k1', url: 'http://stand/a.m3u8', at: 0 };

// Что сейчас читает зритель: заголовок подготовки, буферизация, отказ или плашка серии.
function screen(p) {
  const o = p.overlay();
  const title = o.querySelector('.tc-preparing-title');
  return {
    title: title ? title.textContent : null,
    buffering: !!o.querySelector('.tc-buffering'),
    refused: !!o.querySelector('.tc-refused'),
    next: !!o.querySelector('.tc-next'),
  };
}

// Подъём во вкладке: упаковка, ящик, первый сегмент, ``waiting`` у ``<video>``, конец.
// ``end`` - чем кончается подъём: кадром, отказом или тихим концом без кадра.
async function lift(here, end) {
  let box = null;
  let st = { state: 'starting', has_next: null, start: { waited: 1, here, packed: false } };
  const p = player({ box: () => box, state: () => st });
  p.mount();
  await p.time.run(2500);
  const packing = screen(p);
  box = BOX;
  st = { state: 'starting', has_next: null, start: { waited: 3, here, packed: true } };
  await p.time.run(4500);
  const packed = screen(p);
  p.video.dispatch('waiting');
  const stalled = screen(p);
  await p.time.run(9000);
  const later = screen(p);
  if (end === 'frame') {
    st = { state: 'playing', has_next: null, start: null };
    p.video.dispatch('playing');
  } else if (end === 'early') {
    // Кадр пошёл раньше, чем вкладка доложила о нём: в ответах ещё висит ``start``.
    p.video.dispatch('playing');
  } else if (end === 'refused') {
    st = { state: 'idle', has_next: null, start: null, refusal: 'source_did_not_answer', last_error: 'no' };
  } else {
    st = { state: 'starting', has_next: null, start: null };
  }
  await p.time.run(13000);
  const over = screen(p);
  p.video.dispatch('waiting');
  return { packing, packed, stalled, later, over, afterWaiting: screen(p) };
}

// Плашка следующей серии стоит, а продукт уже поднимает серию во вкладке.
async function plaque() {
  let st = { state: 'playing', has_next: true, season: 8, episode: 1, start: null };
  const p = player({ box: () => BOX, state: () => st });
  p.mount();
  await p.time.run(200);
  p.video.dispatch('playing');
  p.video.duration = 100;
  p.tick(95);
  st = { state: 'starting', has_next: true, season: 8, episode: 1,
    start: { waited: 2, here: true, packed: true } };
  p.video.dispatch('waiting');
  await p.time.run(4500);
  return screen(p);
}

async function main() {
  const facts = {
    here: await lift(true, 'frame'),
    tv: await lift(false, 'frame'),
    early: await lift(true, 'early'),
    died: await lift(true, 'refused'),
    quiet: await lift(true, 'quiet'),
    plaque: await plaque(),
  };
  process.stdout.write(JSON.stringify(facts) + '\n');
  process.exit(0);
}

main();
