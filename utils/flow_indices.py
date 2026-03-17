import numpy as np
import pandas as pd
from typing import Dict, List, Union


def flowAggregator(stations: pd.DataFrame) -> Dict[str, Union[pd.DataFrame, pd.Series]]:
    """
    Translate R's flowAggregator() to Python/pandas.

    stations: DataFrame with columns:
      - 'WaterYear', 'Month'
      - station columns like 'BND','FTO','YRS','AMF','SNS','TLG','MRC','SJF','SIS','TNL', etc.
    Returns dict with:
      - DataFrames: Apr_Jul, Oct_Mar, Oct_Sep, Jan_May, Apr_May, Apr_Sep, Mar_Nov
      - Series: Apr_Jul_Sac, Oct_Mar_Sac, Oct_Sep_Sac,
                Apr_Jul_SJ,  Oct_Mar_SJ,  Oct_Sep_SJ,
                Jan_May_8Sta, Apr_May_8Sta,
                Oct_Sep_Sha,  Apr_Jul_Fea, Oct_Sep_Fea,
                Apr_Sep_Am,   Mar_Nov_Am,  Oct_Sep_Am,
                Oct_Sep_Tr
    """
    def _sum_by_year(df: pd.DataFrame, months: Union[List[int], None]) -> pd.DataFrame:
        if months is not None:
            sub = df[df["Month"].isin(months)].copy()
        else:
            sub = df.copy()
        # Sum all numeric columns by WaterYear (pandas will ignore non-numeric)
        grouped = sub.groupby("WaterYear").sum(numeric_only=True).reset_index()
        return grouped

    # Period aggregates
    Apr_Jul = _sum_by_year(stations, list(range(4, 8)))
    Oct_Mar = _sum_by_year(stations, [10, 11, 12, 1, 2, 3])
    Oct_Sep = _sum_by_year(stations, None)  # all months (matches R code behavior)
    Jan_May = _sum_by_year(stations, [1, 2, 3, 4, 5])
    Apr_May = _sum_by_year(stations, [4, 5])
    Apr_Sep = _sum_by_year(stations, list(range(4, 10)))
    Mar_Nov = _sum_by_year(stations, [3, 4, 5, 6, 7, 8, 9, 10, 11])

    # Convenience to get a Series aligned by WaterYear safely
    def col(df: pd.DataFrame, name: str) -> pd.Series:
        if name not in df.columns:
            return pd.Series(np.nan, index=df["WaterYear"])
        s = df.set_index("WaterYear")[name]
        s.name = name
        return s

    # Sacramento flows: BND + FTO + YRS + AMF
    Apr_Jul_Sac = col(Apr_Jul, "BND") + col(Apr_Jul, "FTO") + col(Apr_Jul, "YRS") + col(Apr_Jul, "AMF")
    Oct_Mar_Sac = col(Oct_Mar, "BND") + col(Oct_Mar, "FTO") + col(Oct_Mar, "YRS") + col(Oct_Mar, "AMF")
    Oct_Sep_Sac = col(Oct_Sep, "BND") + col(Oct_Sep, "FTO") + col(Oct_Sep, "YRS") + col(Oct_Sep, "AMF")

    # San Joaquin flows: SNS + TLG + MRC + SJF
    Apr_Jul_SJ = col(Apr_Jul, "SNS") + col(Apr_Jul, "TLG") + col(Apr_Jul, "MRC") + col(Apr_Jul, "SJF")
    Oct_Mar_SJ = col(Oct_Mar, "SNS") + col(Oct_Mar, "TLG") + col(Oct_Mar, "MRC") + col(Oct_Mar, "SJF")
    Oct_Sep_SJ = col(Oct_Sep, "SNS") + col(Oct_Sep, "TLG") + col(Oct_Sep, "MRC") + col(Oct_Sep, "SJF")

    # Eight Station
    Jan_May_8Sta = (
        col(Jan_May, "BND") + col(Jan_May, "FTO") + col(Jan_May, "YRS") + col(Jan_May, "AMF")
        + col(Jan_May, "SNS") + col(Jan_May, "TLG") + col(Jan_May, "MRC") + col(Jan_May, "SJF")
    )
    Apr_May_8Sta = (
        col(Apr_May, "BND") + col(Apr_May, "FTO") + col(Apr_May, "YRS") + col(Apr_May, "AMF")
        + col(Apr_May, "SNS") + col(Apr_May, "TLG") + col(Apr_May, "MRC") + col(Apr_May, "SJF")
    )

    # Shasta
    Oct_Sep_Sha = col(Oct_Sep, "SIS")

    # Feather
    Apr_Jul_Fea = col(Apr_Jul, "FTO")
    Oct_Sep_Fea = col(Oct_Sep, "FTO")

    # American
    Apr_Sep_Am = col(Apr_Sep, "AMF")
    Mar_Nov_Am = col(Mar_Nov, "AMF")
    Oct_Sep_Am = col(Oct_Sep, "AMF")

    # Trinity
    Oct_Sep_Tr = col(Oct_Sep, "TNL")

    return {
        "Apr_Jul_Sac": Apr_Jul_Sac,
        "Oct_Mar_Sac": Oct_Mar_Sac,
        "Oct_Sep_Sac": Oct_Sep_Sac,
        "Apr_Jul_SJ": Apr_Jul_SJ,
        "Oct_Mar_SJ": Oct_Mar_SJ,
        "Oct_Sep_SJ": Oct_Sep_SJ,
        "Jan_May_8Sta": Jan_May_8Sta,
        "Apr_May_8Sta": Apr_May_8Sta,
        "Oct_Sep_Sha": Oct_Sep_Sha,
        "Apr_Jul_Fea": Apr_Jul_Fea,
        "Oct_Sep_Fea": Oct_Sep_Fea,
        "Apr_Sep_Am": Apr_Sep_Am,
        "Mar_Nov_Am": Mar_Nov_Am,
        "Oct_Sep_Am": Oct_Sep_Am,
        "Oct_Sep_Tr": Oct_Sep_Tr,
    }


