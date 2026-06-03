from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import numpy as np
import pandas as pd

from drive_cycle_calculator.microtrip import Microtrip
from drive_cycle_calculator.similarity import SimilarityMeasure, pct_deviation

if TYPE_CHECKING:
    from drive_cycle_calculator.segmentation import MicrotripSegmenter
    from drive_cycle_calculator.trip_collection import TripCollection


def _build_summary(microtrips: list[Microtrip]) -> pd.DataFrame:
    """Compute per-microtrip summary metrics from in-memory samples.

    Produces the columns needed for both analysis (``rank``) and synthesis
    (``compute_targets``, ``select_microtrips``).  All metrics are derived
    solely from the motion samples and the trailing-stop duration; no parquet
    files are read beyond what the Microtrip object already holds.
    """
    rows: list[dict] = []
    for mt in microtrips:
        motion = mt.samples
        stop = mt.stop_samples

        if "elapsed_s" in motion.columns:
            elapsed = pd.to_numeric(
                pd.concat([motion, stop])["elapsed_s"], errors="coerce"
            ).dropna()
            duration_s = (
                float(elapsed.iloc[-1] - elapsed.iloc[0])
                if len(elapsed) >= 2
                else float(len(motion) + len(stop))
            )
            dt = pd.to_numeric(motion["elapsed_s"], errors="coerce").diff().bfill().fillna(1.0)
        else:
            duration_s = float(len(motion) + len(stop))
            dt = pd.Series(1.0, index=motion.index)

        speed_col = "smooth_speed_kmh" if "smooth_speed_kmh" in motion.columns else "speed_kmh"
        speed_kmh = pd.to_numeric(
            motion.get(speed_col, pd.Series(dtype=float)), errors="coerce"
        ).fillna(0.0)

        distance_m = float((speed_kmh / 3.6 * dt).sum())
        mean_speed_kmh = float(speed_kmh.mean()) if not speed_kmh.empty else 0.0
        max_speed_kmh = float(speed_kmh.max()) if not speed_kmh.empty else 0.0
        speed_95th_kmh = float(speed_kmh.quantile(0.95)) if not speed_kmh.empty else 0.0
        stop_duration_s = float(mt.stop_duration_after)

        if "acc_ms2" in motion.columns and distance_m > 0:
            acc = pd.to_numeric(motion["acc_ms2"], errors="coerce").fillna(0.0)
            acc_pos = acc.clip(lower=0.0)
            rpa = float((speed_kmh / 3.6 * acc_pos * dt).sum() / distance_m)
        else:
            rpa = float("nan")

        rows.append({
            "parquet_id": mt.parquet_id,
            "trip_file": str(mt.trip_file),
            "path": str(mt.path) if mt.path is not None else "",
            "duration_s": duration_s,
            "stop_duration_s": stop_duration_s,
            "distance_m": distance_m,
            "mean_speed_kmh": mean_speed_kmh,
            "max_speed_kmh": max_speed_kmh,
            "speed_95th_kmh": speed_95th_kmh,
            "rpa": rpa,
        })
    return pd.DataFrame(rows)


