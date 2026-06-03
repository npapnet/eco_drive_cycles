# Drive Cycle Calculator

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data, computing
eco-driving scores, and synthesizing representative drive cycles.

The system processes real-world driving data collected via the Torque app (OBD-II),
computes per-trip metrics, identifies representative drive cycles, and supports
WLTP-style candidate cycle synthesis from microtrip building blocks.

---

## Overview

```{mermaid}
flowchart LR
    A["Raw OBD-II\n(.xlsx / .csv)"] --> B["Archive\nParquets"]
    B --> C["Trip Metrics\n(DuckDB / CSV)"]
    C --> D["Similarity &\nRepresentative Trip"]
    B --> E["Microtrip\nSegmentation"]
    E --> F["Clustering"]
    F --> G["Drive Cycle\nSynthesis"]
```

The pipeline has two branches that diverge after ingestion:

- **Metrics branch** — per-trip scalar metrics, similarity scoring, representative trip identification.
- **Synthesis branch** — microtrip segmentation, clustering, and stochastic assembly of a synthetic representative drive cycle.

---

## Contents

```{toctree}
:maxdepth: 2
:caption: User Guide

pipeline
quickstart/index
```

```{toctree}
:maxdepth: 2
:caption: Theory

theory/ingestion-preprocessing
theory/microtrip-spec
theory/synthesis-algorithm
```

```{toctree}
:maxdepth: 2
:caption: API Reference

api/index
```