def sacIndex(
    sacAprJul: Union[np.ndarray, pd.Series, List[float]],
    sacOctMar: Union[np.ndarray, pd.Series, List[float]],
    modelWaterYears: int,
    aji: float,
    omi: float,
    c: float,
    d: float,
    bn: float,
    an: float,
    w: float,
) -> Dict[str, np.ndarray]:
    """
    Sacramento 4-River 40-30-30 Index (translated from R).

    Returns dict with:
      - "SacIndex": np.ndarray of floats
      - "SacWYT":   np.ndarray of ints (1..5)
    """
    sacAprJul = np.asarray(sacAprJul, dtype=float)
    sacOctMar = np.asarray(sacOctMar, dtype=float)
    n = modelWaterYears if modelWaterYears is not None else min(len(sacAprJul), len(sacOctMar))
    sacAprJul = sacAprJul[:n]
    sacOctMar = sacOctMar[:n]

    SacIndex = np.full(n, np.nan, dtype=float)
    SacWYT = np.full(n, np.nan, dtype=float)

    def classify(x: float) -> int:
        if x < c:
            return 5
        elif x < d:
            return 4
        elif x < bn:
            return 3
        elif x < an:
            return 2
        else:
            return 1

    # First year
    SacIndex[0] = aji * sacAprJul[0] + omi * sacOctMar[0] + 0.3 * 5.15  #  We changed 6.5 to 5.15 since the Calsim3 data started from WY1921 and Sac index for WY before that was 5.15
    SacWYT[0] = classify(SacIndex[0])

    # Subsequent years
    for i in range(1, n):
        carry = 10.0 if SacIndex[i - 1] > 10.0 else SacIndex[i - 1]
        SacIndex[i] = aji * sacAprJul[i] + omi * sacOctMar[i] + 0.3 * carry
        SacWYT[i] = classify(SacIndex[i])

    return {"SacIndex": SacIndex, "SacWYT": SacWYT.astype(int)}


def sjIndex(
    sjAprJul: Union[np.ndarray, pd.Series, List[float]],
    sjOctMar: Union[np.ndarray, pd.Series, List[float]],
    modelWaterYears: int,
    aji: float,
    omi: float,
    c: float,
    d: float,
    bn: float,
    an: float,
    w: float,
) -> Dict[str, np.ndarray]:
    """
    San Joaquin 4-River 60-20-20 Index (translated from R).

    Returns dict with:
      - "SJIndex": np.ndarray of floats
      - "SJWYT":   np.ndarray of ints (1..5)
    """
    sjAprJul = np.asarray(sjAprJul, dtype=float)
    sjOctMar = np.asarray(sjOctMar, dtype=float)
    n = modelWaterYears if modelWaterYears is not None else min(len(sjAprJul), len(sjOctMar))
    sjAprJul = sjAprJul[:n]
    sjOctMar = sjOctMar[:n]

    SJIndex = np.full(n, np.nan, dtype=float)
    SJWYT = np.full(n, np.nan, dtype=float)

    def classify(x: float) -> int:
        if x < c:
            return 5
        elif x < d:
            return 4
        elif x < bn:
            return 3
        elif x < an:
            return 2
        else:
            return 1

    # First year
    SJIndex[0] = aji * sjAprJul[0] + omi * sjOctMar[0] + 0.2 * 2.5
    SJWYT[0] = classify(SJIndex[0])

    # Subsequent years
    for i in range(1, n):
        carry = 4.5 if SJIndex[i - 1] > 4.5 else SJIndex[i - 1]
        SJIndex[i] = aji * sjAprJul[i] + omi * sjOctMar[i] + 0.2 * carry
        SJWYT[i] = classify(SJIndex[i])

    return {"SJIndex": SJIndex, "SJWYT": SJWYT.astype(int)}


