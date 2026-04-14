# Parks Meteo Optimization

## Overview

Parks Meteo Optimization is a Python-based pipeline for analyzing meteorological data from Prince Edward Island National Park (PEINP). The project uses a modular agent-based architecture to perform data ingestion, quality assurance, redundancy analysis, Fire Weather Index (FWI) computation, and uncertainty modeling — enabling optimized weather station network management and fire risk assessment.

Key features:
- Automated ingestion of HOBO weather station CSVs and ECCC (Environment and Climate Change Canada) hourly data
- Per-station identity preserved through the full pipeline (no cross-station blending)
- Data cleaning with missing value handling and outlier detection
- Redundancy analysis using PCA and K-means clustering
- FWI computation using verified Van Wagner (1987) equations with optional fire-season filtering
- Cross-validation against independent Stanhope reference FWI (MAE < 0.003 across all indices)
- Uncertainty quantification using KDE distributions with Total Variation distance
- Interactive Jupyter notebook for exploratory analysis

## Data Sources

### HOBO Weather Stations (5 stations)
- **Cavendish**, **Greenwich**, **North Rustico Wharf**, **Stanley Bridge Wharf**, **Tracadie Wharf**
- Hourly CSVs in `data/raw/<StationName>/<Year>/`
- Columns: temperature, humidity, wind speed, rain, solar radiation, barometric pressure, etc.

### ECCC Stanhope Weather Station
- Climate ID: 8300590 — operational since 1961
- Hourly data fetched via ECCC MSC GeoMet API using `src/fetch_eccc.py`
- CSVs saved to `data/raw/ECCC Stanhope Weather Station/<Year>/`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Pegjoey99/parks-meteo-optimization.git
   cd parks-meteo-optimization
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Pipeline

1. Place your meteorological CSV files in `data/raw/`, organized by station and year:
   ```
   data/raw/Cavendish/2024/PEINP_Cav_WeatherStn_May2024.csv
   data/raw/Greenwich/2024/PEINP_GR_WeatherStn_May2024.csv
   ```

2. (Optional) Fetch ECCC Stanhope data:
   ```bash
   python src/fetch_eccc.py --year 2024 --start-month 5 --end-month 10
   ```

3. Run the main pipeline:
   ```bash
   python src/main.py
   ```

   The pipeline executes these stages:
   1. **Ingestion** — loads all station CSVs, normalizes columns, resamples to daily per station
   2. **Cleaning** — drops sparse columns, imputes missing values, flags outliers
   3. **FWI computation** — computes Van Wagner (1987) indices per station (May–Oct fire season)
   4. **Redundancy analysis** — PCA, K-means clustering, correlation heatmap
   5. **Uncertainty analysis** — KDE distributions with probability loss scoring
   6. **Cross-validation** — compares pipeline FWI against Stanhope reference (if available)

   Outputs are saved to `outputs/fwi/`, `outputs/redundancy/`, and `outputs/uncertainty/`.

## Notebook Usage

For interactive analysis and visualization:

1. Launch Jupyter Notebook:
   ```bash
   jupyter notebook
   ```

2. Open `notebooks/analysis.ipynb`

3. Run cells sequentially to:
   - Import libraries and agents
   - Load and preprocess data
   - Perform redundancy analysis
   - Compute FWI
   - Analyze uncertainty
   - Generate visualizations

The notebook provides step-by-step execution with inline plots and results.

## Project Structure

```
parks-meteo-optimization/
├── src/
│   ├── agents/
│   │   ├── ingest_agent.py      # Data ingestion and preprocessing
│   │   ├── clean_agent.py       # QA/QC and data cleaning
│   │   ├── redundancy_agent.py  # PCA and clustering analysis
│   │   ├── fwi_agent.py         # Fire Weather Index (Van Wagner 1987)
│   │   └── uncertainty_agent.py # Uncertainty modeling with KDE
│   ├── main.py                  # Main pipeline execution
│   └── fetch_eccc.py            # ECCC API data fetcher for Stanhope
├── stanhope-fwi/                # Reference FWI implementation (standalone)
│   └── compute_stanhope_fwi.py  # Standalone Stanhope FWI from ECCC API
├── data/
│   ├── raw/                     # Input CSV files (per station/year)
│   │   ├── Cavendish/
│   │   ├── Greenwich/
│   │   ├── North Rustico Wharf/
│   │   ├── Stanley Bridge Wharf/
│   │   ├── Tracadie Wharf/
│   │   └── ECCC Stanhope Weather Station/
│   ├── interim/                 # Intermediate processed data
│   └── processed/               # Ingested parquet output
├── outputs/
│   ├── fwi/                     # FWI results, cross-validation, plots
│   ├── redundancy/              # PCA, clustering, correlation heatmaps
│   └── uncertainty/             # KDE plots and probability loss
├── notebooks/
│   └── analysis.ipynb           # Interactive analysis notebook
├── README.md
└── requirements.txt
```

## Key Outputs

| Output | File | Description |
|---|---|---|
| FWI per station | `outputs/fwi/fwi_results.csv` | Daily FFMC, DMC, DC, ISI, BUI, FWI per station (fire season) |
| Cross-validation | `outputs/fwi/fwi_crossval.csv` | Pipeline FWI vs Stanhope reference |
| FWI plot | `outputs/fwi/fwi_plot.png` | Time series of fire weather indices |
| Correlation heatmap | `outputs/redundancy/correlation_heatmap.png` | Inter-variable correlations |
| KDE plots | `outputs/uncertainty/*.png` | Distribution comparison (raw vs cleaned) |

## Column Conventions

The pipeline normalizes all sensor columns to canonical short names:

| Canonical Name | Description | Used by FWI |
|---|---|---|
| `temperature` | Air temperature (°C) | ✓ |
| `humidity` | Relative humidity (%) | ✓ |
| `wind` | Wind speed (km/h) | ✓ |
| `rain` | Precipitation (mm) | ✓ |
| `station` | Station name (derived from folder) | grouping |
| `wind_direction` | Wind direction (degrees) | |
| `barometric_pressure` | Station pressure (kPa) | |
| `dew_point` | Dew point temperature (°C) | |
| `solar_radiation` | Solar radiation (W/m²) | |

## Requirements

- Python 3.8+
- pandas
- numpy
- matplotlib
- seaborn
- scikit-learn
- scipy
- pyarrow (Parquet support)
- openpyxl (Excel support)

See `requirements.txt` for exact versions.

## References

- Van Wagner, C.E. (1987). *Development and structure of the Canadian Forest Fire Weather Index System.* Forestry Technical Report 35. Canadian Forest Service, Ottawa.
- ECCC MSC GeoMet API: `https://api.weather.gc.ca/`

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.