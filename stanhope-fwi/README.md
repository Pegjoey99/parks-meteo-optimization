# Stanhope Fire Weather Index

This repository demonstrates how to compute the **Canadian Forest Fire Weather Index (FWI)** for the Stanhope weather station on Prince Edward Island, using open data published by Environment and Climate Change Canada (ECCC).

## Background

The FWI System is the standard Canadian tool for quantifying fire weather danger. It takes four daily weather observations (measured at noon local time) and produces six indices describing fuel moisture and potential fire behaviour:

| Index | What it represents |
|---|---|
| FFMC | Fine fuel moisture - how easily surface litter ignites |
| DMC  | Duff moisture - moisture in the upper soil and organic layer |
| DC   | Drought code - deep soil moisture deficit over the whole season |
| ISI  | Initial spread index - how fast a fire would spread |
| BUI  | Buildup index - total available fuel |
| **FWI** | **Fire Weather Index - the overall fire danger number** |

Each moisture code carries "memory" of prior days: FFMC responds within a day, DMC over about two weeks, DC over the whole season. This is why the script must run sequentially from the start of the fire season and cannot compute one day in isolation.

### Why not just use the CWFIS map?

The [CWFIS interactive map](https://cwfis.cfs.nrcan.gc.ca) shows FWI on a 250 m raster grid, but the grid is **masked to burnable forest fuel types**. Stanhope sits within a coastal national park (dunes, beach, non-forested habitat) which the fuel model classifies as non-burnable. No FWI cell is assigned to Stanhope in the raster even though fire weather conditions at the station are real and operationally relevant.

We solve this by going back to the source: pulling the actual hourly weather observations recorded at the Stanhope station and running the FWI equations ourselves.

## Data source

**ECCC MSC GeoMet open data API** - no registration or API key required.

- Station: **STANHOPE**, Prince Edward Island
- Climate ID: `8300590`
- Coordinates: 46.416N, 63.083W, elevation 3 m
- Hourly record: 2013-12-10 to present
- API endpoint: `https://api.weather.gc.ca/collections/climate-hourly/items`

## Repository contents

```
compute_stanhope_fwi.py              - fetch data and compute FWI for any year
data/
  stanhope/
    fwi_stanhope_computed_2025.csv   - pre-computed example (fire season 2025)
```

## Pre-computed example: 2025 fire season

The file `data/stanhope/fwi_stanhope_computed_2025.csv` contains the computed FWI for Stanhope across the 2025 fire season (May-October), with columns:

| Column | Description |
|---|---|
| Date | Calendar date |
| T_noon | Temperature at noon (C) |
| RH_noon | Relative humidity at noon (%) |
| Wind_noon | Wind speed at noon (km/h) |
| Precip_24h | 24-hour precipitation ending at noon (mm) |
| FFMC | Fine Fuel Moisture Code |
| DMC | Duff Moisture Code |
| DC | Drought Code |
| ISI | Initial Spread Index |
| BUI | Buildup Index |
| FWI | **Fire Weather Index** |

Notable dates in 2025: FWI peaked at **32.5 on August 17** and **31.1 on August 24** (both "Very High" danger). A sustained elevated period ran August 9-14 (FWI 22-29).

## Running the script yourself

**Requirements:** Python 3.7+, standard library only. No packages to install. Internet connection required.

```bash
python compute_stanhope_fwi.py
```

The year and season dates are set at the top of the script in the **CONFIGURATION** block. Adjust them to compute any year from 2014 onward:

```python
YEAR        = 2025   # change to any year with hourly data (2014-present)
START_MONTH = 5      # May - start of fire season for PEI
END_MONTH   = 10     # October - end of fire season
```

The script will:

1. Fetch all hourly observations from the ECCC API (1-second delay between requests)
2. Extract the noon temperature, RH, wind speed, and 24-hour precipitation for each day
3. Run the Van Wagner (1987) FWI equations sequentially through the season
4. Save a CSV to `data/stanhope/fwi_stanhope_computed_<YEAR>.csv`

## Danger class thresholds

| FWI range | Danger class |
|---|---|
| < 5 | Low |
| 5 to 12 | Moderate |
| 13 to 19 | High |
| 20 to 30 | Very High |
| > 30 | Extreme |

## References

- Van Wagner, C.E. (1987). *Development and structure of the Canadian Forest Fire Weather Index System.* Forestry Technical Report 35. Canadian Forest Service, Ottawa.
- ECCC MSC GeoMet API documentation: https://eccc-msc.github.io/open-data/msc-geomet/readme_en/
- CWFIS interactive map: https://cwfis.cfs.nrcan.gc.ca
