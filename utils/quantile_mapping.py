import os

import numpy as np
from scipy.stats import gamma
from scipy.interpolate import interp1d

# Global seed for reproducible quantile mapping. The only stochastic step in
# qmap_single is tie-breaking among equal historical basis values (the
# rng.choice call below). Seeding a dedicated Generator makes all QM output
# deterministic and reproducible run-to-run. Override with the
# CSSTOCHASTIC_QMAP_SEED environment variable if a different seed is needed.
QMAP_SEED = int(os.environ.get("CSSTOCHASTIC_QMAP_SEED", "42"))

def std(x):
    # Sample standard deviation (ddof=1 to match R's sd)
    return np.std(x, ddof=1)

def qmap_single(basis_sim, basis_hist, target, allow_negative=False):
    """
    Quantile-mapping for a single CalSim timeseries using one target.
    Args:
        basis_sim: DataFrame, simulated basis (columns: year, month, value)
        basis_hist: DataFrame, historical basis (columns: year, month, value)
        target: DataFrame, historical target (columns: year, month, value)
        allow_negative: bool, if False, clamp negative quantile_mapped_values to 0
    Returns:
        DataFrame with columns: year, month, quantile_mapped_value
    """
    # Prepare output
    quantile_mapped = np.zeros(len(basis_sim))

    # Dedicated, seeded RNG for deterministic tie-breaking. Seeded per call
    # from the global QMAP_SEED so a pair's result is independent of how many
    # pairs/timesteps were processed before it (order-independent
    # reproducibility), and isolated from the global numpy RNG state.
    rng = np.random.default_rng(QMAP_SEED)

    # Precompute monthly distributions and parameters
    parhat_basis = np.full((12, 2), np.nan)
    parhat_target = np.full((12, 2), np.nan)
    basis_mondata_mon = [None] * 12
    eprob_basis_mon = [None] * 12
    tprob_basis_mon = [None] * 12
    target_mondata_mon = [None] * 12
    eprob_target_mon = [None] * 12
    tprob_target_mon = [None] * 12

    for imon in range(12):
        month = imon + 1
        # Get monthly data for basis and target
        basis_mondata = basis_hist.loc[basis_hist['month'] == month, 'value'].values
        target_mondata = target.loc[target['month'] == month, 'value'].values

        # Empirical probabilities (Weibull plotting position)
        eprob_basis = np.arange(1, len(basis_mondata) + 1) / (1 + len(basis_mondata))
        eprob_target = np.arange(1, len(target_mondata) + 1) / (1 + len(target_mondata))

        # Gamma parameters for basis
        if len(basis_mondata) > 1 and np.mean(basis_mondata) > 0:
            parhat1_basis = (np.mean(basis_mondata) / std(basis_mondata)) ** 2
            parhat2_basis = np.var(basis_mondata, ddof=1) / np.mean(basis_mondata)
        else:
            parhat1_basis = np.nan
            parhat2_basis = np.nan
        # Gamma parameters for target
        if len(target_mondata) > 1 and np.mean(target_mondata) > 0:
            parhat1_target = (np.mean(target_mondata) / std(target_mondata)) ** 2
            parhat2_target = np.var(target_mondata, ddof=1) / np.mean(target_mondata)
        else:
            parhat1_target = np.nan
            parhat2_target = np.nan

        # Theoretical probabilities using gamma CDF
        try:
            tprob_basis = gamma.cdf(np.sort(np.unique(basis_mondata)), parhat1_basis, scale=parhat2_basis)
        except Exception:
            tprob_basis = np.full_like(np.sort(np.unique(basis_mondata)), np.nan)
        try:
            tprob_target = gamma.cdf(np.sort(np.unique(target_mondata)), parhat1_target, scale=parhat2_target)
        except Exception:
            tprob_target = np.full_like(np.sort(np.unique(target_mondata)), np.nan)

        # Store
        parhat_basis[imon, :] = [parhat1_basis, parhat2_basis]
        parhat_target[imon, :] = [parhat1_target, parhat2_target]
        basis_mondata_mon[imon] = basis_mondata
        eprob_basis_mon[imon] = eprob_basis
        tprob_basis_mon[imon] = tprob_basis
        target_mondata_mon[imon] = target_mondata
        eprob_target_mon[imon] = eprob_target
        tprob_target_mon[imon] = tprob_target

    # Quantile mapping for each time step in the simulation
    for j in range(len(basis_sim)):
        selmon = int(basis_sim.iloc[j]['month']) - 1  # 0-based
        selval = basis_sim.iloc[j]['value']

        basis_mondata_selmon = basis_mondata_mon[selmon]
        target_mondata_selmon = target_mondata_mon[selmon]
        eprob_basis_selmon = eprob_basis_mon[selmon]
        tprob_basis_selmon = tprob_basis_mon[selmon]
        eprob_target_selmon = eprob_target_mon[selmon]

        # If all target values are the same, just use that value
        if len(np.unique(target_mondata_selmon)) == 1:
            quantile_val = np.unique(target_mondata_selmon)[0]
        else:
            # If in the historic range, use empirical distribution
            if len(basis_mondata_selmon) == 0:
                quantile_val = np.nan
            elif selval <= np.max(basis_mondata_selmon) and selval >= np.min(basis_mondata_selmon):
                sortdata = np.sort(basis_mondata_selmon)
                mvalind = np.where(sortdata == selval)[0]
                if len(mvalind) > 1:
                    randind = rng.choice(mvalind)
                    nonexprob_basis = eprob_basis_selmon[randind]
                else:
                    try:
                        f = interp1d(sortdata, eprob_basis_selmon, kind='linear', fill_value="extrapolate")
                        nonexprob_basis = float(f(selval))
                    except Exception:
                        nonexprob_basis = np.nan
            # If above historic range, use gamma CDF tail
            elif selval > np.max(basis_mondata_selmon):
                cdf_selval = gamma.cdf(selval, parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                cdf_maxval = tprob_basis_selmon[-1] if len(tprob_basis_selmon) > 0 else 0
                cdf_delta = cdf_selval - cdf_maxval
                nonexprob_basis = min(eprob_basis_selmon[-1] + cdf_delta, 0.9999)
            # If below historic range, use gamma CDF lower tail
            elif selval < np.min(basis_mondata_selmon):
                cdf_selval = gamma.cdf(selval, parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                cdf_minval = tprob_basis_selmon[0] if len(tprob_basis_selmon) > 0 else 0
                cdf_delta = cdf_minval - cdf_selval
                nonexprob_basis = max(eprob_basis_selmon[0] - cdf_delta, 0.0001)
            else:
                nonexprob_basis = np.nan

            # Map to target using empirical distribution
            if nonexprob_basis <= np.max(eprob_target_selmon) and nonexprob_basis >= np.min(eprob_target_selmon):
                sortdata = np.sort(target_mondata_selmon)
                try:
                    f = interp1d(eprob_target_selmon, sortdata, kind='linear', fill_value="extrapolate")
                    quantile_val = float(f(nonexprob_basis))
                except Exception:
                    quantile_val = np.nan
            else:
                # If outside empirical range, use gamma quantile mapping
                if not np.isnan(parhat_target[selmon, 0]):
                    if nonexprob_basis > np.max(eprob_target_selmon):
                        extval1 = gamma.ppf(nonexprob_basis, parhat_target[selmon, 0], scale=parhat_target[selmon, 1])
                        extval2 = gamma.ppf(eprob_target_selmon[-1], parhat_target[selmon, 0], scale=parhat_target[selmon, 1])
                        val_delta = extval1 - extval2
                        quantile_val = np.max(target_mondata_selmon) + val_delta
                    elif nonexprob_basis < np.min(eprob_target_selmon):
                        extval1 = gamma.ppf(nonexprob_basis, parhat_target[selmon, 0], scale=parhat_target[selmon, 1])
                        extval2 = gamma.ppf(eprob_target_selmon[0], parhat_target[selmon, 0], scale=parhat_target[selmon, 1])
                        val_delta = extval2 - extval1
                        quantile_val = np.min(target_mondata_selmon) - val_delta
                    else:
                        quantile_val = np.nan
                else:
                    # If target gamma params are nan, fallback to basis gamma params
                    if nonexprob_basis > np.max(eprob_target_selmon):
                        extval1 = gamma.ppf(nonexprob_basis, parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                        extval2 = gamma.ppf(eprob_target_selmon[-1], parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                        val_delta = extval1 - extval2
                        quantile_val = (1 + val_delta / np.max(basis_mondata_selmon)) * np.max(target_mondata_selmon)
                    elif nonexprob_basis < np.min(eprob_target_selmon):
                        extval1 = gamma.ppf(nonexprob_basis, parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                        extval2 = gamma.ppf(eprob_target_selmon[0], parhat_basis[selmon, 0], scale=parhat_basis[selmon, 1])
                        val_delta = extval2 - extval1
                        if np.min(target_mondata_selmon) >= 0:
                            quantile_val = (1 - val_delta / np.min(basis_mondata_selmon)) * np.min(target_mondata_selmon)
                        else:
                            quantile_val = (1 + val_delta / np.min(basis_mondata_selmon)) * np.min(target_mondata_selmon)
                    else:
                        quantile_val = np.nan

        quantile_mapped[j] = quantile_val

    # Return DataFrame with year, month, and quantile-mapped value
    out = basis_sim[['year', 'month']].copy()
    
    # Apply negative value handling if requested
    if not allow_negative:
        quantile_mapped = np.maximum(0, quantile_mapped)
    
    out['quantile_mapped_value'] = quantile_mapped
    return out