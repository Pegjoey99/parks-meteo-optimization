import pandas as pd
import numpy as np
from pathlib import Path
import logging
import os


class IngestAgent:
    def __init__(self, data_dir="data/raw", output_dir="data/processed"):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("IngestAgent")
        self.logger.setLevel(logging.INFO)

    # ---------------------------------------------------------
    # Column name normalization
    # ---------------------------------------------------------
    def _get_canonical_name(self, col_lower):
        """Map a lowered verbose sensor column name to a canonical short name."""
        # Most specific patterns first to avoid false matches
        if "accumulated rain" in col_lower:
            return "accumulated_rain"
        if "dew point" in col_lower:
            return "dew_point"
        if "solar radiation" in col_lower:
            return "solar_radiation"
        if "barometric pressure" in col_lower:
            return "barometric_pressure"
        if "water temperature" in col_lower:
            return "water_temperature"
        if "water pressure" in col_lower:
            return "water_pressure"
        if "water flow" in col_lower:
            return "water_flow"
        if "water level" in col_lower:
            return "water_level"
        if "diff pressure" in col_lower:
            return "diff_pressure"
        if "battery" in col_lower:
            return "battery"

        # Wind — check gust before generic wind
        if "gust" in col_lower:
            if "m/s" in col_lower:
                return "gust_speed_ms"
            return "gust_speed"
        if "wind direction" in col_lower or "wind dir" in col_lower:
            return "wind_direction"
        if "wind" in col_lower and "speed" in col_lower:
            if "m/s" in col_lower:
                return "wind_speed_ms"
            return "wind"  # km/h — used by FWI

        # Core meteorological
        if "temperature" in col_lower:
            return "temperature"
        if col_lower.startswith("rh ") or col_lower.startswith("rh("):
            return "humidity"
        if "rain" in col_lower:
            return "rain"

        # ECCC column names (e.g. "temp (°c)", "rel hum (%)", "wind spd (km/h)")
        if col_lower.startswith("temp") and ("°c" in col_lower or "(c)" in col_lower):
            return "temperature"
        if "rel hum" in col_lower or "relative_humidity" in col_lower:
            return "humidity"
        if "wind spd" in col_lower:
            return "wind"
        if "precip" in col_lower:
            return "rain"
        if "stn press" in col_lower or "stn_pressure" in col_lower:
            return "barometric_pressure"

        return None

    def _normalize_columns(self, df):
        """Rename verbose sensor columns to canonical short names.

        When multiple columns map to the same canonical name (e.g. two
        temperature sensors), only the first is kept.
        Unmapped columns (unknown sensors) are dropped to keep the
        DataFrame consistent across stations.
        """
        rename_map = {}
        seen = set()
        drop_cols = []

        for col in df.columns:
            if col in ("Date", "Time", "source_file", "timestamp"):
                continue

            canonical = self._get_canonical_name(col.lower())

            if canonical is not None:
                if canonical not in seen:
                    rename_map[col] = canonical
                    seen.add(canonical)
                else:
                    drop_cols.append(col)  # duplicate canonical — drop
            else:
                drop_cols.append(col)  # unknown sensor — drop

        df = df.rename(columns=rename_map)
        if drop_cols:
            df = df.drop(columns=drop_cols, errors="ignore")

        self.logger.info(f"Normalized columns: {list(rename_map.values())}")
        return df

    # ---------------------------------------------------------
    # CSV loading (normalize columns per-file before concat)
    # ---------------------------------------------------------
    def _load_csvs(self):
        files = list(self.data_dir.rglob("*.csv"))
        if not files:
            raise FileNotFoundError(f"No CSV files found in {self.data_dir}")

        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f)
                df = self._normalize_columns(df)
                df["source_file"] = f.name
                # Derive station name from folder hierarchy
                # e.g. data/raw/Cavendish/2025/file.csv -> "Cavendish"
                parts = f.relative_to(self.data_dir).parts
                df["station"] = parts[0] if len(parts) > 1 else "unknown"
                dfs.append(df)
            except Exception as e:
                self.logger.warning(f"Skipping {f}: {e}")

        if not dfs:
            raise ValueError("No valid CSVs could be loaded.")

        combined = pd.concat(dfs, ignore_index=True)
        self.logger.info(f"Combined into DataFrame with shape: {combined.shape}")
        return combined

    # ---------------------------------------------------------
    # Timestamp handling (Date + Time combination)
    # ---------------------------------------------------------
    def _normalize_timestamp(self, df, target_col="timestamp"):
        # Combine Date + Time if both exist
        if "Date" in df.columns and "Time" in df.columns:
            df[target_col] = pd.to_datetime(
                df["Date"].astype(str) + " " + df["Time"].astype(str),
                errors="coerce",
                utc=True,
            )
            df = df.drop(columns=["Date", "Time"])
            df = df.dropna(subset=[target_col])
            df = df.sort_values(target_col).reset_index(drop=True)
            self.logger.info("Combined Date + Time into timestamp column.")
            return df

        # Fallback: find a timestamp-like column
        candidates = [
            "timestamp", "time", "datetime", "date_time",
            "date", "date/time", "date/time (lst)",
            "localtime", "obs_time", "observation_time",
        ]

        found = None
        for c in candidates:
            if c in df.columns:
                found = c
                break

        if found is None:
            for col in df.columns:
                if "time" in col.lower() or "date" in col.lower():
                    found = col
                    break

        if found is None:
            raise KeyError("No timestamp-like column found in ingested data.")

        self.logger.info(f"Normalizing timestamps from column: {found}")
        df[found] = pd.to_datetime(df[found], errors="coerce")
        df = df.dropna(subset=[found])
        if found != target_col:
            df = df.rename(columns={found: target_col})
        df = df.sort_values(target_col).reset_index(drop=True)
        return df

    # ---------------------------------------------------------
    # Numeric coercion (skip timestamp and source_file)
    # ---------------------------------------------------------
    def _coerce_numeric(self, df, timestamp_col="timestamp"):
        skip = {timestamp_col, "source_file", "station"}
        for col in df.columns:
            if col in skip:
                continue
            df[col] = pd.to_numeric(df[col], errors="coerce")
        self.logger.info("Coerced non-timestamp columns to numeric where possible.")
        return df

    # ---------------------------------------------------------
    # Main pipeline
    # ---------------------------------------------------------
    def ingest(self, resample=None, timestamp_col="timestamp"):
        df = self._load_csvs()
        df = self._normalize_timestamp(df, target_col=timestamp_col)
        df = self._coerce_numeric(df, timestamp_col=timestamp_col)

        # Drop source_file before resampling (not numeric)
        if "source_file" in df.columns:
            df = df.drop(columns=["source_file"])

        if resample is not None:
            if "station" in df.columns:
                # Resample per station to avoid blending different locations
                df = df.set_index(timestamp_col)
                resampled = (
                    df.groupby("station")
                    .resample(resample)
                    .mean(numeric_only=True)
                )
                resampled = resampled.reset_index()
                df = resampled
                self.logger.info(
                    f"Resampled to {resample} per station, shape: {df.shape}"
                )
            else:
                df = df.set_index(timestamp_col)
                df = df.resample(resample).mean(numeric_only=True)
                df = df.reset_index()
                self.logger.info(f"Resampled to {resample}, shape: {df.shape}")

        out_path = self.output_dir / "ingested_data.parquet"
        df.to_parquet(out_path, index=False)
        self.logger.info(f"Ingested data saved to {out_path}")

        return df
