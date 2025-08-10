from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import pandas as pd
import yfinance as yf

from analytics import compute_metrics_from_close

router = APIRouter(prefix="/api", tags=["metrics"])

# Keep these consistent with the UI controls
RANGE_MAP = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
    "MAX": "max",
}
INTERVAL_MAP = {"d": "1d", "w": "1wk", "m": "1mo"}


def _download_one(ticker: str, yf_period: str, yf_interval: str) -> pd.DataFrame:
    """Download OHLC with yfinance and return a tidy DataFrame (date index).
    Columns: open, high, low, close, adj_close, volume
    """
    df = yf.download(
        ticker,
        period=yf_period,
        interval=yf_interval,
        progress=False,
        auto_adjust=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"]).set_index(
            pd.DatetimeIndex([], name="Date")
        )
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


@router.get("/metrics")
async def metrics(
    tickers: str = Query(..., description="Comma-separated Yahoo tickers, e.g., AAPL,MSFT,VOD.L"),
    interval: str = Query("d", regex="^(d|w|m)$", description="d=1d, w=1wk, m=1mo"),
    range_: str = Query("1Y", alias="range", regex="^(1M|3M|6M|1Y|5Y|MAX)$"),
):
    yf_period = RANGE_MAP.get(range_, "1y")
    yf_interval = INTERVAL_MAP.get(interval, "1d")

    out: Dict[str, dict] = {}
    for t in [x.strip() for x in tickers.split(",") if x.strip()]:
        df = _download_one(t, yf_period, yf_interval)
        m = compute_metrics_from_close(df.get("close"), interval)
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
