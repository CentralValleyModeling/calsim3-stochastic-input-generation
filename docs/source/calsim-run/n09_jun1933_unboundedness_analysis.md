# n09 June 1933 Unboundedness Analysis

## Context

After applying Fix 4 (relaxed `meetSJRR` under low Millerton storage), n09's
April 1962 failure was resolved. Re-running WRIMS produced a new failure at
**June 1933, Cycle 14 (sjrbase)**. WRIMS reported this as "infeasible"
(Status:-1), but the true cause turned out to be **LP unboundedness**.

## Diagnosis Sequence

### 1. Initial Misdiagnosis

The initial assumption was that June 1933 was another low-flow infeasibility
similar to n03/n07. However, all four existing WRESL fixes were already applied
in the n09 run:
- Fix 1: Mokelumne allocation floor (irrelevant -- June, not July)
- Fix 2: Bear/Deadman Creek guard (fires, but I_BCK040=0 and I_BUR005=0)
- Fix 3: Mendota Pool cap (always applied)
- Fix 4: meetSJRR relaxation (fires -- S_MLRTN(-1) = 123.67 < 130)

### 2. LP Export Analysis (Dead End)

Attempted to solve the WRIMS-exported LP/MPS files externally using PuLP/CBC.
**This was a dead end**: WRIMS LP exports are incomplete -- they omit implicit
variable bounds (e.g., free variables are not declared as such). CBC reports
"unbounded" for all variants because it treats unlabeled variables as bounded
[0, inf] when they should be free [-inf, inf].

Key finding: **Do not attempt external CBC solver approaches on WRIMS LP exports.**

### 3. LP Constraint Classification

Parsed all 3,419 LP constraints from `1933_06_c14_cR___infeasible.lp`:
- 83 hard >= constraints
- 511 hard <= constraints
- 2,665 hard equalities
- 160 soft constraints (with slack/surplus penalty variables)

Compared with the "stuck" LP (`stuck_16.lp`, the last successful iteration):
the two LP files are **100% identical** in constraint structure and coefficients.

### 4. DSS State Variables

Read S_MLRTN trajectory from DSS output:
- March 1933: S_MLRTN = 262 TAF
- April 1933: S_MLRTN = 167 TAF
- May 1933: S_MLRTN = 123.67 TAF (below 130 threshold, below 135 dead storage)

This confirms the `lowStorage` case of Fix 4's `meetSJRR` fires at June 1933.

### 5. HiGHS Solver Breakthrough

Installed `highspy` (HiGHS solver v1.14) via pip. This solver correctly
distinguishes infeasible from unbounded models.

**Key findings in sequence:**

#### a. LP Relaxation is Feasible
With all integers relaxed and a zero objective, the LP is **feasible**
(HighsModelStatus.kOptimal). The continuous constraint system has no conflicts.

#### b. All Binary Combinations are Feasible
The LP has 4 binary variables:
- `intsjrdiversion`
- `int_sjr205`
- `int_sackaccr_abv`
- `int_mpinflow_abv`

All 16 combinations of fixed binary values produce feasible LPs with zero
objective.

#### c. Actual Objective Causes Unboundedness
With the actual WRIMS objective function, **all 16 binary combinations are
unbounded** (HighsModelStatus.kUnbounded).

280 variables have negative costs (rewards) and infinite upper bounds in the
exported LP. Capping all at 1e6 makes all 16 combos optimal.

#### d. Single Variable Identified
Only **one** variable actually hits the cap: `d_sjr205_sjr201`
- Cost (reward): -500,000
- Lower bound: 0
- Upper bound: infinity (in the exported LP)
- Solution when capped at 1e8: 1e8 (pushing to infinity)

Bounding `d_sjr205_sjr201` alone at any finite value (tested 10 to 99,999)
makes the LP optimal. MIP also solves: intsjrdiversion=1, int_sjr205=0,
int_sackaccr_abv=0, int_mpinflow_abv=0.

