# %%
"""
Step 6 — Rank microtrips within each cluster using one or more similarity measures.

For each measure in MEASURES_MAP, computes a per-cluster similarity score and rank.
Exports ranked_microtrips.csv with score_<name> and rank_<name> columns for every
active measure, in MEASURES_MAP order.

Run 062_plot_representatives.py to visualise the top-ranked microtrips.
"""

import json
from pathlib import Path

import pandas as pd

from drive_cycle_calculator.similarity.measures import (
    SimilarityMeasure,
    cosine_similarity,
    pct_deviation,
    z_score_distance,
)

# ── Script Configuration ───────────────────────────────────────────────────────
# Comment out entries to exclude a measure from the output.
MEASURES_MAP = {
    "z_score": z_score_distance,
    "pct_deviation": pct_deviation,
    "cosine": cosine_similarity,
}
# ───────────────────────────────────────────────────────────────────────────────

# Identifier columns to exclude from similarity calculation (must match clustering).
META_COLS = frozenset(
    {
        "trip_id",
        "parquet_id",
        "microtrip_index",
        "filename",
        "motion_samples",
        "stop_samples",
        "cluster_id",
    }
)


def rank_microtrips(
    df: pd.DataFrame,
    features: list[str],
    measures: dict[str, SimilarityMeasure],
) -> pd.DataFrame:
    """Return df augmented with score_<name> and rank_<name> columns per measure.

    Scores and ranks are computed per cluster_id group. Rank 1 = most similar
    to the fleet (highest score).
    """
    result = df.copy()
    for name, fn in measures.items():
        score_col = f"score_{name}"
        result[score_col] = 0.0
        for _, group in result.groupby("cluster_id"):
            fleet_matrix = group[features].to_numpy()
            scores = [fn(fleet_matrix, fleet_matrix[i]) for i in range(len(group))]
            result.loc[group.index, score_col] = scores
        result[f"rank_{name}"] = (
            result.groupby("cluster_id")[score_col]
            .rank("dense", ascending=False)
            .astype(int)
        )
    return result


# ── Load shared config ─────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())
OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips/"

# ── Load data ──────────────────────────────────────────────────────────────────
summary_clustered_path = MICROTRIPS_DIR / "summary_clustered.csv"
if not summary_clustered_path.exists():
    print(f"Error: Could not find {summary_clustered_path}")
    print("Please run 040_microtrip_clustering.py first.")
    raise SystemExit(1)

df = pd.read_csv(summary_clustered_path)

if "cluster_id" not in df.columns:
    print("Error: 'cluster_id' column not found in summary. Did you run step 04?")
    raise SystemExit(1)

df["cluster_id"] = df["cluster_id"].astype(str)

features = [c for c in df.columns if c not in META_COLS]
primary = next(iter(MEASURES_MAP))
print(f"Found {df['cluster_id'].nunique()} clusters.")
print(f"Using {len(features)} features: {features}")
print(f"Measures: {list(MEASURES_MAP)}")

# ── Rank ───────────────────────────────────────────────────────────────────────
ranked = rank_microtrips(df, features, MEASURES_MAP)

# ── Export ─────────────────────────────────────────────────────────────────────
ranked_path = MICROTRIPS_DIR / "ranked_microtrips.csv"
ranked.sort_values(["cluster_id", f"rank_{primary}"]).to_csv(ranked_path, index=False)
print(f"Ranked summary saved to {ranked_path}")
# %%
