# %%
"""
Step 4 — Cluster microtrips by their numeric features.

1. Loads the summary CSV produced by 03_build_microtrips.py.
2. Auto-detects feature columns: every column NOT in META_COLS is treated as a
   numeric feature.  Adding new metrics to 03 automatically includes them here.
3. Runs the elbow method to help choose N_CLUSTERS.
4. Fits KMeans and visualises cluster separation via a pairplot.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ── Configuration ─────────────────────────────────────────────────────────────
ROOTDIR = Path(__file__).parents[2]

OUTPUT_DIR = ROOTDIR / "data"

# Identifier columns — excluded from clustering features.
# Keep in sync with the same constant in 03_build_microtrips.py.
META_COLS = frozenset({"trip_id", "parquet_id", "microtrip_index", "filename"})

N_CLUSTERS = 4  # adjust after inspecting the elbow plot

# ── Load summary ───────────────────────────────────────────────────────────────
microtrips_dir = OUTPUT_DIR / "microtrips"
SUMMARY_FILE = microtrips_dir / "summary.csv"

df = pd.read_csv(SUMMARY_FILE)
# %%
df.head()
# %%
df.columns
# %%
# ── Auto-detect feature columns ────────────────────────────────────────────────
FEATURES = [c for c in df.columns if c not in META_COLS]
print(f"Feature columns ({len(FEATURES)}): {FEATURES}")

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

#%%
FIGS_DIR  = OUTPUT_DIR / "figs"
FIGS_DIR.mkdir(exist_ok=True, parents=True) 
g.savefig(FIGS_DIR / "microtrip_clusters_pairplot.png", dpi=300)
# %%
# ── Cluster summary ────────────────────────────────────────────────────────────
df.groupby("cluster")[FEATURES].mean().round(2)
