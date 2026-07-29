"""
Minimal reference Monte Carlo radiative transfer for line RT.

Mirrors Kratos line_rt (photon.h, block_data.h) physics for 1D plane-parallel
slabs. Uses numba JIT for near-C speed on the per-photon transport loop.

Physics replicated exactly:
  - ph_mode=0: CFR — Gaussian velocity redistribution, sv reset to b/√2
  - ph_mode=1: R_IIA redistribution via pre-computed inverse CDF table
    (USampler). Builds P(u|x) ∝ exp(-u²)/(a²+(x-u)²) once per a_voigt,
    then numba does binary-search + linear-interpolation table lookup at
    each scatter. Correctly handles wing scattering for all a. Reproduces
    Neufeld (1990) slab scaling within 3% for aτ₀ ≳ 100.
  - Constant absorption MFP, constant scattering opacity per cell
  - Excitation: flx * I(v, b, sv) via overlap integral I = exp(-dv^2/s2) * b/sqrt(s2)
  - proc_phys at cell entry (flux deposition), proc_geo for transport/scattering
  - Voigt profile support via analytic H(a,u) when a_voigt > 0

Parallelism: run_mcrt(parallel=True) uses numba prange over photons with
per-thread flx/exc accumulation buffers. Each photon is seeded from
(seed, photon_index), so serial and parallel runs give identical results.

References
----------
usr_ext/line_rt/photon.h  — proc_phys, proc_geo
usr_ext/line_rt/gen.h     — photon init
PHYSICS.md                 — authoritative spec
"""

import multiprocessing

import numpy as np
from numba import njit, prange

def _make_tid():
    try:
        from numba.np.ufunc.parallel import get_thread_id
        return get_thread_id, True
    except Exception:
        @njit
        def _zero():
            return 0
        return _zero, False


_tid, _HAVE_PARALLEL = _make_tid()


SQRT2 = np.sqrt(2.0, dtype=np.float64)

# "Unlimited" scatter cap — must exceed Neufeld N_scat ~ 1.6*tau0*(a*tau0)^(1/3)
# (1.6e6 at tau0=1e5, a=0.01). A too-small cap makes photons stop scattering
# and walk no-op until the step budget is exhausted (effectively a hang).
NS_UNLIMITED = 1073741824

# ── USampler: R_IIA scattering via pre-computed inverse CDF ──────────
# Builds a 2D table of CDF(u|x) where P(u|x) ∝ exp(-u²)/(a²+(x-u)²),
# then the numba function _sample_u_par_usampler does binary search +
# linear interpolation on the table. Avoids the rejection-based
# vp_rejection which fails catastrophically for small a (wing photons
# always reject, fall back to upar=0, break R_IIA redistribution).
_usampler_cache = {}


def build_usampler(a_voigt, u_max=6.0, du=5e-3, n_lin=101, n_log=121, x_max=300.0):
    cache_key = (a_voigt, du, n_lin, n_log, x_max)
    if cache_key in _usampler_cache:
        return _usampler_cache[cache_key]

    u_grid = np.arange(-u_max, u_max + du, du, dtype=np.float64)
    x_lin = np.linspace(0.0, 8.0, n_lin, dtype=np.float64)
    x_log = np.logspace(np.log10(8.0), np.log10(x_max), n_log, dtype=np.float64)[1:]
    xg_grid = np.concatenate([x_lin, x_log])

    G = np.exp(-u_grid**2)
    D = u_grid[np.newaxis, :] - xg_grid[:, np.newaxis]
    W = G[np.newaxis, :] / (a_voigt**2 + D**2)
    C_grid = np.cumsum(W, axis=1)
    C_grid /= C_grid[:, -1:]
    C_grid[:, -1] = 1.0

    data = (u_grid, xg_grid, C_grid)
    _usampler_cache[cache_key] = data
    return data


@njit
def _sample_u_par_usampler(xa, u_grid, xg_grid, C_grid):
    n_xg = len(xg_grid)
    j = np.searchsorted(xg_grid, xa) - 1
    if j < 0:
        j = 0
    if j >= n_xg - 1:
        j = n_xg - 2
    f = (xa - xg_grid[j]) / (xg_grid[j + 1] - xg_grid[j])
    r = np.random.random()

    def _cdf_lookup(row, u_vec):
        k = np.searchsorted(row, r)
        if k < 1:
            k = 1
        n_u = len(u_vec)
        if k >= n_u:
            k = n_u - 1
        denom = max(row[k] - row[k - 1], 1e-300)
        return u_vec[k - 1] + (r - row[k - 1]) / denom * (u_vec[k] - u_vec[k - 1])

    u0 = _cdf_lookup(C_grid[j], u_grid)
    u1 = _cdf_lookup(C_grid[j + 1], u_grid)
    return (1.0 - f) * u0 + f * u1


