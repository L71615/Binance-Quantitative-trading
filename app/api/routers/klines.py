from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.kline import KLine
from app.models.setting import Setting

router = APIRouter(prefix="/api/klines", tags=["klines"])


def _get_setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(Setting, key)
    return row.value if row else default


@router.get("")
def get_klines(symbol: str, interval: str = "1h", limit: int = 200,
               session: Session = Depends(get_session)):
    rows = (
        session.query(KLine)
        .filter_by(symbol=symbol, interval=interval)
        .order_by(KLine.open_time.asc())
        .limit(limit)
        .all()
    )
    if rows:
        return [_k_to_dict(r) for r in rows]
    # Fall back to live Binance call
    from app.broker.binance import BinanceClient
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    api_key = ""  # public endpoint, no key required for klines
    api_secret = ""
    c = BinanceClient(api_key, api_secret, testnet=testnet)
    try:
        raw = c.get_klines(symbol, interval, limit=limit)
        out = []
        for k in raw:
            row = KLine(
                symbol=symbol, interval=interval,
                open_time=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                open=float(k[1]), high=float(k[2]), low=float(k[3]),
                close=float(k[4]), volume=float(k[5]),
            )
            session.add(row)
            out.append(_k_to_dict(row))
        session.commit()
        return out
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        c.close()


def _k_to_dict(r: KLine) -> dict:
    return {
        "open_time": int(r.open_time.timestamp() * 1000),
        "open": r.open, "high": r.high, "low": r.low, "close": r.close,
        "volume": r.volume,
    }
