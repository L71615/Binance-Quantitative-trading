from app.db import engine, SessionLocal, Base, get_session
from sqlalchemy import text


def test_engine_is_sqlite():
    assert "sqlite" in str(engine.url)


def test_base_is_declarative():
    assert hasattr(Base, "metadata")


def test_session_yields_session():
    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_get_session_dependency():
    gen = get_session()
    sess = next(gen)
    try:
        result = sess.execute(text("SELECT 2")).scalar()
        assert result == 2
    finally:
        try:
            next(gen)
        except StopIteration:
            pass