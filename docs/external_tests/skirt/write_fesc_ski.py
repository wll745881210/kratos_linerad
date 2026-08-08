#!/usr/bin/env python3
"""Generate SKIRT f_esc ski configs for the dusty-slab benchmark.

Each ski has N_DIR distant SEDInstruments whose directions uniformly
sample the unit sphere (Fibonacci lattice); the escape fraction is the
mean of the per-instrument isotropic-equivalent luminosities. See
run_fesc.sh for the run/parse logic.

Usage:
  python3 write_fesc_ski.py <tau_m> <tau_a> <aspect> <n_phot> <out.ski>
  python3 write_fesc_ski.py calib <n_dust> <aspect> <n_phot> <out.ski>

Geometry/physics (SI units, apple-to-apple with the Kratos test):
  slab half-thickness L/2 along x (L = 1 m), transverse extent
  W = aspect * L; isotropic monochromatic line-center midplane source;
  LyaNeutralHydrogenGasMix at T = 3 K (a = 0.0272, b = 222.7 m/s;
  3 K is the minimum temperature SKIRT accepts for the Ly-alpha
  material mix, so a = 0.149 is not reachable; both codes are
  therefore run at a = 0.0272);
  frequency-independent pure absorption via
  AbsorptionOnlyMaterialMixDecorator(MeanInterstellarDustMix).
  tau_m is the MEAN half-depth (Kratos test convention,
  tau_m = sqrt(pi) * n_H sigma0 L/2).
"""
import sys

# ----------------------------- physics (SI) --------------------------------
LAM0 = 1.21567e-7          # Lya line center [m]
K_B = 1.380649e-23         # [J/K]
M_P = 1.67262192e-27       # [kg]
T_GAS = 3.0                # K -> a = 0.0272, b = 222.7 m/s (SKIRT minimum T)
V_TH = (2.0 * K_B * T_GAS / M_P) ** 0.5          # 222.7 m/s
SIGMA0_100K = 5.92e-17                          # line-center cross section [m^2]
SIGMA0 = SIGMA0_100K * (100.0 / T_GAS) ** 0.5   # at 3 K
A_VOIGT = 4.72e-3 * (100.0 / T_GAS) ** 0.5      # damping parameter = 0.0272

L_BOX = 1.0                # slab full thickness along x [m]
N_DIR = 48                 # distant instruments (Fibonacci lattice on sphere)

# wavelength window: |x| <~ 270 at 3 K (12000 bins -> dx ~ 0.045)
LAM_MIN = 1.2154256e-7
LAM_MAX = 1.2159144e-7


def n_h_for_tau_m(tau_m):
    """H number density [m^-3] for MEAN half-depth tau_m."""
    return tau_m / ((3.141592653589793 ** 0.5) * SIGMA0 * L_BOX / 2.0)


def instruments_xml():
    """N_DIR SEDInstruments on a Fibonacci lattice (inertialess frame)."""
    out = []
    golden = 3.141592653589793 * (3.0 - 5.0 ** 0.5)
    for k in range(N_DIR):
        inc = __import__('math').degrees(
            __import__('math').acos(1.0 - 2.0 * (k + 0.5) / N_DIR))
        azi = __import__('math').degrees(golden * k) % 360.0
        out.append(
            '          <SEDInstrument instrumentName="dir%d" radius="0 m"\n'
            '              distance="10 Mpc" inclination="%.4f deg"\n'
            '              azimuth="%.4f deg" roll="0 deg"\n'
            '              recordComponents="false" numScatteringLevels="0"\n'
            '              recordPolarization="false" recordStatistics="false"/>'
            % (k, inc, azi))
    return '\n'.join(out)


