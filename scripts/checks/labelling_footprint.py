"""How many separated areas must be labelled for a valid geographic split. At least 3.

Supports: validation.md 27, labelling.md

Installed from the session that produced the result. Run from anywhere:

    python scripts/checks/labelling_footprint.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from config.loader import load_config  # noqa: E402
from config.schema import Config  # noqa: E402
from models.dataset import PatchRef, assign_splits  # noqa: E402

cfg = load_config(load_env=False)
s = cfg.models.split
p = cfg.models.patch
print(f"defaults: block {s.block_km} km, buffer {s.buffer_px} px "
      f"= {s.buffer_px * p.scale_m:.0f} m, patch {p.size_px} px "
      f"= {p.size_px * p.scale_m:.0f} m\n")

buffer_m = s.buffer_px * p.scale_m
block_m = s.block_km * 1000.0
interior = max(0.0, block_m - 2 * buffer_m)
print(f"a {s.block_km:.0f} km block has a usable interior of "
      f"{interior / 1000:.2f} km square = {(interior / 1000) ** 2:.1f} km2")
print(f"  ({100 * (interior ** 2) / (block_m ** 2):.0f}% of the block; the "
      f"buffer is a band around every edge)")
print(f"the Baige AOI (3 km buffer) is ~28 km2 -- smaller than one block, so "
      f"it cannot be partitioned at all\n")


def simulate(n_sites: int, per_site: int, separation_km: float,
             config: Config) -> dict:
    """Patches clustered at n_sites, separated along one axis."""
    refs = []
    for site in range(n_sites):
        base = site * separation_km * 1000.0
        for k in range(per_site):
            # Keep every patch inside one block's interior, so what is being
            # tested is the number of separated sites and not the buffer.
            span = p.size_px * p.scale_m
            x = base + block_m / 2.0 + ((k % 3) - 1) * span * 0.5
            y = block_m / 2.0 + ((k // 3) - 1) * span * 0.5
            refs.append(PatchRef(path=Path(f"s{site}_{k}.npz"), x_m=x, y_m=y))
    splits = assign_splits(refs, config)
    return {name: len(v) for name, v in splits.items()}


print("sites separated by one block, 12 patches each:")
rows = []
for n in (1, 2, 3, 4, 6, 10):
    counts = simulate(n, 12, s.block_km, cfg)
    ok = all(counts[k] > 0 for k in ("train", "val", "test"))
    print(f"  {n:2d} site(s) -> {counts}   {'OK' if ok else 'UNUSABLE'}")
    rows.append({"sites": n, **counts, "usable": ok})

print("\nthe minimum is 3 separated sites; below that a partition is empty "
      "and its metrics are undefined, not zero.")

smallest = next((r["sites"] for r in rows if r["usable"]), None)
print(f"\nguidance for labelling:")
print(f"  * label in AT LEAST {smallest} areas at least {s.block_km:.0f} km apart,")
print(f"    and preferably 6-10, so each partition holds more than one site;")
print(f"  * within a site, only the patches matter, not full coverage: "
      f"{p.size_px * p.scale_m:.0f} m squares of labelled ground;")
print(f"  * keep each site's labels {buffer_m:.0f} m clear of a block edge, or "
      f"place sites near block centres.")

out = ROOT / "outputs" / "phase6_labelling_footprint.json"
out.write_text(json.dumps({
    "block_km": s.block_km,
    "buffer_m": buffer_m,
    "patch_m": p.size_px * p.scale_m,
    "block_interior_km2": round((interior / 1000) ** 2, 2),
    "baige_aoi_km2": 28,
    "simulation": rows,
    "minimum_separated_sites": smallest,
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
