'use strict';
// Отказ потока после первого кадра на настоящем ``player.js``: пока лента пересобирается,
// виден экран буферизации, а сняв его, плёнка снова идёт; четвёртый отказ - экран потери.
// Экран читается каждые 10 мс виртуального времени.
const { player } = require('./player_page.js');

const BOX = { key: 'k1', url: 'http://stand/a.m3u8', at: 140.75 };

async function framed() {
  const st = { state: 'playing', has_next: null, start: null };
  const p = player({ box: () => BOX, state: () => st });
  p.mount();
  await p.time.run(1000);
  p.video.dispatch('playing');
  await p.time.run(1500);
  return p;
}

// Первый миг после отказа, когда виден экран буферизации; ``null`` - не виден ни разу.
async function failOnce(p) {
  const start = p.time.now();
  p.video.error = { code: 3 };
  p.video.dispatch('error');
  let seen = null;
  for (let t = 0; t <= 1500; t += 10) {
    await p.time.run(start + t);
    if (seen === null && p.overlay().querySelector('.tc-buffering')) seen = t;
  }
  return seen;
}

async function main() {
  const p = await framed();
  const facts = { buffering: await failOnce(p) };
  p.video.dispatch('playing');
  await p.time.run(p.time.now() + 50);
  facts.cleared = !p.overlay().querySelector('.tc-buffering');
  const q = await framed();
  for (let i = 0; i < 3; i += 1) await failOnce(q);
  q.video.dispatch('error');
  await q.time.run(q.time.now() + 50);
  facts.lost = !!q.overlay().querySelector('.tc-lost');
  process.stdout.write(JSON.stringify(facts) + '\n');
  process.exit(0);
}

main();
