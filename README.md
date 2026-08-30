# Binance Spot Grid Trading Platform

A local-only automated grid trading bot for Binance Spot (no leverage).
For learning and personal use.

## Quick start (Windows)

1. Clone this repo (or open `D:/bian`).
2. Double-click `run.bat`.
3. Browser opens to `http://localhost:5173` — first time, follow the API key setup wizard.

## Configuration

Settings are stored encrypted in `data/app.db` (via OS keyring). Configure via the UI's **Settings** page; no plaintext keys live in this repo.

## Testing

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## Reference projects

The `借鉴/` directory contains 9 open-source projects used as reference. See `借鉴/<repo>/_LICENSE_NOTES.md` for license details per project.