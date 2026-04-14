"""
Stanhope Fire Weather Index (FWI) Calculator
=============================================

This script computes the Canadian Forest Fire Weather Index (FWI) for the
Stanhope weather station (Prince Edward Island) using observed weather data
retrieved directly from the ECCC (Environment and Climate Change Canada) API.

WHY NOT JUST USE THE CWFIS MAP?
--------------------------------
The CWFIS interactive map (https://cwfis.cfs.nrcan.gc.ca) shows FWI values on
a 250m raster grid that is masked to burnable forest fuel types. Stanhope sits
within Prince Edward Island National Park — a coastal area of dunes and beach —
which the fuel model classifies as non-burnable. As a result, no FWI is assigned
to Stanhope in the raster even though fire weather conditions are still relevant
for park management.

Instead, we take the FWI inputs (temperature, humidity, wind, precipitation)
directly from the Stanhope weather station observational record (ECCC climate
ID 8300590, operating since 1961) and run the standard FWI equations ourselves.
This produces an authoritative, location-specific FWI series.

THE FWI SYSTEM (Van Wagner 1987)
---------------------------------
The Canadian FWI System uses noon weather observations to compute six indices:

  Moisture codes (memory of past weather):
    FFMC — Fine Fuel Moisture Code  (1-day memory, surface litter)
    DMC  — Duff Moisture Code       (~12-day memory, upper soil layer)
    DC   — Drought Code             (~52-day memory, deep soil moisture)

  Fire behaviour indices (today's conditions):
    ISI  — Initial Spread Index     (fire spread rate, from FFMC + wind)
    BUI  — Buildup Index            (total fuel available, from DMC + DC)
    FWI  — Fire Weather Index       (overall fire intensity, from ISI + BUI)

FWI > 19 is considered "High", > 30 is "Very High", > 38 is "Extreme".

DATA SOURCE
-----------
ECCC MSC GeoMet open data API — no API key required.
Station: STANHOPE, PE  |  Climate ID: 8300590  |  Lat: 46.416N, Lon: 63.083W
Hourly record available from 2013-12-10 onward.

USAGE
-----
Adjust the configuration block below (YEAR, START_MONTH, END_MONTH) and run:

    python compute_stanhope_fwi.py

Output CSV is saved to: data/stanhope/fwi_stanhope_computed_<YEAR>.csv

REQUIREMENTS
------------
Python 3.7+, standard library only (no pip installs needed).
Requires an internet connection to fetch data from the ECCC API.
"""

import urllib.request, urllib.parse, json, csv, math, os, time
from datetime import datetime, timedelta

# ─── CONFIGURATION — edit these to change what you compute ───────────────────

CLIMATE_ID  = "8300590"    # ECCC station ID for Stanhope PE
YEAR        = 2025         # Year to compute
START_MONTH = 5            # May (fire season start for PEI)
END_MONTH   = 10           # October (fire season end)

# FWI start-of-season "startup" values (standard Canadian defaults for spring)
# These are the assumed moisture code values on the first day of computation.
# They represent "average" spring conditions after snowmelt.
FFMC_START = 85.0
DMC_START  = 6.0
DC_START   = 15.0

API_BASE = "https://api.weather.gc.ca/collections/climate-hourly/items"
DELAY    = 1.0  # seconds between API requests — be respectful of public servers

# ─── FWI System equations (Van Wagner 1987) ──────────────────────────────────

def rh_from_dewpoint(t, td):
    """Compute relative humidity (%) from temperature and dew point (°C)."""
    return 100 * math.exp((17.625 * td / (243.04 + td)) - (17.625 * t / (243.04 + t)))

