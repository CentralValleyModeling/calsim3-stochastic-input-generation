# WRESL Modifications for Product B Infeasibilities

Modified copies of CalSim 3 WRESL files addressing Product B stochastic infeasibilities.
See `docs/source/calsim-run/sjr_infeasibility_report.md` for full analysis.

Source study: `9.3.1_danube_hist`

## Files

| File | Fix | Failure Mode |
|------|-----|-------------|
| `Mok_WS.wresl` | Floor Mokelumne allocation at zero | Low-flow (n03, n07) |
| `Merced_Ops.wresl` | Guard Bear/Deadman Creek delivery under zero inflow | Low-flow (n03) |
| `SJR_Cycle_Defs_Local.wresl` | Increase mdota_max from 10000 to 50000 | High-flow (n01, n04, n05, n06) |
| `SJR_Rest_Req_Cycle1.wresl` | Relax meetSJRR bypass equality when storage < 130 TAF (Fix 4+5) | Low-storage Friant (n09 c14) |
| `SJR_Rest_Req_Cycle2.wresl` | Relax boundC_MLRTNmain + meetSJRR when storage < 130 TAF (Fix 6) | Low-storage Friant (n09 c19) |
| `SJR_Rest_Full.wresl` | Relax boundC_MLRTNmain when storage < 130 TAF (Fix 7) | Low-storage Friant (n09 c24) |
| `friant_wsf.wresl` | Guard TREvap_sep divide-by-zero when area = 0 (Fix 8) | Zero-storage Friant (n09 May 1962) |
| `friant_rain_fld_est.wresl` | Guard TF_est_evap divide-by-zero when area = 0 (Fix 8) | Zero-storage Friant (n09 May 1962) |
| `SJR_Rest_Req_Cycle3.wresl` | Relax meetSJRR when storage < 130 TAF (Fix 9, proactive) | Low-storage Friant |
| `SJR_Rest_Req_Cycle4.wresl` | Relax boundC_MLRTNmain + meetSJRR when storage < 130 TAF (Fix 10, proactive) | Low-storage Friant |

## Original file locations (relative to Run/)

- `SanJoaquin/LowerMokelumne/Mok_WS.wresl`
- `SanJoaquin/Merced/Merced_Ops.wresl`
- `Other/SJR_Cycle_Defs_Local.wresl`
- `SanJoaquin/Friant/SJR_Rest_Req_Cycle1.wresl`
- `SanJoaquin/Friant/SJR_Rest_Req_Cycle2.wresl`
- `SanJoaquin/Friant/SJR_Rest_Full.wresl`
- `SanJoaquin/Friant/friant_wsf.wresl`
- `SanJoaquin/Friant/friant_rain_fld_est.wresl`
- `SanJoaquin/Friant/SJR_Rest_Req_Cycle3.wresl`
- `SanJoaquin/Friant/SJR_Rest_Req_Cycle4.wresl`
