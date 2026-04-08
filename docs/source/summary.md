# Wrap-up

## Technical Findings
The Phase I effort has yielded several important technical findings that inform both the interpretation of results and the planning for Phase II work.

### WGEN Wet Bias

The exclusion of pre-1948 data from the WGEN sampling pool creates a systematic wet bias in 100-year stochastic sequences. Because atmospheric circulation data from NCEP/NCAR Reanalysis 1 is only available from 1948 onward, the WGEN cannot sample from the Dust Bowl era (1930s) and other pre-1948 dry periods. As a result, the 1948-2018 sampling period is approximately centered within the stochastic distribution, while the full historical record including pre-1948 would be drier.

This finding has important implications for drought analysis. The stochastic sequences may underrepresent the frequency and severity of extreme dry periods that could plausibly occur. Users should be aware that the 1000-year ensemble does not include Dust Bowl-like conditions, which could affect conclusions about system performance during extreme droughts.

![Oroville Inflow Comparison](figures/s2-methods_oroville-inflow-comparison.png)
_Comparison of Oroville inflow: CalSim 3 historical (black), WGEN historical VIC (red), and 1000-year stochastic sequences (gray). The 1948--2018 effective sampling period is nearly centered within the stochastic distribution._

This bias is not spatially uniform. The WGEN tends to run wet in the Sacramento Valley and dry in Southern California, driven by the 1920--1950 period being exceptionally dry in the Sacramento basin relative to post-1948 conditions.

### VIC Model Bias

VIC-modeled flows show approximately 25-30% positive bias compared to CalSim 3 historical inputs. This substantial bias necessitates quantile mapping correction for all VIC-derived inputs. Without bias correction, direct use of VIC outputs would systematically overestimate water availability throughout the system.

The quantile mapping approach successfully corrects the distributional bias, achieving close alignment between the mapped values and CalSim 3 historical targets during the validation period. However, the need for such significant correction highlights the importance of careful calibration and validation in any stochastic generation framework.

### Trend Inheritance

Quantile mapping inherits long-term trends from the VIC model. If VIC shows a drying trend at a particular location, mapped flows will also be drier regardless of the target distribution. This phenomenon was observed at Folsom, where unexpected negative bias appeared after mapping despite the quantile mapping procedure being correctly implemented.

The underlying issue is that quantile mapping corrects the distribution of values but preserves the temporal sequence from the basis time series. If the basis (VIC) has a trend that differs from the target (CalSim historical), that trend propagates through to the mapped output. This limitation should be considered when interpreting long-term patterns in the stochastic sequences.

### Offsetting Effects

An interesting pattern emerged from the analysis of different input categories. Rim inflows show a systematic wet bias from the WGEN and VIC modeling chain, while valley hydrology from CalSimHydro shows a dry bias due to lower WGEN precipitation and higher VIC-derived ET. These opposing biases create partially offsetting effects in the overall water budget.

The physical mechanism is straightforward: rim inflows are dominated by upper-watershed precipitation and snowmelt processes where VIC's positive bias amplifies water production, while valley floor hydrology (CalSimHydro) is dominated by ET that VIC overestimates, reducing available water. At the system level, more water enters through rim inflows but more is consumed through valley ET, creating a partial cancellation. Progress Meeting 2 results quantified this pattern, showing rim inflow increases of 25–30% partially offset by CalSimHydro deep percolation decreases of ~15% and Small Watershed reductions of ~13.5%.

The net system-wide impact of these offsetting biases remains to be quantified through full CalSim 3 runs. It is possible that some of the biases cancel out when integrated across the complete model domain, though localized effects may still be significant. The CalSim run phase will provide critical information about how these biases interact within the full system simulation, particularly whether reservoir operations amplify or dampen the net bias signal.

### Closure Term Correlation

Monthly correlation between closure terms and unimpaired flows proved too low for reliable quantile mapping. Only one location (Nicholas) showed correlation greater than 0.5, making standard quantile mapping infeasible for most closure term variables. This limitation led to the development of the WGEN sampling date approach, which achieves approximately 0.8 correlation with historical values by leveraging the temporal mapping embedded in the WGEN sampling process.

Fortunately, closure terms are being retired in future CalSim versions. This planned retirement reduces the long-term importance of the closure term methodology developed in Phase I, though the approach remains necessary for near-term work with current model versions.



## Outstanding Dependencies

Several external dependencies affect the timing and scope of the Phase I effort. Understanding these dependencies is essential for project planning and for anticipating potential changes to the methodology.

### ET Methodology

The Modeling Support Office (MSO) is developing an alternative evapotranspiration calculation method separate from VIC. This new methodology is expected to accompany the final DCR 2025 release in June 2026. The current VIC-based approach will continue for Phase I, with the possibility of incorporating the new MSO methodology as a Phase II enhancement.

