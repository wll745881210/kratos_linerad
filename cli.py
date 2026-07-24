"""Line RT Interface CLI."""

import argparse
import json
import os
import sys

import numpy as np


def parse_source(source_str):
    """Parse a source string like 'point,0,0,0,0.8,2.35e-4' into a dict."""
    parts = source_str.split(",")
    src_type = parts[0].strip().lower()
    if src_type == "point":
        return {
            "type": "point",
            "x": float(parts[1]) if len(parts) > 1 else 0.0,
            "y": float(parts[2]) if len(parts) > 2 else 0.0,
            "z": float(parts[3]) if len(parts) > 3 else 0.0,
            "luminosity": float(parts[4]) if len(parts) > 4 else 0.8,
            "wavelength_cm": float(parts[5]) if len(parts) > 5 else 2.35e-4,
        }
    elif src_type == "parallel":
        return {
            "type": "parallel_beam",
            "flux": float(parts[1]) if len(parts) > 1 else 1e6,
            "area": float(parts[2]) if len(parts) > 2 else 1.0,
        }
    else:
        return {"type": src_type, "raw": source_str}


def main():
    parser = argparse.ArgumentParser(description="Line RT Interface")
    parser.add_argument(
        "--source",
        default="point,0,0,0,0.8,2.35e-4",
        help="Source: type,params",
    )
    parser.add_argument("--species", default="CO", help="Species name")
    parser.add_argument(
        "--cycles", type=int, default=5, help="Number of iteration cycles"
    )
    parser.add_argument(
        "--n-photon", type=int, default=50000, help="Number of photons"
    )
    parser.add_argument(
        "--n-scat", type=int, default=10000, help="Max scattering events"
    )
    parser.add_argument(
        "--n-step", type=int, default=10000, help="Max steps per photon"
    )
    parser.add_argument(
        "--ph-mode",
        type=int,
        default=1,
        choices=[0, 1],
        help="Photon mode: 0=coherent, 1=CFR",
    )
    parser.add_argument(
        "--n-thread", type=int, default=1, help="Number of threads"
    )
    parser.add_argument(
        "--output", default="results.npz", help="Output file path"
    )
    parser.add_argument(
        "--work-dir",
        default="/tmp/line_rt_cli",
        help="Working directory for temporary files",
    )
    args = parser.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)

    source_cfg = parse_source(args.source)
    print(f"Source: {source_cfg}")
    print(f"Species: {args.species}")
    print(f"Cycles: {args.cycles}, Photons: {args.n_photon}")
    print(f"Mode: {'CFR' if args.ph_mode == 1 else 'coherent'}")
    print(f"Output: {args.output}")
    print(f"Work dir: {args.work_dir}")

    print("\nGenerating photons… (stub)")

    print("Running iterate… (stub)")

    results = {
        "source": source_cfg,
        "species": args.species,
        "cycles": args.cycles,
        "n_photon": args.n_photon,
        "ph_mode": args.ph_mode,
    }
    out_path = os.path.join(args.work_dir, args.output)
    np.savez(out_path, **results)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
