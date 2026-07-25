"""Panel tab layouts that assemble widgets into VBox/HBox/Accordion."""

import ipywidgets as widgets
from .widgets import source_widgets, species_widgets, fields_widgets, iter_widgets, output_widgets


def source_panel():
    w = source_widgets()

    pos_box = widgets.HBox([w["pos_x"], w["pos_y"], w["pos_z"]])
    dir_box = widgets.HBox([w["direction_x"], w["direction_y"], w["direction_z"]])

    pos_acc = widgets.Accordion(children=[pos_box], selected_index=None)
    pos_acc.set_title(0, "Position (x, y, z)")

    dir_acc = widgets.Accordion(children=[dir_box], selected_index=None)
    dir_acc.set_title(0, "Direction (x, y, z)")

    preview_button = widgets.Button(description="Preview", button_style="info")
    preview_output = widgets.Output()

    def on_preview(_):
        preview_output.clear_output()
        with preview_output:
            print("Preview: generate 2D histogram of photon positions (stub)")

    preview_button.on_click(on_preview)

    return widgets.VBox([
        widgets.HTML("<h3>Source Configuration</h3>"),
        w["source_type"],
        w["luminosity"],
        w["wavelength_cm"],
        pos_acc,
        dir_acc,
        w["area"],
        w["flux"],
        w["n_photon"],
        w["vel_width"],
        widgets.HBox([preview_button]),
        preview_output,
    ])


def species_panel():
    w = species_widgets()

    load_button = widgets.Button(description="Load", button_style="info")
    species_info = widgets.HTML(value="<i>No species loaded.</i>")

    def on_load(_):
        species_info.value = f"<b>{w['species_name'].value}</b> — source: {w['data_source'].value} (stub: call molecular.lamda_fetcher)"
        w["transition_label"].disabled = False

    load_button.on_click(on_load)

    return widgets.VBox([
        widgets.HTML("<h3>Species & Transition</h3>"),
        w["species_name"],
        w["data_source"],
        w["transition_label"],
        w["transition_info"],
        widgets.HBox([load_button]),
        species_info,
    ])


def fields_panel(mesh=None):
    w = fields_widgets(mesh)

    preview_button = widgets.Button(description="Preview Slice", button_style="info")
    slice_output = widgets.Output()

    def on_preview_slice(_):
        slice_output.clear_output()
        with slice_output:
            import matplotlib.pyplot as plt
            print("Preview: call core.fields.slice_plot_2d (stub)")
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.set_title("Field Slice Preview")
            ax.text(0.5, 0.5, "Stub", ha="center", va="center", transform=ax.transAxes)
            plt.show()

    preview_button.on_click(on_preview_slice)

    return widgets.VBox([
        widgets.HTML("<h3>Physical Fields</h3>"),
        w["field_type"],
        w["mfp_i_sca"],
        w["mfp_i_abs"],
        w["b_sca"],
        w["b_abs"],
        widgets.HBox([preview_button]),
        slice_output,
    ])


def iter_panel():
    w = iter_widgets()

    output_area = widgets.Output()
    progress_bar = widgets.FloatProgress(value=0, min=0, max=100, description="Progress:")

    def on_run(_):
        output_area.clear_output()
        with output_area:
            print(f"Running {w['n_cycles'].value} cycles with {w['n_photon'].value} photons…")
            print("Stub: call core.iterator.iterate with callback")

    def on_stop(_):
        with output_area:
            print("Stopped by user.")

    w["run_button"].on_click(on_run)
    w["stop_button"].on_click(on_stop)

    return widgets.VBox([
        widgets.HTML("<h3>Iteration Controls</h3>"),
        w["n_cycles"],
        w["n_photon"],
        w["n_scat"],
        w["n_step"],
        w["ph_mode"],
        w["n_thread"],
        widgets.HBox([w["run_button"], w["stop_button"]]),
        progress_bar,
        output_area,
    ])


def output_panel():
    w = output_widgets()

    tab = widgets.Tab()
    tab.children = [
        widgets.VBox([widgets.HTML("<h4>Spectrum</h4>"), w["fig_spectrum"]]),
        widgets.VBox([widgets.HTML("<h4>Flux Maps</h4>"), w["fig_flux"]]),
        widgets.VBox([widgets.HTML("<h4>Population Maps</h4>"), w["fig_population"]]),
        widgets.VBox([widgets.HTML("<h4>Convergence</h4>"), w["fig_convergence"]]),
    ]
    tab.set_title(0, "Spectrum")
    tab.set_title(1, "Flux Maps")
    tab.set_title(2, "Population Maps")
    tab.set_title(3, "Convergence")

    return widgets.VBox([
        widgets.HTML("<h3>Output</h3>"),
        w["progress"],
        w["output_area"],
        tab,
    ])
