#!/usr/bin/env python3
"""
PaS.io data fetcher.

Runs on a schedule inside GitHub Actions. Pulls three public feeds and writes
them as static JSON into data/ for the front end to read.

  - EIA      -> electricity.json   (national trend + per-state prices)
  - FRED     -> commodities.json   (copper + aluminum monthly series)  [no key needed]
  - Finnhub  -> stocks.json        (quote per ticker, grouped by tier)

API KEYS ARE READ FROM ENVIRONMENT VARIABLES ONLY. Never hardcode a key in
this file. In GitHub they come from repo Secrets; locally, export them in your
shell before running:

    export EIA_API_KEY=xxxx
    export FINNHUB_API_KEY=xxxx
    python scripts/fetch_data.py

Design rule (see CLAUDE.md): each source is isolated in try/except so one
failing feed never blocks the others. A failed source keeps its previous data
and is simply marked not-live for that run.
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

EIA_KEY = os.environ.get("EIA_API_KEY", "").strip()
FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()  # optional
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()

# 50 states + DC, used to filter EIA's response (it also returns regional rollups)
STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY",
}

LB_PER_TONNE = 2204.6226


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_json(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": "PaS.io/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_text(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": "PaS.io/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def load(name):
    with open(os.path.join(DATA, f"{name}.json")) as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, f"{name}.json"), "w") as f:
        json.dump(obj, f, indent=2)


# ---------------------------------------------------------------- EIA

def fetch_eia(current):
    if not EIA_KEY:
        raise RuntimeError("EIA_API_KEY not set")

    base = "https://api.eia.gov/v2/electricity/retail-sales/data/"

    # National residential price, annual, for the trend line
    nat_url = (
        f"{base}?api_key={EIA_KEY}"
        "&frequency=annual&data[0]=price"
        "&facets[sectorid][]=RES&facets[stateid][]=US"
        "&start=2015"
        "&sort[0][column]=period&sort[0][direction]=asc&length=5000"
    )
    nat = get_json(nat_url)["response"]["data"]
    series = [[row["period"], round(float(row["price"]), 2)]
              for row in nat if row.get("price") is not None]

    # Per-state residential price, monthly; keep the latest period for each state
    st_url = (
        f"{base}?api_key={EIA_KEY}"
        "&frequency=monthly&data[0]=price"
        "&facets[sectorid][]=RES"
        "&sort[0][column]=period&sort[0][direction]=desc&length=8000"
    )
    rows = get_json(st_url)["response"]["data"]
    states, seen = {}, set()
    for row in rows:
        sid = row.get("stateid")
        if sid in STATES and sid not in seen and row.get("price") is not None:
            states[sid] = round(float(row["price"]), 2)
            seen.add(sid)
        if len(seen) >= len(STATES):
            break

    if not series or not states:
        raise RuntimeError("EIA returned no usable rows")

    current["source"] = "EIA API v2"
    current["updated_at"] = now_iso()
    current["national"] = {"units": "cents/kWh", "series": series}
    current["states"] = states
    current["note"] = "Live: EIA Electric Power Monthly, residential sector."
    return current


# ---------------------------------------------------------------- FRED (no key)

def fred_csv(series_id):
    # Public CSV endpoint — no API key required.
    txt = get_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    out = []
    for line in txt.splitlines()[1:]:  # skip header
        parts = line.split(",")
        if len(parts) != 2:
            continue
        date, val = parts[0].strip(), parts[1].strip()
        if val in (".", ""):
            continue
        out.append([date[:7], float(val)])  # YYYY-MM
    return out


def fetch_commodities(current):
    # PCOPPUSDM / PALUMUSDM are global prices in USD per metric ton, monthly.
    copper_t = fred_csv("PCOPPUSDM")[-36:]   # last ~3 years
    alum_t = fred_csv("PALUMUSDM")[-36:]
    if not copper_t or not alum_t:
        raise RuntimeError("FRED returned no rows")

    # Copper shown in USD/lb to match the familiar "$/lb" framing; aluminum in USD/tonne.
    copper = [[d, round(v / LB_PER_TONNE, 2)] for d, v in copper_t]
    alum = [[d, round(v, 0)] for d, v in alum_t]

    current["source"] = "FRED (IMF global prices)"
    current["updated_at"] = now_iso()
    current["copper"] = {"units": "USD/lb", "series": copper}
    current["aluminum"] = {"units": "USD/t", "series": alum}
    current["note"] = "Live: FRED PCOPPUSDM / PALUMUSDM, monthly."
    return current


# ---------------------------------------------------------------- Finnhub

def fetch_stocks(current):
    if not FINNHUB_KEY:
        raise RuntimeError("FINNHUB_API_KEY not set")

    ok = 0
    for tier in current["tiers"]:
        for t in tier["tickers"]:
            url = f"https://finnhub.io/api/v1/quote?symbol={t['sym']}&token={FINNHUB_KEY}"
            try:
                q = get_json(url, timeout=20)
                if q.get("c"):  # current price present
                    t["price"] = round(float(q["c"]), 2)
                    t["dp"] = round(float(q.get("dp") or 0), 2)
                    ok += 1
            except Exception as e:
                print(f"  ! {t['sym']} quote failed: {e}")
            time.sleep(1.1)  # stay under the 60 calls/minute free limit

    if ok == 0:
        raise RuntimeError("no quotes returned (check key / rate limit)")

    current["source"] = "Finnhub"
    current["updated_at"] = now_iso()
    current["note"] = f"Live: Finnhub quotes ({ok} tickers). ~15-min delayed."
    return current


# ---------------------------------------------------------------- main

def run(name, fn):
    print(f"[{name}] fetching...")
    try:
        data = fn(load(name))
        save(name, data)
        print(f"[{name}] OK")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError, ValueError) as e:
        print(f"[{name}] FAILED, keeping previous data: {e}")
        return False


def main():
    results = {
        "electricity": run("electricity", fetch_eia),
        "commodities": run("commodities", fetch_commodities),
        "stocks": run("stocks", fetch_stocks),
    }
    meta = load("meta")
    meta["generated_at"] = now_iso()
    meta["live"] = results
    save("meta", meta)
    print("done:", results)


if __name__ == "__main__":
    main()
