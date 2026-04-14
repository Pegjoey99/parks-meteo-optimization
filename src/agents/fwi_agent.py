import logging
import math
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


class FWIAgent:
    """Compute Fire Weather Index series using Van Wagner (1987) equations.

    Reference
    ---------
    Van Wagner, C.E. (1987). Development and structure of the Canadian
    Forest Fire Weather Index System. Forestry Technical Report 35.
    Canadian Forest Service, Ottawa.
    """

    def __init__(self, output_dir="outputs/fwi"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("FWIAgent")
        self.logger.setLevel(logging.INFO)

    # ── Van Wagner 1987 equations ─────────────────────────────

    @staticmethod
    def _ffmc_next(ffmc_prev: float, temp: float, rh: float,
                   wind: float, rain: float) -> float:
        """Fine Fuel Moisture Code (1-day memory, surface litter)."""
        mo = 147.2 * (101.0 - ffmc_prev) / (59.5 + ffmc_prev)

        # Rain wetting phase
        if rain > 0.5:
            rf = rain - 0.5
            if mo > 150.0:
                mo = (mo + 42.5 * rf * math.exp(-100.0 / (251.0 - mo))
                      * (1.0 - math.exp(-6.93 / rf))
                      + 0.0015 * (mo - 150.0) ** 2 * rf ** 0.5)
            else:
                mo = (mo + 42.5 * rf * math.exp(-100.0 / (251.0 - mo))
                      * (1.0 - math.exp(-6.93 / rf)))
            if mo > 250.0:
                mo = 250.0

        # Equilibrium moisture content
        ed = (0.942 * rh ** 0.679
              + 11.0 * math.exp((rh - 100.0) / 10.0)
              + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh)))
        ew = (0.618 * rh ** 0.753
              + 10.0 * math.exp((rh - 100.0) / 10.0)
              + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh)))

        # Drying / wetting
        if mo > ed:
            ko = (0.424 * (1.0 - (rh / 100.0) ** 1.7)
                  + 0.0694 * wind ** 0.5 * (1.0 - (rh / 100.0) ** 8))
            kd = ko * 0.581 * math.exp(0.0365 * temp)
            m = ed + (mo - ed) * 10.0 ** (-kd)
        elif mo < ew:
            ko = (0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7)
                  + 0.0694 * wind ** 0.5 * (1.0 - ((100.0 - rh) / 100.0) ** 8))
            kw = ko * 0.581 * math.exp(0.0365 * temp)
            m = ew - (ew - mo) * 10.0 ** (-kw)
        else:
            m = mo

        return 59.5 * (250.0 - m) / (147.2 + m)

    @staticmethod
    def _dmc_next(dmc_prev: float, temp: float, rh: float,
                  rain: float, month: int) -> float:
        """Duff Moisture Code (~12-day memory, upper soil layer)."""
        # Effective day-length factors by month (Van Wagner Table 1)
        el = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9,
              12.4, 10.9, 9.4, 8.0, 7.8, 6.3]

        if temp < -1.1:
            temp = -1.1

        rk = 1.894 * (temp + 1.1) * (100.0 - rh) * el[month - 1] * 1e-4

        if rain > 1.5:
            ra = rain - 1.5
            rw = 0.92 * ra - 1.27
            wmi = 20.0 + 280.0 / math.exp(0.023 * dmc_prev)
            if dmc_prev <= 33.0:
                b = 100.0 / (0.5 + 0.3 * dmc_prev)
            elif dmc_prev <= 65.0:
                b = 14.0 - 1.3 * math.log(dmc_prev)
            else:
                b = 6.2 * math.log(dmc_prev) - 17.2
            wmr = wmi + 1000.0 * rw / (48.77 + b * rw)
            pr = 43.43 * (5.6348 - math.log(wmr - 20.0))
        else:
            pr = dmc_prev

        if pr < 0.0:
            pr = 0.0
        return pr + rk

    @staticmethod
    def _dc_next(dc_prev: float, temp: float, rain: float,
                 month: int) -> float:
        """Drought Code (~52-day memory, deep soil moisture)."""
        # Day-length adjustment factors by month (Van Wagner Table 2)
        fl = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8,
              6.4, 5.0, 2.4, 0.4, -1.6, -1.6]

        if temp < -2.8:
            temp = -2.8

        pe = (0.36 * (temp + 2.8) + fl[month - 1]) / 2.0
        if pe < 0.0:
            pe = 0.0

        if rain > 2.8:
            ra = rain - 2.8
            rw = 0.83 * ra - 1.27
            smi = 800.0 * math.exp(-dc_prev / 400.0)
            dr = dc_prev - 400.0 * math.log(1.0 + 3.937 * rw / smi)
            if dr < 0.0:
                dr = 0.0
        else:
            dr = dc_prev

        return dr + pe

    @staticmethod
    def _isi(wind: float, ffmc_val: float) -> float:
        """Initial Spread Index (fire spread rate from FFMC + wind)."""
        fm = 147.2 * (101.0 - ffmc_val) / (59.5 + ffmc_val)
        sf = 19.115 * math.exp(-0.1386 * fm) * (1.0 + fm ** 5.31 / 4.93e7)
        return sf * math.exp(0.05039 * wind)

    @staticmethod
    def _bui(dmc_val: float, dc_val: float) -> float:
        """Buildup Index (total fuel available from DMC + DC)."""
        if dmc_val <= 0.4 * dc_val:
            return 0.8 * dmc_val * dc_val / (dmc_val + 0.4 * dc_val)
        else:
            u = (dmc_val
                 - (1.0 - 0.8 * dc_val / (dmc_val + 0.4 * dc_val))
                 * (0.92 + (0.0114 * dmc_val) ** 1.7))
            return max(u, 0.0)

    @staticmethod
    def _fwi(isi_val: float, bui_val: float) -> float:
        """Fire Weather Index (overall fire intensity from ISI + BUI)."""
        if bui_val <= 80.0:
            bb = 0.1 * isi_val * (0.626 * bui_val ** 0.809 + 2.0)
        else:
            bb = 0.1 * isi_val * (1000.0 / (25.0 + 108.64
                                             * math.exp(-0.023 * bui_val)))
        if bb <= 1.0:
            return bb
        return math.exp(2.72 * (0.434 * math.log(bb)) ** 0.647)

    # ── Main computation ──────────────────────────────────────

    def _compute_single_series(self, df, ffmc_init, dmc_init, dc_init):
        """Compute FWI for a single sorted, NaN-free DataFrame."""
        out = []
        ffmc_val, dmc_val, dc_val = ffmc_init, dmc_init, dc_init

        for timestamp, row in df.iterrows():
            temp = float(row['temperature'])
            rh = float(row['humidity'])
            wind = float(row['wind'])
            rain = float(row['rain'])

            month = timestamp.month if hasattr(timestamp, 'month') else 1

            ffmc_val = self._ffmc_next(ffmc_val, temp, rh, wind, rain)
            dmc_val = self._dmc_next(dmc_val, temp, rh, rain, month)
            dc_val = self._dc_next(dc_val, temp, rain, month)

            isi_val = self._isi(wind, ffmc_val)
            bui_val = self._bui(dmc_val, dc_val)
            fwi_val = self._fwi(isi_val, bui_val)

            out.append({
                'temperature': temp,
                'humidity': rh,
                'wind': wind,
                'rain': rain,
                'ffmc': ffmc_val,
                'dmc': dmc_val,
                'dc': dc_val,
                'isi': isi_val,
                'bui': bui_val,
                'fwi': fwi_val,
            })

        return pd.DataFrame(out, index=df.index)

    def compute_fwi(self, df, ffmc_init=85.0, dmc_init=6.0, dc_init=15.0,
                    save_as='fwi_results.csv', plot=True,
                    fire_season=None):
        """Compute daily FWI from a meteorological DataFrame.

        Required columns: temperature, humidity, wind, rain.
        If a 'station' column is present, FWI is computed independently
        per station so that moisture codes do not leak across locations.
        Timestamp can be a 'timestamp' or 'date' column, or the index.

        Parameters
        ----------
        fire_season : tuple of int, optional
            (start_month, end_month) to restrict computation to fire season.
            E.g. ``(5, 10)`` for May–October (standard Atlantic Canada).
            Moisture codes are reset to startup values at the beginning of
            each season.  When *None* (default), all rows are processed.
        """
        self.logger.info("Starting FWI computation")

        df = df.copy()
        has_station = 'station' in df.columns

        # Set timestamp/date as index if present
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')

        # Validate required columns
        required = ['temperature', 'humidity', 'wind', 'rain']
        missing_cols = [c for c in required if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns for FWI: {missing_cols}")

        # Drop rows with NaN in required columns
        df = df.dropna(subset=required)
        if df.empty:
            raise ValueError("No valid rows after dropping NaN in required FWI columns")

        # Fire season filter
        if fire_season is not None:
            sm, em = fire_season
            before = len(df)
            df = df[df.index.month.isin(range(sm, em + 1))]
            self.logger.info(
                f"Fire season filter (months {sm}–{em}): "
                f"{before} -> {len(df)} rows"
            )
            if df.empty:
                raise ValueError("No rows left after fire season filter")

        df = df.sort_index()

        if has_station:
            stations = sorted(df['station'].unique())
            self.logger.info(
                f"Computing FWI per station: {stations} "
                f"({len(df)} total time steps)"
            )
            parts = []
            for stn in stations:
                stn_df = df.loc[df['station'] == stn].drop(columns=['station'])
                stn_df = stn_df.sort_index()
                stn_result = self._compute_single_series(
                    stn_df, ffmc_init, dmc_init, dc_init
                )
                stn_result['station'] = stn
                parts.append(stn_result)
                self.logger.info(
                    f"  {stn}: {len(stn_result)} days, "
                    f"peak FWI {stn_result['fwi'].max():.1f}"
                )
            result = pd.concat(parts)
            result = result.sort_index()
        else:
            self.logger.info(f"Processing {len(df)} time steps")
            result = self._compute_single_series(
                df, ffmc_init, dmc_init, dc_init
            )

        self.logger.info(f"FWI computation complete. Shape: {result.shape}")

        save_path = self.output_dir / save_as
        result.to_csv(save_path, index=True)
        self.logger.info(f"Saved FWI results to {save_path}")

        plot_path = None
        if plot:
            plot_path = self.plot_fwi(result)

        return result, plot_path

    def validate(self, result: pd.DataFrame, reference: pd.DataFrame) -> Dict[str, float]:
        """Validate computed FWI values against reference values."""
        self.logger.info("Starting FWI validation")
        common_idx = result.index.intersection(reference.index)
        if common_idx.empty:
            self.logger.warning("No overlapping index for validation")
            raise ValueError("No overlapping index for validation")

        cur = result.loc[common_idx]
        ref = reference.loc[common_idx]

        metrics = {}
        for col in ['ffmc', 'dmc', 'dc', 'isi', 'bui', 'fwi']:
            if col in cur.columns and col in ref.columns:
                diff = np.abs(cur[col] - ref[col])
                metrics[f'{col}_mae'] = float(diff.mean())
                metrics[f'{col}_max_error'] = float(diff.max())
                self.logger.info(
                    f"{col.upper()} - MAE: {metrics[f'{col}_mae']:.4f}, "
                    f"Max Error: {metrics[f'{col}_max_error']:.4f}"
                )

        self.logger.info("FWI validation complete")
        return metrics

    def validate_ranges(self, fwi_df: pd.DataFrame) -> Dict:
        """Validate FWI outputs against physically expected ranges.

        Expected ranges (Van Wagner 1987):
            FFMC : 0 – 101
            DMC  : >= 0
            DC   : >= 0
            ISI  : >= 0
            BUI  : >= 0
            FWI  : >= 0
        """
        self.logger.info("Validating FWI against expected ranges")

        checks = {
            'ffmc': {'min': 0.0, 'max': 101.0},
            'dmc':  {'min': 0.0, 'max': None},
            'dc':   {'min': 0.0, 'max': None},
            'isi':  {'min': 0.0, 'max': None},
            'bui':  {'min': 0.0, 'max': None},
            'fwi':  {'min': 0.0, 'max': None},
        }

        report: Dict = {}
        all_passed = True

        for col, bounds in checks.items():
            if col not in fwi_df.columns:
                continue

            series = fwi_df[col].dropna()
            col_min = float(series.min())
            col_max = float(series.max())
            col_mean = float(series.mean())

            below = int((series < bounds['min']).sum()) if bounds['min'] is not None else 0
            above = int((series > bounds['max']).sum()) if bounds['max'] is not None else 0
            violations = below + above
            passed = violations == 0

            if not passed:
                all_passed = False
                self.logger.warning(
                    f"{col.upper()} range violations: {violations} "
                    f"(below {bounds['min']}: {below}, above {bounds['max']}: {above})"
                )
            else:
                self.logger.info(
                    f"{col.upper()} OK — min={col_min:.2f}, max={col_max:.2f}, mean={col_mean:.2f}"
                )

            report[col] = {
                'min': col_min,
                'max': col_max,
                'mean': col_mean,
                'violations': violations,
                'passed': passed,
            }

        report['all_passed'] = all_passed
        self.logger.info(f"Range validation {'PASSED' if all_passed else 'FAILED'}")
        return report

    def plot_fwi(self, fwi_df: pd.DataFrame, save_as: str = 'fwi_plot.png') -> Path:
        """Plot FWI time series."""
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 6))
        plt.plot(fwi_df.index, fwi_df['fwi'], label='FWI', color='red')
        plt.plot(fwi_df.index, fwi_df['ffmc'], label='FFMC', alpha=0.7)
        plt.plot(fwi_df.index, fwi_df['dmc'], label='DMC', alpha=0.7)
        plt.plot(fwi_df.index, fwi_df['dc'], label='DC', alpha=0.7)
        plt.xlabel('Date')
        plt.ylabel('Index Value')
        plt.title('Fire Weather Indices Over Time')
        plt.legend()
        plt.grid(True, alpha=0.3)

        output_path = self.output_dir / save_as
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()
        self.logger.info(f"Saved FWI plot to {output_path}")
        return output_path
