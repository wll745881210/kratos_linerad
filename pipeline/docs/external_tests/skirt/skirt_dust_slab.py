#!/usr/bin/env python3
"""SKIRT escape-fraction harness for the Kratos absorption+scattering slab test.

Replicates the Kratos test_absorption_scattering.py setup in SKIRT 9:
  - Ly-alpha at T = 10 K (a = 0.149), static medium
  - plane-parallel slab of half-thickness L/2 along x, emulated by a wide box
    (transverse extent W = aspect * L; no periodic boundaries in SKIRT)
  - isotropic monochromatic line-center source in the midplane (thin box)
  - neutral H scattering via LyaNeutralHydrogenGasMix
  - frequency-independent pure absorption via
    AbsorptionOnlyMaterialMixDecorator(MeanInterstellarDustMix)

Escape fraction = total escaped luminosity / source luminosity, parsed from
the all-sky SEDInstrument output (radius=0 captures 4 pi).

The dust mix normalization is calibrated empirically: a pure-absorption run
(no hydrogen) is compared against an exact geometric quadrature for the same
finite box, yielding the effective tau_a per unit dust number density.

All run products go to ~/scratch/skirt_tst/fesc/.
"""
import argparse
import os
import subprocess
import sys

import numpy as np

SKIRT = os.path.expanduser(
    '~/scratch/skirt_tst/SKIRT9/build/SKIRT/main/skirt')
WORK = os.path.expanduser('~/scratch/skirt_tst/fesc')

# ----------------------------- physics (SI) --------------------------------
LAM0 = 1.21567e-7          # Lya line center [m]
K_B = 1.380649e-23         # [J/K]
M_P = 1.67262192e-27       # [kg]
C = 2.99792458e8           # [m/s]
L_SUN = 3.828e26           # [W]
DIST = 3.08567758e23       # instrument distance 10 Mpc [m]

T_GAS = 10.0                                   # K  -> a = 0.149
V_TH = np.sqrt(2.0 * K_B * T_GAS / M_P)        # thermal velocity [m/s]
SIGMA0_100K = 5.92e-17                         # line-center cross section [m^2]
SIGMA0 = SIGMA0_100K * np.sqrt(100.0 / T_GAS)  # at 10 K [m^2]
A_VOIGT = 4.72e-3 * np.sqrt(1.0e4 / T_GAS)     # damping parameter

L_BOX = 1.0   # slab full thickness along x [m]


def n_h_for_tau_m(tau_m):
    """Hydrogen number density [m^-3] for mean half-depth tau_m.

    Kratos test convention: tau_m = sqrt(pi) * tau_c, where tau_c is the
    line-center half-depth (tau_c = n_H sigma0 L/2).
    """
    return tau_m / (np.sqrt(np.pi) * SIGMA0 * L_BOX / 2.0)


# ------------------------------ ski template --------------------------------
SKI_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!-- MONTECARLOSIMULATION (c) Astronomical Observatory, Ghent University -->
<skirt-simulation-hierarchy type="MonteCarloSimulation" format="1.0"
    producer="skirt_dust_slab.py" time="2026-08-07">
  <MonteCarloSimulation userLevel="Regular" simulationMode="LyaExtinctionOnly"
      iteratePrimaryEmission="false" iterateSecondaryEmission="false"
      numPackets="{n_phot}">
    <random type="Random"><Random/></random>
    <units type="Units"><SIUnits/></units>
    <cosmology type="Cosmology"><LocalUniverseCosmology/></cosmology>
    <sourceSystem type="SourceSystem">
      <SourceSystem minWavelength="{lam_min} m" maxWavelength="{lam_max} m"
          sourceBias="0.5">
        <sources type="Source">
          <GeometricSource>
            <geometry type="Geometry">
              <UniformBoxGeometry minX="-{sx} m" maxX="{sx} m"
                  minY="-{hw} m" maxY="{hw} m"
                  minZ="-{hw} m" maxZ="{hw} m"/>
            </geometry>
            <sed type="SED">
              <LyaGaussianSED dispersion="1e-6 km/s"/>
            </sed>
            <normalization type="LuminosityNormalization">
              <IntegratedLuminosityNormalization wavelengthRange="Source"
                  integratedLuminosity="1 Lsun"/>
            </normalization>
          </GeometricSource>
        </sources>
      </SourceSystem>
    </sourceSystem>
    <mediumSystem type="MediumSystem">
      <MediumSystem>
        <photonPacketOptions type="PhotonPacketOptions">
          <PhotonPacketOptions/>
        </photonPacketOptions>
        <lyaOptions type="LyaOptions">
          <LyaOptions lyaAccelerationScheme="{accel}" lyaAccelerationStrength="1"
              includeHubbleFlow="false"/>
        </lyaOptions>
        <media type="Medium">
{media}
        </media>
        <grid type="SpatialGrid">
          <CartesianSpatialGrid minX="-{hl} m" maxX="{hl} m"
              minY="-{hw} m" maxY="{hw} m" minZ="-{hw} m" maxZ="{hw} m">
            <meshX type="Mesh"><LinMesh numBins="{nx}"/></meshX>
            <meshY type="Mesh"><LinMesh numBins="{nyz}"/></meshY>
            <meshZ type="Mesh"><LinMesh numBins="{nyz}"/></meshZ>
          </CartesianSpatialGrid>
        </grid>
      </MediumSystem>
    </mediumSystem>
    <instrumentSystem type="InstrumentSystem">
      <InstrumentSystem>
        <defaultWavelengthGrid type="WavelengthGrid">
          <LogWavelengthGrid minWavelength="{lam_min} m"
              maxWavelength="{lam_max} m" numWavelengths="64"/>
        </defaultWavelengthGrid>
        <instruments type="Instrument">
          <SEDInstrument instrumentName="instrument1" radius="0 m"
              distance="{dist} Mpc" inclination="0 deg" azimuth="0 deg"
              roll="0 deg" recordComponents="false" numScatteringLevels="0"
              recordPolarization="false" recordStatistics="false"/>
        </instruments>
      </InstrumentSystem>
    </instrumentSystem>
    <probeSystem type="ProbeSystem"><ProbeSystem/></probeSystem>
  </MonteCarloSimulation>
