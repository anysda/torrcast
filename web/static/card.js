// Карточка картины: 4.3 (фильм) и 4.4 (сериал) - один экран, разница только в
// сезонах/сериях и в подписи года. Верстается СТРОГО под форму ``GET /api/card/{key}``
// из SPEC §6.2: полей «жанры» там нет, и на экране их тоже нет - это разошлось с
// макетом честно, а не по забывчивости.
'use strict';

const TCCard = {
  _voiceKey: 'tc-voice',
  // Ход запуска на ТВ из этой карточки: переживает подмену тела доборами.
  _tvSaid: null,
  // Сколько ждать, пока каст поднимется: холодный рой - это десятки секунд.
  _CAST_WAIT: 150000,
  // Идущий показ меняет карточку и после первых доборов: не крутить пустой круг
  // запросов, но и не оставить «Завершить» после того, как вкладка ушла.
  _PLAY_POLL: 1000,
  // Сколько карточка доспрашивает дорожки раздачи: потолок отбора у продукта 180 с.
  _VOICES_WAIT: 200000,
  // Номер живого захода на экран: возврат на карточку гасит опросы прошлого визита,
  // иначе их добор подменял бы тело у экрана, который человек видит сейчас.
  _visit: 0,
  // Номер единственного добора этого визита: новый повод освежить карточку отменяет
  // предыдущий долгий ответ, чтобы один показ не умножал опросы `/api/card`.
  _loadId: 0,
  // Тело, стоящее на экране: тихий добор сравнивает с ним ответ и не трогает DOM,
  // пока данные те же.
  _shown: null,
  // Сезон, выбранный ЗРИТЕЛЕМ на этой карточке: подмена тела добором больше не
  // сбрасывает вкладку на первый сезон (дефект возврата TC-1240).
  _picked: null,

  async mount(root, key) {
    TCCard._visit += 1;
    root.replaceChildren();
    const query = new URLSearchParams(location.search).get('query') || '';
    const facts = TCCard._facts();
    TCKept.mark(root, location.pathname + location.search);
    if (TCCard._tvSaid && TCCard._tvSaid.done) TCCard._tvSaid = null;
    // Карточка уже видена - её узлы возвращаются на экран целиком, без скелетов и
    // без ожидания ответа: свежесть доедет тихим добором и подменит тело, если
    // изменилось.
    const kept = TCKept.take(location.pathname + location.search);
    if (kept) {
      TCKept.resume(root, kept);
      TCCard._armConnect(root, TCCard._visit);
      root.querySelector('.tc-back').focus();
      TCCard._load(root, key, query, true, facts);
      return;
    }
    const shell = TCCard._shell(key);
    root.appendChild(shell);
    shell.querySelector('.tc-back').focus();
    TCCard._load(root, key, query, false, facts);
  },

  // Цел ли экран для памяти (`kept.js`): тело собралось - есть раздачи и описание
  // (пусть и «нет описания» словами), и ни один скелет не стоит.
  ready(root) {
    const body = root.querySelector('#tc-card-body');
    if (!body || root.querySelector('.tc-skel-line, .tc-tile-skeleton')) return false;
    const said = body.querySelector('[data-tc-card-description]');
    return !!body.querySelector('.tc-releases') && !!(said && said.textContent.trim());
  },

  async _load(root, key, query, quiet, facts, season) {
    // Перезагрузка без номера (возврат, повтор, показ на ТВ) спрашивает вкладку зрителя:
    // иначе сервер разбирал первый сезон, и серии открытой вкладки приходили пустыми.
    const picked = TCCard._picked && TCCard._picked.key === key ? TCCard._picked.n : undefined;
    season = season || picked;
    const mine = TCCard._visit;
    const load = ++TCCard._loadId;
    let data = null;
    const voicesUntil = Date.now() + TCCard._VOICES_WAIT;
    for (let turn = 0; ; turn += 1) {
      if (mine !== TCCard._visit || load !== TCCard._loadId || !TCCard._here(root, key)) return;
      // Целое тело без дорожек дальше спрашивает только их: долгий заход держится до них.
      const hearing = !!(data && data.voices_pending && !data.searching);
      const said = await TCApi.card(key, query, turn > 0, facts, season, hearing);
      if (mine !== TCCard._visit || load !== TCCard._loadId || !TCCard._here(root, key)) return;
      if (said.data) data = said.data;
      if (data && data.picture && TCRouter._card === key) TCRouter._picture = data.picture;
      // Preview уже честно назвал карточку по фактам плитки. Полный круг иногда не
      // находит его ключ (раздачи успели смениться), и пустой `{ error }` не должен
      // стирать это тело вместе с заголовком, как было у «Вперёд» на 14.8 с.
      if (said.missing && !data) data = TCCard._fallback(key);
      // Дорожки доезжают добором после «Играть», а не держат её: отбор раздачи - это рой.
      const voicesLeft = !!(data && data.voices_pending) && Date.now() < voicesUntil;
      const last = !said.partial && !voicesLeft;
      // Карточка идущего показа опрашивает дальше и после целого ответа: поток вкладки,
      // ушедшей с ``/play``, сносится через секунды, и тело должно услышать смерть
      // показа само. Без этого «Завершить» и возврат из плеера оставляли бы кнопки
      // застывшими до перезагрузки (замер на стенде `.107`, TC-1240).
      const busy = !!(data && data.playing);
      // Заказ с этой карточки уже назван мостом `starting`, но отметка показа ещё
      // может прийти только следующим ответом карточки. Держим один добор до неё,
      // иначе полный ответ до старта обрывал опрос и кнопки отставали до кадра.
      const waiting = !!(TCCard._tvSaid && TCCard._tvSaid.key === key && !TCCard._tvSaid.done);
      if (quiet) {
        // Тихий добор не сносит стоящее тело ничем: ни отказом, ни кусочным ответом -
        // только ЦЕЛИКОМ изменившийся ответ, и никогда скелетом.
        const settled = TCCard._keepKnown(key, query, data);
        if (settled && !said.partial && !TCCard._same(key, query, settled)) {
          TCCard._show(root, key, query, settled, true);
        }
        if (last && !busy && !waiting) return;
      } else {
        const shown = TCCard._keepKnown(key, query, data || TCCard._fallback(key));
        if (!TCCard._same(key, query, shown)) {
          TCCard._show(root, key, query, shown);
        }
        if (last && !busy && !waiting) return;
      }
      // У полного ответа `wait=1` возвращается сразу. Пауза нужна только живому
      // показу, иначе пять таких ответов исчерпывали счётчик за один миг.
      if (busy || waiting) await new Promise((done) => setTimeout(done, TCCard._PLAY_POLL));
    }
  },

  // Тот же ли ответ, из которого стоит текущее тело: DOM при равенстве не трогается.
  _same(key, query, data) {
    const was = TCCard._shown;
    return !!was && was.key === key && was.query === query
      && JSON.stringify(was.data) === JSON.stringify(data);
  },

  // Долгий ответ уточняет preview, но не вправе стереть уже увиденное, если источник
  // опоздал или полный круг назвал картину иначе. Новые непустые данные по-прежнему
  // побеждают, а пустота и недоезд остаются на скелете только до первого показа.
  _keepKnown(key, query, next) {
    const was = TCCard._shown;
    if (!next || !was || was.key !== key || was.query !== query) return next;
    const old = was.data || {};
    const kept = { ...next };
    if (String(old.blurb || '').trim() && !String(kept.blurb || '').trim()) {
      kept.blurb = old.blurb;
    }
    if (Array.isArray(old.related) && old.related.length > 0
      && (!Array.isArray(kept.related) || kept.related.length === 0)) {
      kept.related = old.related;
    }
    return kept;
  },

  _here(root, key) {
    return document.body.contains(root) && TCCard._onCard(key);
  },

  // Маршрут нормализован: ``:`` в ключе браузер оставляет как есть, а не ``%3A``.
  _onCard(key) {
    const route = location.pathname;
    return route.startsWith('/card/') && decodeURIComponent(route.slice('/card/'.length)) === key;
  },

  _facts() {
    const values = new URLSearchParams(location.search);
    const title = values.get('title');
    const year = values.get('year');
    const kind = values.get('kind');
    return title && year && kind ? { title, shown: values.get('shown') || '', year, kind } : null;
  },

  _season(key, query, season) {
    const root = document.getElementById('tc-root');
    if (root && TCCard._here(root, key)) {
      TCCard._load(root, key, query, false, TCCard._facts(), season);
    }
  },

  _show(root, key, query, data) {
    const body = root.querySelector('#tc-card-body');
    if (!body) return;
    // Тело карточки подменяется целиком на каждом доборе, и вместе с ним уезжает элемент,
    // на котором СТОЯЛ фокус: зритель с пультом терял место посреди чтения. Место
    // возвращается по классу - своего имени у кнопок нет, а класс у них один и тот же
    // до и после подмены.
    const stood = document.activeElement;
    const held = body.contains(stood) ? stood.className : '';
    const next = TCCard._body(data, key, query);
    TCCard._keepPoster(body, next);
    body.replaceWith(next);
    TCCard._shown = { key, query, data };
    if (held) TCCard._standAgain(root, held);
  },

  // Добор меняет кнопки и метку просмотра, но та же обложка не должна мигать и
  // повторно ходить в сеть. Переносим ЕЁ узел только при том же адресе: новая
  // картинка всё же обязана встать новой.
  _keepPoster(body, next) {
    const was = body.querySelector('.tc-detail-poster');
    const becomes = next.querySelector('.tc-detail-poster');
    const oldImg = was && was.querySelector('img');
    const newImg = becomes && becomes.querySelector('img');
    if (was && becomes && oldImg && newImg && oldImg.currentSrc === newImg.src) {
      becomes.replaceWith(was);
    }
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
      title: hint.title || '', year: hint.year || null, poster: null, blurb: null,
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

  _body(data, key, query) {
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
    info.appendChild(TCCard._descBlock(data));
    info.appendChild(TCCard._buttons(data, key, query, isShow));
    if (isShow) {
      // Вкладка после подмены тела остаётся ТОЙ ЖЕ, что выбрал зритель: без этого
      // каждый добор возвращал карточку к первому сезону посреди чтения.
      const picked = TCCard._picked && TCCard._picked.key === key
        ? data.seasons.findIndex((season) => season.n === TCCard._picked.n) : -1;
      // Без выбора зрителя открыт сезон закладки (как у сервера), иначе первый.
      const bookmark = TCCardSeries._resumeEpisodeNumber(data).season;
      const resumed = data.seasons.findIndex((season) => season.n === bookmark);
      const firstSeason = data.seasons.findIndex((season) => season.n === 1);
      const fallback = resumed >= 0 ? resumed : firstSeason < 0 ? 0 : firstSeason;
      const selected = picked >= 0 ? picked : fallback;
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
    const again = () => TCCard._load(document.getElementById('tc-root'), key, query, false);
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

  // ``null`` значит, что источник ещё не ответил. Только подтверждённая пустая строка
  // вправе стать словами об отсутствии статьи.
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
    const noReleases = data.searching || (data.releases_count || 0) === 0;
    // «Играть» не ждёт круга карточки: раздачу ищет и выбирает показ по нажатию.
    const noPlay = !data.searching && (data.releases_count || 0) === 0;

    const voices = Array.isArray(data.voices) ? data.voices : [];
    const chosen = TCCard._chosenVoice(voices);

    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'tc-btn tc-btn--primary' + (noPlay ? ' tc-btn--disabled' : '');
    play.dataset.tcPlay = '1';
    play.textContent = TC.say('web.detail.play');
    play.disabled = noPlay;
    play.tabIndex = noPlay ? -1 : 0;
    play.dataset.tcFocusable = noPlay ? undefined : '1';
    play.dataset.tcGroup = 'buttons';
    if (!noPlay) {
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

    if (!noReleases && data.tv) {
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

    if (noReleases && !data.searching) {
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

  // Показ уже поднят - вкладка подключается к нему тем же путём, что и шапка
  // «сейчас играет» (`TCPlayer.open`). Но WatchState ставит `data.playing` раньше
  // первого кадра; готовность берём из `state === 'playing'`, тем же признаком, которым
  // шапка не называет телевизор идущим преждевременно.
  _connect() {
    const connect = document.createElement('button');
    connect.type = 'button';
    connect.className = 'tc-btn tc-btn--primary tc-btn--disabled';
    connect.textContent = TC.say('web.detail.connect');
    connect.disabled = true;
    connect.setAttribute('aria-disabled', 'true');
    connect.tabIndex = -1;
    connect.dataset.tcCardConnect = '1';
    connect.dataset.tcGroup = 'buttons';
    connect.addEventListener('click', () => TCPlayer.open());
    const visit = TCCard._visit;
    requestAnimationFrame(() => TCCard._waitConnect(connect, visit));
    return connect;
  },

  async _waitConnect(connect, visit) {
    while (TCCard._visit === visit && connect.isConnected && connect.disabled) {
      const state = await TCApi.state();
      if (TCCard._visit !== visit || !connect.isConnected || !connect.disabled) return;
      if (state && state.state === 'playing') {
        connect.classList.remove('tc-btn--disabled');
        connect.disabled = false;
        connect.removeAttribute('aria-disabled');
        connect.tabIndex = 0;
        connect.dataset.tcFocusable = '1';
        return;
      }
      await new Promise((done) => setTimeout(done, TCCard._PLAY_POLL));
    }
  },

  _armConnect(root, visit) {
    const connect = root.querySelector('[data-tc-card-connect]');
    if (!connect) return;
    connect.classList.add('tc-btn--disabled');
    connect.disabled = true;
    connect.setAttribute('aria-disabled', 'true');
    connect.tabIndex = -1;
    delete connect.dataset.tcFocusable;
    requestAnimationFrame(() => TCCard._waitConnect(connect, visit));
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
    // Своя остановка не отказ: ожидание каста видит снятую надпись и молча уходит.
    finish.addEventListener('click', () => {
      TCCard._tvSaid = null;
      TCApi.control('stop');
    });
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

  // Новый показ на ТВ - тот же заказ, что у «Играть» (ключи карточки, озвучка зрителя), но
  // без `here`: его берёт приёмник из настройки машины (`config.tv`). Вкладке играть
  // нечего, и она остаётся на карточке: ход каста человек видит на самой кнопке
  // («Готовим…», затем «▶ На ТВ») и в шапке, где встаёт «сейчас играет» с названием.
  async _cast(data, key, query, voices) {
    const kept = sessionStorage.getItem(TCCard._voiceKey);
    const picked = kept && (voices || []).some((v) => v.name === kept) ? kept : undefined;
    TCCard._tvSay(key, 'web.player.preparing', false);
    const asked = TCCard._tvSaid;
    const names = [data.shown, data.title, data.original].filter(Boolean);
    // Показ вкладки с тем же именем ещё секунды «играет» после ухода с `/play`: тогда
    // «На ТВ» только после `starting` нового показа, иначе кнопка врала ~30 с (стенд, 11-09).
    const before = await TCApi.state();
    const stale = !!before && before.state === 'playing' && names.includes(before.title);
    const said = await TCApi.cast({
      query: query || data.title || data.original || key,
      ...TCCard._keys(data, key),
      voice: picked,
      from_start: false,
    });
    if (!said) {
      TCCard._tvSay(key, 'web.player.refused', true);
      return;
    }
    const until = Date.now() + TCCard._CAST_WAIT;
    let began = false;
    let changed = false;
    while (Date.now() < until) {
      await new Promise((done) => setTimeout(done, 1000));
      const state = await TCApi.state();
      const now = state && state.state;
      began = began || now === 'starting';
      // Новый заказ пришёл уже ПОСЛЕ последнего добора карточки. Как только мост назвал
      // его своим, пересобираем её: иначе на самой карточке оставалась «На ТВ», хотя
      // состояние уже требовало «Подключиться»/«Завершить».
      const mine = began || (!stale && names.includes(state && state.title));
      if ((now === 'starting' && !changed) || (now === 'playing' && mine)) {
        const root = document.getElementById('tc-root');
        if (root && TCCard._here(root, key)) TCCard._load(root, key, query, false);
        changed = true;
      }
      // Идущий показ кнопку «На ТВ» прячет, а после его конца она снова своя: старая
      // надпись «▶ На ТВ» на ней уже врёт.
      if (now === 'playing' && mine) {
        TCCard._tvSay(key, 'web.player.on_tv', true);
        TCCard._tvSaid = null;
        return;
      }
      if (TCCard._tvSaid !== asked) return;
      if (began && now === 'idle') break;
    }
    TCCard._tvSay(key, 'web.player.refused', true);
  },

  _tvSay(key, phrase, done) {
    TCCard._tvSaid = { key, text: TC.say(phrase), done };
    const button = document.querySelector('[data-tc-card-tv]');
    if (button && TCCard._onCard(key)) {
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
      // Подпись дорожки на языке страницы; `name` - то, что уйдёт показу как `voice`.
      name.textContent = voice.label || voice.name;
      row.append(name);
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

  // Озвучку продукту называет ЗРИТЕЛЬ, и только он. Список карточки - дорожки раздачи,
  // отобранной фоном, а показ отбирает свою заново: послать первую строку списка как
  // `voice` значит связать ему руки, и вместо показа приходит отказ «no “Есарев” voice
  // track in this release» (замерено на стенде `.104`, показ не поднялся ни разу).
  // Выбор читается прямо в клике: сделанный ПОСЛЕ отрисовки кнопки, в замыкании он
  // остался бы прежним.
  _play(data, key, query, voices, fromStart, season, episode) {
    const kept = sessionStorage.getItem(TCCard._voiceKey);
    const known = kept && (voices || []).some((v) => v.name === kept) ? kept : undefined;
    // Серию сезона показ отбирает сам, как отбирал её вкладке: раздача карточки взята без
    // сезона, и её номер дорожки в чужой раздаче значит другое.
    const picked = season && /^\d+$/.test(known || '') ? undefined : known;
    const keys = TCCard._keys(data, key);
    TCApi.play({
      query: query || data.title || data.original || key,
      // 🔴 Картина обязана быть названа: без неё показ брал бы ту, которую круг
      // считает главной по запросу, а не ту, которую человек открыл. Карточка второй
      // находки запускала первую, и виднее всего это на полке - плитка «Bones and All»
      // зовётся запросом, у которого в круге две картины (замер `.104` 07-09-2026).
      picture: keys.picture,
      release: season ? undefined : keys.release,
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

  // Чем показ узнает картину и раздачу карточки: ключами, а не номером в выдаче. Номер
  // гуляет от круга к кругу («Вверх» под номером 1 получал «Руки вверх!»), ключ - нет.
  // Раздачи карточка могла ещё не выбрать: тогда показ выбирает её сам по ключу картины.
  _keys(data, key) {
    return { picture: data.picture || key, release: data.release || undefined };
  },

  _releases(data) {
    const line = document.createElement('div');
    line.className = 'tc-releases';
    if (data.searching) {
      line.textContent = TC.say('web.detail.searching_releases');
      return line;
    }
    const releases = TC.count('web.detail.release', data.releases_count || 0);
    line.textContent = data.sources_count
      ? releases + ' ' + TC.say('web.detail.from') + ' '
        + TC.count('web.detail.source_from', data.sources_count)
      : releases;
    return line;
  },
};

window.TCCard = TCCard;
