import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from pipeline import run_kratos_cycle, make_cartesian_mesh as _pipeline_make_cartesian_mesh
from kratos_io import write_field_data, write_photon_data, read_output, write_par_file


_KRATOS_EXE = os.path.expanduser("~/apps/kratos_line_rt/bin/kratos")
_PAR_TEMPLATE = os.path.join(
    os.path.dirname(__file__), "..", "pipeline", "line_rt_pipeline.par"
)


def iterate(source_photons, species, fields_init, mesh, n_cycles=5,
            n_photon=None, n_step=10000, n_scat=10000, ph_mode=1,
            par_overrides=None, mol_mass=28.0, work_dir=None,
            callback=None, n_species=None, transition_idx=0,
            n_emission_max=10,
            unit_l0=1.49598e13, unit_t0=1.0):
    if work_dir is None:
        work_dir = os.path.join("/tmp/line_rt", "iterate_output")
    os.makedirs(work_dir, exist_ok=True)
    print(f"[iterate] Run directory: {work_dir}")

    if par_overrides is None:
        par_overrides = {}

    base_overrides = {
        "length": str(float(unit_l0)),
        "time": str(float(unit_t0)),
        "n_cell_global": " ".join(str(int(v)) for v in mesh["n_cell"]),
        "x_min": " ".join(str(v) for v in mesh["x_min"]),
        "x_max": " ".join(
            str(float(mesh["x_min"][i]) + float(mesh["dx"][i]) * int(mesh["n_cell"][i]))
            for i in range(3)
        ),
        "n_step": str(int(n_step)),
        "n_scat": str(int(n_scat)),
        "ph_mode": str(int(ph_mode)),
        "n_fld": "1",
        "n_cycle_lim": "0",
        "t_output_next": "1e32",
        "dt_output": "1e32",
        "final_output": "1",
        "output": "1",
        "mol_mass": str(float(mol_mass)),
    }
    if n_photon is not None:
        base_overrides["n_photon"] = str(int(n_photon))
    base_overrides.update(par_overrides)

    n_tot = mesh["n_tot"]
    results = []

    nx, ny, nz = int(mesh["n_cell"][0]), int(mesh["n_cell"][1]), int(mesh["n_cell"][2])
    shape3d = (nz, ny, nx)

    if species is not None and hasattr(species, "initial_populations"):
        if n_species is None:
            n_species_arr = np.ones(shape3d, dtype=np.float64)
        else:
            n_species_arr = np.broadcast_to(np.asarray(n_species, dtype=np.float64),
                                            shape3d).copy()
        populations = species.initial_populations(n_species_arr)
    else:
        populations = {'n0': np.ones(shape3d, dtype=np.float32),
                       'n_total': np.ones(shape3d, dtype=np.float32)}

    fields = dict(fields_init)
    base_fields_cgs = {k: np.asarray(v, dtype=np.float64).copy()
                       for k, v in fields.items()}

    if species is not None and hasattr(species, "make_fields"):
        fields = species.make_fields(populations, "pre", -1, base_fields=base_fields_cgs,
                                       unit_l0=unit_l0, unit_t0=unit_t0)
        # make_fields may not return mfp_i_abs_0 (absorption is
        # user-provided, not species-derived).  Preserve it from
        # base_fields_cgs, converted to code units.
        if 'mfp_i_abs_0' not in fields and 'mfp_i_abs_0' in base_fields_cgs:
            v_factor = unit_l0
            fields['mfp_i_abs_0'] = np.asarray(base_fields_cgs['mfp_i_abs_0'],
                                                dtype=np.float64) * v_factor

    # Write line-independent fields (b_sca, vel) ONCE - these
    # depend only on the gas (bulk motion, thermal temperature,
    # molecular weight), not on the selected line/band.
    fixed_fields = {k: v for k, v in fields.items()
                    if k in ('b_sca', 'vel_0', 'vel_1', 'vel_2', 'temp')}
    fixed_file = os.path.join(work_dir, "fields_fixed.bin")
    write_field_data(fixed_file, fixed_fields, mesh, unit_l0=unit_l0,
                     group='fixed')
    base_overrides["field_fixed_file"] = "fields_fixed.bin"

    for cycle in range(n_cycles):
        # Line-dependent fields (mfp_i_sca_0, mfp_i_abs_0) are
        # written per cycle (populations evolve).
        line_fields = {k: v for k, v in fields.items()
                       if k in ('mfp_i_sca_0', 'mfp_i_abs_0')}
        field_file = os.path.join(work_dir, f"fields_cycle{cycle}.bin")
        write_field_data(field_file, line_fields, mesh,
                         unit_l0=unit_l0, group='line')

        photon_file = os.path.join(work_dir, f"photons_cycle{cycle}.bin")
        ph_arr = np.asarray(source_photons, dtype=np.float64).copy()
        if ph_arr.shape[1] >= 8:
            v_factor = unit_t0 / unit_l0
            ph_arr[:, 7] *= v_factor
            if ph_arr.shape[1] >= 9:
                ph_arr[:, 8] *= v_factor
        scale_factor = write_photon_data(photon_file, ph_arr)

        prefix = f"cycle{cycle}"
        output, log_text, elapsed = run_kratos_cycle(
            work_dir, cycle, field_file, photon_file,
            prefix, _PAR_TEMPLATE, base_overrides,
        )

        if output is None:
            break

        output["cycle"] = cycle

        if 'mfp_i_sca_0' in fields:
            output['mfp_i_sca_0'] = np.asarray(fields['mfp_i_sca_0'],
                                               dtype=np.float64)

        if 'photons' in output:
            v_factor = unit_t0 / unit_l0
            phot = output['photons']
            for key in ('vel', 'x', 'l'):
                if key in phot:
                    arr = np.asarray(phot[key], dtype=np.float64)
                    if key in ('x', 'l'):
                        arr *= unit_l0
                    else:
                        arr /= v_factor
                    phot[key] = arr

        results.append(output)

        always_process_flux = True
        if always_process_flux:
            exc_flux = output.get("excitation_flux", output.get("exc_flux_flat", output.get("fab_flat", output.get("fab", None))))
            flx = output.get("flx_flat", output.get("flx", None))
            area_factor = unit_l0 * unit_l0 * unit_t0
            inv_scale = 1.0 / scale_factor
            if exc_flux is not None:
                exc_flux = np.asarray(exc_flux, dtype=np.float64)
                exc_flux = np.nan_to_num(exc_flux, nan=0.0, posinf=0.0, neginf=0.0)
                exc_flux = exc_flux * inv_scale / area_factor
                output['exc_flux_flat'] = exc_flux
            if flx is not None:
                flx = np.nan_to_num(np.asarray(flx, dtype=np.float64),
                                    nan=0.0, posinf=0.0, neginf=0.0) * inv_scale / area_factor
                output['flx'] = flx

        if species is not None and hasattr(species, "update_populations"):
            T_field = base_fields_cgs.get('temp', None)
            b_sca_field = base_fields_cgs.get('b_sca', None)
            if b_sca_field is not None and hasattr(b_sca_field, '__len__'):
                b_sca_scalar = float(np.mean(b_sca_field))
            else:
                b_sca_scalar = b_sca_field
            populations = species.update_populations(
                exc_flux, flx, populations, cycle,
                transition_idx=transition_idx,
                T=T_field, b_sca=b_sca_scalar)
            output['populations'] = {k: np.asarray(v, dtype=np.float64).copy()
                                     for k, v in populations.items()}

        if species is not None and hasattr(species, "make_fields"):
            fields = species.make_fields(populations, "post", cycle, base_fields=base_fields_cgs,
                                           transition_idx=transition_idx,
                                           unit_l0=unit_l0, unit_t0=unit_t0)
            if 'mfp_i_abs_0' not in fields and 'mfp_i_abs_0' in base_fields_cgs:
                fields['mfp_i_abs_0'] = np.asarray(base_fields_cgs['mfp_i_abs_0'],
                                                    dtype=np.float64) * unit_l0

        if species is not None and hasattr(species, "generate_emission_photons") and cycle < n_cycles - 1:
            temp_field = fields.get('temp', np.zeros(mesh['n_tot'],
                                                     dtype=np.float64))
            output['emissivity'] = species.compute_emissivity(
                populations, transition_idx, temp_field)
            emission_ph = species.generate_emission_photons(
                populations, transition_idx, temp_field, mesh,
                n_per_cell_max=n_emission_max)
            if len(emission_ph) > 0:
                n_ext_cols = source_photons.shape[1]
                if source_photons.shape[1] < emission_ph.shape[1]:
                    pad = np.zeros((source_photons.shape[0],
                                    emission_ph.shape[1]
                                    - source_photons.shape[1]))
                    source_photons = np.hstack([source_photons, pad])
                elif emission_ph.shape[1] < source_photons.shape[1]:
                    pad = np.zeros((emission_ph.shape[0],
                                    source_photons.shape[1]
                                    - emission_ph.shape[1]))
                    emission_ph = np.hstack([emission_ph, pad])
                source_photons = np.vstack([source_photons, emission_ph])
        else:
            for key in fields:
                if key.startswith("mfp"):
                    exc_flux_norm = np.zeros(n_tot, dtype=np.float32)
                    exc_flux_ptr = output.get("excitation_flux",
                                     output.get("exc_flux_flat",
                                                output.get("fab_flat",
                                                           output.get("fab", None))))
                    if exc_flux_ptr is not None:
                        exc_flux_norm = exc_flux_ptr.astype(np.float32) / (exc_flux_ptr.max() + 1e-35)
                    fields[key] = exc_flux_norm

        if callback is not None:
            callback(cycle, output.get("excitation_flux",
                             output.get("exc_flux_flat",
                                       output.get("fab_flat",
                                                  output.get("fab", None)))), populations)

    return results, populations