def make_ski(tau_m, n_dust, aspect, n_phot, nx=32):
    """tau_m<=0 uses a trace H density (SKIRT requires a Ly-alpha mix);
    n_dust<=0 omits the dust medium."""
    hw = 0.5 * aspect * L_BOX          # transverse half-width [m]
    hl = 0.5 * L_BOX                   # slab half-thickness [m]
    sx = 0.5 * L_BOX / 128.0           # midplane source half-thickness [m]
    n_h = n_h_for_tau_m(tau_m) if tau_m > 0 else 1.0e-30
    nyz = int(round(nx * aspect))
    media = []
    media.append(
        '          <GeometricMedium>\n'
        '            <geometry type="Geometry">\n'
        '              <UniformBoxGeometry minX="-%g m" maxX="%g m"\n'
        '                  minY="-%g m" maxY="%g m"\n'
        '                  minZ="-%g m" maxZ="%g m"/>\n'
        '            </geometry>\n'
        '            <materialMix type="MaterialMix">\n'
        '              <LyaNeutralHydrogenGasMix defaultTemperature="%g K"\n'
        '                  includePolarization="false"/>\n'
        '            </materialMix>\n'
        '            <normalization type="MaterialNormalization">\n'
        '              <NumberMaterialNormalization number="%.6e"/>\n'
        '            </normalization>\n'
        '          </GeometricMedium>' % (hl, hl, hw, hw, hw, hw, T_GAS, n_h))
    if n_dust > 0:
        media.append(
            '          <GeometricMedium>\n'
            '            <geometry type="Geometry">\n'
            '              <UniformBoxGeometry minX="-%g m" maxX="%g m"\n'
            '                  minY="-%g m" maxY="%g m"\n'
            '                  minZ="-%g m" maxZ="%g m"/>\n'
            '            </geometry>\n'
            '            <materialMix type="MaterialMix">\n'
            '              <AbsorptionOnlyMaterialMixDecorator>\n'
            '                <materialMix type="MaterialMix">\n'
            '                  <MeanInterstellarDustMix/>\n'
            '                </materialMix>\n'
            '              </AbsorptionOnlyMaterialMixDecorator>\n'
            '            </materialMix>\n'
            '            <normalization type="MaterialNormalization">\n'
            '              <NumberMaterialNormalization number="%.6e"/>\n'
            '            </normalization>\n'
            '          </GeometricMedium>' % (hl, hl, hw, hw, hw, hw, n_dust))
    return SKI_TEMPLATE.format(
        n_phot='%g' % n_phot, lam_min='%.7e' % LAM_MIN,
        lam_max='%.7e' % LAM_MAX, sx='%.6e' % sx, hw='%.6e' % hw,
        hl='%.6e' % hl, nx=nx, nyz=nyz, media='\n'.join(media),
        instruments=instruments_xml())


SKI_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!-- MONTECARLOSIMULATION (c) Astronomical Observatory, Ghent University -->
<skirt-simulation-hierarchy type="MonteCarloSimulation" format="1.0"
    producer="write_fesc_ski.py" time="2026-08-08">
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
          <LyaOptions lyaAccelerationScheme="None" lyaAccelerationStrength="1"
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
          <LinWavelengthGrid minWavelength="{lam_min} m"
              maxWavelength="{lam_max} m" numWavelengths="12000"/>
        </defaultWavelengthGrid>
        <instruments type="Instrument">
{instruments}
        </instruments>
      </InstrumentSystem>
    </instrumentSystem>
    <probeSystem type="ProbeSystem"><ProbeSystem/></probeSystem>
  </MonteCarloSimulation>
</skirt-simulation-hierarchy>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == 'calib':
        _, _, n_dust, aspect, n_phot, out = sys.argv
        ski = make_ski(-1.0, float(n_dust), float(aspect), float(n_phot))
    else:
        _, tau_m, tau_a, aspect, n_phot, out = sys.argv
        tau_m = float(tau_m)
        tau_a = float(tau_a)
        # dust number density from the A=8 empirical calibration
        # (kappa = 8.289740e-17 tau_a per unit dust density); the exact
        # calibration factor cancels in the code-to-code comparison as
        # long as both codes see the same box, so no per-aspect
        # recalibration is applied here.
        kappa = 8.289740e-17
        n_dust = tau_a / kappa if tau_a > 0 else 0.0
        ski = make_ski(tau_m, n_dust, float(aspect), float(n_phot))
    with open(out, 'w') as fp:
        fp.write(ski)
    print('wrote %s' % out)


if __name__ == '__main__':
    main()