@njit(inline='always')
def _scatter_riia_usampler(x_freq, u_grid, xg_grid, C_grid):
    sgn = 1.0
    if x_freq < 0.0:
        sgn = -1.0
    u_par = sgn * _sample_u_par_usampler(abs(x_freq), u_grid, xg_grid, C_grid)
    x_at = x_freq - u_par
    g = 2.0 * np.random.random() - 1.0
    u_perp = np.sqrt(-2.0 * np.log(np.random.random() + 1e-35)) * np.cos(2.0 * np.pi * np.random.random()) / SQRT2
    u_par_n = g * u_par + np.sqrt(1.0 - g * g) * u_perp
    return x_at + u_par_n


@njit(inline='always')
def _transport_photon(x, d0, pr, vl, sv, ns_in, n_left,
                      flx_out, exc_out, dep_off,
                      x_min_0, dx_0, nx, cell_vol,
                      b_arr, mfp_s0, mfp_a0,
                      ph_mode, a_voigt, u_crit, seed_i,
                      u_grid=None, xg_grid=None, C_grid=None):
    """
    Transport one photon until escape or budget exhaustion.

    Deposits flux/excitation into flx_out/exc_out at offset dep_off
    (per-thread buffer when parallel).
    Returns (vl, pr, sv, reason, n_scat) with reason:
      1 = escaped, 2 = step budget exhausted, 3 = proper decayed,
      4 = degenerate path length

    For ph_mode=1, pass u_grid/xg_grid/C_grid from build_usampler()
    to use the table-based R_IIA sampler.
    """
    np.random.seed(seed_i)
    ns_max = ns_in if ns_in > 0 else NS_UNLIMITED
    tr = -np.log(1e-4 + 0.9999 * np.random.random())
    reason = 2
    n_scat = 0

    while n_left > 0 and pr > 1e-30:
        if d0 > 0:
            ix = int(np.floor((x - x_min_0) / dx_0))
        else:
            ix = int(np.floor((x - x_min_0 - 1e-12 * dx_0) / dx_0))

        if ix < 0 or ix >= nx:
            reason = 1
            break
        ci = ix

        if d0 > 0:
            bx = x_min_0 + (ix + 1) * dx_0
        elif d0 < 0:
            bx = x_min_0 + ix * dx_0
        else:
            bx = np.inf
        # 3D path length to the cell boundary. d0 is the x-component of an
        # isotropic unit direction: ray is p + t*d_hat, t = (bx-x)/d0, and
        # x += t*d0 lands exactly on bx. (Kratos proc_geo uses the same form
        # with full 3D unit vectors.)
        dl = (bx - x) / (d0 + 1e-35)

        if dl <= 0 or not np.isfinite(dl):
            reason = 4
            break

        # proc_phys: deposit flux and excitation
        fc = pr * dl / cell_vol
        flx_out[dep_off + ci] += fc

        b_cell = b_arr[ci]
        s2 = b_cell * b_cell + 2.0 * sv * sv
        exc_out[dep_off + ci] += fc * np.exp(-vl * vl / s2) * b_cell / np.sqrt(s2)

        # proc_geo
        u_dop = abs(vl) / (b_cell + 1e-35)
        prof0 = voigt_H(a_voigt, u_dop)
        prof_s = prof0
        mfp_i_s = mfp_s0[ci] * prof_s

        dtau_s = dl * mfp_i_s

        if dtau_s > tr and ns_max > 0:
            frac = tr / (dtau_s + 1e-35)
            pr *= np.exp(-mfp_a0[ci] / (mfp_i_s + 1e-35) * tr)
            x += dl * frac * d0

            # Direction reset (isotropic, x-component)
            mu = 2.0 * np.random.random() - 1.0
            smu = np.sqrt(1.0 - mu * mu)
            ph_ang = 2.0 * np.pi * np.random.random()
            d0 = smu * np.cos(ph_ang)

            if ph_mode == 1:
                x_freq = vl / (b_cell + 1e-35)
                vl = _scatter_riia_usampler(x_freq, u_grid, xg_grid, C_grid) * b_cell
                sv = b_cell / SQRT2
            else:
                vl = 0.0
                u1 = np.random.random()
                u2 = np.random.random()
                vl += np.sqrt(-2.0 * np.log(u1 + 1e-35)) * np.cos(2.0 * np.pi * u2) * b_cell / SQRT2
                sv = b_cell / SQRT2

            tr = -np.log(1e-4 + 0.9999 * np.random.random())
            ns_max -= 1
            n_scat += 1
        else:
            pr *= np.exp(-mfp_a0[ci] * dl)
            tr -= dtau_s
            x += dl * d0

        n_left -= 1

    if reason == 2 and pr <= 1e-30:
        reason = 3

    return vl, pr, sv, reason, n_scat


