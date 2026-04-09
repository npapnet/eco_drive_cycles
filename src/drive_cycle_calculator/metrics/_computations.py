# _computations.py
# ----------------
# Two sections:
#
# A. PRIVATE HELPERS — used internally by Trip and TripCollection.
#    Named with leading underscore.  Not part of the public API.
#

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# A.  PRIVATE HELPERS
# ────────────────────────────────────────────────────────────────────────────


def gps_to_duration_seconds(gps_series: pd.Series) -> pd.Series:
    """Convert GPS Time column to elapsed seconds from the first valid record.

    This is a more general purpose for clean data (compared to the _schema.py)


    """
    numeric = pd.to_numeric(gps_series, errors="coerce")
    if numeric.notna().any():
        first_value = numeric.dropna().iloc[0]
        return numeric - first_value

    dt = pd.to_datetime(gps_series, errors="coerce", utc=True)
    if dt.notna().any():
        first_dt = dt.dropna().iloc[0]
        return (dt - first_dt).dt.total_seconds()

    return pd.Series([np.nan] * len(gps_series), index=gps_series.index)
