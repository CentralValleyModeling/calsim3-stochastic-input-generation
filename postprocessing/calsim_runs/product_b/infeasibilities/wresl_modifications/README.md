# WRESL Modifications for SJR Cycle 14 Infeasibility

Modified copies of CalSim 3 WRESL files addressing Product B stochastic infeasibilities.
See `docs/source/findings/sjr_infeasibility/sjr_infeasibility_report.md` for full analysis.

Source study: `9.3.1_danube_hist`

## Files

| File | Fix | Failure Mode |
|------|-----|-------------|
| `Mok_WS.wresl` | Floor Mokelumne allocation at zero | Low-flow (n03, n07) |
| `Merced_Ops.wresl` | Guard Bear/Deadman Creek delivery under zero inflow | Low-flow (n03) |
| `SJR_Cycle_Defs_Local.wresl` | Increase mdota_max from 10000 to 50000 | High-flow (n01, n04, n05, n06) |

## Original file locations (relative to Run/)

- `SanJoaquin/LowerMokelumne/Mok_WS.wresl`
- `SanJoaquin/Merced/Merced_Ops.wresl`
- `Other/SJR_Cycle_Defs_Local.wresl`
