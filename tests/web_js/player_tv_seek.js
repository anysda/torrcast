'use strict';
// Перемотка, нажатая НЕ в этой вкладке (карточка, Home Assistant, мост), на настоящем
// ``player.js`` во время показа на ТВ: вкладка узнаёт о ней только из снимка ``/api/state``
// (``seek``: номер и цель от моста). Печатает плёнку вкладки после каждого шага.
const { player } = require('./player_page.js');

const BOX = { key: 'k1', url: 'http://stand/a.m3u8', at: 0, tv: true };

// Снимок отдаётся только после того, как плёнка вкладки встала на ``film``: иначе первый
// же доклад пришёл бы раньше, и сценарий не отличил бы «запомнил номер» от «подтянул».
async function onTv(film, first) {
  let st = null;
  const p = player({ box: () => BOX, state: () => st });
  p.mount();
  await p.time.run(1000);
  p.video.currentTime = film;
  st = first;
  return { p, say(next) { st = next; } };
}

const round = (value) => Math.round(value * 10) / 10;

async function main() {
  // Мост перемотал назад: ТВ доложил 745.1 при плёнке 1062 (живой приёмник 06-10-2026).
  const back = await onTv(1062, { state: 'playing', position: 1060, seek: { n: 1, to: 1060 } });
  await back.p.time.run(3000);
  const beforeSeek = round(back.p.video.currentTime);
  back.say({ state: 'playing', position: 745.1, seek: { n: 2, to: 745.1 } });
  await back.p.time.run(6000);
  const afterSeek = round(back.p.video.currentTime);
  const seekingAfter = back.p.ctx.TCPlayer._seeking;
  // Тот же номер дальше: доклад чуть позади плёнки - обычный излёт, назад не тянем (TC-1147).
  back.p.video.currentTime = 760;
  back.say({ state: 'playing', position: 750, seek: { n: 2, to: 745.1 } });
  await back.p.time.run(9000);
  const sameNumber = round(back.p.video.currentTime);

  // Первый снимок каста несёт старую перемотку: номер только запоминается.
  const fresh = await onTv(760, { state: 'playing', position: 745, seek: { n: 3, to: 745 } });
  await fresh.p.time.run(6000);
  const firstSnapshot = round(fresh.p.video.currentTime);

  // Снимок без перемотки (простой мост, ``seek: null``) ведёт себя как раньше.
  const bare = await onTv(760, { state: 'playing', position: 745, seek: null });
  await bare.p.time.run(6000);
  const noSeek = round(bare.p.video.currentTime);

  // Пульт ТВ мимо страницы: номера нет, доклад на 300 с позади плёнки (стенд 06-10-2026).
  const remote = await onTv(1690, { state: 'playing', position: 1690, seek: null });
  await remote.p.time.run(3000);
  remote.say({ state: 'playing', position: 1381.8, seek: null });
  await remote.p.time.run(6000);
  const remoteBack = round(remote.p.video.currentTime);

  // Пульт назад, ТВ 18 с ищет место и докладывает его же, заиграв (стенд 06-10-2026).
  const buffered = await onTv(526.1, { state: 'playing', position: 524, seek: null });
  await buffered.p.time.run(3000);
  buffered.say({ state: 'starting', position: 217.8, seek: null });
  await buffered.p.time.run(21000);
  buffered.say({ state: 'playing', position: 217.8, seek: null });
  await buffered.p.time.run(23500);
  const afterBuffer = round(buffered.p.video.currentTime);

  // «На комп» между докладами: вкладка садится на доклад плюс ход часов с мига, когда он
  // заиграл, а не на сам доклад. Плёнку до нажатия держим на том же месте, чтобы посадку
  // делало нажатие, а не подтяжка `_follow`.
  const home = await onTv(300, { state: 'playing', position: 300, seek: null });
  await home.p.time.run(8000);
  home.p.video.currentTime = 300;
  home.p.ctx.TCPlayer._makeHandlers().onToggleTv();
  await home.p.time.run(10);
  const landedHome = round(home.p.video.currentTime);

  const facts = {
    beforeSeek, afterSeek, seekingAfter, sameNumber, firstSnapshot, noSeek, remoteBack,
    afterBuffer, landedHome,
  };
  process.stdout.write(JSON.stringify(facts) + '\n');
  process.exit(0);
}

main();
