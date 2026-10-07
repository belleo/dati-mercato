"""
Scarica i dati di mercato della watchlist con yfinance, calcola gli indicatori
usati dalla skill "analista-titoli" e (opzionale) pubblica il risultato su GitHub.

Uso:
    python market_data.py            # calcola e salva in data/
    python market_data.py --push     # calcola, salva e fa commit + push su GitHub
    python market_data.py --fundamentals --push   # aggiunge capitalizzazione e P/E (piu' lento)

Output:
    data/latest.csv              ultima fotografia (una riga per titolo)
    data/latest.json             stessi dati + metadati (data aggiornamento)
    data/history/AAAA-MM-GG.csv  archivio giornaliero
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
HIST = DATA / "history"
WATCHLIST = BASE / "watchlist.csv"

# Benchmark per la forza relativa
BENCHMARK = {"IT": "FTSEMIB.MI", "US": "^GSPC"}
EXTRA_INDICES = ["^NDX"]

TRADING_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


# ---------------------------------------------------------------- download
def use_windows_certs() -> None:
    """Fa fidare curl_cffi (usato da yfinance) anche dei certificati di Windows.

    Serve quando un antivirus (es. Avast Web Shield) ispeziona l'HTTPS con una
    propria CA, presente nello store di Windows ma non in certifi.
    Va chiamata prima di importare yfinance.
    """
    import os
    import ssl

    if sys.platform != "win32" or os.environ.get("SSL_CERT_FILE"):
        return
    import certifi

    pems = [Path(certifi.where()).read_text(encoding="ascii")]
    for store in ("ROOT", "CA"):
        for der, enc, _ in ssl.enum_certificates(store):
            if enc == "x509_asn":
                pems.append(ssl.DER_cert_to_PEM_cert(der))
    bundle = BASE / "cacert.pem"
    bundle.write_text("\n".join(pems), encoding="ascii")
    os.environ["SSL_CERT_FILE"] = str(bundle)


def download_prices(tickers: list[str]) -> dict[str, pd.Series]:
    use_windows_certs()
    import yfinance as yf

    raw = yf.download(
        tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    out: dict[str, pd.Series] = {}
    for t in tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                s = raw[t]["Close"]
            else:  # un solo ticker
                s = raw["Close"]
            s = s.dropna()
            if len(s) > 0:
                out[t] = s
        except KeyError:
            pass
    return out


def download_fundamentals(tickers: list[str]) -> dict[str, dict]:
    use_windows_certs()
    import yfinance as yf

    keys = {
        "marketCap": "capitalizzazione",
        "trailingPE": "pe_ttm",
        "forwardPE": "pe_forward",
        "enterpriseToEbitda": "ev_ebitda",
        "dividendYield": "dividend_yield",
        "beta": "beta",
        "currency": "valuta",
    }
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            out[t] = {v: info.get(k) for k, v in keys.items()}
        except Exception as e:  # rete, rate limit, ticker sconosciuto
            print(f"  fondamentali non disponibili per {t}: {e}", file=sys.stderr)
            out[t] = {}
    return out


# ---------------------------------------------------------------- indicatori
def pct_return(s: pd.Series, days: int) -> float:
    if len(s) <= days:
        return np.nan
    return s.iloc[-1] / s.iloc[-days - 1] - 1


def ytd_return(s: pd.Series) -> float:
    last = s.index[-1]
    prev_year = s[s.index.year < last.year]
    if prev_year.empty:
        return np.nan
    return s.iloc[-1] / prev_year.iloc[-1] - 1


def rsi(s: pd.Series, period: int = 14) -> float:
    if len(s) <= period:
        return np.nan
    delta = s.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return 100 - 100 / (1 + rs)


def max_drawdown(s: pd.Series) -> float:
    return float((s / s.cummax() - 1).min())


def indicators(s: pd.Series, bench: pd.Series | None) -> dict:
    last = s.iloc[-1]
    y1 = s.tail(252)
    sma50 = s.tail(50).mean() if len(s) >= 50 else np.nan
    sma200 = s.tail(200).mean() if len(s) >= 200 else np.nan
    # pendenza SMA200: confronto con il valore di 20 sedute fa
    sma200_prev = s.iloc[:-20].tail(200).mean() if len(s) >= 220 else np.nan
    rets = s.pct_change().dropna()

    d = {
        "data_prezzo": s.index[-1].strftime("%Y-%m-%d"),
        "prezzo": last,
        "var_1g": pct_return(s, 1),
        "sma50": sma50,
        "sma200": sma200,
        "dist_sma200": last / sma200 - 1 if sma200 == sma200 else np.nan,
        "sopra_sma200": bool(last > sma200) if sma200 == sma200 else None,
        "sma200_in_salita": bool(sma200 > sma200_prev) if sma200_prev == sma200_prev else None,
        "golden_cross": bool(sma50 > sma200) if sma200 == sma200 else None,
        "rsi14": rsi(s),
        "ret_ytd": ytd_return(s),
        "max_52s": y1.max(),
        "min_52s": y1.min(),
        "dist_max_52s": last / y1.max() - 1,
        "dist_min_52s": last / y1.min() - 1,
        "vol_1a": rets.tail(252).std() * np.sqrt(252),
        "max_drawdown_1a": max_drawdown(y1),
    }
    for k, n in TRADING_DAYS.items():
        d[f"ret_{k}"] = pct_return(s, n)
    for k in ("6m", "12m"):
        if bench is not None:
            rb = pct_return(bench, TRADING_DAYS[k])
            rt = d[f"ret_{k}"]
            d[f"forza_rel_{k}"] = (1 + rt) / (1 + rb) - 1 if rb == rb and rt == rt else np.nan
        else:
            d[f"forza_rel_{k}"] = np.nan
    return d


def build_table(wl: pd.DataFrame, prices: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for _, r in wl.iterrows():
        t, mkt = r["ticker"], r["mercato"]
        s = prices.get(t)
        if s is None or len(s) < 30:
            print(f"  dati insufficienti per {t}", file=sys.stderr)
            continue
        b_t = BENCHMARK.get(mkt)
        bench = prices.get(b_t) if b_t else None
        row = {"ticker": t, "nome": r["nome"], "mercato": mkt, "benchmark": b_t}
        row.update(indicators(s, bench))
        rows.append(row)
    # righe per gli indici, utili come contesto
    for idx in list(BENCHMARK.values()) + EXTRA_INDICES:
        s = prices.get(idx)
        if s is not None and len(s) >= 30:
            row = {"ticker": idx, "nome": "INDICE", "mercato": "IDX", "benchmark": None}
            row.update(indicators(s, None))
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- output
def save(df: pd.DataFrame) -> str:
    DATA.mkdir(exist_ok=True)
    HIST.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = datetime.now().strftime("%Y-%m-%d")

    out = df.copy()
    num_cols = out.select_dtypes(include="number").columns
    out[num_cols] = out[num_cols].round(4)

    out.to_csv(DATA / "latest.csv", index=False)
    out.to_csv(HIST / f"{day}.csv", index=False)
    payload = {
        "aggiornato_il": now,
        "fonte": "Yahoo Finance via yfinance (prezzi rettificati per dividendi e split)",
        "note": "Rendimenti, distanze, volatilita' e forza relativa sono decimali (0.05 = +5%).",
        "titoli": json.loads(out.to_json(orient="records")),
    }
    (DATA / "latest.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    return day


def git_push(day: str) -> None:
    def git(*args):
        return subprocess.run(["git", "-C", str(BASE), *args], capture_output=True, text=True)

    git("pull", "--rebase", "--autostash")
    git("add", "data")
    c = git("commit", "-m", f"Dati mercato {day}")
    if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
        print("Nessuna modifica da pubblicare.")
        return
    p = git("push")
    if p.returncode != 0:
        print("ERRORE push:", p.stderr, file=sys.stderr)
        sys.exit(1)
    print("Pubblicato su GitHub.")


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="commit e push su GitHub")
    ap.add_argument("--fundamentals", action="store_true", help="aggiunge capitalizzazione, P/E, EV/EBITDA")
    args = ap.parse_args()

    wl = pd.read_csv(WATCHLIST)
    tickers = sorted(set(wl["ticker"]) | set(BENCHMARK.values()) | set(EXTRA_INDICES))
    print(f"Scarico {len(tickers)} serie...")
    prices = download_prices(tickers)
    df = build_table(wl, prices)
    if df.empty:
        print("Nessun dato scaricato: controlla la connessione o i ticker.", file=sys.stderr)
        sys.exit(1)

    if args.fundamentals:
        print("Scarico i fondamentali...")
        f = download_fundamentals([t for t in df["ticker"] if not t.startswith("^") and t != "FTSEMIB.MI"])
        fdf = pd.DataFrame.from_dict(f, orient="index")
        df = df.merge(fdf, left_on="ticker", right_index=True, how="left")

    day = save(df)
    print(f"Salvati {len(df)} titoli in {DATA}")
    if args.push:
        git_push(day)


if __name__ == "__main__":
    main()