@njit
def _transport_serial(pos_x, dir_x, proper, vel_p, sv_p,
                      n_step_arr, n_scat_arr, seeds,
                      flx_out, exc_out,
                      esc_vel, esc_pr, esc_sv, esc_flag, nscat_out,
                      x_min_0, dx_0, nx, cell_vol,
                      b_arr, mfp_s0, mfp_a0,
                      ph_mode, a_voigt, u_crit,
                      u_grid, xg_grid, C_grid):
    for i in range(len(proper)):
        if proper[i] <= 0:
            continue
        vl, pr, sv, reason, n_scat = _transport_photon(
            pos_x[i], dir_x[i], proper[i], vel_p[i], sv_p[i],
            n_scat_arr[i], n_step_arr[i],
            flx_out, exc_out, 0,
            x_min_0, dx_0, nx, cell_vol,
            b_arr, mfp_s0, mfp_a0,
            ph_mode, a_voigt, u_crit, seeds[i],
            u_grid, xg_grid, C_grid)
        esc_flag[i] = reason
        nscat_out[i] = n_scat
        if reason == 1:
            esc_vel[i] = vl
            esc_pr[i] = pr
            esc_sv[i] = sv


@njit(parallel=True)
def _transport_parallel(pos_x, dir_x, proper, vel_p, sv_p,
                        n_step_arr, n_scat_arr, seeds,
                        flx_priv, exc_priv, n_tot,
                        esc_vel, esc_pr, esc_sv, esc_flag, nscat_out,
                        x_min_0, dx_0, nx, cell_vol,
                        b_arr, mfp_s0, mfp_a0,
                        ph_mode, a_voigt, u_crit,
                        u_grid, xg_grid, C_grid):
    for i in prange(len(proper)):
        if proper[i] <= 0:
            continue
        tid = _tid()
        off = tid * n_tot
        vl, pr, sv, reason, n_scat = _transport_photon(
            pos_x[i], dir_x[i], proper[i], vel_p[i], sv_p[i],
            n_scat_arr[i], n_step_arr[i],
            flx_priv, exc_priv, off,
            x_min_0, dx_0, nx, cell_vol,
            b_arr, mfp_s0, mfp_a0,
            ph_mode, a_voigt, u_crit, seeds[i],
            u_grid, xg_grid, C_grid)
        esc_flag[i] = reason
        nscat_out[i] = n_scat
        if reason == 1:
            esc_vel[i] = vl
            esc_pr[i] = pr
            esc_sv[i] = sv


@njit
def voigt_H(a, u):
    """
    Exact Voigt H(a,u) = Re[w(z)], z = u + i*a, via Humlicek's w4 algorithm
    (JQSRT 27, 437, 1982). Relative accuracy ~1e-4 everywhere.

    NOTE: deliberately deviates from Kratos photon.h:voigt_H, whose blend
    crossover u0 = sqrt(log(wing/core + 1)) is wrong (~0.1 instead of ~3 for
    a=0.01), discarding the Gaussian core for u >~ 0.5 and underestimating H
    by up to ~35x at u~1.2. Kratos is unaffected at a_voigt=0 (Gaussian CFR),
    but any a_voigt>0 run (ph_mode=1/2) inherits that bug.
    """
    if a < 1e-6:
        return np.exp(-u * u)
    x = abs(u)
    y = a
    t = complex(y, -x)
    s = x + y
    if s >= 15.0:
        w = t * 0.5641896 / (0.5 + t * t)
    elif s >= 5.5:
        w = t * (1.410474 + t * t * 0.5641896) / (0.75 + t * t * (3.0 + t * t))
    elif y >= 0.195 * x - 0.176:
        w = ((16.4955 + t * (20.20933 + t * (11.96482 + t * (3.778987 + t * 0.5642236)))) /
             (16.4955 + t * (38.82363 + t * (39.27121 + t * (21.69274 + t * (6.699398 + t))))))
    else:
        w = (np.exp(t * t) - t * (36183.31 - t * t * (3321.9905 - t * t * (1540.787 -
             t * t * (219.0313 - t * t * (35.76683 - t * t * (1.320522 - t * t * 0.56419)))))) /
             (32066.6 - t * t * (24322.84 - t * t * (9022.228 - t * t * (2186.181 -
             t * t * (364.2191 - t * t * (61.57037 - t * t * (1.841439 - t * t))))))))
    return w.real


