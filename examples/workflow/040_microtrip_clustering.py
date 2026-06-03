# %%
"""
Step 4 — Cluster microtrips by their numeric features.

1. Loads the summary CSV produced by 030_build_microtrips.py.
2. Auto-detects feature columns: every column NOT in META_COLS is treated as a
   numeric feature.  Adding new metrics to 030 automatically includes them here.
3. Runs the elbow method to help choose N_CLUSTERS.
4. Fits KMeans and visualises cluster separation via a pairplot.

Configuration is read from config.json in the same directory as this script.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ── Configuration (loaded from config.json) ───────────────────────────────────
ROOTDIR = Path(__file__).parents[2]
_cfg = json.loads((Path(__file__).parent / "config.json").read_text())

OUTPUT_DIR = ROOTDIR / _cfg["output_dir"]

REPORTS_DIR = OUTPUT_DIR / "reports/"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)

FIGS_DIR = REPORTS_DIR / "figs-clustering"
FIGS_DIR.mkdir(exist_ok=True, parents=True)


# Identifier columns from MicrotripSegmenter.export_collection() — excluded from
# clustering features.  All other numeric columns in summary.csv are used.
META_COLS = frozenset({"trip_id", "microtrip_idx", "path"})

N_CLUSTERS = _cfg["clustering"]["n_clusters"]  # adjust after inspecting the elbow plot

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
# plt.show()

# %%
# ── Fit KMeans ─────────────────────────────────────────────────────────────────
km = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init="auto")
df["cluster_id"] = km.fit_predict(X_scaled).astype(str)

# ── Save augmented summary to microtrips/ ──────────────────────────────────────
clustered_path = microtrips_dir / "summary_clustered.csv"
df.to_csv(clustered_path, index=False)
print(f"Clustered summary written to {clustered_path}")

# %%
# ── Pairplot — cluster separation across all feature pairs ─────────────────────
# plt.figure()
g = sns.pairplot(
    df[FEATURES + ["cluster_id"]],
    hue="cluster_id",
    diag_kind="kde",
    plot_kws={"alpha": 0.5, "s": 20},
)
g.figure.suptitle("Microtrip clusters — pairplot", y=1.02)


# %%
g.savefig(FIGS_DIR / "microtrip_clusters_pairplot.png", dpi=300)
# %%
# ── Cluster summary ────────────────────────────────────────────────────────────
cluster_sizes = df.groupby("cluster_id").size().rename("count")
cluster_mean = df.groupby("cluster_id")[FEATURES].mean().round(3)
cluster_std = df.groupby("cluster_id")[FEATURES].std().round(3)

print(f"\nItems per cluster:\n{cluster_sizes.to_string()}")
print(f"\nCluster means:\n{cluster_mean.to_string()}")

# %%
# ── Markdown report ────────────────────────────────────────────────────────────


def _mean_std_table(mean_df: pd.DataFrame, std_df: pd.DataFrame) -> str:
    clusters = mean_df.index.tolist()
    header = "| Feature | " + " | ".join(f"Cluster {c}" for c in clusters) + " |"
    sep = "| --- | " + " | ".join("---" for _ in clusters) + " |"
    rows = [header, sep]
    for feat in mean_df.columns:
        cells = " | ".join(
            f"{mean_df.loc[c, feat]:.3f} ± {std_df.loc[c, feat]:.3f}" for c in clusters
        )
        rows.append(f"| {feat} | {cells} |")
    return "\n".join(rows)


sizes_table = "| Cluster | Count |\n| --- | --- |\n" + "\n".join(
    f"| {c} | {n} |" for c, n in cluster_sizes.items()
)

report = f"""\
# Microtrip Clustering Report

## Configuration

- **Features ({len(FEATURES)}):** {", ".join(FEATURES)}
- **N clusters:** {N_CLUSTERS}
- **Total microtrips:** {len(df)}

## Cluster sizes

{sizes_table}

## Cluster profiles (mean ± std)

{_mean_std_table(cluster_mean, cluster_std)}

## Pairplot

![Microtrip cluster pairplot](figs-clustering/microtrip_clusters_pairplot.png)
"""

report_path = REPORTS_DIR / "microtrip_clusters_report.md"
report_path.write_text(report, encoding="utf-8")
print(f"\nReport written to {report_path}")

plt.show()