</skirt-simulation-hierarchy>
"""

MEDIUM_H = """          <GeometricMedium>
            <geometry type="Geometry">
              <UniformBoxGeometry minX="-{hl} m" maxX="{hl} m"
                  minY="-{hw} m" maxY="{hw} m"
                  minZ="-{hw} m" maxZ="{hw} m"/>
            </geometry>
            <materialMix type="MaterialMix">
              <LyaNeutralHydrogenGasMix defaultTemperature="{tgas} K"
                  includePolarization="false"/>
            </materialMix>
            <normalization type="MaterialNormalization">
              <NumberMaterialNormalization number="{n_h}"/>
            </normalization>
          </GeometricMedium>"""

MEDIUM_DUST = """          <GeometricMedium>
            <geometry type="Geometry">
              <UniformBoxGeometry minX="-{hl} m" maxX="{hl} m"
                  minY="-{hw} m" maxY="{hw} m"
                  minZ="-{hw} m" maxZ="{hw} m"/>
            </geometry>
            <materialMix type="MaterialMix">
              <AbsorptionOnlyMaterialMixDecorator>
                <materialMix type="MaterialMix">
                  <MeanInterstellarDustMix/>
                </materialMix>
              </AbsorptionOnlyMaterialMixDecorator>
            </materialMix>
            <normalization type="MaterialNormalization">
              <NumberMaterialNormalization number="{n_dust}"/>
            </normalization>
          </GeometricMedium>"""

# wavelength window covering |x| <~ 3000 at 10 K
LAM_MIN = 1.21562e-7
LAM_MAX = 1.21572e-7


def make_ski(tau_m, n_dust, aspect, n_phot, nx=32, accel="None"):
    """Return ski-file text. tau_m<=0 uses a trace H density (SKIRT requires
    a Ly-alpha material mix to be present); n_dust<=0 omits the dust."""
    hw = 0.5 * aspect * L_BOX          # transverse half-width [m]
    hl = 0.5 * L_BOX                   # slab half-thickness [m]
    sx = 0.5 * L_BOX / 128.0           # midplane source half-thickness [m]
    n_h = n_h_for_tau_m(tau_m) if tau_m > 0 else 1.0e-30
    media = [MEDIUM_H.format(hl=hl, hw=hw, tgas=T_GAS, n_h='%.6e' % n_h)]
    if n_dust > 0:
        media.append(MEDIUM_DUST.format(hl=hl, hw=hw,
                                        n_dust='%.6e' % n_dust))
    if not media:
        raise ValueError('at least one medium required')
    return SKI_TEMPLATE.format(
        n_phot='%g' % n_phot, lam_min='%.6e' % LAM_MIN,
        lam_max='%.6e' % LAM_MAX, sx='%.6e' % sx, hw='%.6e' % hw,
        hl='%.6e' % hl, nx=nx, nyz=int(round(nx * aspect)),
        media='\n'.join(media), dist='%.8e' % (DIST / 3.08567758e22),
        accel=accel)


# ------------------------------ running -------------------------------------
def run_dir(tag):
    d = os.path.join(WORK, tag)
    os.makedirs(d, exist_ok=True)
    return d


def run_skirt(tag, tau_m, n_dust, aspect, n_phot, nx=32, threads=16):
    """Write ski, run SKIRT, return path to the SED file."""
    d = run_dir(tag)
    ski = os.path.join(d, 'fesc.ski')
    with open(ski, 'w') as fp:
        fp.write(make_ski(tau_m, n_dust, aspect, n_phot, nx))
    log = os.path.join(d, 'fesc_log.txt')
    with open(log, 'w') as lf:
        subprocess.run([SKIRT, '-t', str(threads), '-b', '-k', ski],
                       cwd=d, stdout=lf, stderr=subprocess.STDOUT, check=True)
    return os.path.join(d, 'fesc_instrument1_sed.dat')


def parse_fesc(sed_path):
    """Escape fraction = 4 pi d^2 * integral(F_nu d nu) / L_sun."""
    lam, fnu = np.loadtxt(sed_path, unpack=True)
    nu = C / lam
    order = np.argsort(nu)
    lum = 4.0 * np.pi * DIST**2 * np.trapezoid(fnu[order], nu[order])
    return lum / L_SUN


# ------------------- exact pure-absorption reference ------------------------
def fesc_pure_abs_box(tau_a, aspect, n=4_000_000, seed=1234):
    """Exact escape fraction for a pure-absorption finite box.

    Isotropic source uniformly distributed in the midplane
    (x=0, |y|,|z| <= W/2); optical depth tau_a is the half-depth along x.
    Evaluated by (deterministic) Monte Carlo quadrature of the geometric
    integral; no scattering physics involved.
    """
    rng = np.random.default_rng(seed)
    ys = (rng.random(n) - 0.5) * aspect * L_BOX
    zs = (rng.random(n) - 0.5) * aspect * L_BOX
    mu = 2.0 * rng.random(n) - 1.0                     # cos(theta_x)
    phi = 2.0 * np.pi * rng.random(n)
    st = np.sqrt(np.maximum(1.0 - mu**2, 1e-30))
    oy, oz = st * np.cos(phi), st * np.sin(phi)
    eps = 1e-30
    sx_ = (0.5 * L_BOX) / np.maximum(np.abs(mu), eps)
    sy_ = (0.5 * aspect * L_BOX - np.sign(oy) * ys) / np.maximum(np.abs(oy), eps)
    sz_ = (0.5 * aspect * L_BOX - np.sign(oz) * zs) / np.maximum(np.abs(oz), eps)
    s = np.minimum(sx_, np.minimum(sy_, sz_))
    return float(np.mean(np.exp(-tau_a * s / (0.5 * L_BOX))))


def calibrate_dust(n_dust0, aspect, n_phot=20_000):
    """Effective tau_a per unit dust number density, from one pure-dust run."""
    sed = run_skirt('calib_A%g' % aspect, tau_m=-1, n_dust=n_dust0,
                    aspect=aspect, n_phot=n_phot)
    f_meas = parse_fesc(sed)
    # invert the exact quadrature curve by bisection
    lo, hi = 1e-6, 30.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if fesc_pure_abs_box(mid, aspect) > f_meas:
            lo = mid
        else:
            hi = mid
    tau_eff = 0.5 * (lo + hi)
    return tau_eff / n_dust0, f_meas, tau_eff


# --------------------------------- CLI --------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)

    pc = sub.add_parser('calib', help='pure-dust calibration run')
    pc.add_argument('--n-dust0', type=float, default=1.0e13)
    pc.add_argument('--aspect', type=float, default=8.0)
    pc.add_argument('--n-phot', type=float, default=20_000)

    pr = sub.add_parser('run', help='single production run')
    pr.add_argument('--tau-m', type=float, required=True)
    pr.add_argument('--tau-a', type=float, required=True)
    pr.add_argument('--tau-a-per-n', type=float, required=True,
                    help='calibrated tau_a per unit dust number density')
    pr.add_argument('--aspect', type=float, default=8.0)
    pr.add_argument('--n-phot', type=float, default=50_000)

    pq = sub.add_parser('quad', help='exact pure-absorption quadrature only')
    pq.add_argument('--tau-a', type=float, required=True)
    pq.add_argument('--aspect', type=float, default=8.0)

    args = ap.parse_args()

    if args.cmd == 'quad':
        f = fesc_pure_abs_box(args.tau_a, args.aspect)
        print('quadrature f_esc(tau_a=%g, aspect=%g) = %.6f'
              % (args.tau_a, args.aspect, f))
        return

    if args.cmd == 'calib':
        kappa, f_meas, tau_eff = calibrate_dust(args.n_dust0, args.aspect,
                                                int(args.n_phot))
        print('dust-only run: f_esc = %.6f -> effective tau_a = %.6f'
              % (f_meas, tau_eff))
        print('calibration: tau_a per unit dust number density = %.6e'
              % kappa)
        print('(quadrature check E2-like slab value for the same tau_a)')
        return

    # production run
    n_dust = args.tau_a / args.tau_a_per_n
    tag = ('tm%g_ta%g_A%g_N%g'
           % (args.tau_m, args.tau_a, args.aspect, args.n_phot))
    sed = run_skirt(tag, args.tau_m, n_dust, args.aspect, int(args.n_phot))
    f = parse_fesc(sed)
    print('%s: f_esc = %.6f  (n_dust=%.4e)' % (tag, f, n_dust))


if __name__ == '__main__':
    main()
