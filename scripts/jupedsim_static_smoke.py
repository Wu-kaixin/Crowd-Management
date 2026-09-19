from pathlib import Path

import jupedsim as jps
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Polygon


def main():
    # ---------------------------------------------------------
    # 1. Environment geometry
    # ---------------------------------------------------------
    environment = Polygon(
        [
            (0.0, 0.0),
            (12.0, 0.0),
            (12.0, 12.0),
            (0.0, 12.0),
        ]
    )

    # ---------------------------------------------------------
    # 2. Region occupied by the static crowd
    # ---------------------------------------------------------
    crowd_region = Polygon(
        [
            (3.0, 3.0),
            (9.0, 3.0),
            (9.0, 9.0),
            (3.0, 9.0),
        ]
    )

    # ---------------------------------------------------------
    # 3. Generate pedestrian positions with JuPedSim
    # ---------------------------------------------------------
    positions = jps.distributions.distribute_by_number(
        polygon=crowd_region,
        number_of_agents=50,
        distance_to_agents=0.55,
        distance_to_polygon=0.30,
        seed=42,
    )

    crowd_points = np.asarray(positions, dtype=float)

    print("Crowd point cloud shape:", crowd_points.shape)
    print("First five pedestrians:")
    print(crowd_points[:5])

    # ---------------------------------------------------------
    # 4. Save as ABCG-compatible N x 2 point cloud
    # ---------------------------------------------------------
    output_dir = Path("outputs/jupedsim_step1")
    output_dir.mkdir(parents=True, exist_ok=True)

    np.save(
        output_dir / "static_crowd_points.npy",
        crowd_points,
    )

    # ---------------------------------------------------------
    # 5. Simple visualization
    # ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6, 6))

    ex, ey = environment.exterior.xy
    ax.plot(ex, ey)

    cx, cy = crowd_region.exterior.xy
    ax.plot(cx, cy, linestyle="--")

    ax.scatter(
        crowd_points[:, 0],
        crowd_points[:, 1],
        s=25,
    )

    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title("JuPedSim Static Crowd — Step 1")

    fig.tight_layout()
    fig.savefig(
        output_dir / "static_crowd.png",
        dpi=200,
    )

    plt.show()


if __name__ == "__main__":
    main()