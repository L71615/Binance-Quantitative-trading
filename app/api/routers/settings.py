from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crypto_store import save_secret, load_secret, delete_secret
from app.db import get_session
from app.models.setting import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

_API_KEY_SLUG = "api_key"
_API_SECRET_SLUG = "api_secret"


def _get_setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(Setting, key)
    return row.value if row else default


def _set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


class SettingsUpdate(BaseModel):
    binance_testnet: bool | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None


@router.get("")
def get_settings(session: Session = Depends(get_session)):
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    has_key = load_secret(_API_KEY_SLUG) is not None
    has_secret = load_secret(_API_SECRET_SLUG) is not None
    return {
        "binance_testnet": testnet,
        "has_api_key": has_key,
        "has_api_secret": has_secret,
    }


@router.put("")
def put_settings(update: SettingsUpdate, session: Session = Depends(get_session)):
    if update.binance_testnet is not None:
        _set_setting(session, "binance_testnet", "true" if update.binance_testnet else "false")
    if update.binance_api_key is not None:
        if update.binance_api_key == "":
            delete_secret(_API_KEY_SLUG)
        else:
            save_secret(_API_KEY_SLUG, update.binance_api_key)
            _set_setting(session, "binance_api_key", "set")  # marker only
    if update.binance_api_secret is not None:
        if update.binance_api_secret == "":
            delete_secret(_API_SECRET_SLUG)
        else:
            save_secret(_API_SECRET_SLUG, update.binance_api_secret)
            _set_setting(session, "binance_api_secret", "set")
    session.commit()
    return {"ok": True}


@router.post("/test-binance")
def test_binance(session: Session = Depends(get_session)):
    api_key = load_secret(_API_KEY_SLUG) or ""
    api_secret = load_secret(_API_SECRET_SLUG) or ""
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    if not api_key or not api_secret:
        return {"ok": False, "error": "missing credentials"}
    from app.broker.binance import BinanceClient
    c = BinanceClient(api_key, api_secret, testnet=testnet)
    try:
        info = c.get_account_info()
        return {"ok": True, "can_trade": info.get("canTrade", False), "testnet": testnet}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        c.close()