"""Обновление настоящей машиной: права процесса, установленный загрузчик и его запуск.

Отвечает на :mod:`torrcast.ports.upgrade_environment` за живой системой; сценарию
(:mod:`torrcast.usecases.upgrade`) ни путей, ни подпроцессов не видно.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: Куда установщик кладёт загрузчик рядом с venv. Тот же путь, что у ``PREFIX`` в
#: ``install.sh``; переопределение читаем оттуда же, чтобы стенд и живая машина
#: спрашивали одно и то же место.
PREFIX = "/opt/torrcast"

#: Метка «нас уже поднимали через sudo». 🔴 Едет за sudo ЯВНЫМ `env`, а не окружением:
#: sudo окружение вытирает, и без метки sudo, который прав не дал (так бывает при
#: собственном `runas` в sudoers), увёл бы обновление в бесконечную цепочку
#: самоподнятий - каждое со своим приглашением пароля.
ELEVATED = "TORRCAST_ELEVATED"


class SystemUpgradeEnvironment:
    """Права, поднятие прав, путь до загрузчика и его запуск копией во временном каталоге."""

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def can_elevate(self) -> bool:
        if os.environ.get(ELEVATED):
            return False
        return bool(shutil.which("sudo")) and bool(self._myself())

    def elevate(self) -> int:
        """Позвать себя же под sudo и отдать наверх его код возврата.

        Потоки не перехватываются, и это не мелочь: приглашение пароля рисует sudo, и
        рисовать его он обязан в терминал человека. Своего приглашения тут нет и быть не
        может - пароль идёт мимо продукта, из `/dev/tty` прямо в sudo.
        """
        done = subprocess.run(
            ["sudo", "--", "env", f"{ELEVATED}=1", self._myself(), *sys.argv[1:]],
            check=False,
        )
        return done.returncode

    def _myself(self) -> str:
        """Чем звать эту же команду заново, либо пусто, если себя не найти.

        Абсолютом: за sudo PATH уже не наш (`secure_path` в sudoers), и голое имя
        разрешалось бы в чужом окружении.
        """
        return shutil.which(sys.argv[0]) or ""

    def loader(self) -> str:
        path = Path(os.environ.get("TORRCAST_PREFIX", PREFIX)) / "install"
        return str(path) if path.is_file() else ""

    def hand_off(self, loader: str, installed: str, language: str) -> int:
        """Запустить загрузчик КОПИЕЙ во временном каталоге и дождаться его.

        🔴 Копия, а не оригинал. Загрузчик лежит в ``/opt/torrcast``, а установка
        переписывает ровно этот каталог; ``sh`` дочитывает скрипт по ходу исполнения, и
        подменённый под ним файл увёл бы обновление в середину чужого текста. Ту же
        плату берёт и питон, поэтому после возврата отсюда зовущий не читает с диска
        ничего нового (:meth:`torrcast.usecases.upgrade.Upgrade.run`).

        Потоки не перехватываются: заставку обновления рисует сам установщик, и рисует
        он её в терминал человека. Перехвати мы вывод - на экране не осталось бы ничего,
        кроме тишины на всю установку.
        """
        with tempfile.TemporaryDirectory(prefix="torrcast-upgrade-") as box:
            copy = Path(box) / "install"
            shutil.copy2(loader, copy)
            copy.chmod(0o755)
            done = subprocess.run(
                ["sh", str(copy)],
                check=False,
                env={
                    **os.environ,
                    "TORRCAST_UPGRADE_FROM": installed,
                    "TORRCAST_LANGUAGE": language,
                },
                stdin=subprocess.DEVNULL,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
        return done.returncode
