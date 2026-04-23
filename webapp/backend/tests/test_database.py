from __future__ import annotations

from types import SimpleNamespace

import app.core.database as database_module


class _FakeAsyncEngine:
    def __init__(self) -> None:
        self.disposed = 0
        self.sync_engine = SimpleNamespace(dispose=self._dispose)

    def _dispose(self) -> None:
        self.disposed += 1


def test_init_db_disposes_replaced_engine(monkeypatch) -> None:
    """Reinitializing the DB layer disposes the old engine before replacement."""
    created: list[_FakeAsyncEngine] = []
    original_engine = database_module._engine
    original_session_factory = database_module._session_factory

    def _fake_create_async_engine(*args: object, **kwargs: object) -> _FakeAsyncEngine:
        engine = _FakeAsyncEngine()
        created.append(engine)
        return engine

    monkeypatch.setattr(database_module, "create_async_engine", _fake_create_async_engine)

    try:
        database_module._engine = None
        database_module._session_factory = None

        database_module.init_db("postgresql+asyncpg://first")
        first_engine = created[-1]
        assert first_engine.disposed == 0

        database_module.init_db("postgresql+asyncpg://second")
        assert first_engine.disposed == 1
        assert database_module._engine is created[-1]
    finally:
        database_module._engine = original_engine
        database_module._session_factory = original_session_factory