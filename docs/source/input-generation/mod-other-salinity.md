# mod_other/salinity

```{admonition} Repository Module
:class: tip

**Module:** `inventory/screening/salinity/`  
Delta salinity boundary conditions (constant/repeating)
```

Delta salinity boundary conditions used in CalSim 3 water quality modeling.

The 5 salinity variables represent constant or repeating boundary conditions for Delta salinity modeling. No scripting is required: these variables are held constant or follow predetermined repeating patterns directly from the CalSim 3 baseline DSS, and are copied without modification into stochastic runs. This approach reflects the decision that Delta salinity modeling in CalSim 3 does not require stochastically-varying boundary conditions, given the dominant role of operational rules and flow management in determining actual salinity outcomes.
