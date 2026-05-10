# %%
"""
Step 4 — proceesing of microtrips

1. Loads the summary csv
2. Performs microtrip clustering
3. plots a graph in seaborn(?) which shows different aspect with the differne tclustering. 

"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from drive_cycle_calculator.obd_file import OBDFile
from drive_cycle_calculator.processing_config import ProcessingConfig
from drive_cycle_calculator.schema import SegmentationConfig
from drive_cycle_calculator.segmentation import MicrotripSegmenter

# ── Configuration ─────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]

OUTPUT_DIR = ROOTDIR / "data"  # must contain a trips/ sub-folder of Parquets

FEATURES = ["motion_samples", "stop_samples", "duration_s", "stop_duration_s", "mean_speed_kmh"]
N_CLUSTERS = 4  # adjust after inspecting the elbow plot
# %%
PROCESSING_CONFIG = ProcessingConfig(window=4, stop_threshold_kmh=2.0)

SEGMENTATION_CONFIG = SegmentationConfig(
    stop_threshold_kmh=2.0,
    stop_min_duration_s=1.0,
    microtrip_min_duration_s=15.0,
    microtrip_min_distance_m=50.0,
)

# ── Setup ──────────────────────────────────────────────────────────────────────

trips_dir = OUTPUT_DIR / "trips"
microtrips_dir = OUTPUT_DIR / "microtrips"

if not trips_dir.is_dir():
    print(f"No trips/ directory found under {OUTPUT_DIR}.")
    print("Run 01_ingest.py first.")
    raise SystemExit(1)

microtrips_dir.mkdir(parents=True, exist_ok=True)

# %%
SUMMARY_FILE = microtrips_dir/"summary.csv"
df = pd.read_csv(SUMMARY_FILE)
# %%
df.head()
# %%
df.columns
# %%
# ── Feature scaling ────────────────────────────────────────────────────────────
X = df[FEATURES].to_numpy()
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# %%
# ── Elbow method — inspect to choose N_CLUSTERS ────────────────────────────────
inertias = []
k_range = range(2, 10)
for k in k_range:
    km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    km.fit(X_scaled)
    inertias.append(km.inertia_)

fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(list(k_range), inertias, marker="o")
ax.set_xlabel("Number of clusters (k)")
ax.set_ylabel("Inertia")
ax.set_title("Elbow Method — KMeans on microtrip features")
ax.axvline(N_CLUSTERS, color="red", linestyle="--", alpha=0.5, label=f"chosen k={N_CLUSTERS}")
ax.legend()
plt.tight_layout()
plt.show()

# %%
# ── Fit KMeans ─────────────────────────────────────────────────────────────────
km = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init="auto")
df["cluster"] = km.fit_predict(X_scaled).astype(str)

# %%
# ── Pairplot — cluster separation across all feature pairs ─────────────────────
g = sns.pairplot(
    df[FEATURES + ["cluster"]],
    hue="cluster",
    diag_kind="kde",
    plot_kws={"alpha": 0.5, "s": 20},
)
g.figure.suptitle("Microtrip clusters — pairplot", y=1.02)
plt.show()

# %%
# ── Cluster summary ────────────────────────────────────────────────────────────
df.groupby("cluster")[FEATURES].mean().round(2)
