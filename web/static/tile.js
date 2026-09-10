// Одна плитка (Tile.dc.html) как настоящий DOM-узел. Обложки своей у четверти находок
// нет, и это штатное состояние: тогда рисуется кислотный блок с названием, а не дыра.
// Настоящее фото и мокаповый градиент - РАЗНЫЕ вещи: градиент из макета сюда не идёт
// вовсе, только фото или типографский блок без него.
'use strict';

const TCTile = {
  // shape: {key, title, year, kind, poster, query, caption2, best, progress,
  //         group, loading, onActivate}
  build(shape) {
    const tile = document.createElement('div');
    tile.className = 'tc-tile';
    tile.dataset.tcTile = '1';
    if (shape.group) tile.dataset.tcGroup = shape.group;
    // Пометка для прогрева (`warm.js`) - ТОТ ЖЕ запрос, с которым откроется карточка:
    // другого источника у неё нет, и разойтись им негде. Стоит на самой плитке, потому
    // что видно на экране именно её, а не строку списка.
    if (shape.query) tile.dataset.tcWarm = shape.query;
    if (!shape.loading) {
      tile.tabIndex = 0;
      tile.dataset.tcFocusable = '1';
      tile.setAttribute('role', 'button');
    }

    const frame = document.createElement('div');
    frame.className = 'tc-tile-frame';
    tile.appendChild(frame);

    if (shape.loading) {
      const skeleton = document.createElement('div');
      skeleton.className = 'tc-tile-skeleton';
      frame.appendChild(skeleton);
      return tile;
    }

    frame.appendChild(TCTile._art(shape));
    frame.appendChild(TCTile._scan());
    // В углу обложки стоит ГОД, а не разрешение файла: год отличает одно название от
    // его же переснятой копии, а разрешение к выбору картины отношения не имеет и
    // всё равно выбирается позже, на самой карточке.
    if (shape.year) frame.appendChild(TCTile._badge('tc-tile-year', String(shape.year)));
    if (shape.best) frame.appendChild(TCTile._badge('tc-tile-best', TC.say('web.search.best_match')));
    if (shape.progress !== undefined && shape.progress !== null) {
      frame.appendChild(TCTile._progress(shape.progress));
    }
    for (const corner of ['tl', 'tr', 'bl', 'br']) {
      const mark = document.createElement('div');
      mark.className = 'tc-tile-corner tc-tile-corner--' + corner;
      frame.appendChild(mark);
    }

    tile.appendChild(TCTile._caption(shape));

    if (shape.onActivate) {
      const go = () => shape.onActivate(shape.key, shape.query);
      tile.addEventListener('click', go);
      tile.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          go();
        }
      });
    }
    return tile;
  },

  // Выдача и полки отдают ИМЯ картинки, а не адрес: байты лежат за существующим
  // маршрутом `/api/poster/{name}` (`hass/serve.py`). Ставить имя в `src` как есть
  // значит просить его от текущей папки: с `/card/{key}` это `/card/{name}`, что
  // отвечает оболочкой страницы с кодом 200, и обложка молча пропадает у всех.
  posterUrl(name) {
    return '/api/poster/' + encodeURIComponent(name);
  },

  _art(shape) {
    if (shape.poster) {
      const img = document.createElement('img');
      img.className = 'tc-tile-art-img';
      img.loading = 'lazy';
      img.alt = '';
      img.src = TCTile.posterUrl(shape.poster);
      img.addEventListener('error', () => {
        img.replaceWith(TCTile._noArt(shape.title));
      });
      return img;
    }
    return TCTile._noArt(shape.title);
  },

  _noArt(title) {
    const block = document.createElement('div');
    block.className = 'tc-tile-noart';
    const label = document.createElement('div');
    label.className = 'tc-tile-noart-title';
    label.textContent = title || '';
    const mark = document.createElement('div');
    mark.className = 'tc-tile-noart-mark';
    const square = document.createElement('span');
    square.className = 'tc-tile-noart-square';
    const word = document.createElement('span');
    word.textContent = TC.say('web.tile.no_art');
    mark.append(square, word);
    block.append(label, mark);
    return block;
  },

  _scan() {
    const scan = document.createElement('div');
    scan.className = 'tc-tile-scan';
    return scan;
  },

  _badge(cls, text) {
    const badge = document.createElement('div');
    badge.className = cls;
    badge.textContent = text;
    return badge;
  },

  _progress(share) {
    const bar = document.createElement('div');
    bar.className = 'tc-tile-progress';
    const fill = document.createElement('i');
    fill.style.width = Math.max(0, Math.min(1, share)) * 100 + '%';
    bar.appendChild(fill);
    return bar;
  },

  _caption(shape) {
    const cap = document.createElement('div');
    cap.className = 'tc-tile-cap';
    const title = document.createElement('div');
    title.className = 'tc-caption';
    title.textContent = shape.title || '';
    cap.appendChild(title);
    if (shape.caption2) {
      const cap2 = document.createElement('div');
      cap2.className = 'tc-cap2';
      cap2.textContent = shape.caption2;
      cap.appendChild(cap2);
    }
    return cap;
  },
};

window.TCTile = TCTile;