def shastaIndex(shastaOctSep: Union[np.ndarray, pd.Series, List[float]], modelWaterYears: int) -> np.ndarray:
    """
    Shasta River Index (translated from R).
    Returns np.ndarray of ints in {1,2}.
    """
    shastaOctSep = np.asarray(shastaOctSep, dtype=float)
    n = modelWaterYears if modelWaterYears is not None else len(shastaOctSep)
    shastaOctSep = shastaOctSep[:n]

    cond1IndSha = np.full(n, np.nan, dtype=float)
    cond2Sha = np.full(n, np.nan, dtype=float)
    cond2IndSha = np.full(n, np.nan, dtype=float)
    ShaIndex = np.full(n, np.nan, dtype=float)

    cond1IndSha[0] = 1 if shastaOctSep[0] < 3.2 else 2
    cond2Sha[0] = 0.0
    cond2IndSha[0] = 1 if cond2Sha[0] > 0.8 else 2
    ShaIndex[0] = 1 if (cond1IndSha[0] + cond2IndSha[0]) < 4 else 2

    for i in range(1, n):
        cond1IndSha[i] = 1 if shastaOctSep[i] < 3.2 else 2
        cond2Sha[i] = (8 - shastaOctSep[i] - shastaOctSep[i - 1]) if (shastaOctSep[i] < 4 and shastaOctSep[i - 1] < 4) else 0.0
        cond2IndSha[i] = 1 if cond2Sha[i] > 0.8 else 2
        ShaIndex[i] = 1 if (cond1IndSha[i] + cond2IndSha[i]) < 4 else 2

    return ShaIndex.astype(int)


def featherIndex(
    feaAprJul: Union[np.ndarray, pd.Series, List[float]],
    feaOctSep: Union[np.ndarray, pd.Series, List[float]],
    modelWaterYears: int,
) -> np.ndarray:
    """
    Feather River Index (translated from R).
    Returns np.ndarray of ints in {0,1}.
    """
    feaAprJul = np.asarray(feaAprJul, dtype=float)
    feaOctSep = np.asarray(feaOctSep, dtype=float)
    n = modelWaterYears if modelWaterYears is not None else min(len(feaAprJul), len(feaOctSep))
    feaAprJul = feaAprJul[:n]
    feaOctSep = feaOctSep[:n]

    cond1IndFea = np.full(n, np.nan, dtype=float)
    cond2Fea = np.full(n, np.nan, dtype=float)
    cond2IndFea = np.full(n, np.nan, dtype=float)
    FeaIndex = np.full(n, np.nan, dtype=float)

    cond1IndFea[0] = 1 if feaAprJul[0] < 0.6 else 0
    cond2Fea[0] = 0.0
    cond2IndFea[0] = 1 if cond2Fea[0] > 0.4 else 0
    FeaIndex[0] = min(cond1IndFea[0] + cond2IndFea[0], 1)

    for i in range(1, n):
        cond1IndFea[i] = 1 if feaAprJul[i] < 0.6 else 0
        cond2Fea[i] = (5 - feaOctSep[i] - feaOctSep[i - 1]) if (feaOctSep[i] < 2.5 and feaOctSep[i - 1] < 2.5) else 0.0
        cond2IndFea[i] = 1 if cond2Fea[i] > 0.4 else 0
        FeaIndex[i] = int(min(cond1IndFea[i] + cond2IndFea[i], 1))

    return FeaIndex.astype(int)


def trinWYT(trinOctSep: Union[np.ndarray, pd.Series, List[float]], modelWaterYears: int) -> np.ndarray:
    """
    Trinity River WYT (translated from R).
    Returns np.ndarray of ints in {1,2,3,4,5}.
    """
    trinOctSep = np.asarray(trinOctSep, dtype=float)
    n = modelWaterYears if modelWaterYears is not None else len(trinOctSep)
    trinOctSep = trinOctSep[:n]

    TrinWYT = np.empty(n, dtype=int)
    for i in range(n):
        x = trinOctSep[i]
        if x < 0.65:
            TrinWYT[i] = 5
        elif x < 1.025:
            TrinWYT[i] = 4
        elif x < 1.35:
            TrinWYT[i] = 3
        elif x < 2.0:
            TrinWYT[i] = 2
        else:
            TrinWYT[i] = 1
    return TrinWYT