class MicrotripCollection:
    """A container for a set of microtrips with their summary metrics.

    Construct via:
      - ``MicrotripCollection.from_parquets(directory)``  — loads from saved Parquets
      - ``MicrotripCollection.from_trip_collection(tc, segmenter)``  — from live Trips

    Only persisted collections (built via ``from_parquets``) may be passed to
    ``synthesize()``.  Non-persisted collections (from ``from_trip_collection``)
    are useful for immediate inspection but microtrip data is bound via weakref.
    """

    def __init__(
        self,
        microtrips: list[Microtrip],
        summary: pd.DataFrame,
        persisted: bool,
    ) -> None:
        self._microtrips = microtrips
        self._summary = summary
        self._persisted = persisted

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_parquets(
        cls,
        directory: Path,
        summary_csv: Path | None = None,
    ) -> "MicrotripCollection":
        """Load a persisted collection from a directory of microtrip Parquets.

        Parameters
        ----------
        directory : Path
            Directory containing ``*.parquet`` microtrip files.
        summary_csv : Path, optional
            CSV with extra columns (e.g. ``cluster_id``) to merge into the
            summary.  Must have a ``path`` column matching the parquet paths.
        """
        parquets = sorted(Path(directory).glob("*.parquet"))
        microtrips = [Microtrip.from_parquet(p) for p in parquets]
        summary = _build_summary(microtrips)
        if summary_csv is not None:
            extra = pd.read_csv(summary_csv)
            extra_cols = [c for c in extra.columns if c not in summary.columns and c != "path"]
            if extra_cols:
                summary = summary.merge(extra[["path"] + extra_cols], on="path", how="left")
        return cls(microtrips, summary, persisted=True)

    @classmethod
    def from_trip_collection(
        cls,
        tc: TripCollection,
        segmenter: MicrotripSegmenter,
    ) -> "MicrotripCollection":
        """Build a non-persisted collection by segmenting a TripCollection in place.

        Microtrips are weakref-bound to the live Trip objects in ``tc``.
        The summary is computed eagerly while the Trips are alive. If the
        Trip objects are GC'd later, iterating over the collection and
        accessing ``mt.samples`` will raise RuntimeError.

        Use this for immediate inspection only. For synthesis, call
        ``MicrotripSegmenter.export_collection()`` then ``from_parquets()``.
        """
        result = segmenter.segment_collection(tc)
        microtrips = [mt for mts in result.values() for mt in mts]
        summary = _build_summary(microtrips)
        return cls(microtrips, summary, persisted=False)

    # ── Container ─────────────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[Microtrip]:
        return iter(self._microtrips)

    def __len__(self) -> int:
        return len(self._microtrips)

    def __repr__(self) -> str:
        return f"MicrotripCollection({len(self._microtrips)} microtrips, persisted={self._persisted})"

    @property
    def summary(self) -> pd.DataFrame:
        """One row per microtrip with metrics and path.  Returns a copy."""
        return self._summary.copy()

    @property
    def is_persisted(self) -> bool:
        """True only when every microtrip has a saved Parquet path.

        Non-persisted collections are weakref-bound to live Trip objects and
        will raise RuntimeError on data access once those trips are GC'd.
        Only persisted collections may be passed to ``synthesize()``.
        """
        return self._persisted

    # ── Analysis ──────────────────────────────────────────────────────────────

    def rank(
        self,
        group_col: str,
        metrics: list[str] | None = None,
        measure: SimilarityMeasure = pct_deviation,
    ) -> pd.DataFrame:
        """Rank microtrips by similarity to their group mean.

        Parameters
        ----------
        group_col : str
            Column in ``summary`` that defines the groups (e.g. ``cluster_id``
            or ``wltp_phase``).
        metrics : list[str], optional
            Numeric columns to include in the similarity computation.
            Defaults to ``["mean_speed_kmh", "rpa", "speed_95th_kmh",
            "idle_fraction"]`` — the subset present in the summary is used
            automatically.
        measure : SimilarityMeasure
            Similarity function.  Defaults to ``pct_deviation``.

        Returns
        -------
        pd.DataFrame
            ``summary`` with two additional columns: ``score`` (float, higher
            is more representative) and ``rank`` (int, 1 = most representative
            within its group).
        """
        if metrics is None:
            defaults = ["mean_speed_kmh", "rpa", "speed_95th_kmh", "idle_fraction"]
            metrics = [c for c in defaults if c in self._summary.columns]

        df = self._summary.copy()
        if group_col not in df.columns:
            raise ValueError(f"group_col {group_col!r} not found in summary columns")
        if not metrics:
            raise ValueError("No numeric metric columns available for ranking")

        score_map: dict[int, float] = {}
        for _, group in df.groupby(group_col):
            fleet = group[metrics].to_numpy(dtype=float)
            for idx, row in group.iterrows():
                trip_vec = np.array([row[m] for m in metrics], dtype=float)
                score_map[idx] = measure(fleet, trip_vec)

        df["score"] = pd.Series(score_map)
        df["rank"] = (
            df.groupby(group_col)["score"]
            .rank(method="first", ascending=False)
            .astype(int)
        )
        return df