#### e. Constraints on d_sjr205_sjr201
The variable participates in these constraints:
- `continuitysjr205` (SJR node 205 mass balance)
- `continuitysjr201` (SJR node 201 mass balance)
- `meetsjrr` (the Fix 4 soft constraint)
- `set_srrp_lmt1` (recapture limit)
- `sjrr_passthru` (passthrough requirement)

None provide an effective upper bound because free seepage variables at SJR205
can absorb arbitrary excess flow -- phantom water enters via seepage and exits
via the bypass, generating infinite reward.

### 6. Root Cause

Fix 4 set `lhs>rhs penalty 0` on the over-delivery side of `meetSJRR`:
```
case lowStorage {
    condition S_MLRTN(-1) < 130.
    rhs REST_RCH_NP
    lhs>rhs penalty 0      <-- zero penalty for over-delivery
    lhs<rhs penalty 9999999
}
```

In WRESL, `penalty 0` means the solver imposes zero cost for the variable
exceeding the RHS. Combined with D_SJR205_SJR201's reward of -500,000 from
its priority weighting in SJRBASE, the net incentive is to increase
D_SJR205_SJR201 without limit.

Later cycles (SJR_Rest_Full.wresl, SJR_Rest_VA.wresl) include:
```
goal setSJRRflow {D_SJR205_SJR201 < Rest_Rch_Target}
```
which would cap the variable. But SJRBASE (cycle 14) does not include these
files, so there is no upper bound on D_SJR205_SJR201 in this cycle.

**WRIMS/CBC misreports LP unboundedness as "infeasible" (Status:-1).**

## Fix 5

Change `lhs>rhs penalty 0` to `lhs>rhs penalty 9999999`:
```
case lowStorage {
    condition S_MLRTN(-1) < 130.
    rhs REST_RCH_NP
    lhs>rhs penalty 9999999   <-- prevents unboundedness
    lhs<rhs penalty 9999999
}
```

Net cost of over-delivery becomes +9,499,999 per CFS
(penalty 9,999,999 minus variable reward 500,000).

### Verification

Simulated Fix 5 by adding a surplus variable with penalty 9,999,999 to the
exported LP and solving with HiGHS:
- LP: kOptimal, objective = -14,454,243,003.98
- MIP: kOptimal, objective = -14,454,243,004.01
- D_SJR205_SJR201 = 0
- surplus (over-delivery) = 0
- C_MLRTN = 215 TAF
- S_MLRTN = 135 TAF

Solution is physically reasonable: the solver chooses zero bypass flow rather
than paying the 9,999,999 penalty, stores water in Millerton to 135 TAF
(just above dead storage), and releases via the main channel (C_MLRTN = 215).

## Key Lessons

1. **WRIMS/CBC conflates unbounded and infeasible** -- both are reported as
   Status:-1 ("infeasible"). When diagnosing WRIMS LP failures, always check
   for unboundedness as well.

2. **WRIMS LP exports are incomplete** -- they omit free variable declarations
   and some implicit bounds. External solvers (CBC, PuLP) cannot reliably solve
   these files. HiGHS was more robust because it correctly handles the exported
   format with relaxed integers.

3. **`penalty 0` in WRESL is not the same as no penalty** -- it explicitly sets
   zero cost on the slack/surplus variable for that side of the inequality. If
   the decision variable already has a large reward (negative cost), `penalty 0`
   creates an unbounded direction. Use `penalty 9999999` (or another large value)
   on both sides when relaxing a constraint to a soft constraint.

4. **Check cycle-specific variable bounds** -- a variable may be bounded in
   later cycles but unbounded in the current cycle. SJRBASE (cycle 14) does not
   include the `setSJRRflow` upper bound that later cycles enforce.

## Tools Used

- `highspy` (HiGHS solver v1.14) -- pip installed in csstochastic conda env
- LP file: `1933_06_c14_cR___infeasible.lp` (3,500 cols, 3,419 rows, 4 binaries)
- WRIMS study: `9.3.1_danube_hist`, n09 rerun with Fixes 1-4 applied
