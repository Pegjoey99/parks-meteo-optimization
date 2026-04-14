import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import seaborn as sns
import os
import logging


class RedundancyAgent:
    def __init__(self, output_dir="outputs/redundancy"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.logger = logging.getLogger("RedundancyAgent")
        self.logger.setLevel(logging.INFO)

    # ---------------------------------------------------------
    # 1. MERGE STATIONS SAFELY
    # ---------------------------------------------------------
    def merge_stations(self, df, on="timestamp"):
        """
        Accepts either a single DataFrame or a list of DataFrames.
        Returns a merged DataFrame with duplicates removed.
        """
        if isinstance(df, pd.DataFrame):
            merged = df.copy()
        elif isinstance(df, list) and len(df) > 0:
            merged = df[0].copy()
            for other in df[1:]:
                merged = pd.merge(
                    merged,
                    other,
                    on=on,
                    how="outer",
                    suffixes=("", "_dup")
                )
        else:
            raise ValueError("merge_stations received no valid DataFrames")

        # Drop duplicate columns
        dup_cols = [c for c in merged.columns if c.endswith("_dup")]
        if dup_cols:
            self.logger.info(f"Dropping duplicate columns: {dup_cols}")
            merged = merged.drop(columns=dup_cols)

        if on in merged.columns:
            merged = merged.sort_values(on).reset_index(drop=True)
        else:
            self.logger.warning(f"Column '{on}' not found for sorting. Skipping sort.")
            merged = merged.reset_index(drop=True)
        self.logger.info(f"Merged DataFrame shape: {merged.shape}")
        return merged

    # ---------------------------------------------------------
    # 2. STANDARDIZE NUMERIC COLUMNS SAFELY
    # ---------------------------------------------------------
    def standardize(self, df):
        df_std = df.copy()

        numeric_cols = df_std.select_dtypes(include=["float64", "int64"]).columns.tolist()

        if len(numeric_cols) == 0:
            self.logger.warning("No numeric columns found for standardization. Skipping.")
            return df_std

        # Drop columns that are entirely NaN
        numeric_cols = [c for c in numeric_cols if not df_std[c].isna().all()]

        if len(numeric_cols) == 0:
            self.logger.warning("All numeric columns are empty after cleaning. Skipping.")
            return df_std

        # Fill NaN with column means before scaling (StandardScaler cannot handle NaN)
        df_std[numeric_cols] = df_std[numeric_cols].fillna(df_std[numeric_cols].mean())

        scaler = StandardScaler()
        df_std[numeric_cols] = scaler.fit_transform(df_std[numeric_cols])

        self.logger.info(f"Standardized {len(numeric_cols)} numeric columns.")
        return df_std

    # ---------------------------------------------------------
    # 3. PCA WITH FALLBACK
    # ---------------------------------------------------------
    def run_pca(self, df, n_components=3):
        numeric_df = df.select_dtypes(include=["float64", "int64"])

        if numeric_df.empty:
            raise ValueError("No numeric columns available for PCA")

        # Drop columns that are all NaN
        numeric_df = numeric_df.dropna(axis=1, how="all")

        if numeric_df.empty:
            raise ValueError("All numeric columns are NaN — cannot run PCA")

        # Fill remaining NaNs with column means
        numeric_df = numeric_df.fillna(numeric_df.mean())

        pca = PCA(n_components=min(n_components, numeric_df.shape[1]))
        components = pca.fit_transform(numeric_df)

        explained = pca.explained_variance_ratio_

        self.logger.info(f"PCA completed. Variance explained: {explained}")

        return {
            "components": components,
            "explained_variance": explained,
            "pca_model": pca
        }

    # ---------------------------------------------------------
    # 4. CLUSTERING WITH FALLBACK
    # ---------------------------------------------------------
    def run_clustering(self, df, n_clusters=3):
        numeric_df = df.select_dtypes(include=["float64", "int64"])

        if numeric_df.empty:
            self.logger.warning("No numeric columns for clustering. Skipping.")
            return None

        numeric_df = numeric_df.fillna(numeric_df.mean())

        if numeric_df.shape[0] < n_clusters:
            self.logger.warning("Not enough samples for clustering. Skipping.")
            return None

        kmeans = KMeans(n_clusters=n_clusters, n_init=10)
        labels = kmeans.fit_predict(numeric_df)

        self.logger.info("Clustering completed.")
        return labels

    # ---------------------------------------------------------
    # 5. CORRELATION HEATMAP (SAFE)
    # ---------------------------------------------------------
    def correlation_heatmap(self, df):
        numeric_df = df.select_dtypes(include=["float64", "int64"])

        if numeric_df.empty:
            self.logger.warning("No numeric columns for correlation heatmap.")
            return None

        corr = numeric_df.corr()

        plt.figure(figsize=(12, 10))
        sns.heatmap(corr, cmap="coolwarm", center=0)
        path = os.path.join(self.output_dir, "correlation_heatmap.png")
        plt.savefig(path)
        plt.close()

        self.logger.info(f"Correlation heatmap saved to {path}")
        return path

    # ---------------------------------------------------------
    # 6. MAIN PIPELINE
    # ---------------------------------------------------------
    def run_analysis(self, df, merge_on="timestamp", pca_components=3):
        self.logger.info("Starting redundancy analysis...")

        merged = self.merge_stations(df, on=merge_on)
        standardized = self.standardize(merged)

        # PCA
        try:
            pca_result = self.run_pca(standardized, n_components=pca_components)
        except ValueError as e:
            self.logger.error(str(e))
            pca_result = None

        # Clustering
        clusters = self.run_clustering(standardized)

        # Correlation heatmap
        corr_path = self.correlation_heatmap(standardized)

        return {
            "merged": merged,
            "standardized": standardized,
            "pca": pca_result,
            "clusters": clusters,
            "correlation_heatmap": corr_path
        }
