from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import yfinance as yf
import pandas as pd
from typing import List, Dict

from analytics import compute_metrics_from_close  # uses your analytics.py

app = FastAPI(title="Smart Stock Viewer API")

# CORS for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Map UI params → yfinance params
RANGE_MAP = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y", "5Y": "5y", "MAX": "max"}
INTERVAL_MAP = {"d": "1d", "w": "1wk", "m": "1mo"}

def _download_one(ticker: str, yf_period: str, yf_interval: str) -> List[Dict]:
    df = yf.download(ticker, period=yf_period, interval=yf_interval,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        return []
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume",
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

@app.get("/api/metrics")
async def metrics(
    tickers: str = Query(..., description="Comma-separated Yahoo tickers, e.g., AAPL,MSFT,VOD.L"),
    interval: str = Query("d", regex="^(d|w|m)$", description="d=1d, w=1wk, m=1mo"),
    range_: str = Query("1Y", alias="range", regex="^(1M|3M|6M|1Y|5Y|MAX)$"),
):
    yf_period = RANGE_MAP.get(range_, "1y")
    yf_interval = INTERVAL_MAP.get(interval, "1d")

    out: Dict[str, dict] = {}
    for t in [x.strip() for x in tickers.split(",") if x.strip()]:
        rows = _download_one(t, yf_period, yf_interval)
        if not rows:
            out[t.upper()] = {
                "series": {"dates": [], "returns": [], "rolling_vol_30": []},
                "summary": {"annualised_return": None, "annualised_volatility": None,
                            "var_95_1d": None, "var_99_1d": None}
            }
            continue
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")

        m = compute_metrics_from_close(df["close"], interval)
        out[t.upper()] = {
            "series": {
                "dates": m.series.dates,
                "returns": m.series.returns,
                "rolling_vol_30": m.series.rolling_vol_30,
            },
            "summary": {
                "annualised_return": m.summary.annualised_return,
                "annualised_volatility": m.summary.annualised_volatility,
                "var_95_1d": m.summary.var_95_1d,
                "var_99_1d": m.summary.var_99_1d,
            },
        }

    return JSONResponse({"tickers": list(out.keys()), "interval": interval, "range": range_, "metrics": out})

# Keep this LAST so it doesn't swallow /api routes
app.mount("/", StaticFiles(directory=".", html=True), name="static")
