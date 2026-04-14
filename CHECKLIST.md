# Pipeline Checklist — Parks Meteo Optimization

## 1. Data Ingestion
- [x] Raw CSV files present in `data/raw/` for all stations
- [x] `IngestAgent` loads all station folders without errors
- [x] Daily resampling (`resample='D'`) produces expected row count (5086 rows)
- [x] Ingested DataFrame columns match expected schema (20 columns)

## 2. Data Cleaning
- [x] `CleanAgent` runs without errors
- [x] Missing values handled (imputed or dropped)
- [x] Outliers flagged or removed (2 temperature range issues)
- [x] Cleaned output saved to `data/cleaned/cleaned_data.parquet`
- [x] Row retention rate is acceptable (5086/5086 = 100% rows retained, 20→16 columns)

## 3. Redundancy Analysis (PCA & Clustering)
- [x] PCA explained variance computed ([23.1%, 15.3%, 14.6%])
- [x] Number of components for ≥90% variance identified
- [x] K-Means clustering labels assigned (3 clusters: 351, 2322, 2413)
- [x] Correlation heatmap generated and saved to `outputs/redundancy/`
- [x] Redundant variables flagged for review (wind/gust_speed r=0.96)

## 4. FWI Computation
- [x] `FWIAgent` computes all indices (FFMC, DMC, DC, ISI, BUI, FWI)
- [x] FWI values within expected physical ranges (FWI 0.68–55.79)
- [x] Range validation report passes all checks (PASSED ✓)
- [x] FWI time-series plot saved to `outputs/fwi/fwi_plot.png`
- [x] High/Very-High FWI days counted and reviewed (peak 55.8 at Stanley Bridge)

## 5. Uncertainty Modeling
- [x] `UncertaintyAgent` compares ingested vs cleaned distributions
- [x] Probability loss (Total Variation distance) computed per variable
- [x] KDE plots generated for core variables (temperature, humidity, wind, rain)
- [x] Plots saved to `outputs/uncertainty/` (28 KDE plots)
- [x] High-impact variables (TV > 0.10) flagged (water_level 0.479, water_temp 0.420, barometric/water/diff pressure, humidity, dew_point, wind, gust_speed)

## 6. Visualization & Reporting
- [x] Time-series plots for temperature, humidity, wind, rain
- [x] Correlation matrix heatmap generated
- [x] Summary & Recommendations cell executed
- [ ] Actionable recommendations reviewed by team

## 7. Final Validation
- [x] All outputs present under `outputs/` and `data/`
- [x] Notebook runs end-to-end without errors (`Run All`)
- [x] Results cross-checked against Stanhope FWI reference (368 days, FWI MAE=0.37)
- [ ] Findings documented and communicated to stakeholders
