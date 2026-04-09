import numpy as np


def similarity(overall_val: float, rep_val: float) -> float:
    """% similarity between a representative value and the overall mean.

    Returns a value in [0, 100]. Perfect match returns 100.0.
    """
    if np.isnan(overall_val):
        return 0.0
    if overall_val == 0:
        return 100.0 if rep_val == 0 else 0.0
    return max(0.0, 100.0 - abs(rep_val - overall_val) / abs(overall_val) * 100)
