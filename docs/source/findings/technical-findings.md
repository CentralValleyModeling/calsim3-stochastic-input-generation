
# Technical Findings

The Phase I effort has yielded several important technical findings that inform both the interpretation of results and the planning for Phase II work.

## WGEN Wet Bias

The exclusion of pre-1948 data from the WGEN sampling pool creates a systematic wet bias in 100-year stochastic sequences. Because atmospheric circulation data from NCEP/NCAR Reanalysis 1 is only available from 1948 onward, the WGEN cannot sample from the Dust Bowl era (1930s) and other pre-1948 dry periods. As a result, the 1948-2018 sampling period is approximately centered within the stochastic distribution, while the full historical record including pre-1948 would be drier.

This finding has important implications for drought analysis. The stochastic sequences may underrepresent the frequency and severity of extreme dry periods that could plausibly occur. Users should be aware that the 1000-year ensemble does not include Dust Bowl-like conditions, which could affect conclusions about system performance during extreme droughts.

## VIC Model Bias

VIC-modeled flows show approximately 25-30% positive bias compared to CalSim 3 historical inputs. This substantial bias necessitates quantile mapping correction for all VIC-derived inputs. Without bias correction, direct use of VIC outputs would systematically overestimate water availability throughout the system.

The quantile mapping approach successfully corrects the distributional bias, achieving close alignment between the mapped values and CalSim 3 historical targets during the validation period. However, the need for such significant correction highlights the importance of careful calibration and validation in any stochastic generation framework.

## Trend Inheritance

Quantile mapping inherits long-term trends from the VIC model. If VIC shows a drying trend at a particular location, mapped flows will also be drier regardless of the target distribution. This phenomenon was observed at Folsom, where unexpected negative bias appeared after mapping despite the quantile mapping procedure being correctly implemented.

The underlying issue is that quantile mapping corrects the distribution of values but preserves the temporal sequence from the basis time series. If the basis (VIC) has a trend that differs from the target (CalSim historical), that trend propagates through to the mapped output. This limitation should be considered when interpreting long-term patterns in the stochastic sequences.

## Offsetting Effects

An interesting pattern emerged from the analysis of different input categories. Rim inflows show a systematic wet bias from the WGEN and VIC modeling chain, while valley hydrology from CalSimHydro shows a dry bias due to lower WGEN precipitation and higher VIC-derived ET. These opposing biases create partially offsetting effects in the overall water budget.

The physical mechanism is straightforward: rim inflows are dominated by upper-watershed precipitation and snowmelt processes where VIC's positive bias amplifies water production, while valley floor hydrology (CalSimHydro) is dominated by ET that VIC overestimates, reducing available water. At the system level, more water enters through rim inflows but more is consumed through valley ET, creating a partial cancellation. Progress Meeting 2 results quantified this pattern, showing rim inflow increases of 25–30% partially offset by CalSimHydro deep percolation decreases of ~15% and Small Watershed reductions of ~13.5%.

The net system-wide impact of these offsetting biases remains to be quantified through full CalSim 3 runs. It is possible that some of the biases cancel out when integrated across the complete model domain, though localized effects may still be significant. The CalSim run phase will provide critical information about how these biases interact within the full system simulation, particularly whether reservoir operations amplify or dampen the net bias signal.

## Closure Term Correlation

Monthly correlation between closure terms and unimpaired flows proved too low for reliable quantile mapping. Only one location (Nicholas) showed correlation greater than 0.5, making standard quantile mapping infeasible for most closure term variables. This limitation led to the development of the WGEN sampling date approach, which achieves approximately 0.8 correlation with historical values by leveraging the temporal mapping embedded in the WGEN sampling process.

Fortunately, closure terms are being retired in future CalSim versions. This planned retirement reduces the long-term importance of the closure term methodology developed in Phase I, though the approach remains necessary for near-term work with current model versions.

