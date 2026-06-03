# %%
"""
Step 6 — Rank microtrips within each cluster by similarity to the cluster mean.

Loads the persisted microtrip collection and the clustered summary from
040_microtrip_clustering.py, ranks microtrips per cluster using
MicrotripCollection.rank(), and writes microtrips/ranked_microtrips.csv for
use in 062_plot_representatives.py.

Configuration is read from config.json in the same directory.
"""

import json
from pathlib import Path

from drive_cycle_calculator.microtrip_collection import MicrotripCollection

# ── Config ─────────────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]
MICROTRIPS_DIR = OUTPUT_DIR / "microtrips"

# ── Load ───────────────────────────────────────────────────────────────────────
clustered_csv = MICROTRIPS_DIR / "summary_clustered.csv"
if not clustered_csv.exists():
    print(f"summary_clustered.csv not found at {clustered_csv}.")
    print("Run 040_microtrip_clustering.py first.")
    raise SystemExit(1)

mc = MicrotripCollection.from_parquets(MICROTRIPS_DIR, summary_csv=clustered_csv)
print(f"Loaded {len(mc)} microtrips in {mc.summary['cluster_id'].nunique()} clusters.")

# ── Rank ───────────────────────────────────────────────────────────────────────
ranked = mc.rank(group_col="cluster_id")

# ── Export ─────────────────────────────────────────────────────────────────────
out_path = MICROTRIPS_DIR / "ranked_microtrips.csv"
ranked.sort_values(["cluster_id", "rank"]).to_csv(out_path, index=False)
print(f"Ranked summary saved to {out_path}")
print("  Next: run 062_plot_representatives.py")
# %%
