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
    TCPlayer._advanced = false;
    TCPlayer._hasNext = false;
    TCPlayer._last = null;
    TCPlayer._tvMark = null;
    TCPlayer._idleTimer = null;
    TCPlayer._leftSent = false;
    TCPlayer._halted = false;
    TCPlayer._framed = false;
    TCPlayer._ordered = false;
    TCPlayer._seeking = false;
    TCPlayer._seekTimer = null;

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
    video.addEventListener('playing', () => {
      TCPlayer._framed = true;
      TCPlayer._ordered = false;
      TCPlayer._clearOverlay();
    });
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
        //: Пока ящика нет, эти же ответы двигают экран подготовки: раз в две секунды
        //: срок уменьшается, а полоса идёт по значению. Другого источника числа у
        //: страницы нет и быть не должно. Подъём кончился отказом - экран говорит это
        //: словами, а не ждёт дальше: «уже не поднимется» - это пустой ``start`` при
        //: названном отказе (``last_error`` кладёт мост, слово-причину ``refusal`` -
        //: юнит, :mod:`torrcast.domain.start_refusal`). Слова нет - строка остаётся
        //: короткой, без выдуманного хвоста.
        if (!TCPlayer._url) {
          if (!state.start && (state.refusal || state.last_error)) TCPlayer._screenRefused(state.refusal);
          else TCPlayer._screenPreparing(state);
        }
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
    // Ушли с ``/play`` изнутри приложения (не закрытие вкладки - на него отвечает
    // `pagehide` ниже): цикл это увидел первым, и сказать «ухожу» тут естественно.
    TCPlayer._callOff();
    TCPlayer._left();
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
      TCPlayer._leave();
      return;
    }
    // 🔴 Кончившаяся серия называется серверу поимённо и СЕЙЧАС, до отсчёта: за его
    // 10 секунд сторож юнита доигрывает сериал сам, и снимок к ответу уже говорил бы
    // про НОВУЮ серию - её имя вместо кончившейся читалось бы как «перейди дальше»,
    // и показ перепрыгивал серию, уезжая со вкладки на телевизор (замер на стенде
    // `.104` 10-09-2026: s1e2 кончилась, вкладка получила s1e4 на ТВ и чёрный экран).
    const ended = TCPlayer._endedMark();
    TCPlayer._overlay.replaceChildren();
    TCPlayerNext.mount(
      TCPlayer._overlay,
      () => TCApi.next(ended),
      () => TCPlayer._clearOverlay(),
    );
  },

  //: Серия, которая играет в эту секунду, поимённо - тело ``POST /api/next``; снимок её
  //: ещё не назвал (фильм, первые секунды) - пустой зов, старое поведение без имени.
  _endedMark() {
    const state = TCPlayer._last || {};
    return state.season && state.episode ? { season: state.season, episode: state.episode } : {};
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
    TCPlayer._framed = false;
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
      toTv: !!TCPlayer._toTv,
    });
  },

  //: Секунда показа на ТВ между докладами приёмника. Приставка докладывает место
  //: рывками раз в ~10 с (замер на стенде `.104` 10-09-2026: шаги 10.0 с ровно), и
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
  //: вовсе: пока каст поднимается (рукопожатие, LOAD, первый кадр - на стенде `.104`
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
    // вообще пришёл. Замер на стенде `.104` 12-09-2026: `_seeking` гас уже на чтении +1.2 с
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
  _screenBuffering() {
    const bare = !TCPlayer._framed;
    TCPlayer._halt(bare);
    TCPlayerScreens.buffering(TCPlayer._overlay, bare ? TCPlayer._leave : null);
  },

  _screenLost(code) {
    TCPlayer._halt(true);
    TCPlayerScreens.lost(TCPlayer._overlay, code, TCPlayer._retry, TCPlayer._leave);
  },

  //: Плёнки нет (подготовка, отказ, потеря потока) - панель прячется целиком: экран
  //: лежал поверх неё, и её кнопки были видны, но не нажимались ни одна (стенд `.104`,
  //: 11-09-2026: шесть кнопок отказа, каждая «не нажимается»). Выход - кнопка экрана.
  _halt(on) {
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
  //: `TCPlayerBox.STALE`, после - `_ordered`): иначе показ поднимался для никого (стенд
  //: `.104` 11-09: после «Назад» 60 с `starting`). `pagehide` не снимает: `F5` - не уход.
  _callOff() {
    if (TCPlayer._ordered) {
      TCPlayer._ordered = false;
      TCApi.control('stop');
      return;
    }
    if (TCPlayer._url || sessionStorage.getItem(TCPlayerBox.STALE) === null) return;
    const preparing = !!(TCPlayer._overlay && TCPlayer._overlay.querySelector('.tc-preparing'));
    TCPlayerBox.dropStale();
    if (preparing) TCApi.control('stop');
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
          TCApi.control('seekby', delta).then(TCPlayer._noteIfRefused);
          TCPlayer._markSeeking(Math.max(0, pos + delta));
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
            TCApi.control('seekby', target - pos).then(TCPlayer._noteIfRefused);
            TCPlayer._markSeeking(target);
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
          // всё это время вкладка гремела на всю комнату (замер на стенде `.104`
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
      onFullscreen() {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else TCPlayer._nodes.frame.requestFullscreen().catch(() => {});
      },
      onClose() { TCPlayer._leave(); },
    };
  },
};

//: Стрелки/пробел/F/Esc принадлежат плееру целиком (§4.5), а не D-pad'у (`nav.js`):
//: слушатель ставится в фазе перехвата, чтобы `stopImmediatePropagation` погасил
//: геометрический D-pad раньше, чем тот переставит фокус по тем же стрелкам.
document.addEventListener('keydown', (event) => {
  if (location.pathname !== '/play' || !TCPlayer._video || !TCPlayer._handlers) return;
  const handlers = TCPlayer._handlers;
  // Плёнки нет - перематывать и ставить на паузу нечего: стрелки уходят D-pad'у между
  // кнопками экрана («Ещё раз», «Назад»), Enter жмёт ту, что под фокусом. Плеер - Esc.
  if (TCPlayer._halted) {
    if (event.key === 'Escape') handlers.onClose();
    return;
  }
  // Enter на кнопке под фокусом - нажатие ЭТОЙ кнопки: «−10 с» и «На ТВ» с пульта
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

// Закрытие вкладки, переход на другой сайт и `F5` роняют один и тот же `pagehide`
// (TC-1124), в отличие от ухода с ``/play`` внутри приложения - тот ловит сам цикл
// `_reportPosition`. `fetch` на выгружаемой странице не гарантирован, поэтому «ухожу»
// шлёт `sendBeacon` (`TCApi.left`), а не обычный запрос позиции.
window.addEventListener('pagehide', () => { if (TCPlayer._mounted()) TCPlayer._left(); });

window.TCPlayer = TCPlayer;
