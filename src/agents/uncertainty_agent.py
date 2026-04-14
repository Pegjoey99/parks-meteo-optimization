import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
import matplotlib.pyplot as plt
import os
import logging


class UncertaintyAgent:
    def __init__(self, output_dir="outputs/uncertainty"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.logger = logging.getLogger("UncertaintyAgent")
        self.logger.setLevel(logging.INFO)

    def _safe_kde(self, series, bw_method="scott"):
        clean = series.dropna().values

        if len(clean) < 10:
            self.logger.warning("Too few points for KDE. Skipping.")
            return None

        if np.var(clean) < 1e-6:
            self.logger.warning("Variance too low for KDE. Skipping.")
            return None

        try:
            kde = gaussian_kde(clean, bw_method=bw_method)
            return kde
        except Exception as e:
            self.logger.warning(f"KDE failed: {e}")
            return None

    def _prob_loss(self, orig_kde, clean_kde, orig_series, clean_series, n_points=500):
        """Compute probability loss between original and cleaned distributions.

        Uses Total Variation distance:
            TV = 0.5 * integral( |p_orig(x) - p_clean(x)| ) dx

        Returns a value in [0, 1] where 0 = identical distributions and
        1 = completely disjoint distributions.
        """
        lo = min(float(orig_series.min()), float(clean_series.min()))
        hi = max(float(orig_series.max()), float(clean_series.max()))

        xs = np.linspace(lo, hi, n_points)
        dx = (hi - lo) / (n_points - 1)

        p_orig = orig_kde(xs)
        p_clean = clean_kde(xs)

        tv = 0.5 * np.sum(np.abs(p_orig - p_clean)) * dx
        return float(np.clip(tv, 0.0, 1.0))

    def _plot_kde(self, kde, series, name):
        xs = np.linspace(series.min(), series.max(), 200)
        ys = kde(xs)

        plt.figure(figsize=(8, 5))
        plt.plot(xs, ys)
        plt.title(f"KDE for {name}")
        plt.xlabel(name)
        plt.ylabel("Density")

        path = os.path.join(self.output_dir, f"kde_{name}.png")
        plt.savefig(path)
        plt.close()

        self.logger.info(f"KDE plot saved to {path}")
        return path

    def run_analysis(self, ingested_df, cleaned_df, variables=None):
        """
        Compare original vs cleaned distributions for selected variables.
        """
        self.logger.info("Starting uncertainty analysis...")

        if variables is None:
            variables = cleaned_df.select_dtypes(include=["float64", "int64"]).columns.tolist()

        results = {}

        for var in variables:
            if var not in ingested_df.columns or var not in cleaned_df.columns:
                continue

            orig = ingested_df[var]
            clean = cleaned_df[var]

            orig_kde = self._safe_kde(orig)
            clean_kde = self._safe_kde(clean)

            var_result = {"original_kde": None, "cleaned_kde": None, "prob_loss": None}

            if orig_kde is not None:
                var_result["original_kde_plot"] = self._plot_kde(orig_kde, orig, f"{var}_original")

            if clean_kde is not None:
                var_result["cleaned_kde_plot"] = self._plot_kde(clean_kde, clean, f"{var}_cleaned")

            if orig_kde is not None and clean_kde is not None:
                var_result["prob_loss"] = self._prob_loss(orig_kde, clean_kde, orig, clean)
                self.logger.info(f"{var} prob_loss = {var_result['prob_loss']:.4f}")

            results[var] = var_result

        self.logger.info("Uncertainty analysis completed.")
        return results