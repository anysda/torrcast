// Вынесено из card.js, чтобы не разрастаться в один файл (по правилу «дели, а не сжимай»):
// вкладки сезонов, список серий и полка «ещё из этой серии» - весь сериальный довесок
// над общей карточкой картины.
'use strict';

const TCCardSeries = {
  tabs(data, key, query) {
    const tabs = document.createElement('div');
    tabs.className = 'tc-tabs';
    data.seasons.forEach((season, index) => {
      const tab = document.createElement('div');
      tab.className = 'tc-tab' + (index === 0 ? ' is-active' : '');
      tab.textContent = TC.say('web.detail.season', { n: season.n });
      tab.tabIndex = 0;
      tab.dataset.tcFocusable = '1';
      tab.dataset.tcGroup = 'season-tabs';
      tab.setAttribute('role', 'button');
      tab.addEventListener('click', () => {
        tabs.querySelectorAll('.tc-tab').forEach((el) => el.classList.remove('is-active'));
        tab.classList.add('is-active');
        tabs.nextSibling.replaceWith(TCCardSeries.episodes(data, index, key, query));
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
    for (const episode of season.episodes) {
      const row = document.createElement('div');
      const isResume = season.n === resumeEpisode.season && episode.n === resumeEpisode.episode;
      row.className = 'tc-ep' + (episode.watched ? ' is-watched' : '') + (isResume ? ' is-resume' : '');
      row.tabIndex = 0;
      row.dataset.tcFocusable = '1';
      row.dataset.tcGroup = 'episodes';
      row.dataset.tcEpisode = 's' + season.n + 'e' + episode.n;
      row.setAttribute('role', 'button');
      const num = document.createElement('div');
      num.className = 'tc-ep-num';
      num.textContent = String(episode.n);
      const title = document.createElement('div');
      title.className = 'tc-ep-title';
      title.textContent = TC.say('web.detail.season', { n: season.n }) + ' · ' + episode.n;
      const meta = document.createElement('div');
      meta.className = 'tc-ep-meta';
      if (episode.watched) {
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
      row.addEventListener('click', () => TCCard._play(data, key, query,
        TCCard._chosenVoice(data.voices || []), false, season.n, episode.n));
      list.appendChild(row);
    }
    return list;
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
        key: tile.key, title: tile.title, poster: tile.poster,
        caption2: String(tile.year || ''), group: 'related',
        onActivate: (key) => TCRouter.go('/card/' + encodeURIComponent(key)),
      }));
    }
    wrap.append(head, row);
    return wrap;
  },
};

window.TCCardSeries = TCCardSeries;
