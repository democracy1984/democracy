import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Изолированная SQLite-база на каждый тест."""
    import core.database as database

    database.close_db()
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()
    yield database
    database.close_db()


@pytest.fixture(autouse=True)
def reset_cooldowns():
    from core import helpers
    from core import state

    helpers.user_last_action_time.clear()
    state.PM_OPT_OUT.clear()
    state.PM_DIALOG_USER_IDS.clear()
    state.PM_INTRO_SENT.clear()
    yield
    helpers.user_last_action_time.clear()
