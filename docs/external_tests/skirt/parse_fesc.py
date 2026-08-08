#!/usr/bin/env python3
"""Parse the direction-averaged escape fraction from a run_fesc.sh run.

Usage: python3 parse_fesc.py <run-dir>
Prints: f_esc=<mean>  scatter=<std>  n_dirs=<n>
"""
import glob
import os
import sys

import numpy as np

C = 2.99792458e8
L_SUN = 3.828e26
DIST = 3.08567758e23        # 10 Mpc in m


def sed_lum(path):
    lam, fnu = np.loadtxt(path, unpack=True)
    nu = C / lam
    order = np.argsort(nu)
    return 4.0 * np.pi * DIST**2 * np.trapezoid(fnu[order], nu[order])


def main():
    d = sys.argv[1]
    vals = []
    for f in sorted(glob.glob(os.path.join(d, 'fesc_dir*_sed.dat'))):
        vals.append(sed_lum(f) / L_SUN)
    if not vals:
        sys.exit('no SED files found in %s' % d)
    vals = np.array(vals)
    # convergence check: sub-means over the first 6 and 12 directions
    sub = ''
    for n in (6, 12):
        if len(vals) > n:
            sub += '  mean%d=%.6f' % (n, vals[:n].mean())
    print('f_esc=%.6f  scatter=%.6f  n_dirs=%d%s'
          % (vals.mean(), vals.std(), len(vals), sub))


if __name__ == '__main__':
    main()
