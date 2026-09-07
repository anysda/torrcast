// Экран показа ``/play`` (ТЗ §4.5, §7.1-7.4): состояния подготовки/буферизации/показа/
// потери потока, автопереход между сериями и режим «на ТВ». Разметку строят соседние
// модули (`player-panel.js` - панель, `player-next.js` - плашка автоперехода), тут -
// только состояние сеанса и hls.js. Сеанс на странице ровно один: поля лежат прямо на
// самом ``TCPlayer``, как и у `TCCard` (`_tries`), а не в отдельном классе.
'use strict';

const TCPlayer = {
  MAX_RETRIES: 3,
  IDLE_MS: 3000,
  POLL_MS: 2000,
  POSITION_MS: 2000,
  DRIFT_S: 5,

  ready() {
    return typeof window.Hls !== 'undefined' && window.Hls.isSupported();
  },

  //: Шапка главной ведёт сюда без нового запроса на показ: показ уже идёт (§7.4).
  open() {
    TCRouter.go('/play');
  },

  mount(root) {
    root.replaceChildren();
    TCPlayer._url = '';
    TCPlayer._key = '';
    TCPlayer._onTv = false;
    TCPlayer._retries = 0;
    TCPlayer._advanced = false;
    TCPlayer._hasNext = false;
    TCPlayer._last = null;
    TCPlayer._idleTimer = null;

    const wrap = document.createElement('div');
    wrap.className = 'tc-player';
    root.appendChild(wrap);

    TCPlayer._handlers = TCPlayer._makeHandlers();
    TCPlayer._nodes = TCPlayerPanel.mount(wrap, TCPlayer._handlers);
    TCPlayer._overlay = document.createElement('div');
    wrap.appendChild(TCPlayer._overlay);

    const video = document.createElement('video');
    video.className = 'tc-player-video';
    video.playsInline = true;
    TCPlayer._nodes.frame.prepend(video);
    TCPlayer._video = video;
    video.addEventListener('playing', () => TCPlayer._clearOverlay());
    video.addEventListener('waiting', () => { if (!TCPlayer._advanced) TCPlayer._screenBuffering(); });
    video.addEventListener('timeupdate', () => TCPlayer._onTimeUpdate());
    video.addEventListener('ended', () => TCPlayer._startNext());

    wrap.addEventListener('mousemove', TCPlayer._wake);
    wrap.addEventListener('click', TCPlayer._wake);
    TCPlayer._wake();

    TCPlayer._render({});
    TCPlayer._live();
    TCPlayer._pollState();
    TCPlayer._reportPosition();
  },

  //: Идёт ли ещё этот сеанс: ушли с ``/play`` - все свои циклы это видят и останавливаются.
  _mounted() {
    return location.pathname === '/play' && !!TCPlayer._nodes && document.body.contains(TCPlayer._nodes.frame);
  },

  _sleep(ms) {
    return new Promise((resolve) => { setTimeout(resolve, ms); });
  },

  //: Ящик пуст, пока показ не готов (§7.3): опрашиваем его, как и card.js опрашивает
  //: частичную карточку, тем же самым приёмом - без сокета, без push.
  async _live() {
    TCPlayer._screenPreparing();
    while (TCPlayer._mounted() && !TCPlayer._url) {
      if (await TCPlayerBox.rebox(TCPlayer)) break;
      await TCPlayer._sleep(1000);
    }
  },

  async _pollState() {
    while (TCPlayer._mounted()) {
      const state = await TCApi.state();
      if (state) {
        TCPlayer._hasNext = !!state.has_next;
        TCPlayer._last = state;
        TCPlayer._render(state);
      }
      await TCPlayer._sleep(TCPlayer.POLL_MS);
    }
  },

  //: Единственная дверь позиции браузера в продукт (§7.2): пока идёт показ, а не то,
  //: что решил читатель, - второго писателя закладки заводить нельзя.
  async _reportPosition() {
    while (TCPlayer._mounted()) {
      const video = TCPlayer._video;
      if (video && TCPlayer._key) {
        const phase = video.ended ? 'ended' : video.paused ? 'paused'
          : video.readyState < 3 ? 'buffering' : 'playing';
        const code = await TCApi.position({
          key: TCPlayer._key, phase, pos: video.currentTime || 0, dur: video.duration || 0,
        });
        //: 409 - ящик уже подменён другим показом, и это единственный сигнал о смене,
        //: который вкладка получает даром (`player-box.js`).
        if (code === 409) await TCPlayerBox.rebox(TCPlayer);
      }
      await TCPlayer._sleep(TCPlayer.POSITION_MS);
    }
  },

  _onTimeUpdate() {
    TCPlayer._render(TCPlayer._last || {});
    const video = TCPlayer._video;
    if (!TCPlayer._advanced && video.duration > 0 && video.duration - video.currentTime <= 1) {
      TCPlayer._startNext();
    }
  },

  //: Автопереход (§4.5): плашка с отсчётом у сериалов, прямой возврат в карточку у
  //: фильмов - там переходить некуда, ``has_next`` это и называет.
  _startNext() {
    if (TCPlayer._advanced) return;
    TCPlayer._advanced = true;
    if (!TCPlayer._hasNext) {
      history.back();
      return;
    }
    TCPlayer._overlay.replaceChildren();
    TCPlayerNext.mount(
      TCPlayer._overlay,
      () => TCApi.next(),
      () => TCPlayer._clearOverlay(),
    );
  },
  // ------------------------------------------------------------------ hls.js

  //: Поток - ОДНА полоса упаковки на всю машину (замер 06-09-2026): тут ровно один
  //: ``Hls``, старый уничтожается ДО создания нового, второго читателя не заводим.
  _attach(url, at) {
    if (TCPlayer._hls) {
      TCPlayer._hls.destroy();
      TCPlayer._hls = null;
    }
    const video = TCPlayer._video;
    const onReady = () => { video.currentTime = at || 0; video.play().catch(() => {}); };
    if (TCPlayer.ready()) {
      // Секунду показа знает hls.js, а не `<video>`: первый кусок он просит ДО того, как
      // `onReady` тронет `currentTime`, и с закладки уходит за `v0.m4s`, уводя головку
      // единственной полосы упаковки в начало (стенд `.104`: 95 с, ноль байт картинки).
      const hls = new Hls({ startPosition: at > 0 ? at : -1 });
      TCPlayer._hls = hls;
      hls.on(Hls.Events.MANIFEST_PARSED, onReady);
      hls.on(Hls.Events.ERROR, (event, data) => { if (data.fatal) TCPlayer._onStreamError(); });
      hls.loadSource(url);
      hls.attachMedia(video);
    } else {
      video.src = url;
      video.addEventListener('loadedmetadata', onReady, { once: true });
      video.addEventListener('error', () => TCPlayer._onStreamError(), { once: true });
    }
  },

  //: После трёх неудач - экран ошибки с «Повторить» (§4.5); до тех пор - тихий перезапуск.
  _onStreamError() {
    TCPlayer._retries += 1;
    if (TCPlayer._retries > TCPlayer.MAX_RETRIES) {
      TCPlayer._screenLost(TCPlayer._retries);
      return;
    }
    window.setTimeout(() => TCPlayer._attach(TCPlayer._url, TCPlayer._video.currentTime || 0), 1000);
  },

  _retry() {
    TCPlayer._retries = 0;
    TCPlayer._screenBuffering();
    TCPlayer._attach(TCPlayer._url, TCPlayer._video.currentTime || 0);
  },
  // ------------------------------------------------------------------ снимок на панели

  //: Не на ТВ - правда у самого ``<video>`` (§5): позиция и «докуда упаковано» из
  //: буфера hls.js. На ТВ - из ``/api/state``, потому что местная плёнка ничего не знает
  //: про телевизор (решение 4: звук снят, но кадр идёт для перемотки без разрыва).
  _render(state) {
    if (!TCPlayer._nodes) return;
    const video = TCPlayer._video;
    const onTv = TCPlayer._onTv;
    const title = state.shown_as || state.title || '';
    const episode = state.season && state.episode ? `s${state.season}e${state.episode}` : '';
    let pos = 0, dur = 0, paused = true, volume = 1, packagedPct = null;
    if (onTv) {
      pos = state.position || 0;
      dur = state.duration || 0;
      paused = state.state === 'paused';
      volume = typeof state.volume === 'number' ? state.volume : 0;
      packagedPct = typeof state.warm === 'number' ? state.warm : null;
      if (video && Math.abs((video.currentTime || 0) - pos) > TCPlayer.DRIFT_S) video.currentTime = pos;
    } else if (video) {
      pos = video.currentTime || 0;
      dur = video.duration || 0;
      paused = video.paused;
      volume = video.volume;
      packagedPct = TCPlayer._packagedPct(video, dur);
    }
    TCPlayerPanel.update(TCPlayer._nodes, {
      title, episode, pos, dur, paused, volume, packagedPct, hasNext: TCPlayer._hasNext, onTv,
    });
  },

  _packagedPct(video, dur) {
    if (!dur) return null;
    const ranges = video.buffered;
    for (let i = 0; i < ranges.length; i += 1) {
      if (ranges.start(i) <= video.currentTime && video.currentTime <= ranges.end(i)) {
        return Math.min(100, (100 * ranges.end(i)) / dur);
      }
    }
    return null;
  },
  // ------------------------------------------------------------------ экраны

  //: Три состояния оверлея рисует `player-screens.js` - тут только зовём его нужным
  //: экраном, разметка и текст лежат там.
  _clearOverlay() {
    TCPlayerScreens.clear(TCPlayer._overlay);
  },

  _screenPreparing() {
    TCPlayerScreens.preparing(TCPlayer._overlay);
  },

  _screenBuffering() {
    TCPlayerScreens.buffering(TCPlayer._overlay);
  },

  _screenLost(code) {
    TCPlayerScreens.lost(TCPlayer._overlay, code, TCPlayer._retry);
  },

  // ------------------------------------------------------------------ фокус и клавиши

  _wake() {
    if (!TCPlayer._nodes) return;
    TCPlayer._nodes.frame.classList.remove('is-idle');
    clearTimeout(TCPlayer._idleTimer);
    TCPlayer._idleTimer = setTimeout(() => {
      if (TCPlayer._nodes) TCPlayer._nodes.frame.classList.add('is-idle');
    }, TCPlayer.IDLE_MS);
  },

  _volumeBy(delta) {
    if (TCPlayer._onTv) {
      const current = TCPlayer._last && typeof TCPlayer._last.volume === 'number' ? TCPlayer._last.volume : 0;
      TCApi.control('volume', Math.min(1, Math.max(0, current + delta)));
    } else if (TCPlayer._video) {
      TCPlayer._video.volume = Math.min(1, Math.max(0, TCPlayer._video.volume + delta));
    }
  },

  // ------------------------------------------------------------------ нажатия панели

  //: Пока «на ТВ» - пульт зовёт мост (``control``), сама плёнка страницы идёт без
  //: звука и только подстраивается (§4.5); иначе управляет местный ``<video>`` сам.
  _makeHandlers() {
    return {
      onToggle() {
        if (TCPlayer._onTv) { TCApi.control('toggle'); return; }
        const video = TCPlayer._video;
        if (video.paused) video.play().catch(() => {}); else video.pause();
      },
      onSeekBy(delta) {
        if (TCPlayer._onTv) { TCApi.control('seekby', delta); return; }
        TCPlayer._video.currentTime = Math.max(0, (TCPlayer._video.currentTime || 0) + delta);
      },
      onSeekTo(frac) {
        if (TCPlayer._onTv) {
          const dur = (TCPlayer._last && TCPlayer._last.duration) || 0;
          const pos = (TCPlayer._last && TCPlayer._last.position) || 0;
          if (dur > 0) TCApi.control('seekby', frac * dur - pos);
          return;
        }
        const dur = TCPlayer._video.duration || 0;
        if (dur > 0) TCPlayer._video.currentTime = frac * dur;
      },
      onNext() { TCApi.next(); },
      onToggleTv() {
        if (TCPlayer._onTv) {
          TCApi.toWeb().then(() => {
            TCPlayer._onTv = false;
            TCPlayer._video.muted = false;
            if (TCPlayer._last) TCPlayer._video.currentTime = TCPlayer._last.position || 0;
          });
        } else {
          // 🔴 Звук на компе снимается ПО НАЖАТИЮ, а не по ответу продукта: между ними
          // рукопожатие с приёмником и загрузка потока - секунды, а не миллисекунды, и
          // всё это время вкладка гремела на всю комнату (замер на стенде `.104`
          // 07-09-2026, пункт 9: через 2 с после «На ТВ» `video.muted` был `false`).
          // Решение 4 владельца требует обратного. Отказ каста возвращает звук назад.
          TCPlayer._video.muted = true;
          TCApi.toTv().then((said) => {
            if (!said) {
              TCPlayer._video.muted = false;
              return;
            }
            TCPlayer._onTv = true;
          });
        }
      },
      onFullscreen() {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else TCPlayer._nodes.frame.requestFullscreen().catch(() => {});
      },
      onClose() { history.back(); },
    };
  },
};

