"""Line RT Interface CLI — high-level launcher for linert.LineRT."""

import argparse
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_LINERT = os.path.join(os.path.expanduser('~/scratch/line_rt'), 'linert.py')
if os.path.exists(_LINERT):
    sys.path.insert(0, os.path.dirname(_LINERT))

from linert import (LineRT, SlabSource, PointSource, Result)


def main():
    parser = argparse.ArgumentParser(description="Line RT Interface")
    parser.add_argument("--source", default="slab,-5,0,0,1,0,0,1.0,50000,1e5",
                        help="Source: type,x,y,z,dir_x,dir_y,dir_z,luminosity,n_photon,b_sca")
    parser.add_argument("--species", default=None, help="Species name (e.g. CO)")
    parser.add_argument("--lamda-file", default=None, help="Path to LAMDA .dat file")
    parser.add_argument("--transition", default=None, type=float,
                        help="Transition rest frequency [GHz]")
    parser.add_argument("--cycles", type=int, default=5, help="Number of iteration cycles")
    parser.add_argument("--n-photon", type=int, default=50000, help="Number of photons")
    parser.add_argument("--n-scat", type=int, default=10000, help="Max scattering events")
    parser.add_argument("--n-step", type=int, default=10000, help="Max steps per photon")
    parser.add_argument("--ph-mode", type=int, default=1, choices=[0, 1],
                        help="Photon mode: 0=coherent, 1=CFR")
    parser.add_argument("--mol-mass", type=float, default=28.0,
                        help="Molecular mass [g/mol]")
    parser.add_argument("--n-fld", type=int, default=1, help="Number of flux components")
    parser.add_argument("--output", default="results.npz", help="Output file path")
    parser.add_argument("--work-dir", default="/tmp/line_rt_cli",
                        help="Working directory")
    args = parser.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)

    src_parts = args.source.split(",")
    src_type = src_parts[0].strip().lower()
    src_floats = [float(x) for x in src_parts[1:]]

    if src_type == "slab":
        x0 = src_floats[0] if len(src_floats) > 0 else -5.0
        luminosity = src_floats[1] if len(src_floats) > 1 else 1.0
        n_ph = int(src_floats[2]) if len(src_floats) > 2 else 50000
        b_sca = src_floats[3] if len(src_floats) > 3 else 1e5
        source = SlabSource(x0=x0, luminosity=luminosity,
                            n_photon=n_ph, b_sca=b_sca)
    elif src_type == "point":
        x, y, z = (src_floats[0], src_floats[1], src_floats[2])
        lumi = src_floats[3] if len(src_floats) > 3 else 0.8
        n_ph = int(src_floats[4]) if len(src_floats) > 4 else 50000
        b_sca = src_floats[5] if len(src_floats) > 5 else 1e5
        source = PointSource(position=(x, y, z), luminosity=lumi,
                             n_photon=n_ph, b_sca=b_sca)
    else:
        print(f"Unknown source type: {src_type}")
        sys.exit(1)

    species = None
    transition = None
    if args.species and args.lamda_file:
        from molecular.lamda_format import load_species_transition, Transition
        if args.transition is not None:
            species, transition = load_species_transition(
                args.lamda_file, freq_GHz=args.transition)
        else:
            from molecular.lamda_format import load_lamda
            with open(args.lamda_file) as f:
                species = load_lamda(f.readlines())

    print(f"Source: {src_type}")
    print(f"Species: {args.species or 'none'}")
    print(f"Cycles: {args.cycles}, Photons: {args.n_photon}")

    if species is not None:
        rt = LineRT(
            source=source,
            x_min=(-5, 0, 0), x_max=(5, 5, 5),
            n_cell=(64, 32, 32),
            species=species,
            n_total=np.full(64 * 32 * 32, 1e4, dtype=np.float64),
            transition=transition,
            temperature=100.0,
            n_photon=args.n_photon,
            n_step=args.n_step, n_scat=args.n_scat,
            ph_mode=args.ph_mode,
            n_cycles=args.cycles, n_fld=args.n_fld,
            mol_mass=args.mol_mass,
            work_dir=args.work_dir,
        )
    else:
        rt = LineRT(
            source=source,
            x_min=(-5, 0, 0), x_max=(5, 5, 5),
            n_cell=(64, 32, 32),
            mfp_i_sca=1e-3,
            n_photon=args.n_photon,
            n_step=args.n_step, n_scat=args.n_scat,
            ph_mode=args.ph_mode,
            n_cycles=args.cycles,
            mol_mass=args.mol_mass,
            work_dir=args.work_dir,
        )

    result = rt.run(n_cycles=args.cycles)
    results = {"source": src_type, "cycles": args.cycles,
               "n_photon": args.n_photon, "ph_mode": args.ph_mode}
    out_path = os.path.join(args.work_dir, args.output)
    np.savez(out_path, **results)
    print(f"\nResults saved to {out_path}")
    print(result)


if __name__ == "__main__":
    main()
