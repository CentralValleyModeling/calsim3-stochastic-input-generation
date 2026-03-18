# Key Findings

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

