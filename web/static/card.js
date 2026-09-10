// Карточка картины: 4.3 (фильм) и 4.4 (сериал) - один экран, разница только в
// сезонах/сериях и в подписи года. Верстается СТРОГО под форму ``GET /api/card/{key}``
// из SPEC §6.2: полей «жанры» там нет, и на экране их тоже нет - это разошлось с
// макетом честно, а не по забывчивости.
'use strict';

const TCCard = {
  _tries: 0,
  _voiceKey: 'tc-voice',

  async mount(root, key) {
    root.replaceChildren();
    const query = new URLSearchParams(location.search).get('query') || '';
    const shell = TCCard._shell(key);
    root.appendChild(shell);
    shell.querySelector('.tc-back').focus();

    TCCard._tries = 0;
    await TCCard._load(root, key, query);
  },

  async _load(root, key, query) {
    if (!document.body.contains(root) || location.pathname !== '/card/' + encodeURIComponent(key)) {
      return;
    }
    const { data, partial } = await TCApi.card(key, query);
    const body = root.querySelector('#tc-card-body');
    if (!body) return;
    // Тело карточки подменяется целиком на каждом доборе (до пяти раз), и вместе с ним
    // уезжает элемент, на котором СТОЯЛ фокус: зритель с пультом терял место посреди
    // чтения. Место возвращается по классу - своего имени у кнопок нет, а класс у них
    // один и тот же до и после подмены.
    const stood = document.activeElement;
    const held = body.contains(stood) ? stood.className : '';
    if (data) body.replaceWith(TCCard._body(data, key, query));
    if (held) TCCard._standAgain(root, held);
    if (partial && TCCard._tries < 5) {
      TCCard._tries += 1;
      setTimeout(() => TCCard._load(root, key, query), 2000);
    }
  },

  // Вернуть фокус туда же, где он стоял до подмены тела; такой кнопки в новом теле нет -
  // отдать его первой помеченной, чтобы пульт не остался ни на чём.
  _standAgain(root, held) {
    const same = held ? root.querySelector('[data-tc-focusable].' + held.trim().split(/\s+/).join('.')) : null;
    const goes = same || root.querySelector('[data-tc-focusable]');
    if (goes) goes.focus();
  },

  _shell(key) {
    const wrap = document.createElement('div');
    wrap.className = 'tc-detail';
    wrap.dataset.tcCard = '1';
    const blur = document.createElement('div');
    blur.className = 'tc-detail-blur';
    blur.style.setProperty('--tc-hue', String(TCCard._hue(key)));
    const shade = document.createElement('div');
    shade.className = 'tc-detail-shade';
    const scan = document.createElement('div');
    scan.className = 'tc-scan';
    const frame = document.createElement('div');
    frame.className = 'tc-detail-frame';

    const top = document.createElement('div');
    top.className = 'tc-detail-top';
    const back = document.createElement('div');
    back.className = 'tc-back';
    back.textContent = TC.say('web.detail.back');
    back.tabIndex = 0;
    back.dataset.tcFocusable = '1';
    back.dataset.tcGroup = 'top';
    back.setAttribute('role', 'button');
    const activate = () => history.back();
    back.addEventListener('click', activate);
    back.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
    });
    const brand = document.createElement('div');
    brand.className = 'tc-brand';
    brand.textContent = 'Torrcast';
    top.append(back, brand);

    const body = document.createElement('div');
    body.id = 'tc-card-body';
    body.className = 'tc-detail-body';
    body.appendChild(TCCard._posterBlock(null, false, true));
    body.appendChild(TCCard._loadingInfo());

    frame.append(top, body);
    wrap.append(blur, shade, scan, frame);
    return wrap;
  },

  _hue(key) {
    let sum = 0;
    for (const char of String(key)) sum = (sum * 31 + char.charCodeAt(0)) % 360;
    return sum;
  },

  _loadingInfo() {
    const info = document.createElement('div');
    info.className = 'tc-detail-info';
    const title = document.createElement('div');
    title.className = 'tc-skel-line';
    title.style.height = '5.5rem';
    title.style.width = '60%';
    const skel = document.createElement('div');
    skel.className = 'tc-detail-skel';
    for (const width of ['100%', '93%', '56%']) {
      const line = document.createElement('div');
      line.className = 'tc-skel-line';
      line.style.width = width;
      skel.appendChild(line);
    }
    info.append(title, skel);
    return info;
  },

  // ``loading`` - карточка ещё не приехала совсем; ``poster`` пустой при этом ничего
  // не значит про обложку САМОЙ картины - тем и отличается от «обложки честно нет».
  _posterBlock(poster, isShow, loading) {
    const wrap = document.createElement('div');
    wrap.className = 'tc-detail-poster' + (isShow ? ' tc-detail-poster--show' : '');
    const frame = document.createElement('div');
    frame.className = 'tc-tile-frame';
    frame.appendChild(loading ? TCTile.build({ loading: true }).querySelector('.tc-tile-skeleton')
      : TCTile.build({ poster, loading: false }).querySelector('.tc-tile-art-img, .tc-tile-noart'));
    wrap.appendChild(frame);
    return wrap;
  },

  _body(data, key, query) {
    const isShow = Array.isArray(data.seasons) && data.seasons.length > 0;
    const body = document.createElement('div');
    body.id = 'tc-card-body';
    body.className = 'tc-detail-body';
    body.appendChild(TCCard._posterBlock(data.poster, isShow, false));

    const info = document.createElement('div');
    info.className = 'tc-detail-info';
    info.append(...TCCard._titleBlock(data, isShow));
    info.appendChild(TCCard._descBlock(data));
    info.appendChild(TCCard._buttons(data, key, query, isShow));
    if (isShow) {
      const firstSeason = data.seasons.findIndex((season) => season.n === 1);
      const selected = firstSeason < 0 ? 0 : firstSeason;
      info.append(TCCardSeries.tabs(data, key, query, selected),
        TCCardSeries.episodes(data, selected, key, query));
    }
    // Серии и франшиза - разные полки, и сериалу положены обе (ТЗ §8): пока полка родни
    // стояла в `else`, она не рисовалась сериалу вовсе. На стенде `.104` 10-09-2026 это
    // и было пустое место под «Чужим»: лучшее совпадение продукта - `tv:чужой:2021`,
    // и шесть частей франшизы приезжали в `related`, но до страницы не доходили.
    if (Array.isArray(data.related) && data.related.length > 0) {
      info.appendChild(TCCardSeries.related(data));
    }
    info.appendChild(TCCard._releases(data));
    body.appendChild(info);
    return body;
  },

  _titleBlock(data, isShow) {
    const title = document.createElement('div');
    title.className = 'tc-title-detail';
    title.textContent = data.shown || data.title || '';
    if (isShow) {
      const row = document.createElement('div');
      row.className = 'tc-detail-title-row';
      const meta = document.createElement('div');
      meta.className = 'tc-meta';
      meta.append(...TCCard._metaBits(TCCard._showMeta(data)));
      row.append(title, meta);
      return [row];
    }
    const meta = document.createElement('div');
    meta.className = 'tc-detail-meta';
    if (data.original && data.original !== (data.shown || data.title)) {
      const orig = document.createElement('div');
      orig.className = 'tc-orig';
      orig.textContent = data.original;
      meta.appendChild(orig);
      meta.appendChild(TCCard._dot());
    }
    const line = document.createElement('div');
    line.className = 'tc-meta';
    line.append(...TCCard._metaBits(TCCard._movieMeta(data)));
    meta.appendChild(line);
    return [title, meta];
  },

  _dot() {
    const dot = document.createElement('div');
    dot.className = 'tc-dot';
    return dot;
  },

  // Строка «2024 · 2 ч 49 мин · IMDb 8.5» собрана из отдельных узлов, а не одной
  // строкой: рейтингу нужен свой узел (``data-tc-card-rating``) для прибора приёмки.
  _metaBits(bits) {
    const nodes = [];
    bits.forEach((bit, index) => {
      if (index > 0) nodes.push(document.createTextNode(' · '));
      const span = document.createElement('span');
      if (bit.rating) span.dataset.tcCardRating = '1';
      span.textContent = bit.text;
      nodes.push(span);
    });
    return nodes;
  },

  _movieMeta(data) {
    const bits = [];
    if (data.year) bits.push({ text: String(data.year) });
    const runtime = TCTime.runtimeWords(data.runtime);
    if (runtime) bits.push({ text: data.runtime_estimated ? '~' + runtime : runtime });
    if (data.rating !== null && data.rating !== undefined) {
      bits.push({ text: TC.say('web.detail.rating', { rating: data.rating }), rating: true });
    }
    return bits;
  },

  _showMeta(data) {
    const bits = [];
    if (data.year) bits.push({ text: String(data.year) });
    bits.push({ text: TC.say('web.detail.seasons', { n: data.seasons.length }) });
    if (data.rating !== null && data.rating !== undefined) {
      bits.push({ text: TC.say('web.detail.rating', { rating: data.rating }), rating: true });
    }
    return bits;
  },

  _descBlock(data) {
    if (data.blurb === null || data.blurb === undefined) {
      const skel = document.createElement('div');
      skel.className = 'tc-detail-skel';
      skel.dataset.tcCardDescription = '1';
      for (const width of ['100%', '93%', '56%']) {
        const line = document.createElement('div');
        line.className = 'tc-skel-line';
        line.style.width = width;
        skel.appendChild(line);
      }
      return skel;
    }
    const desc = document.createElement('div');
    desc.className = 'tc-detail-desc tc-body';
    desc.dataset.tcCardDescription = '1';
    desc.style.display = '-webkit-box';
    desc.style.webkitBoxOrient = 'vertical';
    desc.style.webkitLineClamp = '5';
    desc.style.overflow = 'hidden';
    desc.textContent = data.blurb + ' ';
    const more = document.createElement('span');
    more.className = 'tc-more';
    more.textContent = TC.say('web.detail.more');
    more.tabIndex = 0;
    more.dataset.tcFocusable = '1';
    more.dataset.tcGroup = 'desc-more';
    more.addEventListener('click', () => {
      desc.style.webkitLineClamp = 'unset';
      desc.style.overflow = 'visible';
      more.remove();
    });
    desc.appendChild(more);
    return desc;
  },

  _buttons(data, key, query, isShow) {
    const row = document.createElement('div');
    row.className = 'tc-buttons';
    const noReleases = (data.releases_count || 0) === 0;

    const voices = Array.isArray(data.voices) ? data.voices : [];
    const chosen = TCCard._chosenVoice(voices);

    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'tc-btn tc-btn--primary' + (noReleases ? ' tc-btn--disabled' : '');
    play.dataset.tcPlay = '1';
    play.textContent = TC.say('web.detail.play');
    play.disabled = noReleases;
    play.tabIndex = noReleases ? -1 : 0;
    play.dataset.tcFocusable = noReleases ? undefined : '1';
    play.dataset.tcGroup = 'buttons';
    if (!noReleases) {
      play.addEventListener('click', () => TCCard._play(data, key, query, voices, false));
    }
    row.appendChild(play);

    if (data.resumable) {
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'tc-btn tc-btn--secondary';
      again.textContent = TC.say('web.detail.start_over');
      again.tabIndex = 0;
      again.dataset.tcFocusable = '1';
      again.dataset.tcGroup = 'buttons';
      again.addEventListener('click', () => TCCard._play(data, key, query, voices, true));
      row.appendChild(again);
    }

    if (!noReleases) {
      const onTv = document.createElement('button');
      onTv.type = 'button';
      onTv.className = 'tc-btn tc-btn--secondary';
      onTv.textContent = TC.say('web.detail.play_on_tv');
      onTv.tabIndex = 0;
      onTv.dataset.tcFocusable = '1';
      onTv.dataset.tcGroup = 'buttons';
      // Кнопка стояла нажимаемой и не делала НИЧЕГО: обработчика ей не завели вовсе, в
      // отличие от соседних «Играть» и «Сначала» (замер на стенде `.104` 07-09-2026).
      onTv.addEventListener('click', () => {
        TCApi.toTv().then((said) => { if (said) TCRouter.go('/play'); });
      });
      // ТЗ §5: кнопка есть только там, где показ ЭТОЙ картины уже идёт в браузере - на ТВ
      // передаётся идущий поток, а не новый показ, и над неигранной картиной она обещала
      // бы несуществующее. Карточка про показ не знает, поле это не её: спрашивается ящик
      // вкладки - тот же, из которого показ берёт плеер. Скрытую кнопку обходит и пульт
      // (`nav.js` отсеивает по `offsetParent`), так что второго запрета не нужно.
      onTv.hidden = true;
      TCApi.box().then((box) => {
        const shown = box && box.url ? String(box.title || '') : '';
        onTv.hidden = !shown || (shown !== data.title && shown !== data.original);
      });
      row.appendChild(onTv);
    }

    if (voices.length > 0) row.appendChild(TCCard._audio(voices, chosen));

    if (noReleases) {
      const norel = document.createElement('div');
      norel.className = 'tc-norel';
      const mark = document.createElement('div');
      mark.className = 'tc-norel-mark';
      mark.textContent = '!';
      const text = document.createElement('div');
      text.textContent = TC.say('web.detail.no_releases');
      norel.append(mark, text);
      row.appendChild(norel);
    } else if (data.resumable && data.label) {
      const time = TCCard._resumeTime(data);
      if (time) {
        const resumes = document.createElement('div');
        resumes.className = 'tc-resumes';
        resumes.textContent = TC.say('web.detail.resumes', { label: data.label, time });
        row.appendChild(resumes);
      }
    }
    return row;
  },

  // Позиция возобновления есть только у сериалов, и только внутри найденной серии
  // (``seasons[].episodes[].pos``): у фильма контракт карточки её не отдаёт нигде.
  _resumeTime(data) {
    const match = /s\s*(\d{1,2})\s*[.\-_ ]?\s*e\s*(\d{1,3})/i.exec(data.label || '');
    if (!match || !Array.isArray(data.seasons)) return null;
    const season = data.seasons.find((s) => s.n === Number(match[1]));
    const episode = season && season.episodes.find((e) => e.n === Number(match[2]));
    return episode && episode.pos ? TCTime.clock(episode.pos) : null;
  },

  // Отмечена та, что выбрал бы продукт (`default` от карточки), пока зритель не назвал
  // свою. Это ПОДСКАЗКА, а не заказ: в запуск она не уходит - показ ищет раздачу заново
  // и берёт дорожку той, которую нашёл (см. `_play`).
  _chosenVoice(voices) {
    const kept = sessionStorage.getItem(TCCard._voiceKey);
    const mine = kept ? voices.find((v) => v.name === kept) : null;
    return mine || voices.find((v) => v.default) || null;
  },

  _audio(voices, chosen) {
    const wrap = document.createElement('div');
    wrap.style.position = 'relative';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tc-btn tc-btn--accent';
    button.textContent = TC.say('web.detail.audio');
    button.tabIndex = 0;
    button.dataset.tcFocusable = '1';
    button.dataset.tcGroup = 'buttons';
    const drop = document.createElement('div');
    drop.className = 'tc-drop';
    drop.style.position = 'absolute';
    drop.style.top = 'calc(100% + 0.875rem)';
    drop.style.right = '0';
    drop.style.display = 'none';
    drop.style.zIndex = '30';
    for (const voice of voices) {
      const row = document.createElement('div');
      row.className = 'tc-drop-row' + (voice === chosen ? ' is-selected' : '');
      row.tabIndex = 0;
      row.dataset.tcFocusable = '1';
      row.dataset.tcGroup = 'audio-drop';
      row.dataset.tcAudioOption = '1';
      row.setAttribute('role', 'button');
      const name = document.createElement('div');
      name.className = 'tc-drop-name';
      name.textContent = voice.name;
      const meta = document.createElement('div');
      meta.className = 'tc-drop-meta';
      meta.textContent = [voice.quality, voice.seeders].filter((v) => v).join(' · ');
      row.append(name, meta);
      const pick = () => {
        sessionStorage.setItem(TCCard._voiceKey, voice.name);
        drop.style.display = 'none';
        wrap.replaceWith(TCCard._audio(voices, voice));
      };
      row.addEventListener('click', pick);
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); pick(); }
      });
      drop.appendChild(row);
    }
    button.addEventListener('click', () => {
      drop.style.display = drop.style.display === 'none' ? 'block' : 'none';
    });
    wrap.append(button, drop);
    return wrap;
  },

  // Озвучку продукту называет ЗРИТЕЛЬ, и только он. Список карточки собран по всему кругу
  // раздач, а раздачу показ выбирает своим поиском: послать первую строку списка как
  // `voice` значит связать ему руки, и вместо показа приходит отказ «no “Есарев” voice
  // track in this release» (замерено на стенде `.104`, показ не поднялся ни разу).
  // Выбор читается прямо в клике: сделанный ПОСЛЕ отрисовки кнопки, в замыкании он
  // остался бы прежним.
  _play(data, key, query, voices, fromStart, season, episode) {
    const kept = sessionStorage.getItem(TCCard._voiceKey);
    const picked = kept && (voices || []).some((v) => v.name === kept) ? kept : undefined;
    TCApi.play({
      query: query || data.title || data.original || key,
      // 🔴 Номер картины В КРУГЕ обязателен: без него показ брал бы ту, которую круг
      // считает главной по запросу, а не ту, которую человек открыл. Карточка второй
      // находки запускала первую, и виднее всего это на полке - плитка «Bones and All»
      // зовётся запросом, у которого в круге две картины (замер `.104` 07-09-2026).
      pick: data.pick || undefined,
      voice: picked,
      from_start: fromStart,
      season,
      episode,
      // Играть просит СТРАНИЦА, а не ``config.tv``: настройка машины остаётся прежней, и
      // следующий ``cast`` без вкладки снова пойдёт на телевизор (задача «каста в браузер
      // нет» - страница сама плеер, а не пульт до чужого экрана).
      here: true,
    });
  },

  _releases(data) {
    const line = document.createElement('div');
    line.className = 'tc-releases';
    line.textContent = TC.say('web.detail.releases',
      { n: data.releases_count || 0, m: data.sources_count || 0 });
    return line;
  },
};

window.TCCard = TCCard;
