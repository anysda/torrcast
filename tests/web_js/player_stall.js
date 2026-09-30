'use strict';
// Заминка после первого кадра на настоящем ``player.js``: короткая (перемотка на место,
// стык кусков) буферизацию не показывает, долгая показывает, пауза посреди заминки - нет.
// Экран читается каждые 10 мс виртуального времени: вспышка на один кадр не проскочит.
const { player } = require('./player_page.js');

const BOX = { key: 'k1', url: 'http://stand/a.m3u8', at: 0 };

async function framed() {
  const st = { state: 'playing', has_next: null, start: null };
  const p = player({ box: () => BOX, state: () => st });
  p.mount();
  await p.time.run(1000);
  p.video.dispatch('playing');
  await p.time.run(1500);
  return p;
}

// Первый миг, когда виден экран буферизации, от ``waiting``; ``null`` - не виден ни разу.
async function watch(p, span, resumeAt, how) {
  const start = p.time.now();
  p.video.readyState = 2;
  p.video.dispatch('waiting');
  let seen = null;
  for (let t = 0; t <= span; t += 10) {
    if (resumeAt !== null && t === resumeAt) {
      p.video.readyState = 4;
      if (how === 'playing') p.video.dispatch('playing');
    }
    await p.time.run(start + t);
    if (seen === null && p.overlay().querySelector('.tc-buffering')) seen = t;
  }
  return seen;
}

async function main() {
  const threshold = (await framed()).ctx.TCPlayer.STALL_SHOW_MS;
  const facts = {
    threshold,
    short: await watch(await framed(), 1500, 80, 'playing'),
    edge: await watch(await framed(), 1500, threshold - 20, 'playing'),
    long: await watch(await framed(), 1500, null, null),
    paused: await watch(await framed(), 1500, 100, 'paused'),
  };
  process.stdout.write(JSON.stringify(facts) + '\n');
  process.exit(0);
}

main();
