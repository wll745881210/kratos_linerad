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
            callback=None, n_gas=None, transition_idx=0,
            n_emission_max=10):
    if work_dir is None:
        work_dir = os.path.join(os.getcwd(), "iterate_output")
    os.makedirs(work_dir, exist_ok=True)

    if par_overrides is None:
        par_overrides = {}

    base_overrides = {
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
        "output": "1",
        "mol_mass": str(float(mol_mass)),
    }
    if n_photon is not None:
        base_overrides["n_photon"] = str(int(n_photon))
    base_overrides.update(par_overrides)

    n_tot = mesh["n_tot"]
    results = []

    if hasattr(species, "initial_populations"):
        populations = species.initial_populations(n_tot, n_gas=n_gas)
    else:
        populations = {f"n{i}": np.ones(n_tot, dtype=np.float32) for i in range(species.n_levels)}

    fields = dict(fields_init)

    if hasattr(species, "make_fields"):
        fields = species.make_fields(populations, "pre", -1, base_fields=fields)

    for cycle in range(n_cycles):
        field_file = os.path.join(work_dir, f"fields_cycle{cycle}.bin")
        write_field_data(field_file, fields, mesh)

        photon_file = os.path.join(work_dir, f"photons_cycle{cycle}.bin")
        write_photon_data(photon_file, source_photons)

        prefix = f"cycle{cycle}"
        output, log_text, elapsed = run_kratos_cycle(
            work_dir, cycle, field_file, photon_file,
            prefix, _PAR_TEMPLATE, base_overrides,
        )

        if output is None:
            break

        output["cycle"] = cycle
        results.append(output)

        if hasattr(species, "update_populations"):
            fab = output.get("excitation_flux", output.get("fab_flat", output.get("fab", None)))
            flx = output.get("flx_flat", output.get("flx", None))
            populations = species.update_populations(fab, flx, populations, cycle)

        if hasattr(species, "make_fields"):
            fields = species.make_fields(populations, "post", cycle, base_fields=fields,
                                          transition_idx=transition_idx)

        if hasattr(species, "generate_emission_photons") and cycle < n_cycles - 1:
            temp_field = fields.get('temp', np.zeros(mesh['n_tot'],
                                                     dtype=np.float64))
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
                    fab_norm = np.zeros(n_tot, dtype=np.float32)
                    fab_ptr = output.get("fab_flat", output.get("fab", None))
                    if fab_ptr is not None:
                        fab_norm = fab_ptr.astype(np.float32) / (fab_ptr.max() + 1e-35)
                    fields[key] = fab_norm

        if callback is not None:
            callback(cycle, output.get("fab", None), populations)

    return results, populations
