"""
Fetch ECCC hourly weather data for Stanhope PE and save as CSV files
that IngestAgent can ingest alongside HOBO station data.

Saves one CSV per year-month into:
    data/raw/ECCC Stanhope Weather Station/<YEAR>/ECCC_Stanhope_<Mon><YEAR>.csv

Column headers match the ECCC bulk-download format so IngestAgent's
existing canonical-name mappings work out of the box.

Usage:
    python src/fetch_eccc.py                  # fetch 2024 May-Oct
    python src/fetch_eccc.py --year 2023      # fetch 2023 May-Oct
    python src/fetch_eccc.py --year 2023 --start-month 1 --end-month 12  # full year
"""

import argparse
import calendar
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime

CLIMATE_ID = "8300590"  # ECCC station ID for Stanhope PE
API_BASE = "https://api.weather.gc.ca/collections/climate-hourly/items"
DELAY = 1.0  # seconds between API pages

OUT_ROOT = os.path.join("data", "raw", "ECCC Stanhope Weather Station")

# Column mapping from ECCC API property names to standard CSV headers
# that IngestAgent._get_canonical_name() already handles.
CSV_COLUMNS = [
    "Date/Time (LST)",
    "Temp (°C)",
    "Rel Hum (%)",
    "Wind Spd (km/h)",
    "Wind Dir (10s deg)",
    "Precip. Amount (mm)",
    "Stn Press (kPa)",
    "Dew Point Temp (°C)",
]

# Map from CSV header to ECCC API property key
API_KEY_MAP = {
    "Date/Time (LST)":      "LOCAL_DATE",
    "Temp (°C)":            "TEMP",
    "Rel Hum (%)":          "RELATIVE_HUMIDITY",
    "Wind Spd (km/h)":      "WIND_SPEED",
    "Wind Dir (10s deg)":    "WIND_DIRECTION",
    "Precip. Amount (mm)":   "PRECIP_AMOUNT",
    "Stn Press (kPa)":      "STATION_PRESSURE",
    "Dew Point Temp (°C)":  "DEW_POINT_TEMP",
}


def fetch_month(climate_id: str, year: int, month: int) -> list:
    """Fetch all hourly records for one calendar month."""
    start_dt = f"{year}-{month:02d}-01T00:00:00"
    last_day = calendar.monthrange(year, month)[1]
    end_dt = f"{year}-{month:02d}-{last_day:02d}T23:59:59"

    records = []
    offset = 0
    limit = 500

    while True:
        params = {
            "CLIMATE_IDENTIFIER": climate_id,
            "datetime": f"{start_dt}/{end_dt}",
            "f": "json",
            "limit": limit,
            "offset": offset,
            "sortby": "LOCAL_DATE",
        }
        url = API_BASE + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "peinp-meteo-pipeline/1.0"}
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  API error at offset {offset}: {e}")
            break

        features = data.get("features", [])
        records.extend(features)
        total = data.get("numberMatched", len(records))

        if len(records) >= total or not features:
            break
        offset += limit
        time.sleep(DELAY)

    return records


def save_month_csv(records: list, year: int, month: int) -> str:
    """Save fetched records as a CSV file and return the path."""
    month_name = calendar.month_abbr[month]
    year_dir = os.path.join(OUT_ROOT, str(year))
    os.makedirs(year_dir, exist_ok=True)
    out_path = os.path.join(year_dir, f"ECCC_Stanhope_{month_name}{year}.csv")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for feat in records:
            props = feat.get("properties", {})
            row = {}
            for col_header, api_key in API_KEY_MAP.items():
                val = props.get(api_key)
                row[col_header] = val if val is not None else ""
            writer.writerow(row)

    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Fetch ECCC hourly data for Stanhope PE"
    )
    parser.add_argument("--year", type=int, default=2024,
                        help="Year to fetch (default: 2024)")
    parser.add_argument("--start-month", type=int, default=5,
                        help="First month to fetch (default: 5 = May)")
    parser.add_argument("--end-month", type=int, default=10,
                        help="Last month to fetch (default: 10 = Oct)")
    args = parser.parse_args()

    print(f"ECCC Stanhope Data Fetcher")
    print(f"  Station: STANHOPE PE (climate_id={CLIMATE_ID})")
    print(f"  Period:  {args.year}-{args.start_month:02d} to "
          f"{args.year}-{args.end_month:02d}")
    print(f"  Output:  {OUT_ROOT}/{args.year}/")
    print()

    total_records = 0
    for month in range(args.start_month, args.end_month + 1):
        month_name = calendar.month_name[month]
        print(f"  Fetching {month_name} {args.year}...", end=" ", flush=True)
        records = fetch_month(CLIMATE_ID, args.year, month)
        print(f"{len(records)} records", end="")

        if records:
            path = save_month_csv(records, args.year, month)
            print(f" -> {path}")
            total_records += len(records)
        else:
            print(" (skipped, no data)")

    print(f"\nDone. {total_records} total records saved.")


if __name__ == "__main__":
    main()