def ffmc(t, h, w, p, ffmc0):
    """Fine Fuel Moisture Code."""
    mo = 147.2 * (101 - ffmc0) / (59.5 + ffmc0)
    if p > 0.5:
        rf = p - 0.5
        if mo > 150:
            mo = (mo + 42.5 * rf * math.exp(-100 / (251 - mo)) * (1 - math.exp(-6.93 / rf))
                  + 0.0015 * (mo - 150)**2 * rf**0.5)
        else:
            mo = mo + 42.5 * rf * math.exp(-100 / (251 - mo)) * (1 - math.exp(-6.93 / rf))
        if mo > 250:
            mo = 250
    ed = 0.942 * h**0.679 + 11 * math.exp((h - 100) / 10) + 0.18 * (21.1 - t) * (1 - math.exp(-0.115 * h))
    ew = 0.618 * h**0.753 + 10 * math.exp((h - 100) / 10) + 0.18 * (21.1 - t) * (1 - math.exp(-0.115 * h))
    if mo > ed:
        ko = 0.424 * (1 - (h / 100)**1.7) + 0.0694 * w**0.5 * (1 - (h / 100)**8)
        kd = ko * 0.581 * math.exp(0.0365 * t)
        m = ed + (mo - ed) * 10**(-kd)
    elif mo < ew:
        ko = 0.424 * (1 - ((100 - h) / 100)**1.7) + 0.0694 * w**0.5 * (1 - ((100 - h) / 100)**8)
        kw = ko * 0.581 * math.exp(0.0365 * t)
        m = ew - (ew - mo) * 10**(-kw)
    else:
        m = mo
    return 59.5 * (250 - m) / (147.2 + m)

def dmc(t, h, p, dmc0, month):
    """Duff Moisture Code."""
    el = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.8, 6.3]
    if t < -1.1:
        t = -1.1
    rk = 1.894 * (t + 1.1) * (100 - h) * el[month - 1] * 1e-4
    if p > 1.5:
        ra = p - 1.5
        rw = 0.92 * ra - 1.27
        wmi = 20 + 280 / math.exp(0.023 * dmc0)
        if dmc0 <= 33:
            b = 100 / (0.5 + 0.3 * dmc0)
        elif dmc0 <= 65:
            b = 14 - 1.3 * math.log(dmc0)
        else:
            b = 6.2 * math.log(dmc0) - 17.2
        wmr = wmi + 1000 * rw / (48.77 + b * rw)
        pr = 43.43 * (5.6348 - math.log(wmr - 20))
    else:
        pr = dmc0
    if pr < 0:
        pr = 0
    return pr + rk

def dc(t, p, dc0, month):
    """Drought Code."""
    fl = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6]
    if t < -2.8:
        t = -2.8
    pe = (0.36 * (t + 2.8) + fl[month - 1]) / 2
    if pe < 0:
        pe = 0
    if p > 2.8:
        ra = p - 2.8
        rw = 0.83 * ra - 1.27
        smi = 800 * math.exp(-dc0 / 400)
        dr = dc0 - 400 * math.log(1 + 3.937 * rw / smi)
        if dr < 0:
            dr = 0
    else:
        dr = dc0
    return dr + pe

def isi(w, ffmc_val):
    """Initial Spread Index."""
    fm = 147.2 * (101 - ffmc_val) / (59.5 + ffmc_val)
    sf = 19.115 * math.exp(-0.1386 * fm) * (1 + fm**5.31 / 4.93e7)
    return sf * math.exp(0.05039 * w)

def bui(dmc_val, dc_val):
    """Buildup Index."""
    if dmc_val <= 0.4 * dc_val:
        return 0.8 * dmc_val * dc_val / (dmc_val + 0.4 * dc_val)
    else:
        u = dmc_val - (1 - 0.8 * dc_val / (dmc_val + 0.4 * dc_val)) * (0.92 + (0.0114 * dmc_val)**1.7)
        return max(u, 0)

def fwi(isi_val, bui_val):
    """Fire Weather Index."""
    if bui_val <= 80:
        bb = 0.1 * isi_val * (0.626 * bui_val**0.809 + 2)
    else:
        bb = 0.1 * isi_val * (1000 / (25 + 108.64 * math.exp(-0.023 * bui_val)))
    if bb <= 1:
        return bb
    return math.exp(2.72 * (0.434 * math.log(bb))**0.647)