//: Стрелки/пробел/F/Esc принадлежат плееру целиком (§4.5), а не D-pad'у (`nav.js`):
//: слушатель ставится в фазе перехвата, чтобы `stopImmediatePropagation` погасил
//: геометрический D-pad раньше, чем тот переставит фокус по тем же стрелкам.
document.addEventListener('keydown', (event) => {
  if (location.pathname !== '/play' || !TCPlayer._video || !TCPlayer._handlers) return;
  const handlers = TCPlayer._handlers;
  if (event.key === ' ' || event.key === 'Spacebar' || event.key === 'Enter') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onToggle();
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onSeekBy(-10);
  } else if (event.key === 'ArrowRight') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onSeekBy(10);
  } else if (event.key === 'ArrowUp') {
    event.preventDefault(); event.stopImmediatePropagation();
    TCPlayer._volumeBy(0.05);
  } else if (event.key === 'ArrowDown') {
    event.preventDefault(); event.stopImmediatePropagation();
    TCPlayer._volumeBy(-0.05);
  } else if (event.key === 'f' || event.key === 'F') {
    handlers.onFullscreen();
  } else if (event.key === 'Escape') {
    handlers.onClose();
  } else {
    return;
  }
  TCPlayer._wake();
}, true);

window.TCPlayer = TCPlayer;
