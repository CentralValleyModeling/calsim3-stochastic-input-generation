# mod_reservoir/evaporation

```{admonition} Repository Module
:class: tip

**Module:** `mod_reservoir/evaporation/`  
Hargreaves-Samani evaporation for 95 reservoirs
```


Evaporation calculations for 95 CalSim 3.0 reservoirs distributed across three regions: 52 in the Sacramento Valley, 38 in the San Joaquin Valley, and 5 grouped as Other. Each reservoir has an associated Excel spreadsheet with five different reconstruction methods, but the majority employ monthly regression calibration with the Hargreaves-Samani evaporation equation.

## Methodology

### Hargreaves-Samani Equation

The Hargreaves-Samani equation provides the core evaporation calculation using temperature and solar radiation as primary drivers. The equation requires daily maximum temperature, daily minimum temperature, day of year, and reservoir latitude. Monthly radiation factors and calibration coefficients specific to each reservoir adjust raw evaporation estimates to match historical patterns. These parameters were extracted from the original Excel spreadsheets and stored in a JSON database for programmatic access.

The approach employs VLOOKUP-style elevation adjustment where calibration factors vary with reservoir surface elevation. The monthly calibration ensures seasonal patterns match historical evaporation observations or water balance-derived estimates.

### Python Automation

The entire Excel calculation process has been replicated in Python, avoiding the need to run 95 Excel spreadsheets multiple times for different cliamte traces. A dedicated database-extraction script (`_0_extract_reservoir_database.py`) parses the original Excel workbooks and stores all reservoir-specific parameters--monthly radiation factors, calibration coefficients, elevation adjustment tables, latitude, and surface area relationships--into a centralized JSON database. This JSON structure provides programmatic access to all 95 reservoir configurations in a single file, enabling rapid parameter lookups without repeated Excel I/O.

## Results

Validation followed a two-step process to ensure Python implementation fidelity before applying to new climate data. Step one verified Python calculation accuracy by running the same input data (historical temperature) through both Excel and Python implementations. The result was exact numerical matching, validating the Python scripts reproduce Excel calculations perfectly.

Step two applied the validated Python implementation to Product A temperature data from the weather generator. The result showed slightly lower evaporation for most reservoirs compared to historical baselines. The cause is reduced daily temperature range (difference between $T_{max}$ and $T_{min}$) in the synthetic climate, which directly affects the Hargreaves-Samani calculation even when mean temperatures remain similar. The Hargreaves-Samani equation computes reference evapotranspiration approximately as:

$$ET_0 = 0.0023 \cdot (T_{mean} + 17.8) \cdot (T_{max} - T_{min})^{0.5} \cdot R_a$$

where $R_a$ is extraterrestrial radiation. Since the formula involves the square root of temperature range, a compressed diurnal cycle in synthetic climate reduces evaporation even if the mean temperature is the same.

![Reservoir Evaporation Validation](figures/s3-inputs_reservoir-evaporation-validation.png)
*Annual reservoir evaporation distribution by region for WY 1922--2018 (97 water years), showing the three-step validation across Sacramento Valley (52 reservoirs), San Joaquin Valley (38 reservoirs), and Other (5 reservoirs). Original Excel and Python validation box plots are identical (range 36.9--95.5 in/yr, mean 53.2 in/yr), confirming exact replication. Product A synthetic temperature produces slightly lower evaporation (range 25.7--89.5 in/yr, mean 51.0 in/yr), consistent with reduced diurnal temperature range in the weather generator output.*