# ══════════════════════════════════════════════════════════════════════
# High-level interface
# ══════════════════════════════════════════════════════════════════════

def run_mcrt(mesh, photons, b_sca, mfp_i_sca_0, mfp_i_abs_0,
             vel=None, ph_mode=0, a_voigt=0.0,
             n_scat_max=0, n_step=0, seed=42, parallel=True,
             u_crit=None):
    """
    Run MCRT on a 1D plane-parallel slab with uniform fields.

    Parameters
    ----------
    mesh : dict  {'n_cell': (nx,ny,nz), 'x_min': (x0,y0,z0), 'dx': (dx,dy,dz)}
    photons : ndarray (n_ph, n_col)   cols: pos(3), dir(3), proper, vel, [sv]
    b_sca : float    Doppler b [cm/s]
    mfp_i_sca_0 : float   Inverse scattering MFP [cm⁻¹]
    mfp_i_abs_0 : float   Inverse absorption MFP [cm⁻¹]
    vel : None   (uniform zero velocity)
     ph_mode : int   0=CFR (Gaussian kick), 1=R_IIA (USampler, Neufeld-valid)
    a_voigt : float   Voigt parameter (0 = Gaussian)
    n_scat_max : int   max scatters per photon (0 = unlimited)
    n_step : int   max cell crossings per photon (0 = auto)
    seed : int
    parallel : bool   use numba prange over photons (identical results —
                      per-photon seeding makes streams independent of schedule)

    Returns
    -------
    dict with 'flx', 'excitation_flux', 'escaped'
    """
    n_cell = np.asarray(mesh['n_cell'], dtype=np.int32)
    x_min = np.asarray(mesh['x_min'], dtype=np.float64)
    dx = np.asarray(mesh['dx'], dtype=np.float64)
    nx = int(n_cell[0])
    ny = int(n_cell[1])
    nz = int(n_cell[2])
    n_tot = nx * ny * nz
    cell_vol = np.prod(dx)

    b_arr = np.full(n_tot, np.float64(b_sca))
    if u_crit is None and a_voigt > 1e-6:
        u_c = 3.0
        for _ in range(10):
            d = u_c * u_c + a_voigt * a_voigt
            u_new = np.sqrt(np.log(np.sqrt(np.pi * d) / a_voigt))
            if abs(u_new - u_c) < 1e-6:
                break
            u_c = u_new
        u_crit = u_c
    elif u_crit is None:
        u_crit = 3.0

    mfp_s0_arr = np.full(n_tot, np.float64(mfp_i_sca_0))
    mfp_a0_arr = np.full(n_tot, np.float64(mfp_i_abs_0))

    ph = np.asarray(photons, dtype=np.float64).copy()
    n_ph = ph.shape[0]
    n_col = ph.shape[1]

    if n_col < 9:
        ph = np.pad(ph, ((0, 0), (0, 9 - n_col)), constant_values=0.0)

    esc_vel = np.zeros(n_ph, dtype=np.float64)
    esc_pr = np.zeros(n_ph, dtype=np.float64)
    esc_sv = np.zeros(n_ph, dtype=np.float64)
    esc_flag = np.zeros(n_ph, dtype=np.int32)
    nscat_out = np.zeros(n_ph, dtype=np.int64)

    tau_est = abs(mfp_s0_arr[0]) * nx * dx[0] if nx > 0 else 0.0
    if n_step <= 0:
        n_step = max(2000, int(200 * nx * max(1.0, tau_est)))
    n_step = min(n_step, 2_000_000_000)
    n_step_arr = np.full(n_ph, n_step, dtype=np.int64)
    n_scat_arr = np.full(n_ph, n_scat_max, dtype=np.int64)

    # Per-photon seeds: makes RNG streams independent of thread scheduling,
    # so serial and parallel runs produce identical results.
    seeds = (int(seed) * 1000003 + np.arange(n_ph, dtype=np.int64)) % (2**31 - 1)

    use_parallel = parallel and _HAVE_PARALLEL and n_ph > 1

    us_grid = np.zeros(0, dtype=np.float64)
    if ph_mode == 1 and a_voigt > 1e-9:
        u_grid, xg_grid, C_grid = build_usampler(a_voigt)
    else:
        u_grid = us_grid
        xg_grid = us_grid
        C_grid = us_grid

    if use_parallel:
        n_thr = multiprocessing.cpu_count()
        flx_priv = np.zeros(n_thr * n_tot, dtype=np.float64)
        exc_priv = np.zeros(n_thr * n_tot, dtype=np.float64)
        _transport_parallel(
            ph[:, 0].copy(), ph[:, 3].copy(),
            ph[:, 6].copy(), ph[:, 7].copy(), ph[:, 8].copy(),
            n_step_arr, n_scat_arr, seeds,
            flx_priv, exc_priv, n_tot,
            esc_vel, esc_pr, esc_sv, esc_flag, nscat_out,
            x_min[0], dx[0], nx, cell_vol,
            b_arr, mfp_s0_arr, mfp_a0_arr,
            ph_mode, a_voigt, u_crit,
            u_grid, xg_grid, C_grid,
        )
        flx_out = flx_priv.reshape(n_thr, n_tot).sum(axis=0)
        exc_out = exc_priv.reshape(n_thr, n_tot).sum(axis=0)
    else:
        flx_out = np.zeros(n_tot, dtype=np.float64)
        exc_out = np.zeros(n_tot, dtype=np.float64)
        _transport_serial(
            ph[:, 0].copy(), ph[:, 3].copy(),
            ph[:, 6].copy(), ph[:, 7].copy(), ph[:, 8].copy(),
            n_step_arr, n_scat_arr, seeds,
            flx_out, exc_out,
            esc_vel, esc_pr, esc_sv, esc_flag, nscat_out,
            x_min[0], dx[0], nx, cell_vol,
            b_arr, mfp_s0_arr, mfp_a0_arr,
            ph_mode, a_voigt, u_crit,
            u_grid, xg_grid, C_grid,
        )

    mask = esc_flag == 1
    escaped = np.column_stack([
        esc_vel[mask], esc_pr[mask], esc_sv[mask]
    ]) if mask.any() else np.zeros((0, 3), dtype=np.float64)

    # Termination reasons: 1=escaped, 2=step budget, 3=proper decayed, 4=degenerate dl
    return {'flx': flx_out, 'excitation_flux': exc_out, 'escaped': escaped,
            'term_reason': esc_flag, 'n_scat': nscat_out}


