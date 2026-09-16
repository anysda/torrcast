// Главная и поиск (одна вкладка): 4.1 и 4.2. Поиск не отдельный маршрут - он меняет
// содержимое ПОД полем, а само поле и шапка остаются на месте.
'use strict';

const TCHome = {
  _query: '',
  _timer: null,
  _token: 0,
  _found: null,
  _lastHistory: [],
  _lastShelves: { fresh: [], popular: [] },
  // Сколько источников у круга поиска; ``null`` - число ещё неизвестно. Ноль от
  // сервера это ровно «неизвестно»: `web/sources_cache.py` честно отдаёт ноль, пока
  // фон не собрал список (TC-1110), и первый круг после рестарта шёл под надписью
  // «Ищем в 0 источниках…».
  _sourcesCount: null,
  // Номер живого круга опроса полок: вернувшись на главную, прежний круг гаснет,
  // иначе два таймера спрашивали бы сервер вдвоём.
  _shelfPoll: 0,
  // Что шапка знает прямо сейчас: последний ответ о показе, место показа и сборка полок.
  // Они приходят порознь и в любом порядке, а шапка на экране одна.
  _state: null,
  _box: null,
  _assembling: false,
  // Какое тело стоит на экране главной (сериализованные история и полки): тихий
  // добор сравнивает с ним ответ и не пересобирает то, что не менялось.
  _shownHome: '',
  // Какая выдача поиска стоит на экране: один и тот же список находок не
  // пересобирается на каждом шаге опроса - перерисовка перезаказывала бы обложки.
  _shownHits: '',

  async mount(root) {
    // Что искали, написано в АДРЕСЕ (`/?query=…`), а не только в памяти страницы:
    // иначе «назад» из картины возвращает на чистую главную, хотя уходили с выдачи.
    const asked = TCHome._asked();
    TCHome._query = asked;
    TCHome._shelfPoll += 1;
    root.replaceChildren();
    // Выдача берётся из памяти только вместе со СВОИМ запросом: адрес мог уйти вперёд
    // набранного текста, и чужие находки под новым адресом - не честный экран.
    const mine = !asked || (TCHome._found && TCHome._found.query === asked)
      ? TCKept.take(location.pathname + location.search) : null;
    if (mine) {
      TCKept.resume(root, mine);
      TCHome._assembling = false;
      const input = root.querySelector('.tc-search-input');
      input.value = asked;
      input.focus();
      TCHome._askSources();
      TCHome._stateLater(root);
      if (asked) {
        TCHome._runSearch(asked);
      } else {
        TCHome._freshen(root);
      }
      TCHome._markNow();
      return;
    }
    const scan = document.createElement('div');
    scan.className = 'tc-scan';

    TCHome._state = null;
    TCHome._box = null;
    TCHome._assembling = !asked;
    const header = TC.header(TCHome._state, TCHome._assembling, TCHome._box);
    const wrap = document.createElement('div');
    wrap.className = 'tc-shelf-safe';
    wrap.append(TCHome._search(), asked ? TCHome._askedBody(asked) : TCHome._loadingBody());
    root.append(scan, header, wrap);
    const input = wrap.querySelector('.tc-search-input');
    input.value = asked;
    input.focus();
    TCHome._markNow();

    TCHome._askSources();
    // Снимок показа полки НЕ держит: с молчащим ресивером ``/api/state`` едет до 20 с
    // (громкость спрашивается у самого приёмника, `hass/volume.py`), а полки от того,
    // что играет телевизор, не зависят. Плашка «сейчас идёт» встанет на шапку сама,
    // когда state и ящик доедут.
    TCHome._stateLater(root);
    const [history, shelves] = await Promise.all([TCApi.history(), TCApi.shelves()]);
    if (!document.body.contains(root) || location.pathname !== '/') return;
    TCHome._lastHistory = history;
    TCHome._lastShelves = { fresh: shelves.fresh, popular: shelves.popular };
    const assembling = !TCHome._query && !!shelves.partial;
    TCHome._wear(assembling);
    // Полки ещё собираются - тело остаётся скелетным, и меняется в нём ровно одна
    // лента: историю сервер назвал первым же ответом, а ``partial`` приходит только с
    // пустыми полками, так что готовых плиток скелеты не прячут.
    if (assembling) {
      TCHome._wornContinue(history);
    } else {
      const body = document.getElementById('tc-body');
      if (body && !TCHome._query) {
        body.replaceWith(TCHome._body(history, TCHome._lastShelves));
      }
    }
    if (shelves.partial) TCHome._waitShelves(root, TCHome._shelfPoll);
  },

  // Цел ли экран для памяти (`kept.js`): тело есть и ни один скелет не стоит - ни
  // плиточный, ни строка.
  ready(root) {
    const body = root.querySelector('#tc-body');
    return !!body && !root.querySelector('.tc-tile-skeleton, .tc-skel-line');
  },

  // Тихий добор главной после возврата: полки уже стоят, и тело меняется только
  // целиком и только когда ответ правда другой. «Продолжить» подъезжает своей полкой
  // даже пока полки сервер ещё собирает.
  async _freshen(root) {
    const mine = TCHome._shelfPoll;
    const [history, shelves] = await Promise.all([TCApi.history(), TCApi.shelves()]);
    if (mine !== TCHome._shelfPoll || !document.body.contains(root) || location.pathname !== '/') {
      return;
    }
    if (shelves.partial) {
      if (JSON.stringify(history) !== JSON.stringify(TCHome._lastHistory)) {
        TCHome._lastHistory = history;
        TCHome._wornContinue(history);
      }
      TCHome._waitShelves(root, mine);
      return;
    }
    TCHome._lastHistory = history;
    TCHome._lastShelves = { fresh: shelves.fresh, popular: shelves.popular };
    if (JSON.stringify([history, TCHome._lastShelves]) !== TCHome._shownHome) {
      const body = document.getElementById('tc-body');
      if (body) body.replaceWith(TCHome._body(history, TCHome._lastShelves));
    }
  },

  // Плашка «сейчас идёт» доезжает позже полок и пересобирает шапку сама: ждать снимок
  // ДО отрисовки значило бы запереть готовые полки за опросом телевизора.
  async _stateLater(root) {
    const [state, box] = await Promise.all([TCApi.state(), TCApi.box()]);
    if (!document.body.contains(root) || location.pathname !== '/') return;
    TCHome._state = state;
    TCHome._box = box;
    TCHome._wear();
  },

  // История известна с первого ответа, а полки собираются минуту: держать «Продолжить»
  // скелетом всё это время значит прятать от человека уже готовое. Скелетами остаются
  // ровно те две полки, которых пока и правда нет; пустой истории нет и полки.
  _wornContinue(history) {
    const body = document.getElementById('tc-body');
    const first = body && body.firstElementChild;
    if (!first) return;
    if (history.length === 0) first.remove();
    else first.replaceWith(TCHome._continue(history));
  },

  // Шапка пересобирается целиком, а счётчик выдачи, вставший в прежнюю, надо вернуть:
  // он живёт в той же шапке, что и слот сборки. Отдельного слова про сборку не сказано -
  // значит менялся показ, и слот остаётся каким был.
  _wear(loading) {
    if (loading !== undefined) TCHome._assembling = loading;
    const header = document.querySelector('.tc-header');
    if (!header) return;
    header.replaceWith(TC.header(TCHome._state, TCHome._assembling, TCHome._box));
    if (TCHome._found && TCHome._found.query === TCHome._query) {
      TCHome._syncCount(TCHome._found.results.length);
    }
  },

  // Холодный старт: полки ещё собирает фон, и сервер отвечает пустыми с меткой
  // ``X-Torrcast-Partial`` - тем же приёмом, что карточка (TC-1172): вкладка
  // переспрашивает себя сама, и человек дожидается полок, не трогая её. Потолок - 36
  // заходов по 5 с: добор коротких полок стоит фону до ~90 с (TC-1168). Лента не
  // собралась вовсе - на экране остаётся честное «пока пусто», а не вечный опрос.
  async _waitShelves(root, mine) {
    for (let tries = 0; tries < 36; tries += 1) {
      await new Promise((done) => setTimeout(done, 5000));
      if (mine !== TCHome._shelfPoll || !document.body.contains(root) || location.pathname !== '/') {
        return;
      }
      const shelves = await TCApi.shelves();
      TCHome._lastShelves = { fresh: shelves.fresh, popular: shelves.popular };
      if (!shelves.partial) break;
    }
    // Полки дособрались - или не дособрались за все 36 заходов. И там, и там сборки
    // больше нет: тело встаёт тем, что пришло, а «Грузим_» уходит. Раньше этой секунды
    // тело не трогается вовсе - недоехавший ответ приходит ПУСТЫМ, и подменять им
    // скелеты значит написать «пока пусто» над лентой, которая едет (замер на стенде
    // `.104`: полки приехали на 15.3 с, а надпись встала бы на 5.2 с).
    // Тело меняется только на чистой главной: в выдаче поиска свои плитки, и доехавшие
    // полки просто запоминаются - встанут при возврате на неё. Равное показанному
    // тело не подменяется: у плиток на экране нет причины уезжать и собираться заново.
    if (!TCHome._query) {
      const body = document.getElementById('tc-body');
      const fresh = [TCHome._lastHistory, TCHome._lastShelves];
      if (body && JSON.stringify(fresh) !== TCHome._shownHome) {
        body.replaceWith(TCHome._body(...fresh));
      }
    }
    TCHome._wear(false);
  },

  // Спросить, сколько источников у круга поиска. Ответ приходит из серверного кэша, и
  // пока тот не собран, число остаётся неизвестным - потому спрашивается снова с
  // каждым поиском, а не один раз на загрузку страницы.
  _askSources() {
    TCApi.sources().then((count) => {
      TCHome._sourcesCount = count > 0 ? count : null;
      // Счётчик мог встать на шапку раньше ответа про источники - переписать число.
      if (TCHome._found && TCHome._found.query === TCHome._query) {
        TCHome._syncCount(TCHome._found.results.length);
      }
    });
  },

  _asked() {
    return new URLSearchParams(location.search).get('query') || '';
  },

  // Возврат на свою выдачу: находки, которые уже приезжали, показываются сразу, и
  // только незнакомый запрос уходит в источники заново.
  _askedBody(text) {
    if (TCHome._found && TCHome._found.query === text) {
      return TCHome._searchResults(TCHome._found.results);
    }
    TCHome._runSearch(text);
    return TCHome._searchLoading();
  },

  _loadingBody() {
    const body = document.createElement('div');
    body.id = 'tc-body';
    for (const key of ['web.shelf.continue_watching', 'web.shelf.new', 'web.shelf.popular']) {
      body.appendChild(TCHome._shelf(key, 'shelf-loading', Array.from({ length: 6 },
        () => ({ loading: true }))));
    }
    return body;
  },

  _search() {
    const box = document.createElement('div');
    box.className = 'tc-search';
    const input = document.createElement('input');
    input.className = 'tc-search-input';
    input.placeholder = TC.say('web.search.placeholder');
    input.dataset.tcFocusable = '1';
    input.dataset.tcGroup = 'search-field';
    input.addEventListener('input', TCHome._onType);
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && input.value) {
        event.preventDefault();
        input.value = '';
        TCHome._onType({ target: input });
      }
    });
    const hints = document.createElement('div');
    hints.className = 'tc-search-hints';
    for (const key of ['web.search.hint_enter', 'web.search.hint_esc']) {
      const hint = document.createElement('div');
      hint.className = 'tc-hint';
      hint.textContent = TC.say(key);
      hints.appendChild(hint);
    }
    box.append(input, hints);
    return box;
  },

  _onType(event) {
    const text = event.target.value.trim();
    TCHome._query = text;
    TCHome._remember(text);
    clearTimeout(TCHome._timer);
    const body = document.getElementById('tc-body');
    if (text.length < 2) {
      body.replaceWith(TCHome._body(TCHome._lastHistory, TCHome._lastShelves));
      TCHome._markNow();
      return;
    }
    body.replaceWith(TCHome._searchLoading());
    TCHome._markNow();
    TCHome._timer = setTimeout(() => TCHome._runSearch(text), 400);
  },

  // Адрес переписывается на месте, а не добавляется в историю: иначе «назад» отматывал
  // бы набранное по букве вместо возврата на тот экран, с которого ушли.
  _remember(text) {
    const want = text.length < 2 ? '/' : '/?query=' + encodeURIComponent(text);
    if (location.pathname + location.search !== want) history.replaceState({}, '', want);
  },

  // Метка памяти называет адрес НАРИСОВАННОГО тела: при наборе текста адрес меняется
  // раньше тела, и метка по новому адресу назвала бы чужие находки своими. Потому она
  // ставится в момент отрисовки: на монтировании экрана и на смене тела набором.
  _markNow() {
    const root = document.getElementById('tc-root');
    if (root) TCKept.mark(root, location.pathname + location.search);
  },

  // Показ по мере прихода (TC-1126): первая находка первого ответившего источника
  // встаёт на экран сразу, а не ждёт самого медленного из опорных
  // (`torrcast.domain.wait_indexer`) - тот по-прежнему ждётся СЕРВЕРОМ, здесь только
  // опрос уже идущего заказа (`TCApi.searchProgress`, тот же приём, что у `card.js`).
  //
  // Опрос идёт, пока ответ частичный, и не дольше срока сервера: к `finalBy` секунд от
  // начала заказа сервер отдаёт финал из собранного (`hass.search_job.FINAL_BY`), и
  // страница ждёт его с запасом на шаг опроса. Своё число тут было 16 с, а финал
  // «Начало» на стенде ехал 18-21 с: выдача оставалась без «Best match» навсегда.
  // Пока показать нечего, шаг 150 мс: круг, сохранённый на диске, готов за 150-400 мс;
  // с первой находкой шаг снова 400 мс.
  async _runSearch(text, retried = false) {
    if (TCHome._sourcesCount === null) TCHome._askSources();
    const mine = ++TCHome._token;
    const gone = () => mine !== TCHome._token || TCHome._query !== text;
    TCHome._focusFirst = retried;
    const began = Date.now();
    let until = began;
    let known = [];
    let answered = false;
    let misses = 0;
    let asked = began;
    let said;
    do {
      asked = Date.now();
      said = await TCApi.searchProgress(text);
      if (gone()) return;
      if (said.refused) {
        // Отказ словом - готовый ответ поиска, а не сорванный опрос: переспрашивать его
        // нечем, ни сейчас, ни кнопкой. Его читают и зовут картину другими словами.
        TCHome._swapBody(TCHome._searchRefused(said.refused, known));
        return;
      }
      if (said.failed) {
        // Сорванный опрос живого поиска (сервер уже отвечал) не сбой: сервер досчитывает
        // заход, и следующий опрос его застаёт. Сбой - только подряд `_POLL_TRIES` раз.
        misses += 1;
        if (!answered || misses >= TCHome._POLL_TRIES) {
          TCHome._swapBody(TCHome._searchFailed(text, known));
          return;
        }
      } else {
        answered = true;
        misses = 0;
        until = began + said.finalBy * 1000 + TCHome._FINAL_SLACK;
        known = TCHome._showHits(text, known, said);
        if (!said.partial) break;
      }
      await new Promise((done) => setTimeout(done, known.length ? 400 : 150));
      // Срок сверяется по НАЧАЛУ опроса: опрос, начатый до срока и застрявший за ним в
      // очереди браузера, иначе обрывал поиск за миг до финала (TC-1286).
    } while (asked < until || misses > 0);
    if (said.failed || said.partial) return;
    // Финал бывает раньше обложек: сервер называет, что они ещё в пути, и сколько секунд до
    // его потолка. Потолок идёт от начала захода сервера, а заход бывает старше страницы:
    // отсчёт от своего начала опрашивал за потолком и гнал новый круг поиска.
    const postersUntil = Date.now() + said.postersBy * 1000;
    while (said.postersPending && Date.now() + TCHome._POSTER_STEP <= postersUntil) {
      await new Promise((done) => setTimeout(done, TCHome._POSTER_STEP));
      said = await TCApi.searchProgress(text);
      if (gone() || said.failed || said.partial) return;
      known = TCHome._showHits(text, known, said);
    }
  },

  // Ответ опроса на экран: тот же экран не пересобирается, у стоящих обложек нет причины
  // уезжать и заказываться заново. Экран - это список И то, финал ли он: финал, равный
  // последнему превью, обязан встать, иначе «Best match» не появлялся вовсе.
  _showHits(text, known, said) {
    const merged = TCHome._mergeHits(known, said.results, said.partial);
    TCHome._found = { query: text, results: merged };
    if (TCHome._screenOf(merged, said.partial) !== TCHome._shownHits) {
      TCHome._swapBody(TCHome._searchResults(merged, said.partial));
    }
    return merged;
  },

  // Запас сверх срока сервера: опрос, начатый перед самым сроком, и его дорога назад.
  _FINAL_SLACK: 2000,

  // Сколько сорванных опросов подряд живой поиск переживает до экрана сбоя.
  _POLL_TRIES: 3,

  // Шаг дозапроса обложек после финала.
  _POSTER_STEP: 2500,

  _screenOf(results, partial) {
    return JSON.stringify([results, !!partial]);
  },

  // Выдача пересобирается целиком на каждом дописывании находок, а фокус клавиатуры
  // живёт В ПЛИТКЕ: без переноса он каждые 400 мс падал бы на голый `<body>`, и
  // человек возвращался бы к первой плитке, пока круг ещё растёт. Плитка ищется по своей
  // личности, затем по картине: находка, севшая в плитку каталога, меняет личность
  // (`slot`), но не картину. Картины больше нет - фокус встаёт на то же место ряда.
  _swapBody(next) {
    const body = document.getElementById('tc-body');
    if (!body) return;
    const live = '[data-tc-tile][data-tc-focusable]';
    const here = document.activeElement;
    const stood = here && here.matches && here.matches(live) && body.contains(here) ? here : null;
    const place = stood ? Array.from(body.querySelectorAll(live)).indexOf(stood) : -1;
    // После «Try again» фокус стоял на кнопке, которая уходит с экрана: пульт терял место.
    // Он встаёт на первую плитку, как только она есть, если человек не ушёл с кнопки сам.
    const idle = !here || here === document.body || (body.contains(here) && !stood);
    body.replaceWith(next);
    if (!stood) {
      const first = TCHome._focusFirst && idle ? next.querySelector(live) : null;
      if (first) {
        TCHome._focusFirst = false;
        first.focus();
      }
      return;
    }
    const tiles = Array.from(next.querySelectorAll(live));
    const same = tiles.find((tile) => tile.dataset.tcFocusId === stood.dataset.tcFocusId)
      || tiles.find((tile) => tile.dataset.tcKey && tile.dataset.tcKey === stood.dataset.tcKey)
      || tiles[Math.min(place, tiles.length - 1)];
    if (same) same.focus();
  },

  // Уже показанная плитка МЕСТА не меняет: частичный ответ только дописывает новые
  // находки в конец и обновляет поля у тех же ключей - прыгающая под курсором выдача
  // хуже медленной. И убрать плитку, и переставить её может только финальный ответ:
  // порядок находок продуктовый (`hass.search_results`), и берётся он ЦЕЛИКОМ у круга,
  // иначе первым под клик навсегда встаёт тот, кто просто ответил раньше.
  //
  // Превью круга не растёт ровно: `hass.search_progress._preview` пересобирает список
  // по тому, что у клиента индексеров в руках прямо сейчас, и между шагами круга он
  // пустеет. Поэтому частичный ответ плитку не отнимает, даже если её в нём нет.
  //
  // Ключ у двух РАЗНЫХ пунктов меню бывает одним и тем же (одна картина, два плана) -
  // мерж по одному `key` тогда съедал бы второй пункт. Личность плитки - `key` и номер
  // ЕЁ повторения по счёту, а не сам `key` в одиночку. Находка, севшая в плитку каталога
  // (`hass.catalog_merge`), несёт её место в `slot` и остаётся той же плиткой.
  _mergeHits(known, fresh, partial) {
    if (!partial) return fresh;
    const freshIds = TCHome._hitIds(fresh);
    const byId = new Map(freshIds.map((id, index) => [id, fresh[index]]));
    const keptIds = new Set();
    const kept = [];
    for (const [index, id] of TCHome._hitIds(known).entries()) {
      kept.push(byId.has(id) ? byId.get(id) : known[index]);
      keptIds.add(id);
    }
    const added = freshIds
      .map((id, index) => ({ id, hit: fresh[index] }))
      .filter(({ id }) => !keptIds.has(id))
      .map(({ hit }) => hit);
    return kept.concat(added);
  },

  _hitIds(list) {
    const seen = new Map();
    return list.map((hit) => {
      const own = hit.slot || hit.key;
      const n = seen.get(own) || 0;
      seen.set(own, n + 1);
      return own + '\u0000' + n;
    });
  },

  _searchLoading() {
    TCHome._syncCount(null);
    // Тело - не выдача, и сравнение списков его не касается.
    TCHome._shownHits = ' ';
    const body = document.createElement('div');
    body.id = 'tc-body';
    body.appendChild(TCHome._searchingLine());
    const grid = document.createElement('div');
    grid.className = 'tc-grid';
    for (let index = 0; index < 14; index += 1) {
      grid.appendChild(TCTile.build({ loading: true }));
    }
    body.appendChild(grid);
    return body;
  },

  // Сбой поиска не стирает уже показанных плиток: человек видел их и может открыть,
  // а строка сбоя с повтором встаёт над ними.
  _searchFailed(text, known = []) {
    TCHome._syncCount(known.length ? known.length : null);
    const body = document.createElement('div');
    body.id = 'tc-body';
    const failed = document.createElement('div');
    failed.className = 'tc-nothing';
    failed.textContent = TC.say('web.search.failed');
    // Пульт ходит только по `data-tc-focusable` (`nav.js`): без пометки стрелка с поля
    // поиска до кнопки не доходила, и повтор был доступен одной мыши.
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'tc-btn tc-btn--primary tc-search-retry';
    retry.dataset.tcFocusable = '1';
    retry.dataset.tcGroup = 'search-failed';
    retry.textContent = TC.say('web.detail.retry');
    retry.addEventListener('click', () => TCHome._runSearch(text, true));
    body.append(failed, retry);
    if (known.length) {
      const shown = TCHome._searchResults(known, true);
      body.append(...Array.from(shown.children).filter((one) => !one.matches('.tc-searching')));
    }
    TCHome._shownHits = ' ';
    return body;
  },

  // Названный отказ круга поиска: сервер знает, ПОЧЕМУ ничего нет («раздач с сезоном 9
  // нет», «во франшизе столько частей нет»), и зритель читает это словами, а не общее
  // «Ничего для вас». Кнопки повтора тут нет нарочно: второй такой же заход ответит то
  // же самое, помогает другое название - о нём и подсказка (TC-1304).
  _searchRefused(word, known = []) {
    TCHome._syncCount(known.length ? known.length : null);
    const body = document.createElement('div');
    body.id = 'tc-body';
    const said = document.createElement('div');
    said.className = 'tc-nothing';
    said.textContent = word;
    const hint = document.createElement('div');
    hint.className = 'tc-nothing-hint';
    hint.textContent = TC.say('web.search.empty_hint');
    body.append(said, hint);
    if (known.length) {
      const shown = TCHome._searchResults(known, true);
      body.append(...Array.from(shown.children).filter((one) => !one.matches('.tc-searching')));
    }
    TCHome._shownHits = ' ';
    return body;
  },

  // «Ищем в N источниках…» (§4.2): N - число индексеров, включённых у самого круга
  // поиска (`TCApi.sources`), а не выдумка страницы. Числа ещё не знаем - строка идёт
  // без него: ноль тут был бы неправдой про сам поиск, который в это время идёт.
  _searchingLine() {
    const line = document.createElement('div');
    line.className = 'tc-searching';
    const square = document.createElement('div');
    square.className = 'tc-searching-square';
    const label = document.createElement('div');
    label.textContent = TCHome._sourcesCount === null
      ? TC.say('web.search.searching_any')
      : TC.count('web.search.searching', TCHome._sourcesCount);
    line.append(square, label);
    return line;
  },

  // ``partial`` - поиск ещё идёт (TC-1126): строка «Ищем в N источниках…» остаётся над
  // уже найденным, тем же индикатором, что и до первой находки (`_searchingLine`), а
  // не вторым своим. Без аргумента (кеш уже завершённого поиска) строки нет вовсе.
  _searchResults(results, partial) {
    // Нулевой частичный ответ не приговор: источники ещё отвечают, поэтому экран
    // остаётся поиском с теми же скелетами, что и до первого ответа.
    if (results.length === 0 && partial) return TCHome._searchLoading();
    const body = document.createElement('div');
    body.id = 'tc-body';
    if (results.length === 0) {
      TCHome._syncCount(null);
      const nothing = document.createElement('div');
      nothing.className = 'tc-nothing';
      nothing.textContent = TC.say('web.search.empty');
      const hint = document.createElement('div');
      hint.className = 'tc-nothing-hint';
      hint.textContent = TC.say('web.search.empty_hint');
      body.append(nothing, hint);
      return body;
    }
    if (partial) body.appendChild(TCHome._searchingLine());
    // Счёт - то, что на экране. Прежде он считал только плитки с уже найденными
    // раздачами и при двенадцати плитках писал «5 results»: погашенных в нём не было,
    // а стояли они тут же. Неоткрываемых плиток больше нет, и делить экран не на что.
    TCHome._syncCount(results.length);
    // Отрисованный экран запоминается СТРОКОЙ: следующий равный ответ не повод
    // пересобирать экран.
    TCHome._shownHits = TCHome._screenOf(results, partial);
    // Выдача - два РЯДА, а не сетка (§4.2): первые семь крупные (210px, у самой первой
    // плашка «Best match»), остальные второй строкой мельче (168px, `tc-grid--second`).
    // Пока круг идёт, плашки нет ни у кого: назвать лучшее совпадение можно только по
    // полной выдаче, а не по тому, кто ответил первым.
    const ids = TCHome._hitIds(results);
    const first = TCHome._hitsRow(results.slice(0, 7), 'tc-row', !partial, ids.slice(0, 7));
    body.appendChild(first);
    if (results.length > 7) {
      const second = TCHome._hitsRow(
        results.slice(7), 'tc-row tc-grid--second', false, ids.slice(7));
      body.appendChild(second);
    }
    return body;
  },

  _hitsRow(hits, cls, firstBest, ids) {
    const row = document.createElement('div');
    row.className = cls;
    hits.forEach((hit, index) => {
      row.appendChild(TCTile.build({
        key: hit.key,
        title: hit.shown || hit.title,
        poster: hit.poster,
        year: hit.year,
        facts: { title: hit.title, shown: hit.shown || hit.title, year: hit.year, kind: hit.kind },
        best: firstBest && index === 0,
        group: 'search-results',
        // Раздачи этой плитки круг выдачи уже принёс (`pick` - её место в нём): карточка
        // берёт их даром, тем же набранным текстом, и открывается мгновенно. Плитке, до
        // которой круг не дошёл, тот же текст отвечал 404 и отнимал картину - «Атака
        // клонов» по строке «star wars» 404, по своему имени 57 раздач. Она спрашивает
        // СВОЁ имя, как полка и «Похожее» (`_tileFrom`, `card-series.js`), и круг этого
        // имени платится один и только по клику (стенд: 17-39 с вхолодную).
        query: hit.pick === undefined ? hit.title : TCHome._query,
        warm: TCHome._query,
        focusId: ids[index],
        // Пока круг идёт, плитка каталога честно ждёт раздачи под своей обложкой. Когда
        // он кончился, ждать нечего: молчание круга о картине - не приговор ей, и клик
        // у плитки не отнимается ни в одном случае.
        caption2: hit.pending ? TC.say('web.detail.searching_releases') : '',
        onActivate: TCHome._openCard,
      }));
    });
    return row;
  },

  // Счётчик «N находок · M источников» стоит в шапке справа (§4.2/B), на месте плашки
  // «сейчас идёт». Нарисован только над выдачей: ни «ищем», ни «ничего не нашлось»,
  // ни чистая главная его не несут - ``null`` снимает. Числа настоящие: сколько плиток
  // на экране и сколько источников у круга поиска (`TCApi.sources`).
  _syncCount(shown) {
    const header = document.querySelector('.tc-header');
    if (!header) return;
    let line = header.querySelector('.tc-results-count');
    if (shown === null || shown === 0) {
      if (line) line.remove();
      return;
    }
    if (!line) {
      line = document.createElement('div');
      line.className = 'tc-results-count';
      header.appendChild(line);
    }
    const results = TC.count('web.search.result', shown);
    line.textContent = TCHome._sourcesCount === null ? results
      : results + ' · ' + TC.count('web.search.source', TCHome._sourcesCount);
  },

  _body(history, shelves) {
    TCHome._lastHistory = history;
    TCHome._lastShelves = shelves;
    TCHome._syncCount(null);
    // Собранное тело запоминается СТРОКОЙ: тихий добор сравнивает с ней ответ и не
    // трогает экран, пока данные те же.
    TCHome._shownHome = JSON.stringify([history, shelves]);
    const body = document.createElement('div');
    body.id = 'tc-body';
    if (history.length > 0) body.appendChild(TCHome._continue(history));
    body.appendChild(TCHome._shelf('web.shelf.new', 'shelf-new',
      shelves.fresh.map(TCHome._tileFrom)));
    body.appendChild(TCHome._shelf('web.shelf.popular', 'shelf-popular',
      shelves.popular.map(TCHome._tileFrom)));
    return body;
  },

  _continue(history) {
    return TCHome._shelf('web.shelf.continue_watching', 'shelf-continue',
      history.map((item) => ({
        key: item.key,
        title: item.shown || item.title,
        poster: item.poster,
        caption2: item.label || '',
        progress: item.dur ? item.pos / item.dur : 0,
        group: 'shelf-continue',
        hold: item.key,
        query: item.query || item.title,
        facts: item.year && item.kind
          ? { title: item.title, shown: item.shown || item.title, year: item.year, kind: item.kind } : null,
        onActivate: TCHome._openCard,
      })));
  },

  // Год стоит НА обложке и второй раз под плиткой не повторяется; полка «продолжить»
  // собирается отдельно и несёт под плиткой метку серии, а не год.
  _tileFrom(hit) {
    return {
      key: hit.key,
      title: hit.shown || hit.title,
      poster: hit.poster,
      year: hit.year,
      facts: { title: hit.title, shown: hit.shown || hit.title, year: hit.year, kind: hit.kind },
      query: hit.query || hit.title,
      // Греется по ЗАПИСАННОМУ имени: им же карточка ищет круг и им же зовётся справка,
      // а `title` плитки - это имя для человека, и в кэше справки его нет.
      onActivate: TCHome._openCard,
    };
  },

  _shelf(labelKey, group, tiles) {
    const shelf = document.createElement('div');
    shelf.className = 'tc-shelf';
    const head = document.createElement('div');
    head.className = 'tc-shelf-head';
    const title = document.createElement('div');
    title.className = 'tc-section';
    title.textContent = TC.say(labelKey);
    head.appendChild(title);
    shelf.appendChild(head);

    const row = document.createElement('div');
    row.className = 'tc-row';
    if (tiles.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'tc-shelf-empty';
      empty.style.width = '100%';
      empty.textContent = TC.say('web.shelf.empty');
      shelf.appendChild(empty);
      return shelf;
    }
    for (const tile of tiles) {
      tile.group = group;
      row.appendChild(TCTile.build(tile));
    }
    shelf.appendChild(row);
    head.appendChild(TCTile.steps(row));
    return shelf;
  },

  _openCard(key, query, facts) {
    TCRouter.card(key, query, facts);
  },
};

window.TCHome = TCHome;
