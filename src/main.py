import logging
import os
from pathlib import Path

import pandas as pd

from agents.ingest_agent import IngestAgent
from agents.clean_agent import CleanAgent
from agents.fwi_agent import FWIAgent
from agents.redundancy_agent import RedundancyAgent
from agents.uncertainty_agent import UncertaintyAgent


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    setup_logging()
    logger = logging.getLogger("MAIN")

    logger.info("=== Starting Meteorological Optimization Pipeline ===")

    # ---------------------------------------------------------
    # Initialize agents
    # ---------------------------------------------------------
    ingest_agent = IngestAgent(
        data_dir="data/raw",
        output_dir="data/processed"
    )

    clean_agent = CleanAgent(
        output_dir="data/cleaned"
    )

    redundancy_agent = RedundancyAgent(
        output_dir="outputs/redundancy"
    )

    uncertainty_agent = UncertaintyAgent(
        output_dir="outputs/uncertainty"
    )

    fwi_agent = FWIAgent(
        output_dir="outputs/fwi"
    )

    # ---------------------------------------------------------
    # 1. INGESTION
    # ---------------------------------------------------------
    logger.info("Running ingestion...")
    try:
        ingested_df = ingest_agent.ingest(resample="D")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return

    # ---------------------------------------------------------
    # 2. CLEANING
    # ---------------------------------------------------------
    logger.info("Running cleaning...")
    try:
        cleaned_df = clean_agent.run(ingested_df)
    except Exception as e:
        logger.error(f"Cleaning failed: {e}")
        return

    # ---------------------------------------------------------
    # 3. FWI COMPUTATION
    # ---------------------------------------------------------
    logger.info("Computing Fire Weather Index...")
    try:
        fwi_df, fwi_plot = fwi_agent.compute_fwi(
            cleaned_df, fire_season=(5, 10)
        )
        logger.info(f"FWI computed. Shape: {fwi_df.shape}")
    except Exception as e:
        logger.error(f"FWI computation failed: {e}")
        fwi_df = None

    # ---------------------------------------------------------
    # 4. REDUNDANCY ANALYSIS (PCA, clustering, correlation)
    # ---------------------------------------------------------
    logger.info("Running redundancy analysis...")
    try:
        redundancy_result = redundancy_agent.run_analysis(
            cleaned_df,
            merge_on="timestamp"
        )
    except Exception as e:
        logger.error(f"Redundancy analysis failed: {e}")
        redundancy_result = None

    # ---------------------------------------------------------
    # 5. UNCERTAINTY ANALYSIS (KDE)
    # ---------------------------------------------------------
    logger.info("Running uncertainty analysis...")
    try:
        uncertainty_result = uncertainty_agent.run_analysis(
            ingested_df,
            cleaned_df
        )
    except Exception as e:
        logger.error(f"Uncertainty analysis failed: {e}")
        uncertainty_result = None

    # ---------------------------------------------------------
    # 6. CROSS-VALIDATION (Stanhope reference FWI)
    # ---------------------------------------------------------
    cross_val = None
    ref_pattern = Path("stanhope-fwi/data/stanhope")
    ref_files = sorted(ref_pattern.glob("fwi_stanhope_computed_*.csv")) if ref_pattern.exists() else []

    if ref_files:
        logger.info("Running FWI cross-validation against Stanhope reference...")
        try:
            ref_df = pd.read_csv(ref_files[0], parse_dates=["Date"], index_col="Date")
            # Map reference columns to our canonical names
            ref_input = ref_df.rename(columns={
                "T_noon": "temperature",
                "RH_noon": "humidity",
                "Wind_noon": "wind",
                "Precip_24h": "rain",
            })
            ref_input = ref_input[["temperature", "humidity", "wind", "rain"]]

            # Run our FWI on the exact same weather inputs
            our_result, _ = fwi_agent.compute_fwi(
                ref_input,
                save_as="fwi_crossval.csv",
                plot=False,
            )

            # Build reference outputs for comparison (lowercase column names)
            ref_output = ref_df[["FFMC", "DMC", "DC", "ISI", "BUI", "FWI"]].copy()
            ref_output.columns = [c.lower() for c in ref_output.columns]

            cross_val = fwi_agent.validate(our_result, ref_output)
            logger.info(f"Cross-validation results: {cross_val}")
        except Exception as e:
            logger.error(f"Cross-validation failed: {e}")
    else:
        logger.info(
            "Stanhope reference CSV not found — skipping cross-validation. "
            "Run stanhope-fwi/compute_stanhope_fwi.py to generate it."
        )

    # ---------------------------------------------------------
    # 7. FINAL SUMMARY
    # ---------------------------------------------------------
    logger.info("=== Pipeline Complete ===")

    summary = {
        "ingested_rows": len(ingested_df),
        "cleaned_rows": len(cleaned_df),
        "fwi": fwi_df,
        "redundancy": redundancy_result,
        "uncertainty": uncertainty_result,
        "cross_validation": cross_val,
    }

    logger.info("Pipeline summary generated.")
    logger.info("You can now use the outputs for reporting and visualization.")

    return summary


if __name__ == "__main__":
    main()