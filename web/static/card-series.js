// Вынесено из card.js, чтобы не разрастаться в один файл (по правилу «дели, а не сжимай»):
// вкладки сезонов, список серий и полка «ещё из этой серии» - весь сериальный довесок
// над общей карточкой картины.
'use strict';

const TCCardSeries = {
  // Сколько строка вышедшей серии остаётся нажимаемой после открытия карточки, чем бы ни
  // ответил перебор раздач. Приговор `absent` бывает и бесплатным (раздачи называют свои
  // серии именем, сеть не нужна), и тогда он приезжает уже в первом теле - на четвёртой
  // секунде. Гашение в этот момент съедает нажатие, сделанное человеком по строке, которую
  // он видел живой. Порог держит окно нажатия ровно там, где его обещали: первые 10 с.
  GREY_AFTER: 10000,
  _opened: { visit: 0, at: 0 },

  // Сколько миллисекунд карточка на экране. Визит считает `TCCard._visit`: он растёт на
  // каждом открытии и НЕ растёт на доборах, поэтому окно не продлевается опросом.
  _sinceOpen() {
    if (TCCardSeries._opened.visit !== TCCard._visit) {
      TCCardSeries._opened = { visit: TCCard._visit, at: Date.now() };
    }
    return Date.now() - TCCardSeries._opened.at;
  },

  // Погасить строку, когда окно нажатия кончилось: вид, фокус, обработчик и слова.
  _fade(row, play) {
    if (!row.isConnected || row.classList.contains('is-unreleased')) return;
    row.removeEventListener('click', play);
    row.classList.add('is-unreleased');
    row.setAttribute('aria-disabled', 'true');
    row.removeAttribute('tabindex');
    row.removeAttribute('role');
    delete row.dataset.tcFocusable;
    delete row.dataset.tcGroup;
    const meta = row.querySelector('.tc-ep-meta');
    if (meta && !meta.querySelector('[data-tc-absent]')) meta.prepend(TCCardSeries._why());
  },

  // Строка обязана объяснить себя словами: погасшая молча читается как поломка.
  _why() {
    const none = document.createElement('div');
    none.dataset.tcAbsent = '1';
    none.textContent = TC.say('web.detail.episode_absent');
    return none;
  },

  tabs(data, key, query, selected) {
    const tabs = document.createElement('div');
    tabs.className = 'tc-tabs';
    data.seasons.forEach((season, index) => {
      const tab = document.createElement('div');
      tab.className = 'tc-tab' + (index === selected ? ' is-active' : '');
      tab.textContent = TC.say('web.detail.season', { n: season.n });
      tab.tabIndex = 0;
      tab.dataset.tcFocusable = '1';
      tab.dataset.tcGroup = 'season-tabs';
      tab.setAttribute('role', 'button');
      tab.addEventListener('click', () => {
        tabs.querySelectorAll('.tc-tab').forEach((el) => el.classList.remove('is-active'));
        tab.classList.add('is-active');
        // Выбор зрителя помнится на карточке: подмена тела добором не сбрасывает его.
        TCCard._picked = { key, n: season.n };
        tabs.nextSibling.replaceWith(TCCardSeries.episodes(data, index, key, query));
        TCCard._season(key, query, season.n);
      });
      tabs.appendChild(tab);
    });
    return tabs;
  },

  episodes(data, seasonIndex, key, query) {
    const list = document.createElement('div');
    list.className = 'tc-episodes';
    const season = data.seasons[seasonIndex];
    const resumeEpisode = TCCardSeries._resumeEpisodeNumber(data);
    // Вышедшие серии, которых нет ни в одной раздаче (`web/episode_absent.py`). Приговор
    // приезжает ПОЗЖЕ тела карточки, и до него строка здесь обычная: перебор раздач идёт
    // секундами, а нажатие, сделанное до гашения, обязано открыть поиск раздачи.
    const absent = new Set(Array.isArray(season.absent) ? season.absent : []);
    // Вкладка, за которой разбор раздач не нашёл ни одной серии (`web/mark_empty.py`).
    // Пустая и молчащая читается как поломка страницы, а ответ честный: играть нечего.
    if (!season.episodes.length && season.empty) {
      const none = document.createElement('div');
      none.className = 'tc-ep is-unreleased';
      none.dataset.tcSeasonEmpty = '1';
      none.setAttribute('aria-disabled', 'true');
      none.textContent = TC.say('web.detail.season_absent');
      list.appendChild(none);
    }
    const hold = Math.max(0, TCCardSeries.GREY_AFTER - TCCardSeries._sinceOpen());
    for (const episode of season.episodes) {
      const row = document.createElement('div');
      const isResume = season.n === resumeEpisode.season && episode.n === resumeEpisode.episode;
      // Серия ещё не вышла: серая строка с датой выхода, фокус и нажатие её обходят.
      const coming = Boolean(episode.air);
      const gone = !coming && absent.has(episode.n);
      const grey = coming || (gone && hold === 0);
      row.className = 'tc-ep' + (episode.watched ? ' is-watched' : '') + (isResume ? ' is-resume' : '')
        + (grey ? ' is-unreleased' : '');
      row.dataset.tcEpisode = 's' + season.n + 'e' + episode.n;
      if (grey) {
        row.setAttribute('aria-disabled', 'true');
      } else {
        row.tabIndex = 0;
        row.dataset.tcFocusable = '1';
        row.dataset.tcGroup = 'episodes';
        row.setAttribute('role', 'button');
      }
      const num = document.createElement('div');
      num.className = 'tc-ep-num';
      num.textContent = String(episode.n);
      const title = document.createElement('div');
      title.className = 'tc-ep-title';
      title.textContent = TC.say('web.detail.season', { n: season.n }) + ' · ' + episode.n;
      const meta = document.createElement('div');
      meta.className = 'tc-ep-meta';
      if (coming) {
        const air = document.createElement('div');
        air.textContent = TC.say('web.detail.airs', { date: TCCardSeries._date(episode.air) });
        meta.appendChild(air);
      } else if (gone && !hold) {
        meta.appendChild(TCCardSeries._why());
      } else if (episode.watched) {
        const watched = document.createElement('div');
        watched.textContent = TC.say('web.detail.watched');
        meta.appendChild(watched);
      } else if (isResume && episode.pos) {
        const resumes = document.createElement('div');
        resumes.style.fontWeight = '900';
        resumes.textContent = TC.say('web.detail.resumes_here', { time: TCTime.clock(episode.pos) });
        meta.appendChild(resumes);
      }
      const dur = document.createElement('div');
      dur.textContent = episode.dur ? TCTime.clock(episode.dur) : '';
      meta.appendChild(dur);
      row.append(num, title, meta);
      if (isResume && episode.dur) {
        const bar = document.createElement('div');
        bar.className = 'tc-ep-progress';
        bar.style.width = Math.max(0, Math.min(1, episode.pos / episode.dur)) * 100 + '%';
        row.appendChild(bar);
      }
      const play = () => TCCard._play(data, key, query,
        data.voices || [], false, season.n, episode.n)
        .then((said) => TCCard._showPlayRefusal(row, said));
      if (!grey) row.addEventListener('click', play);
      // Приговор уже есть, но окно нажатия ещё идёт: строка живая, и гаснет по будильнику.
      if (gone && hold) setTimeout(() => TCCardSeries._fade(row, play), hold);
      list.appendChild(row);
    }
    return list;
  },

  _date(iso) {
    const [year, month, day] = String(iso).split('-');
    if (!day) return String(iso);
    if (TC.language === 'ru') return day + '.' + month + '.' + year;
    return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)))
      .toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  },

  _resumeEpisodeNumber(data) {
    const match = /s\s*(\d{1,2})\s*[.\-_ ]?\s*e\s*(\d{1,3})/i.exec(data.label || '');
    return match ? { season: Number(match[1]), episode: Number(match[2]) } : { season: -1, episode: -1 };
  },

  related(data) {
    const wrap = document.createElement('div');
    wrap.className = 'tc-detail-series-block';
    const head = document.createElement('div');
    head.className = 'tc-series-head';
    head.textContent = TC.say('web.detail.series');
    const row = document.createElement('div');
    row.className = 'tc-row';
    for (const tile of data.related) {
      row.appendChild(TCTile.build({
        key: tile.key, title: tile.shown || tile.title, poster: tile.poster,
        year: tile.year, group: 'related', query: tile.query || tile.title,
        facts: { title: tile.title, shown: tile.shown || tile.title, year: tile.year, kind: tile.kind },
        onActivate: (key, query, facts) => TCRouter.card(key, query, facts),
      }));
    }
    head.appendChild(TCTile.steps(row));
    wrap.append(head, row);
    return wrap;
  },
};

window.TCCardSeries = TCCardSeries;
