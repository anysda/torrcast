// Сценарии перехода между сериями и раннего выхода из фильма (TC-1336): печатают факты
// экрана показа одной строкой JSON на сценарий. Решает не этот файл, а
// `tests/test_player_next_transition.py` - здесь только то, что видно и слышно продукту:
// плашка на экране, вызовы `TCApi.next`, уход со страницы.
'use strict';

const { player, next } = require('./player_page.js');

const CARD = '.tc-next';

function overlayCard(p) {
  return p.doc.querySelector(CARD);
}

function buttons(p) {
  return p.doc.querySelectorAll(CARD + ' button');
}

// Сериал: снимок называет серию, ``has_next`` взят от `hass/following.py`
// (``None`` - фильм, последняя серия или тишина; тут наоборот, серия впереди есть).
function seriesServer(episode = { season: 1, episode: 2 }) {
  let box = { key: 'k1', url: 'http://stand/a.m3u8', at: 0 };
  return {
    server: {
      box: () => box,
      state: () => ({ has_next: true, ...episode }),
    },
    setBox(next) { box = next; },
  };
}

const scenarios = {
  // Плашка встаёт РОВНО на пороге `TCPlayerNext.SECONDS`, не раньше и не на старой
  // зашитой секунде; досчитав сама, убирает карточку и зовёт `TCApi.next` ровно один
  // раз. Старое видео, доигрывающее свой хвост ПОСЛЕ перехода, второй раз не переводит.
  async seriesCountdown() {
    const { server } = seriesServer();
    const p = player(server);
    p.mount();
    await p.time.run(200);
    p.video.duration = 100;

    p.tick(88.9); // до конца 11.1 с - ещё не порог
    const beforeThreshold = !!overlayCard(p);

    p.tick(94.5); // до конца 5.5 с - внутри обещанных 10, а не только внутри старой 1 с
    const atThreshold = !!overlayCard(p);

    await p.time.run(9200); // девять тиков счётчика: 10 -> 1, карточка ещё висит
    const beforeExpiry = !!overlayCard(p);

    await p.time.run(10200); // десятый тик: 0, досчитала сама
    const afterExpiry = !!overlayCard(p);

    p.tick(99); // старое видео доигрывает ещё кадр на том же четверть-конце
    const afterStaleTick = !!overlayCard(p);

    return {
      beforeThreshold, atThreshold, beforeExpiry, afterExpiry, afterStaleTick,
      nextCalls: p.calls.next.length,
      nextArg: p.calls.next[0],
      boxPolls: p.calls.boxPolls,
    };
  },

  // «Отмена» снимает карточку и не заводит переход; старое видео, доигрывающее тот же
  // самый хвост дальше, не поднимает карточку заново (регрессия мержера 17-09-2026).
  //
  // Ящик, найденный ПОСРЕДИ счёта (тем же путём, что и `midCountdownReboxDefers`),
  // копится в `_pendingBox`, не применяясь, пока карточка висит. «Отмена» обязана
  // сбросить его вместе со счётом - иначе он остаётся сидеть в поле навсегда и позже
  // (`_playNext()`, следующая карточка) применится вместо свежего, замораживая кадр
  // (находка мержера: удалённая строка `_pendingBox = null;` в `_cancelNext()`).
  async seriesCancelHolds() {
    const { server, setBox } = seriesServer();
    const p = player(server);
    p.mount();
    await p.time.run(200);
    p.video.duration = 100;
    p.tick(94.5);
    const mounted = !!overlayCard(p);

    setBox({ key: 'k2', url: 'http://stand/b.m3u8', at: 0 });
    p.ctx.TCPlayerBox.rebox(p.ctx.TCPlayer);
    await p.time.run(700); // ящик найден и лёг в _pendingBox, счёт ещё не дотикал
    const pendingKeyBeforeCancel = p.ctx.TCPlayer._pendingBox && p.ctx.TCPlayer._pendingBox.key;

    const cancel = buttons(p)[1];
    cancel.dispatch('click');
    const goneRightAfter = !overlayCard(p);
    const pendingBoxAfterCancel = p.ctx.TCPlayer._pendingBox;

    await p.time.run(20900); // окно, за которое настоящий счётчик уже бы истёк
    p.tick(94.6);
    p.tick(94.7);
    const stillGone = !overlayCard(p);

    // Свежий ящик после «Отмена» находится и применяется как обычно - вкладка не
    // обязана виснуть на замёрзшем кадре навеки.
    setBox({ key: 'k3', url: 'http://stand/c.m3u8', at: 0 });
    let reboxResult = null;
    p.ctx.TCPlayerBox.rebox(p.ctx.TCPlayer).then((said) => { reboxResult = said; });
    await p.time.run(21200); // время у часов уже 20900 - лимит абсолютный, не длительность
    const reboxedKey = p.ctx.TCPlayer._key;

    return {
      mounted, goneRightAfter, stillGone,
      nextCalls: p.calls.next.length,
      pendingKeyBeforeCancel, pendingBoxAfterCancel,
      reboxResult, reboxedKey,
    };
  },

  // Экран потери потока и перезапуск подменяют весь оверлей МИМО `_playNext`/
  // `_cancelNext` - живая плашка отсчёта обязана уйти вместе со своим счётом, а не
  // тикать невидимо и не увезти зрителя без его участия (дефект мержера 17-09-2026,
  // окно выросло с 1 с до 10 с вместе с поднятым порогом плашки).
  async countdownDiesWithScreenReplace() {
    const lost = await (async () => {
      const { server } = seriesServer();
      const p = player(server);
      p.mount();
      await p.time.run(200);
      p.video.duration = 100;
      p.tick(94.5);
      const mounted = !!overlayCard(p);
      const countingBefore = p.ctx.TCPlayer._counting;

      p.ctx.TCPlayer._screenLost(4); // путь `_onStreamError()` после исчерпанных попыток
      const goneRightAfter = !overlayCard(p);
      const countingAfter = p.ctx.TCPlayer._counting;

      await p.time.run(10300); // окно, за которое живой счётчик уже бы истёк и увёз зрителя
      return { mounted, countingBefore, goneRightAfter, countingAfter, nextCalls: p.calls.next.length };
    })();

    const retry = await (async () => {
      const { server } = seriesServer();
      const p = player(server);
      p.mount();
      await p.time.run(200);
      p.video.duration = 100;
      p.tick(94.5);
      const mounted = !!overlayCard(p);

      p.ctx.TCPlayer._retry(); // «Повторить» -> `_screenBuffering()`
      const goneRightAfter = !overlayCard(p);
      const countingAfter = p.ctx.TCPlayer._counting;

      await p.time.run(10300);
      return { mounted, goneRightAfter, countingAfter, nextCalls: p.calls.next.length };
    })();

    return { lost, retry };
  },

  // Ящик следующей серии находится ПОСРЕДИ счёта: карточку рвать нельзя, ящик ждёт в
  // `_pendingBox` и открывается САМ отсчётом, без второго похода за ящиком.
  async midCountdownReboxDefers() {
    const { server, setBox } = seriesServer();
    const p = player(server);
    p.mount();
    await p.time.run(200);
    p.video.duration = 100;
    p.tick(94.5);
    const mountedBefore = !!overlayCard(p);

    // Заминка-и-возобновление посреди отсчёта не должна стирать карточку.
    p.video.dispatch('playing');
    const survivedPlayingBlip = !!overlayCard(p);

    setBox({ key: 'k2', url: 'http://stand/b.m3u8', at: 0 });
    let reboxResult = null;
    p.ctx.TCPlayerBox.rebox(p.ctx.TCPlayer).then((said) => { reboxResult = said; });
    await p.time.run(300);
    const survivedRebox = !!overlayCard(p);
    const pendingKey = p.ctx.TCPlayer._pendingBox && p.ctx.TCPlayer._pendingBox.key;

    await p.time.run(10300); // остаток счёта до истечения
    const afterExpiry = !!overlayCard(p);

    // `apply()` (`player-box.js`) обязан снять `_ending` СИНХРОННО, иначе открытая
    // серия навсегда теряет собственный автопереход - `_onTimeUpdate` молчит под
    // условием `!TCPlayer._ending` (проба «(е)»: снять сброс отложенно/вовсе - здесь
    // и только здесь это видно, счёт истечения выше её не ловит: сам сброс успевает
    // случиться асинхронно ДО этой проверки).
    p.tick(50); // середина новой серии - до её собственного порога далеко, карточки нет
    const noCardMidway = !!overlayCard(p);
    p.tick(94.6); // хвост той же (переиспользованной в стенде) длительности - новый счёт
    const secondCountdownAppears = !!overlayCard(p);

    return {
      mountedBefore, survivedPlayingBlip, reboxResult, survivedRebox, pendingKey,
      afterExpiry, noCardMidway, secondCountdownAppears,
      appliedKey: p.ctx.TCPlayer._key,
      boxPolls: p.calls.boxPolls,
      nextCalls: p.calls.next.length,
    };
  },

  // ``player-next.js`` в одиночку: карточка обязана снять СЕБЯ по истечении счёта, а не
  // надеяться, что вызвавший код сейчас же перерисует весь оверлей заново (проба «(д)»:
  // убери `card.remove()` из `stop()` - в сборке дефект замаскирован следующим
  // `overlay.replaceChildren()` из `player.js`/`player-screens.js`; тут ей рисовать
  // больше некому, только сама карточка).
  async standaloneNextExpiry() {
    let played = 0;
    const p = next(() => { played += 1; }, () => {});
    const mounted = !!p.card();
    await p.time.run(9200); // девять тиков, карточка ещё должна висеть сама по себе
    const beforeExpiry = !!p.card();
    await p.time.run(10200); // десятый тик: досчитала сама
    const afterExpiry = !!p.card();
    return { mounted, beforeExpiry, afterExpiry, played };
  },

  // Фильм и финал сезона (``has_next: false``) не уходят на пороге плашки серии - только
  // у самого конца, как на ``dev`` до подъёма порога (владелец 17-09-2026).
  async movieDoesNotLeaveEarly() {
    const box = { key: 'm1', url: 'http://stand/movie.m3u8', at: 0 };
    const p = player({ box: () => box, state: () => ({ has_next: false }) });
    p.mount();
    await p.time.run(200);
    p.video.duration = 100;

    p.tick(89); // до конца 11 с
    const goneAt11 = p.calls.routerGo.length;

    p.tick(90.5); // до конца 9.5 с - под старым порогом (10) вкладка уже уехала бы
    const goneAt9_5 = p.calls.routerGo.length;
    const cardAt9_5 = !!overlayCard(p);

    p.tick(99.3); // до конца 0.7 с - тут и только тут уходит настоящий `dev`
    const goneAt0_7 = p.calls.routerGo.length;
    const path = p.calls.routerGo[0];

    return {
      goneAt11, goneAt9_5, cardAt9_5,
      goneAt0_7, path,
      leftAtPosition: 99.3, leftAtRemaining: 100 - 99.3,
    };
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
