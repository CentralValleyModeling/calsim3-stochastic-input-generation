# mod_forcing/inflows

```{admonition} Repository Module
:class: tip

**Module:** `mod_forcing/inflows/`  
Run the rim-inflow model and write its monthly arc flows
```

`mod_forcing/inflows/` runs one rim-inflow model on a weather set and writes its monthly flow on the CalSim 3 rim-inflow arcs. It delivers no SV itself: `mod_hydrology/rim_inflow/` builds the rim-inflow SVs from its arcs ({doc}`mod-hydrology-rim-inflow`).

The config names the model (`inflow_model`), its folder (`inflow_repo`), its environment (`inflow_env`) and the version a run must come from (`inflow_pin`). SAC-SMA is the default and the model the delivered sets use. VIC is a second model the config can select.

## Scripts

`_1_build_forcing.py --forcing historical|A|B` compares the model's weather input with the WGEN files in `BASE` (gate G2), on a seeded sample of 200 cells by default. With `--cells all` it first writes the inputs the adapter builds (SAC-SMA: Product B; VIC: every set), then checks every cell and records the result beside the sha256 of each input file.

`_2_run_product.py --forcing historical|A|B` runs the model and writes `arc_inflow_monthly.csv` and `run_manifest.json`. It stops unless the model is at its pin with no modified files and G2 passed on every cell of the inputs it will read. It writes the flows only if the run passes the adapter's gates (G1, G6). The manifest records the model, its version, the sha256 of every file the run used and each gate's result, and the rim-inflow builder checks it before reading the flows (`utils.paths.require_pinned_run`).

## SAC-SMA

`adapters/sacsma.py` runs SAC-SMA dPL-CalSim through the model's command line, at a pinned commit of its git checkout.

- The model reads NetCDF stores of daily precipitation and temperature on its 4,410 grid cells. Its checkout holds the stores of Historical_Unsplit and Product A, and `_1_build_forcing.py` writes Product B's.
- A run gives the flow of the 196 rim arcs and of the Sacramento valley node I_SRBB_VAL, over WY 1916-2018 for Historical_Unsplit and Product A. The model's share model divides the flow of each multi-arc system among that system's arcs.
- Gate G1 requires a Historical_Unsplit or Product A run to repeat the series the model tracks at the pin.
- Product B runs in ten segments, one per chunk, each from the model state the segment before ended with. Gate G6 checks every hand-off, and the share model is applied once to the joined run.

## VIC

With `inflow_model` set to `vic`, `adapters/vic.py` runs VIC 4.2.d with the CalSim LTO parameters under WSL, from the `VIC_Support_4.2.d` folder of the v1.0 archive. That folder is not a git checkout, so its pin is the sha256 of its binary, parameter and global files.

- `_1_build_forcing.py` writes one forcing file per cell: WGEN precipitation and temperature, and the wind of Historical_Climate_LTO. Historical_Unsplit and Product A take the wind of the same day, and Product B takes the wind of the day WGEN resampled.
- Each arc is the area-weighted runoff plus baseflow of its GridInfo cells (`mod_forcing/climate/reference/GridInfo/`), in TAF per month, with no quantile maps.
- The daily fluxes stay in a compressed store that a later run reuses while the model version and its inputs match. Gate G1 reruns 8 cells and requires them to repeat the store byte for byte.

A VIC chain keeps its own GENERATED folder (`generated_dir`) and its own config file (`CSSTOCHASTIC_CONFIG`). Both scripts stop when the GENERATED folder holds another model's run.
