"""Run known-boundary Step 1 experiments with live or headless execution."""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import yaml

from crowd_management.experiments.static_containment import run_static_containment
from crowd_management.runtime.parallel_config import select_parallel_plan


def _parse_seeds(raw: list[str]) -> list[int]:
    seeds: list[int] = []
    for item in raw:
        if ":" in item:
            start_s, end_s = item.split(":", 1)
            seeds.extend(range(int(start_s), int(end_s) + 1))
        else:
            seeds.append(int(item))
    return seeds


def _configs_from_manifest(path: Path) -> list[Path]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = path.parent
    configs: list[Path] = []
    for env in raw.get("environments", ["square", "rectangle"]):
        for shape in raw.get("shapes", ["circle", "ellipse", "concave", "irregular"]):
            configs.append(root / f"{env}_{shape}.yaml")
    return configs


JobPayload = tuple[str, str, int, bool, bool]


def _jobs_from_cases(path: Path, output: Path, headless: bool, save_plots: bool) -> list[JobPayload]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"] if isinstance(payload, dict) else payload
    root = Path("configs/step1_known_boundary")
    jobs: list[JobPayload] = []
    for case in cases:
        environment = str(case["environment"])
        shape = str(case["shape"])
        seed = int(case["seed"])
        config = root / f"{environment}_{shape}.yaml"
        jobs.append((str(config), str(output / config.stem), seed, headless, save_plots))
    return jobs


def _run_one(payload: tuple[str, str, int, bool, bool]) -> dict[str, object]:
    config, output, seed, headless, save_plots = payload
    config_path = Path(config)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["seed"] = int(seed)
    if "crowd" in raw:
        raw["crowd"]["seed"] = int(seed)
    resolved = Path(output) / f"seed_{int(seed):03d}" / "config.yaml"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    results = run_static_containment(
        resolved,
        resolved.parent,
        methods=["abcg"],
        save_plots=save_plots,
        live=not headless,
        headless=headless,
    )
    row = dict(results["abcg"])
    row["config"] = config_path.name
    row["seed"] = int(seed)
    row["environment"] = str((raw.get("scene") or {}).get("type", "unknown"))
    row["shape"] = str((raw.get("crowd") or {}).get("shape", "unknown"))
    row["heterogeneity"] = bool((raw.get("heterogeneity") or {}).get("enabled", False))
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Known-boundary Step 1 runner.")
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--manifest")
    parser.add_argument("--cases", type=Path, help="JSON list of {environment, shape, seed} development cases.")
    parser.add_argument("--seeds", nargs="+", default=["0"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--workers", default="1")
    parser.add_argument(
        "--no-save-plots",
        action="store_true",
        help="Skip PNG artifacts. Numerics are unchanged; wall-clock only.",
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    configs = [Path(item) for item in args.config]
    if args.manifest:
        configs.extend(_configs_from_manifest(Path(args.manifest)))
    if args.cases is None and not configs:
        raise SystemExit("Provide --config, --manifest, or --cases.")
    seeds = _parse_seeds(args.seeds)
    headless = bool(args.headless)
    save_plots = not bool(args.no_save_plots)
    if args.cases is not None:
        jobs = _jobs_from_cases(args.cases, output, headless, save_plots)
    else:
        jobs = [
            (str(config), str(output / config.stem), seed, headless, save_plots)
            for config in configs
            for seed in seeds
        ]
    if not headless:
        workers = 1
    elif args.workers == "auto":
        workers = select_parallel_plan(max(1, len(jobs)), mode="balanced").workers
    else:
        workers = max(1, int(args.workers))
    rows: list[dict[str, object]] = []
    if workers == 1:
        for job in jobs:
            rows.append(_run_one(job))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_one, job) for job in jobs]
            for future in as_completed(futures):
                rows.append(future.result())

    records = output / "records.csv"
    fieldnames = sorted({key for row in rows for key in row})
    with records.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"wrote {len(rows)} records to {records}")


if __name__ == "__main__":
    main()
