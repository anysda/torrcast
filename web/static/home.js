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
  _sourcesCount: 0,

  async mount(root) {
    // Что искали, написано в АДРЕСЕ (`/?query=…`), а не только в памяти страницы:
    // иначе «назад» из картины возвращает на чистую главную, хотя уходили с выдачи.
    const asked = TCHome._asked();
    TCHome._query = asked;
    root.replaceChildren();
    const scan = document.createElement('div');
    scan.className = 'tc-scan';

    let header = TC.header(null);
    const wrap = document.createElement('div');
    wrap.className = 'tc-shelf-safe';
    wrap.append(TCHome._search(), asked ? TCHome._askedBody(asked) : TCHome._loadingBody());
    root.append(scan, header, wrap);
    const input = wrap.querySelector('.tc-search-input');
    input.value = asked;
    input.focus();

    TCApi.sources().then((count) => { TCHome._sourcesCount = count; });
    const [state, history, shelves] = await Promise.all([
      TCApi.state(), TCApi.history(), TCApi.shelves(),
    ]);
    if (!document.body.contains(root) || location.pathname !== '/') return;
    const fresh = TC.header(state);
    header.replaceWith(fresh);
    header = fresh;
    TCHome._lastHistory = history;
    TCHome._lastShelves = shelves;
    const body = document.getElementById('tc-body');
    if (body && !TCHome._query) body.replaceWith(TCHome._body(history, shelves));
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

  async _runSearch(text) {
    const mine = ++TCHome._token;
    const results = await TCApi.search(text);
    if (mine !== TCHome._token || TCHome._query !== text) return;
    TCHome._found = { query: text, results };
    const body = document.getElementById('tc-body');
    if (body) body.replaceWith(TCHome._searchResults(results));
  },

  _searchLoading() {
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
  // поиска (`TCApi.sources`), а не выдумка страницы.
  _searchingLine() {
    const line = document.createElement('div');
    line.className = 'tc-searching';
    const square = document.createElement('div');
    square.className = 'tc-searching-square';
    const label = document.createElement('div');
    label.textContent = TC.say('web.search.searching', { n: TCHome._sourcesCount });
    line.append(square, label);
    return line;
  },

  _searchResults(results) {
    const body = document.createElement('div');
    body.id = 'tc-body';
    if (results.length === 0) {
      const nothing = document.createElement('div');
      nothing.className = 'tc-nothing';
      nothing.textContent = TC.say('web.search.empty');
      const hint = document.createElement('div');
      hint.className = 'tc-nothing-hint';
      hint.textContent = TC.say('web.search.empty_hint');
      body.append(nothing, hint);
      return body;
    }
    const grid = document.createElement('div');
    grid.className = 'tc-grid';
    results.forEach((hit, index) => {
      grid.appendChild(TCTile.build({
        key: hit.key,
        title: hit.shown || hit.title,
        poster: hit.poster,
        year: hit.year,
        best: !!hit.default,
        group: 'search-results',
        query: TCHome._query,
        onActivate: TCHome._openCard,
      }));
    });
    body.appendChild(grid);
    return body;
  },

  _body(history, shelves) {
    TCHome._lastHistory = history;
    TCHome._lastShelves = shelves;
    const body = document.createElement('div');
    body.id = 'tc-body';
    if (history.length > 0) {
      body.appendChild(TCHome._shelf('web.shelf.continue_watching', 'shelf-continue',
        history.map((item) => ({
          key: item.key,
          title: item.shown || item.title,
          poster: item.poster,
          caption2: item.label || '',
          progress: item.dur ? item.pos / item.dur : 0,
          group: 'shelf-continue',
          query: item.title,
          onActivate: TCHome._openCard,
        }))));
    }
    body.appendChild(TCHome._shelf('web.shelf.new', 'shelf-new',
      shelves.fresh.map(TCHome._tileFrom)));
    body.appendChild(TCHome._shelf('web.shelf.popular', 'shelf-popular',
      shelves.popular.map(TCHome._tileFrom)));
    return body;
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
    return shelf;
  },

  _openCard(key, query) {
    TCRouter.card(key, query);
  },
};

window.TCHome = TCHome;
