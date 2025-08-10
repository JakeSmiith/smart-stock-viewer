from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import yfinance as yf
import pandas as pd
from typing import List, Dict

app = FastAPI(title="Smart Stock Viewer API")

# If you later host the front-end elsewhere, adjust CORS accordingly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Map UI params → yfinance params
RANGE_MAP = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
    "MAX": "max",
}
INTERVAL_MAP = {"d": "1d", "w": "1wk", "m": "1mo"}


def _download_one(ticker: str, yf_period: str, yf_interval: str) -> List[Dict]:
    # yfinance expects Yahoo tickers (e.g., AAPL, VOD.L, BMW.DE)
    df = yf.download(ticker, period=yf_period, interval=yf_interval, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return []
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    })
    df.index = pd.to_datetime(df.index)
    out = []
    for idx, row in df.iterrows():
        out.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row.get("open", float("nan"))),
            "high": float(row.get("high", float("nan"))),
            "low": float(row.get("low", float("nan"))),
            "close": float(row.get("close", float("nan"))),
            "volume": float(row.get("volume", 0.0)),
        })
    return out


@app.get("/api/ohlc")
async def ohlc(
    tickers: str = Query(..., description="Comma-separated Yahoo tickers, e.g., AAPL,MSFT,VOD.L"),
    interval: str = Query("d", regex="^(d|w|m)$", description="d=1d, w=1wk, m=1mo"),
    range_: str = Query("1Y", alias="range", regex="^(1M|3M|6M|1Y|5Y|MAX)$"),
):
    yf_period = RANGE_MAP.get(range_, "1y")
    yf_interval = INTERVAL_MAP.get(interval, "1d")

    results: Dict[str, List[Dict]] = {}
    for t in [x.strip() for x in tickers.split(",") if x.strip()]:
        try:
            results[t.upper()] = _download_one(t, yf_period, yf_interval)
        except Exception:
            results[t.upper()] = []

    return JSONResponse({
        "tickers": list(results.keys()),
        "interval": interval,
        "range": range_,
        "data": results,
    })

# Serve the static front-end from the repo root (index.html)
app.mount("/", StaticFiles(directory=".", html=True), name="static")
