# Project Objectives

Phase I encompasses five core objectives designed to establish the technical foundation for stochastic CalSim 3 simulations.

## O1 - Full Input Integration

The first objective is to develop a complete set of CalSim 3 input variables (State Variables or SVs) derived from a 1,000-year synthetic daily temperature and precipitation dataset. This includes approximately 1,733  individual time series across multiple input categories including rim inflows, water budget components, evapotranspiration, groundwater interactions, Delta operations, and forecasts.

## O2 - Codebase Review

The second objective involves examining the CalSim 3 WRESL code to identify any hard-coded dependencies on the historical timeline. The historical record's specific dates, year types, and sequences may be embedded in model logic in ways that would cause problems with synthetic sequences. This review will assess the effort required to make such dependencies dynamic.

## O3 - Input Quality Assurance

The third objective focuses on evaluating and performing quality control on newly generated synthetic input files. This includes statistical comparison with historical inputs, verification of physical consistency, and identification of any artifacts introduced by the generation methodologies. Quality metrics include correlation coefficients, Nash-Sutcliffe Efficiency, bias statistics, and visual inspection of time series patterns.

## O4 - Output Evaluation

The fourth objective requires evaluating CalSim 3 model outputs (Decision Variables or DVs) by comparing them against the DCR 2023 benchmark run. Key outputs include reservoir storage patterns, Delta flows and exports, water deliveries to contractors, and regulatory compliance metrics. This evaluation will characterize how the stochastic inputs affect model behavior.

## O5 - Infeasibility Documentation

As a secondary priority, the fifth objective is to document any unrealistic model behavior or infeasibilities caused by the new inputs. Stochastic sequences may produce conditions (such as extended multi-year droughts) that cause CalSim's operational rules to behave in unexpected ways. The focus is on documentation for Phase II rather than resolution within Phase I.

