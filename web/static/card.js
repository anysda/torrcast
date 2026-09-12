// Карточка картины: 4.3 (фильм) и 4.4 (сериал) - один экран, разница только в
// сезонах/сериях и в подписи года. Верстается СТРОГО под форму ``GET /api/card/{key}``
// из SPEC §6.2: полей «жанры» там нет, и на экране их тоже нет - это разошлось с
// макетом честно, а не по забывчивости.
'use strict';

const TCCard = {
  _voiceKey: 'tc-voice',
  // Сколько долгих переспросов (`wait=1`) карточка делает после первого ответа. Прежний
  // опрос раз в 2 с сдавался после пятого захода, и скелет описания оставался навсегда;
  // долгий заход возвращается только с изменившимся телом.
  _TURNS: 4,
  // Сколько после первого тела описание стоит скелетом: дальше честное «нет описания»,
  // а доехавшее позже встаёт на его место со следующим ответом.
  _PATIENCE: 6000,
  _patient: 0,
  // Ход запуска на ТВ из этой карточки: переживает подмену тела доборами.
  _tvSaid: null,
  // Сколько ждать, пока каст поднимется: холодный рой - это десятки секунд.
  _CAST_WAIT: 150000,

  async mount(root, key) {
    root.replaceChildren();
    const query = new URLSearchParams(location.search).get('query') || '';
    const shell = TCCard._shell(key);
    root.appendChild(shell);
    shell.querySelector('.tc-back').focus();
    if (TCCard._tvSaid && TCCard._tvSaid.done) TCCard._tvSaid = null;
    await TCCard._load(root, key, query);
  },

  async _load(root, key, query) {
    TCCard._patient = 0;
    let data = null;
    for (let turn = 0; turn <= TCCard._TURNS; turn += 1) {
      if (!TCCard._here(root, key)) return;
      const said = await TCApi.card(key, query, turn > 0);
      if (!TCCard._here(root, key)) return;
      if (said.data) data = said.data;
      if (said.missing) data = { error: 'not_found' };
      const last = !said.partial || turn === TCCard._TURNS;
      if (data && !TCCard._patient) {
        TCCard._patient = Date.now() + TCCard._PATIENCE;
        setTimeout(() => TCCard._settle(root, key), TCCard._PATIENCE);
      }
      TCCard._show(root, key, query, data || TCCard._fallback(key), last || TCCard._settled());
      if (last) return;
    }
  },

  _here(root, key) {
    return document.body.contains(root) && location.pathname === '/card/' + encodeURIComponent(key);
  },

  _settled() {
    return TCCard._patient > 0 && Date.now() >= TCCard._patient;
  },

  // Описание ждёт скелетом не дольше `_PATIENCE` после первого тела; дальше - слова.
  _settle(root, key) {
    if (!TCCard._here(root, key)) return;
    const skel = root.querySelector('.tc-detail-skel[data-tc-card-description]');
    if (skel) skel.replaceWith(TCCard._descBlock({ blurb: '' }, true));
  },

  _show(root, key, query, data, settled) {
    const body = root.querySelector('#tc-card-body');
    if (!body) return;
    // Тело карточки подменяется целиком на каждом доборе, и вместе с ним уезжает элемент,
    // на котором СТОЯЛ фокус: зритель с пультом терял место посреди чтения. Место
    // возвращается по классу - своего имени у кнопок нет, а класс у них один и тот же
    // до и после подмены.
    const stood = document.activeElement;
    const held = body.contains(stood) ? stood.className : '';
    body.replaceWith(TCCard._body(data, key, query, settled));
    if (held) TCCard._standAgain(root, held);
  },

  // Вернуть фокус туда же, где он стоял до подмены тела; такой кнопки в новом теле нет -
  // отдать его первой помеченной, чтобы пульт не остался ни на чём.
  _standAgain(root, held) {
    const same = held ? root.querySelector('[data-tc-focusable].' + held.trim().split(/\s+/).join('.')) : null;
    const goes = same || root.querySelector('[data-tc-focusable]');
    if (goes) goes.focus();
  },

  // Что плитка знала о картине в миг клика (`tile.js`): обложка и имя рисуются сразу, а
  // не после круга поиска (холодная карточка на стенде `.104` ждала его 5.4 с).
  _hint(key) {
    try {
      const kept = JSON.parse(sessionStorage.getItem('tc-art:' + key) || 'null');
      return kept && typeof kept === 'object' ? kept : {};
    } catch (_) {
      return {};
    }
  },

  // Карточка не пришла вовсе (отказ поиска, 404, обрыв): вместо вечного скелета - то,
  // что знала плитка, и честные слова «нет описания» и «нет раздач».
  _fallback(key) {
    const hint = TCCard._hint(key);
    return {
      title: hint.title || '', year: hint.year || null, poster: null, blurb: '',
      voices: [], seasons: [], related: [], releases_count: 0,
    };
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

    const hint = TCCard._hint(key);
    const body = document.createElement('div');
    body.id = 'tc-card-body';
    body.className = 'tc-detail-body';
    body.appendChild(TCCard._posterBlock([hint.poster], false, !hint.poster, hint.title));
    body.appendChild(TCCard._loadingInfo(hint.title));

    frame.append(top, body);
    wrap.append(blur, shade, scan, frame);
    return wrap;
  },

  _hue(key) {
    let sum = 0;
    for (const char of String(key)) sum = (sum * 31 + char.charCodeAt(0)) % 360;
    return sum;
  },

  _loadingInfo(named) {
    const info = document.createElement('div');
    info.className = 'tc-detail-info';
    const title = document.createElement('div');
    if (named) {
      title.className = 'tc-title-detail';
      title.textContent = named;
    } else {
      title.className = 'tc-skel-line';
      title.style.height = '5.5rem';
      title.style.width = '60%';
    }
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

  // ``loading`` - карточка ещё не приехала совсем, и обложки плитки тоже нет: пустой
  // список имён при этом ничего не значит про обложку САМОЙ картины.
  _posterBlock(names, isShow, loading, title) {
    const wrap = document.createElement('div');
    wrap.className = 'tc-detail-poster' + (isShow ? ' tc-detail-poster--show' : '');
    const frame = document.createElement('div');
    frame.className = 'tc-tile-frame';
    frame.appendChild(loading ? TCTile.build({ loading: true }).querySelector('.tc-tile-skeleton')
      : TCCard._art([...new Set(names.filter(Boolean))], title));
    wrap.appendChild(frame);
    return wrap;
  },

  // Обложка цепочкой: та, что стояла на плитке, потом своя у карточки; не загрузилась
  // одна - следующая, и лишь когда кончились все, блок «без обложки», как у плитки.
  // Имя карточки считается по её названию в круге и расходилось с именем плитки
  // («Usuzumizakura Garo» против «GARO»): одно это имя давало 404 и пустое место.
  _art(names, title) {
    if (!names.length) {
      return TCTile.build({ poster: null, title, loading: false }).querySelector('.tc-tile-noart');
    }
    const img = document.createElement('img');
    img.className = 'tc-tile-art-img';
    img.alt = '';
    img.src = TCTile.posterUrl(names[0]);
    img.addEventListener('error', () => img.replaceWith(TCCard._art(names.slice(1), title)));
    return img;
  },

  _body(data, key, query, settled) {
    if (data.error === 'not_found') return TCCard._notFound(key, query);
    const isShow = Array.isArray(data.seasons) && data.seasons.length > 0;
    const body = document.createElement('div');
    body.id = 'tc-card-body';
    body.className = 'tc-detail-body';
    const hint = TCCard._hint(key);
    body.appendChild(TCCard._posterBlock([hint.poster, data.poster], isShow, false,
      data.shown || data.title || hint.title));

    const info = document.createElement('div');
    info.className = 'tc-detail-info';
    info.append(...TCCard._titleBlock(data, isShow));
    info.appendChild(TCCard._descBlock(data, settled));
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

  _notFound(key, query) {
    const body = document.createElement('div');
    body.id = 'tc-card-body';
    body.className = 'tc-detail-body';
    const hint = TCCard._hint(key);
    body.appendChild(TCCard._posterBlock([hint.poster], false, false, hint.title));
    const info = document.createElement('div');
    info.className = 'tc-detail-info';
    const title = document.createElement('div');
    title.className = 'tc-title-detail';
    title.textContent = hint.title || '';
    const said = document.createElement('div');
    said.className = 'tc-detail-desc tc-body';
    said.textContent = TC.say('web.detail.not_found');
    const retry = document.createElement('div');
    retry.className = 'tc-secondary';
    retry.textContent = TC.say('web.detail.retry');
    retry.tabIndex = 0;
    retry.dataset.tcFocusable = '1';
    retry.dataset.tcGroup = 'card-refusal';
    retry.setAttribute('role', 'button');
    const again = () => TCCard._load(document.getElementById('tc-root'), key, query);
    retry.addEventListener('click', again);
    retry.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); again(); }
    });
    info.append(title, said, retry);
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
    bits.push({ text: TC.count('web.detail.seasons', data.seasons.length) });
    if (data.rating !== null && data.rating !== undefined) {
      bits.push({ text: TC.say('web.detail.rating', { rating: data.rating }), rating: true });
    }
    return bits;
  },

  // ``settled`` - ждать справку дальше незачем: недоехавшее описание называется словами,
  // а не остаётся скелетом (замер 11-09: скелет стоял после пятого добора навсегда).
  _descBlock(data, settled) {
    if ((data.blurb === null || data.blurb === undefined) && !settled) {
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
    if (!String(data.blurb || '').trim()) {
      const missing = document.createElement('div');
      missing.className = 'tc-detail-desc tc-body';
      missing.dataset.tcCardDescription = '1';
      missing.textContent = TC.say('web.detail.no_description');
      return missing;
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
    // TC-1225. Картина, которая идёт на приёмнике прямо сейчас (`data.playing`, от
    // `WatchState.showing()`), не держит рядом с собой «PLAY ON TV»: карточка не звала бы
    // повторный показ, а звала бы взять уже идущий или закончить его - и НИ ОДНОЙ из этих
    // кнопок тут не стояло, дефект владельца 12-09-2026. «Играть»/«Сначала»/«PLAY ON TV»
    // остаются как были, когда картина не играет: второй набор кнопок им тут не мешает.
    if (data.playing) {
      row.append(TCCard._connect(), TCCard._finish());
      return row;
    }
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
      onTv.dataset.tcCardTv = '1';
      const said = TCCard._tvSaid;
      onTv.textContent = said && said.key === key ? said.text : TC.say('web.detail.play_on_tv');
      onTv.tabIndex = 0;
      onTv.dataset.tcFocusable = '1';
      onTv.dataset.tcGroup = 'buttons';
      // Кнопка стояла нажимаемой и не делала НИЧЕГО: обработчика ей не завели вовсе, в
      // отличие от соседних «Играть» и «Сначала» (замер на стенде `.104` 07-09-2026).
      // Потом её прятали, пока в ящике вкладки нет показа ЭТОЙ картины, и у неигранной
      // картины пути на ТВ не стало вовсе (дефект владельца 11-09-2026). Теперь она есть
      // у всякой картины с раздачами (`_toTv`).
      onTv.addEventListener('click', () => TCCard._toTv(data, key, query, voices));
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

  // TC-1225. Показ уже идёт - вкладка подключается к нему тем же путём, что и шапка
  // «сейчас играет» (`TCPlayer.open`): ящик вкладки уже несёт `url`/`key`/`at` этого
  // показа (TC-1224), и заказывать его заново нечем и незачем.
  _connect() {
    const connect = document.createElement('button');
    connect.type = 'button';
    connect.className = 'tc-btn tc-btn--primary';
    connect.textContent = TC.say('web.detail.connect');
    connect.tabIndex = 0;
    connect.dataset.tcCardConnect = '1';
    connect.dataset.tcFocusable = '1';
    connect.dataset.tcGroup = 'buttons';
    connect.addEventListener('click', () => TCPlayer.open());
    return connect;
  },

  // Завершить - та же дверь, что и «Назад» из плеера идущего показа
  // (:mod:`hass.stopping`): гасит юнит целиком, а не просто уводит эту вкладку.
  _finish() {
    const finish = document.createElement('button');
    finish.type = 'button';
    finish.className = 'tc-btn tc-btn--secondary';
    finish.textContent = TC.say('web.detail.finish');
    finish.tabIndex = 0;
    finish.dataset.tcCardFinish = '1';
    finish.dataset.tcFocusable = '1';
    finish.dataset.tcGroup = 'buttons';
    finish.addEventListener('click', () => TCApi.control('stop'));
    return finish;
  },

  // «На ТВ» всегда новый каст с закладки: поток вкладки, ушедшей с `/play`, сносится через
  // 5 с (`left_after`), и переданный ТВ показ вставал на первом же куске (стенд, 11-09).
  // Закладку до ухода двигала сама вкладка, так что ТВ продолжает с её места.
  async _toTv(data, key, query, voices) {
    const said = TCCard._tvSaid;
    if (said && said.key === key && !said.done) return;
    await TCCard._cast(data, key, query, voices);
  },

  // Новый показ на ТВ - тот же заказ, что у «Играть» (номер в круге, озвучка зрителя), но
  // без `here`: его берёт приёмник из настройки машины (`config.tv`). Вкладке играть
  // нечего, и она остаётся на карточке: ход каста человек видит на самой кнопке
  // («Готовим…», затем «▶ На ТВ») и в шапке, где встаёт «сейчас играет» с названием.
  async _cast(data, key, query, voices) {
    const kept = sessionStorage.getItem(TCCard._voiceKey);
    const picked = kept && (voices || []).some((v) => v.name === kept) ? kept : undefined;
    TCCard._tvSay(key, 'web.player.preparing', false);
    const names = [data.shown, data.title, data.original].filter(Boolean);
    // Показ вкладки с тем же именем ещё секунды «играет» после ухода с `/play`: тогда
    // «На ТВ» только после `starting` нового показа, иначе кнопка врала ~30 с (стенд, 11-09).
    const before = await TCApi.state();
    const stale = !!before && before.state === 'playing' && names.includes(before.title);
    const said = await TCApi.cast({
      query: query || data.title || data.original || key,
      pick: data.pick || undefined,
      voice: picked,
      from_start: false,
    });
    if (!said) {
      TCCard._tvSay(key, 'web.player.refused', true);
      return;
    }
    const until = Date.now() + TCCard._CAST_WAIT;
    let began = false;
    while (Date.now() < until) {
      await new Promise((done) => setTimeout(done, 1000));
      const state = await TCApi.state();
      const now = state && state.state;
      began = began || now === 'starting';
      if (now === 'playing' && (began || (!stale && names.includes(state.title)))) {
        TCCard._tvSay(key, 'web.player.on_tv', true);
        return;
      }
      if (began && now === 'idle') break;
    }
    TCCard._tvSay(key, 'web.player.refused', true);
  },

  _tvSay(key, phrase, done) {
    TCCard._tvSaid = { key, text: TC.say(phrase), done };
    const button = document.querySelector('[data-tc-card-tv]');
    if (button && location.pathname === '/card/' + encodeURIComponent(key)) {
      button.textContent = TCCard._tvSaid.text;
    }
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
    const releases = TC.count('web.detail.release', data.releases_count || 0);
    line.textContent = data.sources_count
      ? releases + ' ' + TC.say('web.detail.from') + ' '
        + TC.count('web.detail.source_from', data.sources_count)
      : releases;
    return line;
  },
};

window.TCCard = TCCard;
