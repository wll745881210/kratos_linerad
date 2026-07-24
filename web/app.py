"""Panel dashboard for Line RT Interface."""

try:
    import panel as pn
except ImportError:
    import sys
    print(
        "ERROR: Panel is not installed. Install with:\n"
        "    pip install panel\n"
        "    or\n"
        "    pip install line_rt_interface[web]",
        file=sys.stderr,
    )
    sys.exit(1)

pn.extension()

from ui.panels import source_panel, species_panel, fields_panel, iter_panel, output_panel


def get_default_mesh():
    return None


template = pn.template.BootstrapTemplate(title="Line RT Interface")

template.sidebar.append(source_panel())
template.sidebar.append(species_panel())
template.main.append(fields_panel(get_default_mesh()))
template.main.append(iter_panel())
template.main.append(output_panel())

template.servable()
