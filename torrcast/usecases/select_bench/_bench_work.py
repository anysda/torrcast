"""Фоновая подготовка релиза и ожидание её результата с живым прогрессом."""

from __future__ import annotations

import threading
from contextlib import suppress
from typing import Any, cast

import torrcast.usecases.select_bench._bench_state as _bench_state
from torrcast.domain.pick_settings import SWARM_GRACE
from torrcast.domain.rank_settings import PEER_GRACE
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.voice_beside import voice_beside
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.progress import Progress
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_core import _BenchCore


class _BenchWork(_BenchCore):
    """Работа одного прогрева: раздача, метаданные, дорожки - и как её ждут."""

    def _work(self, plan: Plan, prep: _Prep) -> None:
        """Фоновая подготовка: раздача в TorrServer, метаданные по DHT, ffprobe."""
        try:
            prep.phase = "метаданные (DHT)"
            prep.torrent_hash = self.torrserver.add(prep.release.magnet)
            files = self.torrserver.wait_files(
                prep.torrent_hash,
                timeout=self.meta_budget,
                grace=prep.contact_wait or 0.0,
            )
            prep.files = files
            self._sample_supply(prep)
            prep.meta = self.clock() - prep.started
            journal().mark("метаданные", релиз=prep.number, картина=plan.picture.key)
            prep.video = self.choose(plan, prep.release, files)
            prep.phase = "дорожки"
            began = self.clock()
            source = self.torrserver.stream_url(prep.torrent_hash, prep.want.index)
            # Всё, что показ прочитает из роя первым, читается здесь и сейчас: карта
            # опорных кадров (без неё нет сетки) и начало файла (его читает ffmpeg). Это
            # самая ранняя секунда, когда известен файл, - то есть параллельно и ffprobe,
            # и вопросам человека. Показ потом либо берёт готовое, либо
            # дожидается этого же чтения, а не начинает своё вторым потоком.
            _bench_state._bench_warm_file(
                source, alive=lambda: not prep.dropped, name=prep.want.name
            )
            self._sample_supply(prep)
            prep.media = self.prober(
                source,
                timeout=self.probe_budget,
                alive=(
                    None
                    if prep.patient
                    else _bench_state._bench_swarm_pulse(
                        source, SWARM_GRACE, wait=prep.contact_wait
                    )
                ),
            )
            prep.read = self.clock() - began
            self._voice_apart(prep, plan)
            self._sample_supply(prep)
            journal().mark("ffprobe", релиз=prep.number, картина=plan.picture.key)
            prep.phase = "готово"
        except TorrcastError as exc:
            prep.error = str(exc)
            prep.failure = exc
            prep.phase = "сбой"
        finally:
            prep.ready.set()
            if prep.dropped:  # пока грелись, показ ушёл к другому релизу
                self._forget(prep)

    def _voice_apart(self, prep: _Prep, plan: Plan) -> None:
        """Прочитать паспортом отдельный файл звука рядом с видео, если он там лежит.

        Спрашивается ровно там, где иначе релиз пошёл бы в брак: русской дорожки внутри
        видеофайла нет. На здоровом релизе это не стоит ни одного лишнего ffprobe.

        Опознание языка - только паспортом второго файла: имя файла звука в аниме язык не
        называет никогда (194 из 194). Молчание ffprobe тут не беда: дорожки нет - значит
        нет, и релиз судится по одному видеофайлу, как судился раньше.
        """
        if prep.media is None or not voice_unproven(prep.media, native=plan.picture.native):
            return
        found = voice_beside(prep.want, prep.files)
        if found is None:
            return
        prep.voice_file = found
        with suppress(TorrcastError):
            prep.voice_media = self.prober(
                self.torrserver.stream_url(prep.torrent_hash, found.index),
                timeout=self.probe_budget,
            )
        journal().mark("дорожка отдельным файлом", релиз=prep.number, файл=found.base)

    def _sample_supply(self, prep: _Prep) -> None:
        """Снять счётчик байтов именно пока прогрев создаёт спрос на файл."""
        with suppress(Exception):
            read = cast(Any, self.torrserver).status(prep.torrent_hash).get("bytes_read")
            if isinstance(read, (int, float)) and not isinstance(read, bool) and read >= 0:
                prep.supply.append((self.clock() - prep.started, float(read)))

    def _wait(self, prep: _Prep, progress: Progress, prefix: str = "", limit: float = 0.0) -> None:
        """Дождаться подготовки, показывая фазу и бегущее время.

        ``limit`` - потолок ФАЗЫ отбора (:data:`PICK_BUDGET`), а срок выше - потолок одной
        раздачи. Ждём до ближайшего из двух.

        🔴 TC-436. Без ``limit`` потолок фазы проверялся только МЕЖДУ попытками
        (:meth:`resolve`), а ожидание внутри попытки шло по своему сроку до конца: свежий
        прогрев, начатый на 179-й секунде, тянул ещё до 65 с (метаданные плюс проба плюс
        5), и худший обход стоил человеку около 245 с вместо объявленных 180.

        Срезается ровно ожидание сверх потолка, и ни секундой раньше: раздача, прогретая
        под меню (:data:`PREWARM_SPARE`), отвечает мгновенно, и спросить её мы обязаны
        хоть на 179-й секунде - потолки роя тут не режутся, режется выход за потолок фазы.
        """
        asked = prep.contact_wait.activated_at if prep.contact_wait is not None else None
        deadline = (asked or prep.started) + self.meta_budget + self.probe_budget + 5.0
        if limit:
            deadline = min(deadline, limit)
        while not prep.ready.wait(0.2):
            progress.phase(f"{prefix}{prep.phase}")
            if self.clock() > deadline:  # поток сам не уложился - не ждём вечно
                prep.error = prep.error or f"фаза «{prep.phase}» не уложилась в бюджет"
                return

    def _peek(self, prep: _Prep, progress: Progress, deadline: float, phase: str) -> bool:
        """Заглянуть в подготовку с коротким сроком: успела — ``True``, нет — ``False``.

        Отличие от :meth:`_wait` не в сроке, а в последствиях: этот срок наш, а не
        релиза, и просроченному прогреву :attr:`_Prep.error` не ставится. Иначе
        подглядывание за соседом молча делало бы его негодным.
        """
        while not prep.ready.wait(0.2):
            progress.phase(phase)
            if self.clock() > deadline:
                return False
        return True

    def start(self, plan: Plan, number: int, patient: bool = False) -> _Prep:
        """Начать (или вернуть уже начатую) подготовку релиза ``number`` этого плана.

        ``patient`` - спрашивать рой без отсрочек, по полным бюджетам фазы
        (:attr:`_Prep.patient`). Обычный прогрев начинает работу сразу, но часы
        отсрочки запускаются только когда релиз действительно дошёл до вопроса.
        """
        key = (plan.picture.key, number)
        found = self.preps.get(key)
        if found is not None:
            return found
        self._room()
        prep = _Prep(
            number=number,
            release=plan.ranked[number - 1],
            patient=patient,
            contact_wait=None if patient else _bench_state._bench_contact_wait(PEER_GRACE),
        )
        self.preps[key] = prep
        threading.Thread(target=self._work, args=(plan, prep), daemon=True).start()
        return prep
