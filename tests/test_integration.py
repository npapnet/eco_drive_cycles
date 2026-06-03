"""Integration tests for end-to-end drive cycle synthesis pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from drive_cycle_calculator.cli.main import app
from drive_cycle_calculator.cli._layout import _project_layout
from drive_cycle_calculator.microtrip_collection import MicrotripCollection
from drive_cycle_calculator.schema import WLTPSynthesisConfig
from drive_cycle_calculator.synthesis import synthesize
from drive_cycle_calculator.synthesis.wltp import assign_wltp_phases

runner = CliRunner()


def test_integration_pipeline_end_to_end(tmp_path):
    """Run end-to-end pipeline using real data from data/trips/."""
    # 1. Setup project directory layout
    layout = _project_layout(tmp_path)

    # 2. Copy a couple of real archive Parquets from the workspace
    src_dir = Path("data/trips")
    real_parquets = sorted(src_dir.glob("*.parquet"))
    assert len(real_parquets) >= 2, f"Expected real parquets in data/trips, found {len(real_parquets)}"

    # Copy the first two parquets to the project's trips directory
    for p in real_parquets[:2]:
        shutil.copy(p, layout.trips / p.name)

    # 3. Run Step 3: Segment CLI subcommand
    result = runner.invoke(app, ["segment", str(tmp_path)])
    assert result.exit_code == 0, f"Segment CLI command failed: {result.output}"

    # Verify segmentation outputs exist
    microtrip_files = list(layout.microtrips.glob("*.parquet"))
    assert len(microtrip_files) > 0, "No microtrip parquets were produced"
    
    summary_path = layout.reports / "microtrip_summary.csv"
    assert summary_path.is_file(), "microtrip_summary.csv was not created"

    # 4. Load microtrip collection
    mc = MicrotripCollection.from_parquets(layout.microtrips, summary_csv=summary_path)
    assert len(mc) == len(microtrip_files)

    # 5. Assign WLTP phases
    assignments = assign_wltp_phases(mc.summary)
    assert len(assignments) == len(mc)

    # Determine which phases actually got assigned
    assigned_phases = set(assignments.unique())
    assert len(assigned_phases) > 0

    # Ensure all assigned phases have a small, reachable target distance
    phase_min_dist = {phase: 100.0 for phase in assigned_phases}

    # 6. Run synthesis (Step 4 & 5)
    config = WLTPSynthesisConfig(
        phase_min_distance_m=phase_min_dist,
        inter_phase_idle_s=5,
    )
    cycle = synthesize(mc, assignments, config)

    # 7. Validate synthesized cycle DataFrame
    assert isinstance(cycle, pd.DataFrame)
    assert {"t_s", "speed_kmh", "group"}.issubset(cycle.columns)
    assert len(cycle) > 0

    # Non-idle groups in the cycle should match assigned phases
    non_idle_groups = set(cycle.loc[cycle["group"] != "idle", "group"].unique())
    assert non_idle_groups.issubset(assigned_phases)