# ─── Data fetching ────────────────────────────────────────────────────────────

def fetch_hourly_range(climate_id, start_dt, end_dt):
    """
    Fetch all hourly station records from the ECCC MSC GeoMet API.
    The API returns up to 500 records per page, so we loop until we have all of them.
    """
    records = []
    offset = 0
    limit = 500
    date_range = f"{start_dt}/{end_dt}"

    while True:
        params = {
            'CLIMATE_IDENTIFIER': climate_id,
            'datetime': date_range,
            'f': 'json',
            'limit': limit,
            'offset': offset,
            'sortby': 'LOCAL_DATE'
        }
        url = API_BASE + '?' + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'fwi-research/1.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"  API error at offset {offset}: {e}")
            break

        features = data.get('features', [])
        records.extend(features)
        total = data.get('numberMatched', len(records))
        print(f"  Fetched {len(records)}/{total} hourly records...", flush=True)

        if len(records) >= total or not features:
            break
        offset += limit
        time.sleep(DELAY)

    return records

def extract_daily_inputs(records):
    """
    From hourly records, build daily FWI inputs:
      - noon T, RH, Wind  (LST 12:00, or closest midday hour)
      - 24h precip sum (hours 01-24 ending at noon, i.e. prior day 13:00 to current day 12:00)
    Returns dict: date_str -> {'t': float, 'h': float, 'w': float, 'p': float}
    """
    # Index by date and hour
    by_dt = {}
    for feat in records:
        p = feat['properties']
        dt_str = p.get('LOCAL_DATE', '')
        if not dt_str:
            continue
        try:
            dt = datetime.fromisoformat(dt_str.replace(' ', 'T'))
        except:
            continue
        by_dt[dt] = p

    # Get sorted list of datetimes
    all_dts = sorted(by_dt.keys())
    if not all_dts:
        return {}

    # Get unique dates
    dates = sorted(set(dt.date() for dt in all_dts))
    daily = {}

    for d in dates:
        # Noon record: prefer 12:00, fall back to 11:00 or 13:00
        noon_rec = None
        for h in [12, 11, 13]:
            candidate = datetime(d.year, d.month, d.day, h)
            if candidate in by_dt:
                noon_rec = by_dt[candidate]
                break
        if noon_rec is None:
            continue

        t = noon_rec.get('TEMP')
        wind = noon_rec.get('WIND_SPEED')
        rh = noon_rec.get('RELATIVE_HUMIDITY')
        td = noon_rec.get('DEW_POINT_TEMP')

        if t is None or wind is None:
            continue
        if rh is None and td is not None:
            rh = rh_from_dewpoint(float(t), float(td))
        if rh is None:
            continue

        t, rh, wind = float(t), float(rh), float(wind)
        rh = max(1, min(100, rh))  # clamp

        # 24h precip: sum hours from previous day 13:00 through current day 12:00
        precip = 0.0
        for h in range(1, 25):  # 24 hours ending at noon
            dt_check = datetime(d.year, d.month, d.day, 12) - timedelta(hours=24 - h)
            rec = by_dt.get(dt_check)
            if rec and rec.get('PRECIP_AMOUNT') is not None:
                precip += float(rec['PRECIP_AMOUNT'])

        daily[str(d)] = {'t': t, 'h': rh, 'w': wind, 'p': precip}

    return daily

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import calendar

    # Build date range from config
    start_dt = f"{YEAR}-{START_MONTH:02d}-01T00:00:00"
    last_day = calendar.monthrange(YEAR, END_MONTH)[1]
    end_dt   = f"{YEAR}-{END_MONTH:02d}-{last_day:02d}T23:59:59"

    print(f"Stanhope FWI Calculator")
    print(f"Station:  STANHOPE PE  (climate_id={CLIMATE_ID})")
    print(f"Period:   {start_dt[:10]} to {end_dt[:10]}")
    print(f"Startup:  FFMC={FFMC_START}  DMC={DMC_START}  DC={DC_START}")
    print()

    # Step 1: Fetch hourly observations from ECCC
    print("Step 1: Fetching hourly data from ECCC API...")
    records = fetch_hourly_range(CLIMATE_ID, start_dt, end_dt)
    print(f"  Total hourly records retrieved: {len(records)}")

    if not records:
        print("No data returned. Check your internet connection or date range.")
        exit(1)

    # Step 2: Extract daily noon inputs (T, RH, Wind, 24h Precip)
    print("\nStep 2: Extracting daily noon weather inputs...")
    daily_inputs = extract_daily_inputs(records)
    print(f"  Days with complete inputs: {len(daily_inputs)}")

    if not daily_inputs:
        print("No complete daily inputs found. Cannot compute FWI.")
        exit(1)

    print("\n  Sample (first 5 days):")
    for d in sorted(daily_inputs.keys())[:5]:
        v = daily_inputs[d]
        print(f"    {d}  T={v['t']:.1f}°C  RH={v['h']:.0f}%  Wind={v['w']:.0f}km/h  Precip={v['p']:.1f}mm")

    # Step 3: Run FWI equations sequentially (each day depends on the previous)
    print("\nStep 3: Computing FWI for each day...")
    ffmc_val, dmc_val, dc_val = FFMC_START, DMC_START, DC_START
    results = []

    for date_str in sorted(daily_inputs.keys()):
        v = daily_inputs[date_str]
        month = int(date_str[5:7])

        # Moisture codes accumulate memory from prior days — order matters
        ffmc_val = ffmc(v['t'], v['h'], v['w'], v['p'], ffmc_val)
        dmc_val  = dmc(v['t'], v['h'], v['p'], dmc_val, month)
        dc_val   = dc(v['t'], v['p'], dc_val, month)

        # Behaviour indices depend only on today's moisture codes + wind
        isi_val  = isi(v['w'], ffmc_val)
        bui_val  = bui(dmc_val, dc_val)
        fwi_val  = fwi(isi_val, bui_val)

        results.append({
            'Date':       date_str,
            'T_noon':     round(v['t'], 1),
            'RH_noon':    round(v['h'], 0),
            'Wind_noon':  round(v['w'], 0),
            'Precip_24h': round(v['p'], 1),
            'FFMC':       round(ffmc_val, 2),
            'DMC':        round(dmc_val, 2),
            'DC':         round(dc_val, 2),
            'ISI':        round(isi_val, 2),
            'BUI':        round(bui_val, 2),
            'FWI':        round(fwi_val, 2)
        })

    # Step 4: Save to CSV
    out_dir  = os.path.join('data', 'stanhope')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'fwi_stanhope_computed_{YEAR}.csv')

    with open(out_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\nStep 4: Saved {len(results)} days to {out_file}")

    # Summary
    fwi_vals = [r['FWI'] for r in results]
    peak_idx = fwi_vals.index(max(fwi_vals))
    print(f"""
--- {YEAR} Fire Season Summary (Stanhope PE) ---
  Days computed : {len(fwi_vals)}
  Mean FWI      : {sum(fwi_vals)/len(fwi_vals):.1f}
  Peak FWI      : {max(fwi_vals):.1f}  on {results[peak_idx]['Date']}
  Min FWI       : {min(fwi_vals):.1f}

  Danger class thresholds:  Low <5  |  Moderate 5-12  |  High 13-19  |  Very High 20-30  |  Extreme >30
""")

    print("--- Daily FWI ---")
    for r in results:
        bar = '█' * int(r['FWI'] / 2)
        danger = ('LOW' if r['FWI'] < 5 else 'MODERATE' if r['FWI'] < 13
                  else 'HIGH' if r['FWI'] < 20 else 'VERY HIGH' if r['FWI'] < 30 else 'EXTREME')
        print(f"  {r['Date']}  FWI={r['FWI']:5.1f}  {danger:9s}  {bar}")