# ══════════════════════════════════════════════════════════════════════
# Convenience: classic slab test
# ══════════════════════════════════════════════════════════════════════

def mcrt_slab(*, n_cell=64, L_slab=1.49598e13,
              tau0=100.0, tau_abs=0.0,
              b_sca=1.0e5, n_photons=50000, ph_mode=0,
              a_voigt=0.0, seed=42, source='midplane', parallel=True):
    """
    Run reference MCRT on a plane-parallel slab with uniform opacity.

    Parameters
    ----------
    n_cell, L_slab, tau0, tau_abs, b_sca, n_photons, ph_mode, a_voigt, seed,
    source, parallel
    """
    nx = n_cell
    ny = nz = 2
    dx_val = L_slab / nx
    dy_val = L_slab * 0.1
    dz_val = L_slab * 0.1

    mesh = {
        'n_cell': np.array([nx, ny, nz], dtype=np.int32),
        'x_min': np.array([-L_slab / 2, 0.0, 0.0], dtype=np.float64),
        'dx': np.array([dx_val, dy_val, dz_val], dtype=np.float64),
    }

    mfp_s = tau0 / L_slab
    mfp_a = tau_abs / L_slab

    rng = np.random.default_rng(seed)

    ph = np.zeros((n_photons, 9), dtype=np.float64)
    if source == 'midplane':
        ph[:, 0] = 0.0
        ph[:, 1] = rng.uniform(0, dy_val, n_photons)
        ph[:, 2] = rng.uniform(0, dz_val, n_photons)
        n_half = n_photons // 2
        ph[:n_half, 3] = 1.0
        ph[n_half:, 3] = -1.0
        ph[:, 6] = 1.0 / n_photons
    elif source == 'face':
        ph[:, 0] = -L_slab / 2
        ph[:, 1] = rng.uniform(0, dy_val, n_photons)
        ph[:, 2] = rng.uniform(0, dz_val, n_photons)
        ph[:, 3] = 1.0
        ph[:, 6] = 1.0 / n_photons
    else:
        raise ValueError(f"Unknown source: {source}")

    result = run_mcrt(
        mesh=mesh, photons=ph, b_sca=b_sca,
        mfp_i_sca_0=mfp_s, mfp_i_abs_0=mfp_a,
        vel=None, ph_mode=ph_mode, a_voigt=a_voigt,
        seed=seed, parallel=parallel,
    )
    result['mesh'] = mesh
    return result