The alternative ET methodology may offer improvements in bias characteristics or computational efficiency. However, since it will not be available until after Phase I completion, the current approach using VIC-derived ET with quantile mapping represents the best available option for meeting the project timeline. The decision to proceed with VIC-based ET was explicitly confirmed during the October 2025 progress meeting, where MSO staff indicated the new ET approach would require at least six additional months of development and validation before it could be adopted.

### DCR 2025 Transition

The project team is coordinating the transition from DCR 2023 to DCR 2025 as the baseline CalSim 3 model. The draft DCR 2025 is expected by the end of 2025, with the finalized version scheduled for June 2026. This transition affects several aspects of the stochastic input generation work.

DCR 2025 includes several retired closure terms, which will simplify processing for those variables. The retirement of closure terms reduces the complexity of the stochastic generation framework and eliminates the need to maintain the weighted-average methodology for variables that no longer exist in the model. Additionally, DCR 2025 may incorporate updated reservoir sedimentation data, revised operational rules, and potentially the new ET methodology—each of which could affect stochastic input generation requirements.

### Module Version Alignment

When transitioning to DCR 2025, careful attention must be paid to ensuring proper alignment of module versions. CalSimHydro, External Elements (EE), Small Watersheds, Delta Channel Depletion (DCD), and the Delta Salinity Model (DSM) all need to be compatible with the DCR 2025 baseline. A module compatibility list has been prepared for coordination with MSO to verify that all components work together correctly.

The CalSimHydro version issue encountered during Phase I illustrates the risks: the project initially received CalSimHydro version 2020, which was missing WBAs 50 and 91 compared to version 2015 used in DCR 2023. This incompatibility was only discovered after initial runs produced incorrect output counts, requiring rollback to the 2015 version. For DCR 2025, a comprehensive module compatibility check before development begins will prevent similar mid-project disruptions.

Version misalignment could cause subtle errors that are difficult to diagnose. The integration testing phase of DCR 2025 deployment will need to verify that stochastic inputs work correctly with all updated modules.


## Recommendations

Based on the findings from Phase I, the project team offers the following recommendations for completing the current phase and planning for Phase II.

### Proceed with Current ET Methodology

The current VIC-based ET quantile mapping approach should continue for Phase I completion. The MSO's alternative ET methodology will not be available until June 2026, well after the Phase I target completion. Attempting to wait for the new methodology would delay the project without clear benefits for the immediate deliverables.

The alternative ET methodology can be incorporated as a Phase II enhancement if it offers meaningful improvements in bias characteristics or computational efficiency. This approach maintains project momentum while preserving flexibility to adopt better methods when they become available.

### Document Bias Characteristics

Comprehensive documentation of systematic biases should be prepared for inclusion in the final report and user guidance materials. Users of the stochastic inputs need to understand three primary bias sources and their implications:

The WGEN wet bias from post-1948 sampling means the stochastic ensemble excludes Dust Bowl-era (1930s) conditions and other pre-1948 dry periods. Users conducting drought vulnerability analysis should recognize that the 1,000-year ensemble may underestimate the frequency of the most extreme droughts. The VIC positive bias of approximately 25–30% in rim inflows is corrected through quantile mapping but highlights the sensitivity of the generation framework to upstream model calibration. Trend inheritance effects, observed at locations like Folsom where VIC drying trends propagated through quantile mapping, require attention when interpreting long-term patterns in stochastic output.

Clear documentation helps users interpret results appropriately and avoid drawing incorrect conclusions from the stochastic simulations. The biases are not necessarily problems that invalidate the results, but they do require understanding for proper interpretation. A bias summary table comparing each input category's expected direction and magnitude of bias would provide a practical reference for CalSim modelers working with the stochastic dataset.

### Prioritize Reservoir Curve Analysis

The Folsom reservoir storage curve analysis should be completed first among the remaining input categories. Folsom's operational complexity and the lack of a clear generalizable pattern make it a critical test case. The findings from Folsom analysis will determine whether a generalizable methodology exists for complex reservoir operations or whether a repeating pattern fallback is needed.

The approach developed for Folsom can then be applied to other reservoirs with complex operational rules. Starting with the most difficult case ensures that the methodology is robust before applying it more broadly.

### Coordinate DCR 2025 Transition

A dedicated coordination meeting with MSO should be scheduled to align module versions and identify any additional input changes between DCR 2023 and DCR 2025. Early coordination reduces the risk of discovering compatibility issues late in the project when they are more difficult to address.

The meeting should establish a clear understanding of which modules are changing, what new inputs may be required, and how the transition timeline aligns with the project schedule.

### Plan Phase II Scope

Preliminary scoping for Phase II should begin based on emerging findings from Phase I, particularly around model infeasibilities and operational rule modifications that may be needed for extreme stochastic sequences. Extended droughts and multi-year wet sequences may cause CalSim operational rules to behave in unexpected ways that require adjustment for realistic simulation.

Documentation of these issues during Phase I provides the foundation for Phase II planning. The Phase I report should clearly identify areas where model modifications may be beneficial, even if those modifications are beyond the current scope.