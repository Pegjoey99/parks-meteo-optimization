import pandas as pd
import logging
import os


class CleanAgent:
    def __init__(self, output_dir="data/cleaned"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.logger = logging.getLogger("CleanAgent")
        self.logger.setLevel(logging.INFO)

    def detect_missing(self, df):
        missing = df.isna().sum()
        self.logger.info("Missing values per column (non-zero only):")
        self.logger.info(missing[missing > 0])
        return missing

    def validate_ranges(self, df):
        issues = {}

        def add_issue(name, mask):
            if mask.any():
                issues[name] = df[mask]
                self.logger.info(f"Range issues in {name}: {mask.sum()} rows")

        if "humidity" in df.columns:
            add_issue("humidity", (df["humidity"] < 0) | (df["humidity"] > 100))

        if "wind" in df.columns:
            add_issue("wind", df["wind"] < 0)

        if "temperature" in df.columns:
            add_issue("temperature", (df["temperature"] < -50) | (df["temperature"] > 50))

        if "rain" in df.columns:
            add_issue("rain", df["rain"] < 0)

        return issues

    def simple_clean(self, df, max_missing_frac=0.8):
        # Drop columns that are mostly missing
        thresh = int((1 - max_missing_frac) * len(df))
        df_clean = df.dropna(axis=1, thresh=thresh)

        # Fill remaining numeric NaNs with column means
        num_cols = df_clean.select_dtypes(include=["float64", "int64"]).columns
        df_clean[num_cols] = df_clean[num_cols].fillna(df_clean[num_cols].mean())

        self.logger.info(
            f"Cleaned DataFrame shape: {df_clean.shape} "
            f"(from original {df.shape})"
        )
        return df_clean

    def run(self, df, filename="cleaned_data.parquet"):
        self.logger.info("Starting cleaning pipeline...")
        self.detect_missing(df)
        self.validate_ranges(df)
        cleaned = self.simple_clean(df)

        out_path = os.path.join(self.output_dir, filename)
        cleaned.to_parquet(out_path, index=False)
        self.logger.info(f"Cleaned data saved to {out_path}")

        return cleaned
