"""История главной обновляется и после возврата к сохранённой выдаче."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.machine
def test_returned_search_refreshes_history_before_esc() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "node не найден: сторож возврата главной исполняет home.js в node", pytrace=False
        )
    runner = Path(__file__).with_name("web_js") / "home_history.js"
    done = subprocess.run([node, str(runner)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    facts: dict[str, object] = json.loads(done.stdout)
    assert facts["kept"] is True, "тихий добор заменил выдачу до Esc"
    assert facts["key"] == "new", "Esc показал историю до возврата с карточки"
    assert facts["shelves"] == ["shelf-continue", "shelf-new", ""]
    assert facts["partialKept"] is True, "недособранные полки дописали историю в выдачу"
