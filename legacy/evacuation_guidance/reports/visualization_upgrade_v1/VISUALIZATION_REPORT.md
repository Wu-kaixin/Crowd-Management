# Visualization Upgrade Report

## Purpose

This stage strengthens the 2D crowd management visualization layer so evacuation results can be inspected, compared, and presented without re-running simulation. The goal is to support clearer evacuation analysis, professor discussion, and future report or presentation figures.

## Added Features

- Replay data export through `outputs/<run>/replay.npz`.
- Single-run animation rendering for evacuation replay.
- Density heatmap overlay in animations and snapshots.
- Side-by-side synchronized comparison for baseline vs DBACT.
- Four-mode final snapshot grid for baseline / static / random / DBACT.
- Dashboard figure combining evacuation curves, final metric comparison, and final snapshots.
- Heatmap snapshot renderer for selected timestamps.

## Generated Outputs

Smoke workflow generated these local artifacts:

- `outputs/baseline/replay.npz`
- `outputs/static/replay.npz`
- `outputs/random/replay.npz`
- `outputs/dbact/replay.npz`
- `outputs/dbact/dbact_animation.gif`
- `outputs/comparison/baseline_vs_dbact.gif`
- `outputs/comparison/dashboard.png`
- `outputs/comparison/all_modes_grid.png`
- `outputs/dbact/heatmap_snapshots.png`

Representative committed report artifacts:

- `reports/visualization_upgrade_v1/dashboard.png`
- `reports/visualization_upgrade_v1/all_modes_grid.png`
- `reports/visualization_upgrade_v1/heatmap_snapshots.png`

`ffmpeg` was not available in the current PATH, so MP4 requests correctly fell back to GIF output.

## Observations

- The DBACT pipeline is runnable end to end with replay export and offline rendering.
- In the current `simple_room` smoke run, baseline evacuated 149 / 160 pedestrians by 20.0 s, while static, random, and DBACT each evacuated 150 / 160.
- Static guidance currently has a slightly lower mean congestion index than DBACT in this simple one-exit scenario, so side-by-side visualization is useful for analyzing why static remains competitive.
- Heatmap rendering makes the congestion region easier to identify than final scatter plots alone.

## Next Steps

1. improve guider-pedestrian interaction model
2. use two-exit scenario to better show crowd management value
3. tune guidance strength / compliance / guider placement
