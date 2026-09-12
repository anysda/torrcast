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

  async mount(root) {
    // Что искали, написано в АДРЕСЕ (`/?query=…`), а не только в памяти страницы:
    // иначе «назад» из картины возвращает на чистую главную, хотя уходили с выдачи.
    const asked = TCHome._asked();
    TCHome._query = asked;
    root.replaceChildren();
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

    TCHome._askSources();
    // Снимок показа полки НЕ держит: с молчащим ресивером ``/api/state`` едет до 20 с
    // (громкость спрашивается у самого приёмника, `hass/volume.py`), а полки от того,
    // что играет телевизор, не зависят. Плашка «сейчас идёт» встанет на шапку сама,
    // когда state и ящик доедут.
    TCHome._stateLater(root);
    TCHome._shelfPoll += 1;
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
    // полки просто запоминаются - встанут при возврате на неё.
    if (!TCHome._query) {
      const body = document.getElementById('tc-body');
      if (body) body.replaceWith(TCHome._body(TCHome._lastHistory, TCHome._lastShelves));
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
      return;
    }
    body.replaceWith(TCHome._searchLoading());
    TCHome._timer = setTimeout(() => TCHome._runSearch(text), 400);
  },

  // Адрес переписывается на месте, а не добавляется в историю: иначе «назад» отматывал
  // бы набранное по букве вместо возврата на тот экран, с которого ушли.
  _remember(text) {
    const want = text.length < 2 ? '/' : '/?query=' + encodeURIComponent(text);
    if (location.pathname + location.search !== want) history.replaceState({}, '', want);
  },

  // Показ по мере прихода (TC-1126): первая находка первого ответившего источника
  // встаёт на экран сразу, а не ждёт самого медленного из опорных
  // (`torrcast.domain.wait_indexer`) - тот по-прежнему ждётся СЕРВЕРОМ, здесь только
  // опрос уже идущего заказа (`TCApi.searchProgress`, тот же приём, что у `card.js`).
  //
  // Потолок опроса - 40 заходов по 400 мс (16 с): круг поиска живёт секунды, а заказ на
  // сервере - `hass.search_progress.JOB_TTL` (30 с), и это меньше её целиком.
  async _runSearch(text) {
    if (TCHome._sourcesCount === null) TCHome._askSources();
    const mine = ++TCHome._token;
    let known = [];
    for (let tries = 0; tries < 40; tries += 1) {
      const { results, partial } = await TCApi.searchProgress(text);
      if (mine !== TCHome._token || TCHome._query !== text) return;
      const next = TCHome._mergeHits(known, results, partial);
      known = next;
      TCHome._found = { query: text, results: known };
      TCHome._swapBody(TCHome._searchResults(known, partial));
      if (!partial) return;
      await new Promise((done) => setTimeout(done, 400));
    }
  },

  // Выдача пересобирается целиком на каждом дописывании находок, а фокус клавиатуры
  // живёт В ПЛИТКЕ: без переноса он каждые 400 мс падал бы на голый `<body>`, и
  // человек возвращался бы к первой плитке, пока круг ещё растёт.
  _swapBody(next) {
    const body = document.getElementById('tc-body');
    if (!body) return;
    const live = '[data-tc-tile][data-tc-focusable]';
    const here = document.activeElement;
    const at = here && here.matches && here.matches(live) && body.contains(here)
      ? Array.from(body.querySelectorAll(live)).indexOf(here) : -1;
    body.replaceWith(next);
    const tiles = next.querySelectorAll(live);
    if (at >= 0 && tiles[at]) tiles[at].focus();
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
  // ЕЁ повторения по счёту, а не сам `key` в одиночку.
  _mergeHits(known, fresh, partial) {
    if (!partial) return fresh;
    const ids = (list) => {
      const seen = new Map();
      return list.map((hit) => {
        const n = seen.get(hit.key) || 0;
        seen.set(hit.key, n + 1);
        return hit.key + '\u0000' + n;
      });
    };
    const freshIds = ids(fresh);
    const byId = new Map(freshIds.map((id, index) => [id, fresh[index]]));
    const keptIds = new Set();
    const kept = [];
    for (const [index, id] of ids(known).entries()) {
      kept.push(byId.has(id) ? byId.get(id) : known[index]);
      keptIds.add(id);
    }
    const added = freshIds
      .map((id, index) => ({ id, hit: fresh[index] }))
      .filter(({ id }) => !keptIds.has(id))
      .map(({ hit }) => hit);
    return kept.concat(added);
  },

  _searchLoading() {
    TCHome._syncCount(null);
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
    TCHome._syncCount(results.length);
    // Выдача - два РЯДА, а не сетка (§4.2): первые семь крупные (210px, у самой первой
    // плашка «Best match»), остальные второй строкой мельче (168px, `tc-grid--second`).
    // Пока круг идёт, плашки нет ни у кого: назвать лучшее совпадение можно только по
    // полной выдаче, а не по тому, кто ответил первым.
    body.appendChild(TCHome._hitsRow(results.slice(0, 7), 'tc-row', !partial));
    if (results.length > 7) {
      body.appendChild(TCHome._hitsRow(results.slice(7), 'tc-row tc-grid--second', false));
    }
    return body;
  },

  _hitsRow(hits, cls, firstBest) {
    const row = document.createElement('div');
    row.className = cls;
    hits.forEach((hit, index) => {
      row.appendChild(TCTile.build({
        key: hit.key,
        title: hit.shown || hit.title,
        poster: hit.poster,
        year: hit.year,
        best: firstBest && index === 0,
        group: 'search-results',
        query: TCHome._query,
        // У всей выдачи запрос ОДИН - тот, что человек написал: весь экран находок
        // стоит прогреву одного круга, а не одного круга на плитку.
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
        query: item.query || item.title,
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

  _openCard(key, query) {
    TCRouter.card(key, query);
  },
};

window.TCHome = TCHome;
