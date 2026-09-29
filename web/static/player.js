// Экран показа ``/play`` (ТЗ §4.5, §7.1-7.4): состояния подготовки/буферизации/показа/
// потери потока, автопереход между сериями и режим «на ТВ». Разметку строят соседние
// модули (`player-panel.js` - панель, `player-next.js` - плашка автоперехода), тут -
// только состояние сеанса и hls.js. Сеанс на странице ровно один: поля лежат прямо на
// самом ``TCPlayer``, как и у `TCCard` (`_tries`), а не в отдельном классе.
'use strict';

const TCPlayer = {
  MAX_RETRIES: 3,
  POLL_MS: 2000,
  POSITION_MS: 2000,
  ENDED_MS: 250,
  ENDED_WAIT_MS: 30000,
  DRIFT_S: 5,
  TRIM_RATE: 0.75,

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
    TCPlayer._retryTimer = null;
    TCPlayer._retryFrom = 0;
    //: Два разных смысла, разведены после дефекта мержера 17-09-2026: `_counting` -
    //: плашка отсчёта на экране, оверлей и ящик трогать нельзя; `_ending` - переход
    //: уже запущен (кадром счётчика или без него), второй раз `_startNext` не заводить.
    //: Слиты в одном поле - «Отмена» оставляла оба навеки true (`_cancelNext`).
    TCPlayer._counting = false;
    TCPlayer._ending = false;
    TCPlayer._hasNext = false;
    TCPlayer._awaitNext = false;
    TCPlayer._last = null;
    TCPlayer._tvMark = null;
    TCPlayer._leftSent = false;
    TCPlayer._halted = false;
    TCPlayer._framed = false;
    TCPlayer._ordered = false;
    TCPlayer._seeking = false;
    TCPlayer._seekTimer = null;
    TCPlayer._pendingBox = null;
    TCPlayer._nextStop = null;

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
    TCPlayer._hlsLoad();
    video.addEventListener('playing', () => {
      TCPlayer._framed = true;
      TCPlayer._ordered = false;
      // Заминка-и-возобновление ПОСРЕДИ отсчёта не должна стирать плашку из DOM
      // (`_clearOverlay` - это `overlay.replaceChildren()`): таймер `player-next.js`
      // всё равно досчитает и заведёт переход, но теперь от невидимой карточки
      // (мержер 17-09-2026, `player.js:60-65`). Охрана та же, что у `waiting` ниже.
      if (!TCPlayer._counting) TCPlayer._clearOverlay();
      TCPlayer._sendPosition();
    });
    // Отказ подъёма - последнее слово: заминка мёртвого потока его не перебивает.
    video.addEventListener('waiting', () => {
      if (!TCPlayer._counting && !TCPlayer._overlay.querySelector('.tc-refused')) TCPlayer._screenBuffering();
    });
    video.addEventListener('timeupdate', () => TCPlayer._onTimeUpdate());
    video.addEventListener('ended', () => {
      TCPlayer._startNext();
      TCPlayer._nextOnEnd();
      TCPlayer._reportEnded();
    });
    // hls.js recovers most short gaps itself, but a broken MediaSource can finish as the
    // native `error` event only. Without this listener Chromium pauses a healthy-looking
    // video (`readyState === 4`) forever after the error, with no fatal HLS event to wake
    // `_onStreamError` (живой Chromium, Gladiator at 2:09).
    video.addEventListener('error', () => TCPlayer._onStreamError());

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
    const began = Date.now();
    while (TCPlayer._mounted() && !TCPlayer._url) {
      if (await TCPlayerBox.rebox(TCPlayer)) break;
      await TCPlayer._sleep(TCPlayerBox.pace(Date.now() - began));
    }
  },

  async _pollState() {
    while (TCPlayer._mounted()) {
      const state = await TCApi.state();
      if (state) {
        TCPlayer._hasNext = state.has_next === true;
        TCPlayer._awaitNext = state.has_next === null && state.state !== 'idle';
        const refused = !state.start && (state.refusal || state.last_error);
        //: Серия кончилась, а юнит погас, не дав нового ящика: следующей не будет, что бы
        //: ни обещала плашка. `has_next === true` - это дата каталога или номер того же
        //: сезона, а не найденная раздача; поиск юнита мог прийти пустым, и без этого ухода
        //: вкладка стояла на «буферизации» навеки. Только после конца серии: на подъёме
        //: `has_next` тоже `null`, и погасший юнит там значит отказ, а не конец сериала.
        //: Отказ поднять следующую серию - тот же экран отказа, что у первого подъёма.
        if (TCPlayer._ending && !TCPlayer._pendingBox && state.state === 'idle') {
          if (refused) TCPlayer._screenRefused(state.refusal);
          else TCPlayer._leave();
        }
        TCPlayer._last = state;
        TCPlayer._render(state);
        //: Пока ящика нет, эти же ответы двигают экран подготовки: раз в две секунды
        //: срок уменьшается, а полоса идёт по значению. Другого источника числа у
        //: страницы нет и быть не должно. Подъём кончился отказом - экран говорит это
        //: словами, а не ждёт дальше: «уже не поднимется» - это пустой ``start`` при
        //: названном отказе (``last_error`` кладёт мост, слово-причину ``refusal`` -
        //: юнит, :mod:`torrcast.domain.start_refusal`). Слова нет - строка остаётся
        //: короткой, без выдуманного хвоста.
        //: Ящик уже есть, а кадра нет: экран подготовки остаётся экраном подъёма и
        //: переписывается теми же ответами, пока подъём идёт (``_screenBuffering``).
        //: Подъём кончился - один раз на буферизацию или на отказ, если показ умер.
        if (!TCPlayer._url) {
          if (refused) TCPlayer._screenRefused(state.refusal);
          else TCPlayer._screenPreparing(state);
        } else if (!TCPlayer._framed && !TCPlayer._counting
          && TCPlayer._overlay.querySelector('.tc-preparing')) {
          if (refused) TCPlayer._screenRefused(state.refusal);
          else TCPlayer._screenBuffering();
        }
      }
      await TCPlayer._sleep(TCPlayer.POLL_MS);
    }
  },

  //: Единственная дверь позиции браузера в продукт (§7.2): пока идёт показ, а не то,
  //: что решил читатель, - второго писателя закладки заводить нельзя.
  async _reportPosition() {
    while (TCPlayer._mounted()) {
      await TCPlayer._sendPosition();
      await TCPlayer._sleep(TCPlayer.POSITION_MS);
    }
    // Ушли с ``/play`` изнутри приложения (не закрытие вкладки - на него отвечает
    // `pagehide` ниже): цикл это увидел первым, и сказать «ухожу» тут естественно.
    TCPlayer._callOff();
    TCPlayer._left();
  },

  //: Конец серии не ждёт очереди отчёта в две секунды: пока вкладка молчит, показ не
  //: знает, что кадр кончился, и следующая серия не заводится. Шлём чаще, пока не придёт
  //: 409 нового ящика, - сигнал о смене остаётся тем же (`player-box.js`).
  async _reportEnded() {
    const key = TCPlayer._key;
    for (let left = TCPlayer.ENDED_WAIT_MS; left > 0 && TCPlayer._mounted() && TCPlayer._key === key
      && !TCPlayer._pendingBox && TCPlayer._video && TCPlayer._video.ended; left -= TCPlayer.ENDED_MS) {
      await TCPlayer._sendPosition();
      await TCPlayer._sleep(TCPlayer.ENDED_MS);
    }
  },

  //: Первый кадр не ждёт очереди отчёта в две секунды: человек может уйти со страницы
  // сразу после него, и оставленный вместо этой позиции ``left`` сервер читает как
  // ожидание, а не как доказанный показ (`browser_receiver.py`).
  async _sendPosition() {
    const video = TCPlayer._video;
    if (!video || !TCPlayer._key) return;
    const phase = video.ended ? 'ended' : video.paused ? 'paused'
      : video.readyState < 3 ? 'buffering' : 'playing';
    const code = await TCApi.position({
      key: TCPlayer._key, phase, pos: video.currentTime || 0, dur: video.duration || 0,
    });
    //: 409 - ящик уже подменён другим показом, и это единственный сигнал о смене,
    //: который вкладка получает даром (`player-box.js`).
    if (code === 409) await TCPlayerBox.rebox(TCPlayer);
  },

  //: Сказать «ухожу» ровно один раз (TC-1124): страницу закрыли или увели с ``/play``,
  //: и ждать все секунды молчания (:attr:`torrcast.adapters.browser.browser_receiver.
  //: BrowserReceiver.gone_after`) незачем - сама страница знает об уходе раньше таймера.
  //: Обновление (``F5``) шлёт то же слово, но тут же переприцепляется свежим отчётом -
  //: решает это срок на стороне продукта, не эта строка (`browser_receiver.py`).
  _left() {
    if (!TCPlayer._key || TCPlayer._leftSent) return;
    TCPlayer._leftSent = true;
    const video = TCPlayer._video;
    TCApi.left({
      key: TCPlayer._key,
      phase: 'left',
      pos: (video && video.currentTime) || 0,
      dur: (video && video.duration) || 0,
    });
  },

  _onTimeUpdate() {
    TCPlayer._render(TCPlayer._last || {});
    const video = TCPlayer._video;
    // Three failures across a whole film are not a dead stream: half a minute of real
    // playback after a retry gives the attempts back.
    if (TCPlayer._retries && video.currentTime - TCPlayer._retryFrom > 30) TCPlayer._retries = 0;
    // Порог должен совпадать с тем, что обещает плашка (`TCPlayerNext.SECONDS`, 10 с),
    // а не с прошлой зашитой 1 с (замер на двух живых приёмниках 17-09-2026: плашка врала «10» при
    // 0.74 с до конца). 🔴 Без `_hasNext` карточки нет вовсе - фильм и финал сезона
    // уходят на старой 1 с: дефект мержера 17-09-2026 ставил общий 10-секундный порог
    // на оба пути, и вкладка уезжала за 10 с до титров.
    const lead = TCPlayer._hasNext ? TCPlayerNext.SECONDS : 1;
    if (!TCPlayer._ending && video.duration > 0 && video.duration - video.currentTime <= lead) {
      TCPlayer._startNext();
    }
  },

  //: Автопереход (§4.5): плашка с отсчётом у сериалов, прямой возврат в карточку у
  //: фильмов - там переходить некуда, ``has_next`` это и называет.
  _startNext() {
    if (TCPlayer._ending) return;
    TCPlayer._ending = true;
    if (!TCPlayer._hasNext) {
      if (TCPlayer._awaitNext) {
        TCPlayer._screenBuffering();
        return;
      }
      TCPlayer._leave();
      return;
    }
    TCPlayer._counting = true;
    TCPlayer._overlay.replaceChildren();
    TCPlayer._nextStop = TCPlayerNext.mount(
      TCPlayer._overlay,
      () => TCPlayer._playNext(),
      () => TCPlayer._cancelNext(),
    );
  },

  //: «Отмена» снимает МЕСТНЫЙ автопереход, не сам показ: сторож юнита досмотрит
  //: серию сам, и ящик рано или поздно сменится под ЭТИМ же ключом. Не сбрось тут
  //: `_pendingBox` - вкладка виснет на замёрзшем кадре навеки: `rebox()` копит новые
  //: ящики в `_pendingBox`, не применяя их, пока `_counting` не снят (мержер
  //: 17-09-2026, `player-box.js:68`, было воспроизведено на двух живых приёмниках).
  //:
  //: 🔴 `_ending` тут держим true, а НЕ снимаем: плашка встаёт на пороге
  //: `TCPlayerNext.SECONDS` (10 с) до конца, а не на 1 с - старое видео после
  //: «Отмена» ещё играет все эти секунды, и `timeupdate` идёт по нему ~4 раза в
  //: секунду. Снятый тут `_ending` открывал `_onTimeUpdate()`/`ended` тем же
  //: условием заново - плашка возвращалась на «10» через четверть секунды после
  //: своей же «Отмена» (найдено ревью мержера 17-09-2026, до выката не дошло).
  //: Снимает флаг только `TCPlayerBox.apply()`, когда ящик правда сменится.
  _cancelNext() {
    TCPlayer._counting = false;
    TCPlayer._pendingBox = null;
    TCPlayer._clearOverlay();
  },

  //: Серия, которая играет в эту секунду, поимённо - тело ``POST /api/next`` у кнопки
  //: ``web.player.next_episode`` панели (`onNext`): человек просит перескочить СЕЙЧАС, и сервер
  //: должен знать, с какой серии. Автопереход на конце серии его не зовёт - продолжение
  //: ищет живой юнит (`_playNext`). Снимок серию ещё не назвал (фильм, первые секунды) -
  //: пустой зов, старое поведение без имени.
  _endedMark() {
    const state = TCPlayer._last || {};
    return state.season && state.episode ? { season: state.season, episode: state.episode } : {};
  },

  //: Кадр кончился, а ящик следующей серии уже найден: досчитывать плашку не над чем,
  //: зритель смотрит на стоп-кадр. Лента бывает короче счёта (замер стыка: `ended` на
  //: 8.1 с из 10, ящик через 0.5 с после него, а кадр новой серии только по нулю счёта,
  //: ещё через 1.3 с). Пока видео играет, ящик по-прежнему ждёт конца счёта.
  _nextOnEnd() {
    if (!TCPlayer._counting || !TCPlayer._pendingBox) return;
    if (!TCPlayer._video || !TCPlayer._video.ended) return;
    if (TCPlayer._nextStop) TCPlayer._nextStop();
    TCPlayer._nextStop = null;
    TCPlayer._playNext();
  },

  //: Единственная дверь к следующему кадру (счётчик догорел или нажато «Смотреть»,
  //: `player-next.js` зовёт ровно один раз). Пока карточка отсчёта висела, `rebox()`
  //: (`player-box.js`) НЕ трогала оверлей и не подменяла видео - придержала ящик в
  //: `_pendingBox`, чтобы не рвать счёт на середине (замер на двух живых приёмниках 17-09-2026).
  //: Тут этот ящик и открывается: экран «грузится» - та же панель, что у первого кадра
  //: показа, а не голый чёрный `<video>`.
  _playNext() {
    const box = TCPlayer._pendingBox;
    TCPlayer._pendingBox = null;
    TCPlayer._counting = false;
    if (box) {
      // Новый ящик несёт свою длительность - `_ending` снимает `TCPlayerBox.apply()`
      // (`player-box.js:83`), уже ПОСЛЕ того, как видео перецепилось на него. Тут его
      // не трогаем: снять его раньше значило бы пустить `_onTimeUpdate` по ЕЩЁ старому
      // видео на долю секунды - тот самый двойной `_startNext` (мержер 17-09-2026).
      TCPlayerBox.apply(TCPlayer, box);
    } else {
      // Ящика ещё нет: старое видео остаётся на экране со своей старой длительностью.
      // `_ending` держим true до тех пор, пока `rebox()` не найдёт и не применит
      // следующий ящик - иначе тот же `timeupdate` на том же хвосте заводит переход
      // второй раз (§`_onTimeUpdate`, порог посчитан по ЕЩЁ прежней длительности).
      TCPlayer._framed = false;
      TCPlayer._screenBuffering();
    }
    // Поиск продолжения делает живой юнит. Вкладка только открывает его ящик: второй
    // поиск здесь соревновался с ним на границе одиночной серии и сезона.
  },
  // ------------------------------------------------------------------ hls.js

  //: Потолок запаса ВКЛАДКИ, когда ящик своего не назвал. Числа те же, что у умолчаний
  //: hls.js: без них страница молча держала тридцать секунд, сколько бы ни было готово
  //: на раздаче, и запас у зрителя не рос никогда (замер: 300 с готовой упаковки - 34 с
  //: у вкладки). Настраивается ключами ``hls_tab_buffer`` и ``hls_tab_bytes``.
  TAB_SECONDS: 30,
  TAB_BYTES: 60 * 1000 * 1000,

  //: hls.js (414 КБ, 40 мс разбора) не стоит в `index.html`: там он держал первый кадр
  //: любой страницы, а нужен только показу. Грузится с `mount` и ждётся в `_attach`.
  //: Не загрузился - второй попытки нет, `_attach` уходит в родной `<video>`.
  //: Файл не тянется только там, где hls.js сам не нашёл бы источника: его выбор -
  //: `ManagedMediaSource || MediaSource || WebKitMediaSource` (у iPhone с iOS 17.1 есть
  //: лишь первый, и без hls.js пропадают `startPosition` закладки и потолок запаса вкладки).
  _hlsLoad() {
    const source = window.ManagedMediaSource || window.MediaSource || window.WebKitMediaSource;
    if (TCPlayer.ready() || TCPlayer._hlsTried || !source) return null;
    if (!TCPlayer._hlsWait) {
      TCPlayer._hlsWait = new Promise((done) => {
        const tag = document.createElement('script');
        const over = () => { TCPlayer._hlsTried = true; done(); };
        tag.src = '/static/hls-1.5.17.min.js';
        tag.addEventListener('load', over);
        tag.addEventListener('error', over);
        document.head.appendChild(tag);
      });
    }
    return TCPlayer._hlsWait;
  },

  //: Поток - ОДНА полоса упаковки на всю машину (замер 06-09-2026): тут ровно один
  //: ``Hls``, старый уничтожается ДО создания нового, второго читателя не заводим.
  _attach(url, at) {
    const video = TCPlayer._video;
    const loading = TCPlayer._hlsLoad();
    if (loading) {
      // Второй `_attach` за время загрузки заменяет первый: встаёт только последний.
      const turn = (TCPlayer._hlsTurn = (TCPlayer._hlsTurn || 0) + 1);
      loading.then(() => {
        if (turn === TCPlayer._hlsTurn && TCPlayer._video === video) TCPlayer._attach(url, at);
      });
      return;
    }
    if (TCPlayer._hls) {
      TCPlayer._hls.destroy();
      TCPlayer._hls = null;
    }
    // У новой ленты первый закодированный пакет вправе начаться на несколько кадров
    // после нуля. Принудительный seek в 0 после разбора манифеста тогда выбрасывает
    // уже взятый hls.js первый пакет и даёт короткий `waiting` на позиции 0.1.
    // Нулевая посадка уже выбрана startPosition, а закладка всё ещё требует точного seek.
    const onReady = () => {
      if (at > 0) video.currentTime = at;
      video.play().catch(() => {});
    };
    if (TCPlayer.ready()) {
      // Секунду показа знает hls.js, а не `<video>`: первый кусок он просит ДО того, как
      // `onReady` тронет `currentTime`, и с закладки уходит за `v0.m4s`, уводя головку
      // единственной полосы упаковки в начало (живой приёмник: 95 с, ноль байт картинки).
      // Первый кусок просится вместе с подключением `<video>`, а не после открытия MSE.
      const tab = TCPlayer._tab || {};
      const seconds = tab.seconds > 0 ? tab.seconds : TCPlayer.TAB_SECONDS;
      const bytes = tab.bytes > 0 ? tab.bytes : TCPlayer.TAB_BYTES;
      const hls = new Hls({
        startPosition: at > 0 ? at : -1, startFragPrefetch: true,
        maxBufferLength: seconds, maxMaxBufferLength: Math.max(seconds, 600),
        maxBufferSize: bytes,
      });
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
    // A fatal hls.js error can also surface as the native event above. One broken source
    // gets one retry: counting both spent two of the three attempts before a new manifest
    // had even had a chance to load.
    if (TCPlayer._retryTimer) return;
    TCPlayer._retries += 1;
    TCPlayer._retryFrom = TCPlayer._video.currentTime || 0;
    if (TCPlayer._retries > TCPlayer.MAX_RETRIES) {
      TCPlayer._screenLost(TCPlayer._retries);
      return;
    }
    TCPlayer._retryTimer = window.setTimeout(() => {
      TCPlayer._retryTimer = null;
      TCPlayer._attach(TCPlayer._url, TCPlayer._video.currentTime || 0);
    }, 1000);
  },

  //: «Повторить» возвращает СЕРИЮ в игру, не только поток: тот же ключ, та же позиция,
  //: она не кончилась. `_ending` держится true с последнего `_startNext()` (снимает его
  //: только `TCPlayerBox.apply()` у НОВОЙ серии) - не снятый тут, он запирает `!_ending`
  //: у `_onTimeUpdate`/`ended` до конца этой же серии: плашки больше не будет, и вкладка
  //: никуда не перейдёт сама, даже доиграв до самого конца (найдено 17-09-2026).
  _retry() {
    TCPlayer._retries = 0;
    TCPlayer._framed = false;
    TCPlayer._ending = false;
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
    // 🔴 «На ТВ» умеет сняться только нажатием «Вернуть на компьютер» - а показ гаснет и
    // без него: «Завершить», «cast stop» с пульта, конец картины. Ящик про это молчит
    // (`web/box.py`), но продукт - нет: ``idle`` не бывает у идущего показа НИГДЕ, и
    // вкладка, доверяющая ``onTv`` дальше этой секунды, стояла бы немой и замороженной
    // перед погасшим телевизором навсегда (живой приёмник 13-09-2026: «Матрица» снята
    // «cast stop», панель так и звала её «На ТВ»).
    if (TCPlayer._onTv && state.state === 'idle') {
      TCPlayer._onTv = false;
      if (video) video.muted = false;
    }
    const onTv = TCPlayer._onTv;
    const title = state.shown_as || state.title || '';
    const episode = state.season && state.episode ? `s${state.season}e${state.episode}` : '';
    let pos = 0, dur = 0, paused = true, volume = 1, packagedPct = null;
    if (onTv) {
      pos = TCPlayer._tvPosition(state);
      dur = state.duration || 0;
      paused = state.state === 'paused';
      volume = typeof state.volume === 'number' ? state.volume : 0;
      packagedPct = typeof state.warm === 'number' ? state.warm : null;
      if (video) TCPlayer._follow(video, pos, state.state === 'playing');
    } else if (video) {
      // Замедление, которым плёнка догоняла телевизор, тут снимается: показ вернулся во
      // вкладку, и догонять больше некого. Пауза не трогается - она теперь зрителя.
      video.playbackRate = 1;
      pos = video.currentTime || 0;
      dur = video.duration || 0;
      paused = video.paused;
      volume = video.volume;
      packagedPct = TCPlayer._packagedPct(video, dur);
    }
    TCPlayerPanel.update(TCPlayer._nodes, {
      title, episode, pos, dur, paused, volume, packagedPct, hasNext: TCPlayer._hasNext, onTv,
      toTv: !!TCPlayer._toTv, hasTv: !!(TCPlayer._last && TCPlayer._last.tv),
    });
  },

  //: Секунда показа на ТВ между докладами приёмника. Приставка докладывает место
  //: рывками раз в ~10 с (замер на живом приёмнике 10-09-2026: шаги 10.0 с ровно), и
  //: тянуть плёнку вкладки к ЗАСТЫВШЕМУ докладу значило отбрасывать её назад каждые
  //: пять секунд - 14 откатов с ребуфером за 150 с каста (TC-1147). Между докладами
  //: идущего показа секунда дооценивается ходом часов; на паузе берётся сам доклад.
  _tvPosition(state) {
    const said = state.position || 0;
    const now = Date.now();
    if (!TCPlayer._tvMark || TCPlayer._tvMark.pos !== said) TCPlayer._tvMark = { pos: said, at: now };
    if (state.state !== 'playing') return said;
    return said + (now - TCPlayer._tvMark.at) / 1000;
  },

  //: Идти следом за телевизором ТЕМПОМ, а не прыжком. Назад плёнку вкладки не тянем
  //: вовсе: пока каст поднимается (рукопожатие, LOAD, первый кадр - на живом приёмнике
  //: 7-12 с), вкладка играет и выходит вперёд ровно на это время, и тяга назад под
  //: первый же доклад и была тем рывком картины, который видит зритель (замер
  //: 10-09-2026: вкладка 19.3 при телевизоре 6.9 и прыжок на 7.3). Обгон снимается
  //: замедлением на четверть: секунда идёт всегда вперёд, и через полминуты плёнки
  //: сходятся сами. Прыжок остаётся один - вперёд, когда вкладка ОТСТАЛА (ребуфер):
  //: догонять темпом отставание нечем, скорость выше единицы гонит новый ребуфер.
  //: Пауза телевизора останавливает и вкладку, иначе она уедет вперёд на всё её время.
  _follow(video, pos, playing) {
    if (!playing) {
      video.pause();
      return;
    }
    const diff = (video.currentTime || 0) - pos;
    // TC-1218. Назад плёнку не тянем НАРОЧНО (комментарий выше, TC-1147) - но это писалось
    // про секунды хода, которые плёнка сама набежала во время рукопожатия каста. Перемотка
    // НАЗАД панелью через ``onTv`` - та же самая просьба, отправленная приёмнику этим же
    // нажатием (`_makeHandlers.onSeekBy`/`onSeekTo`).
    //
    // 🔴 Первый заход сверял ``diff`` (плёнка минус ``pos``) - и снимал флаг НА ПЕРВОМ ЖЕ
    // кадре после нажатия: доклад приёмника ещё не пришёл, ``pos`` всё ещё старое место,
    // плёнка стоит рядом с ним, разница около нуля - «доехали» читается раньше, чем доклад
    // вообще пришёл. Замер на живом приёмнике 12-09-2026: `_seeking` гас уже на чтении +1.2 с
    // после нажатия (`seek2-run.log`), хотя сам доклад назвал новое место лишь на +4.4 с.
    // Сверять поэтому надо не плёнку с ``pos``, а САМ ``pos`` с целью нажатия
    // (:attr:`_seekTarget`, ставится тем же нажатием) - только доклад о нужном месте
    // считается приездом, а не случайная близость к тому, что ``pos`` показывал ДО ответа.
    if (TCPlayer._seeking) {
      video.currentTime = pos;
      if (Math.abs(pos - TCPlayer._seekTarget) <= TCPlayer.DRIFT_S) TCPlayer._clearSeeking();
    } else if (diff < -TCPlayer.DRIFT_S) {
      video.currentTime = pos;
    }
    video.playbackRate = diff > TCPlayer.DRIFT_S ? TCPlayer.TRIM_RATE : 1;
    if (video.paused) video.play().catch(() => {});
  },

  //: Нажатие панели попросило приёмник и ждёт его доклада (:meth:`_follow`); ``target`` -
  //: абсолютная секунда, куда целились (:meth:`_makeHandlers.onSeekBy`/`onSeekTo`). Срок -
  //: на случай, если доклад так и не подтвердит место (плёнка тогда просто ждёт следующего
  //: обгона, как раньше, а не висит помеченной вечно).
  _markSeeking(target) {
    TCPlayer._seeking = true;
    TCPlayer._seekTarget = target;
    if (TCPlayer._seekTimer) clearTimeout(TCPlayer._seekTimer);
    TCPlayer._seekTimer = setTimeout(TCPlayer._clearSeeking, 15000);
  },

  _clearSeeking() {
    TCPlayer._seeking = false;
    if (TCPlayer._seekTimer) clearTimeout(TCPlayer._seekTimer);
    TCPlayer._seekTimer = null;
  },

  //: Перемотка ТВ панелью. Подтяжку (:meth:`_markSeeking`) взводит только взятая команда:
  //: на отказе пульта (``no_remote``) или обрыве сети ТВ никуда не поедет, и тянуть
  //: вкладку к цели, которой доклад не назовёт, значит дёргать её 15 с впустую.
  _seekTv(delta, target) {
    TCApi.control('seekby', delta).then((said) => {
      TCPlayer._noteIfRefused(said);
      if (said && said.ok) TCPlayer._markSeeking(target);
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
    TCPlayer._halt(false);
    TCPlayerScreens.clear(TCPlayer._overlay);
  },

  //: Срок и источник экран берёт из последнего ответа продукта, а не считает сам:
  //: поле ``start`` кладёт туда :mod:`torrcast.usecases.start_progress`.
  _screenPreparing(state) {
    TCPlayer._halt(true);
    TCPlayerScreens.preparing(
      TCPlayer._overlay, (state || TCPlayer._last || {}).start, TCPlayer._leave,
    );
  },

  _screenRefused(reason) {
    TCPlayer._halt(true);
    TCPlayerScreens.refused(TCPlayer._overlay, reason, TCPlayer._leave);
  },

  //: До первого кадра (свежий ящик, «Повторить») панели делать нечего: перематывать и
  //: слать на ТВ ещё нечего, и её кнопки были мёртвыми (прод 11-09: «куча кнопок, которые
  //: не работают»). Тогда она прячется, как у подготовки, а выход - «Назад» экрана.
  //:
  //: До первого кадра, пока продукт ещё поднимает показ (``start`` в ``/api/state``),
  //: вместо буферизации стоит экран подготовки: он называет фазу подъёма, в том числе
  //: «жду плеер», когда упаковка уже готова и ждут саму вкладку. «Буферизация» до кадра
  //: говорила о сети, которой тут ещё нечего отдавать, и замораживала экран подготовки.
  _screenBuffering() {
    if (!TCPlayer._framed && TCPlayer._last && TCPlayer._last.start) {
      TCPlayer._screenPreparing();
      return;
    }
    const bare = !TCPlayer._framed;
    TCPlayer._halt(bare);
    TCPlayerScreens.buffering(TCPlayer._overlay, bare ? TCPlayer._leave : null);
  },

  _screenLost(code) {
    TCPlayer._halt(true);
    TCPlayerScreens.lost(TCPlayer._overlay, code, TCPlayer._retry, TCPlayer._leave);
  },

  //: Плёнки нет (подготовка, отказ, потеря потока) - панель прячется целиком: экран
  //: лежал поверх неё, и её кнопки были видны, но не нажимались ни одна (живой приёмник,
  //: 11-09-2026: шесть кнопок отказа, каждая «не нажимается»). Выход - кнопка экрана.
  //:
  //: 🔴 Все пять экранов зовут этот метод первым делом, до подмены оверлея - ровно та
  //: точка, где живая плашка отсчёта (`_startNext`) обязана быть остановлена, если её
  //: снимают не своей же дверью (`_playNext`/`_cancelNext`): экран потери потока и
  //: перезапуск подменяли оверлей мимо них, а `setInterval` плашки (`player-next.js`)
  //: продолжал невидимо тикать и сам заводил переход через свои секунды - зритель
  //: смотрел на «поток потерян» и уезжал на следующую серию без своего участия (дефект
  //: мержера 17-09-2026, окно выросло с 1 с до 10 с вместе с поднятым порогом).
  //: `stop()` (возврат `TCPlayerNext.mount`) идемпотентен - двойной зов не вредит.
  _halt(on) {
    if (TCPlayer._nextStop) {
      TCPlayer._nextStop();
      TCPlayer._nextStop = null;
      TCPlayer._counting = false;
    }
    TCPlayer._halted = on;
    if (TCPlayer._nodes) TCPlayer._nodes.frame.classList.toggle('is-halted', on);
  },

  //: Уйти с показа туда, откуда пришли. Вкладка, открытая прямо на ``/play``, своего
  //: «назад» не имеет (``history.state`` пуст - его кладёт только ``TCRouter.go``), и
  //: шаг назад увёл бы на чужой сайт из истории вкладки: тогда - главная.
  _leave() {
    TCPlayer._callOff();
    if (history.state !== null && history.length > 1) history.back();
    else TCRouter.go('/');
  },

  //: Уход до первого кадра снимает подъём, который заказала ЭТА вкладка (до ящика метка
  //: `TCPlayerBox.STALE`, после - `_ordered`): иначе показ поднимался для никого (замер
  //: на живом приёмнике 11-09: после «Назад» 60 с `starting`). `pagehide` не снимает: `F5` - не уход.
  //:
  //: Показ, который идёт ВО ВКЛАДКЕ, уход с `/play` теперь кончает целиком: играть его
  //: дальше некому, и показ, переживший вкладку, светил зрителю на прежнем экране
  //: состоянием приёмника - «CONNECT»/«FINISH» на карточке держались 9.3 с после выхода
  //: (замер на стенде 20-09-2026), пока его не закрывал срок молчания
  //: (:data:`torrcast.adapters.browser.browser_receiver.LEFT_AFTER`). На ТВ так нельзя:
  //: там показ идёт без вкладки, и «Назад» в браузере его не касается.
  _callOff() {
    if (TCPlayer._ordered) {
      TCPlayer._ordered = false;
      TCApi.control('stop');
      return;
    }
    // Задание снимается с вкладки тут же: `_callOff` зовут ДВОЕ - `_leave` перед уходом и
    // цикл отчёта, увидевший уход следом, - и вторым «stop» можно снять уже чужой показ.
    if (TCPlayer._url && !TCPlayer._onTv) {
      TCPlayer._url = '';
      TCApi.control('stop');
      return;
    }
    if (TCPlayer._url || sessionStorage.getItem(TCPlayerBox.STALE) === null) return;
    const preparing = !!(TCPlayer._overlay && TCPlayer._overlay.querySelector('.tc-preparing'));
    TCPlayerBox.dropStale();
    if (preparing) TCApi.control('stop');
  },

  // ------------------------------------------------------------------ фокус и клавиши

  _volumeBy(delta) {
    if (TCPlayer._onTv) {
      const current = TCPlayer._last && typeof TCPlayer._last.volume === 'number' ? TCPlayer._last.volume : 0;
      TCApi.control('volume', Math.min(1, Math.max(0, current + delta)));
    } else if (TCPlayer._video) {
      TCPlayer._video.volume = Math.min(1, Math.max(0, TCPlayer._video.volume + delta));
    }
  },

  // 🔴 TC-1210. Показ во вкладке пульту не по силам - сервер отвечает словом отказа
  // (``no_remote``), а не молчанием, и нажатие не вправе остаться немым.
  _noteIfRefused(said) {
    if (said && !said.ok && said.error === 'no_remote' && TCPlayer._nodes) {
      TCPlayerPanel.flashRefused(TCPlayer._nodes);
    }
  },

  // ------------------------------------------------------------------ нажатия панели

  //: Пока «на ТВ» - пульт зовёт мост (``control``), сама плёнка страницы идёт без
  //: звука и только подстраивается (§4.5); иначе управляет местный ``<video>`` сам.
  _makeHandlers() {
    return {
      onToggle() {
        if (TCPlayer._onTv) { TCApi.control('toggle').then(TCPlayer._noteIfRefused); return; }
        const video = TCPlayer._video;
        if (video.paused) video.play().catch(() => {}); else video.pause();
      },
      onSeekBy(delta) {
        if (TCPlayer._onTv) {
          const pos = TCPlayer._last ? TCPlayer._tvPosition(TCPlayer._last) : 0;
          TCPlayer._seekTv(delta, Math.max(0, pos + delta));
          return;
        }
        TCPlayer._video.currentTime = Math.max(0, (TCPlayer._video.currentTime || 0) + delta);
      },
      onSeekTo(frac) {
        if (TCPlayer._onTv) {
          const dur = (TCPlayer._last && TCPlayer._last.duration) || 0;
          const pos = TCPlayer._last ? TCPlayer._tvPosition(TCPlayer._last) : 0;
          if (dur > 0) {
            const target = frac * dur;
            TCPlayer._seekTv(target - pos, target);
          }
          return;
        }
        const dur = TCPlayer._video.duration || 0;
        if (dur > 0) TCPlayer._video.currentTime = frac * dur;
      },
      onNext() { TCApi.next(TCPlayer._endedMark()); },
      onToggleTv() {
        // Переход уже идёт - второе нажатие ничего не ускорит, а вторую передачу
        // приёмнику заказало бы.
        if (TCPlayer._toTv) return;
        if (TCPlayer._onTv) {
          TCApi.toWeb().then(() => {
            TCPlayer._onTv = false;
            TCPlayer._video.muted = false;
            // Последний доклад приёмника может отставать на целую его каденцию. Садим
            // вкладку на ту же доведённую секунду, что показывали на панели; на паузе
            // `_tvPosition` нарочно возвращает сам доклад, не сдвигая остановленный кадр.
            if (TCPlayer._last) TCPlayer._video.currentTime = TCPlayer._tvPosition(TCPlayer._last);
          });
        } else {
          // 🔴 Звук на компе снимается ПО НАЖАТИЮ, а не по ответу продукта: между ними
          // рукопожатие с приёмником и загрузка потока - секунды, а не миллисекунды, и
          // всё это время вкладка гремела на всю комнату (замер на живом приёмнике
          // 07-09-2026, пункт 9: через 2 с после «На ТВ» `video.muted` был `false`).
          // Решение 4 владельца требует обратного. Отказ каста возвращает звук назад.
          TCPlayer._video.muted = true;
          // Между нажатием и картинкой на приёмнике - рукопожатие и подъём показа, то
          // есть секунды. Всё это время кнопка звала «Показать на ТВ» так же, как до
          // нажатия, и человеку оставалось гадать, услышали его или нет.
          TCPlayer._toTv = true;
          TCPlayer._render(TCPlayer._last || {});
          TCApi.toTv().then((said) => {
            TCPlayer._toTv = false;
            if (!said) {
              TCPlayer._video.muted = false;
              TCPlayer._render(TCPlayer._last || {});
              return;
            }
            TCPlayer._onTv = true;
          });
        }
      },
      onClose() { TCPlayer._leave(); },
    };
  },
};

//: Стрелки/пробел/Esc принадлежат плееру целиком (§4.5), а не D-pad'у (`nav.js`):
//: слушатель ставится в фазе перехвата, чтобы `stopImmediatePropagation` погасил
//: геометрический D-pad раньше, чем тот переставит фокус по тем же стрелкам.
//: Курсор и панель клавиша уже спрятала - `cursor.js` слышит её на окне раньше
//: всякого перехвата документа (TC-1319), и будить панель тут больше нечему.
document.addEventListener('keydown', (event) => {
  if (location.pathname !== '/play' || !TCPlayer._video || !TCPlayer._handlers) return;
  const handlers = TCPlayer._handlers;
  // Плёнки нет - перематывать и ставить на паузу нечего: стрелки уходят D-pad'у между
  // кнопками экрана («Ещё раз», «Назад»), Enter жмёт ту, что под фокусом. Плеер - Esc.
  if (TCPlayer._halted) {
    if (event.key === 'Escape') handlers.onClose();
    return;
  }
  // Enter на кнопке под фокусом - нажатие ЭТОЙ кнопки: «−60 с» и «На ТВ» с пульта
  // иначе ставили на паузу, и ни одна кнопка панели не делала с клавиши своего.
  const here = document.activeElement;
  if (event.key === 'Enter' && here && here.tagName === 'BUTTON' && here !== TCPlayer._nodes.playpause) {
    return;
  }
  if (event.key === ' ' || event.key === 'Spacebar' || event.key === 'Enter') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onToggle();
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onSeekBy(-60);
  } else if (event.key === 'ArrowRight') {
    event.preventDefault(); event.stopImmediatePropagation();
    handlers.onSeekBy(60);
  } else if (event.key === 'ArrowUp') {
    event.preventDefault(); event.stopImmediatePropagation();
    TCPlayer._volumeBy(0.05);
  } else if (event.key === 'ArrowDown') {
    event.preventDefault(); event.stopImmediatePropagation();
    TCPlayer._volumeBy(-0.05);
  } else if (event.key === 'Escape') {
    handlers.onClose();
  } else {
    return;
  }
}, true);

// Закрытие вкладки, переход на другой сайт и `F5` роняют один и тот же `pagehide`
// (TC-1124), в отличие от ухода с ``/play`` внутри приложения - тот ловит сам цикл
// `_reportPosition`. `fetch` на выгружаемой странице не гарантирован, поэтому «ухожу»
// шлёт `sendBeacon` (`TCApi.left`), а не обычный запрос позиции.
window.addEventListener('pagehide', () => { if (TCPlayer._mounted()) TCPlayer._left(); });

window.TCPlayer = TCPlayer;
