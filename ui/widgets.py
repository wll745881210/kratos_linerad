"""Shared ipywidgets factory functions for the Line RT Interface."""

import ipywidgets as widgets;


############################################################
# Source widgets

def source_widgets( ):
    return {
        'source_type'    : widgets.Dropdown(
            options      = [ 'Point Source', 'Parallel Beam', 'Custom' ],
            value        = 'Point Source',
            description  = 'Source Type:',
        ),
        'luminosity'     : widgets.FloatText( value = 0.8, \
                                              description = 'Luminosity:' ),
        'wavelength_cm'  : widgets.FloatText( \
                              value = 2.35e-4, \
                              description = 'Wavelength (cm):' ),
        'pos_x'          : widgets.FloatText( value = 0.0, \
                                              description = 'Pos X:' ),
        'pos_y'          : widgets.FloatText( value = 0.0, \
                                              description = 'Pos Y:' ),
        'pos_z'          : widgets.FloatText( value = 0.0, \
                                              description = 'Pos Z:' ),
        'direction_x'    : widgets.FloatText( value = 0.0, \
                                              description = 'Dir X:' ),
        'direction_y'    : widgets.FloatText( value = 0.0, \
                                              description = 'Dir Y:' ),
        'direction_z'    : widgets.FloatText( value = 1.0, \
                                              description = 'Dir Z:' ),
        'area'           : widgets.FloatText( value = 1.0, \
                                              description = 'Area:' ),
        'flux'           : widgets.FloatText( value = 1e6, \
                                              description = 'Flux:' ),
        'n_photon'       : widgets.IntText( value = 50000, \
                                            description = 'N Photon:' ),
        'vel_width'      : widgets.FloatText( value = 1e5, \
                                              description = 'Vel Width:' ),
    }


############################################################
# Species widgets

def species_widgets( ):
    return {
        'species_name'     : widgets.Dropdown(
            options        = [ 'CO', 'OI', 'OH', 'H2O', 'HCN', 'HCO+', 'CS', \
                               'NH3', 'H2CO', 'CH3OH', 'Custom' ],
            value          = 'CO',
            description    = 'Species:',
        ),
        'data_source'      : widgets.Dropdown(
            options        = [ 'Embedded', 'LAMDA download' ],
            value          = 'Embedded',
            description    = 'Data Source:',
        ),
        'transition_label' : widgets.Dropdown(
            options        = [ ],
            value          = None,
            description    = 'Transition:',
            disabled       = True,
            style          = { 'description_width' : 'initial' },
        ),
        'transition_info'  : widgets.HTML(
            value          = '<i>No transition selected</i>',
            layout         = widgets.Layout( margin = '0 0 0 30px' ),
        ),
    }


############################################################
# Fields widgets

def fields_widgets( mesh = None ):
    w = {
        'field_type'   : widgets.Dropdown(
            options    = [ 'Uniform', 'Spherical Power Law', \
                           'Cylindrical Disk' ],
            value      = 'Uniform',
            description = 'Field Type:',
        ),
        'mfp_i_sca_0'  : widgets.FloatText( value = 1e-13, \
                                            description = 'MFP_i sca:' ),
        'mfp_i_abs_0'  : widgets.FloatText( value = 0.0, \
                                            description = 'MFP_i abs:' ),
        'b_sca'        : widgets.FloatText( value = 1e5, \
                                            description = 'B sca:' ),
        'temperature'  : widgets.FloatText( value = 100.0, \
                                            description = 'Temp (K):' ),
        'n_fld'        : widgets.IntText( value = 1, \
                                          description = 'N Fld:' ),
        'mol_mass'     : widgets.FloatText( value = 28.0, \
                                            description = 'Mol Mass:' ),
    };
    if mesh is not None:
        w[ 'mesh' ] = mesh;
    return w;


############################################################
# Iteration widgets

def iter_widgets( ):
    return {
        'n_cycles'   : widgets.IntSlider(
            value    = 3, min = 1, max = 20, step = 1, \
            description = 'N Cycles:',
        ),
        'n_photon'   : widgets.IntText( value = 20000, \
                                        description = 'N Photon:' ),
        'n_scat'     : widgets.IntText( value = 10000, \
                                        description = 'N Scat:' ),
        'n_step'     : widgets.IntText( value = 10000, \
                                        description = 'N Step:' ),
        'ph_mode'    : widgets.Dropdown(
            options  = [ ( '0=CFR', 0 ), ( '1=R_IIA (global)', 1 ), \
                         ( '2=R_IIA (const mem)', 2 ), \
                         ( '3=R_IIA (blend)', 3 ) ],
            value    = 0,
            description = 'Ph Mode:',
            style    = { 'description_width' : 'initial' },
        ),
        'run_button' : widgets.Button( description = 'Run', \
                                       button_style = 'success' ),
        'stop_button': widgets.Button( description = 'Stop', \
                                       button_style = 'danger' ),
    }


############################################################
# Output widgets

def output_widgets( ):
    return {
        'output_area'    : widgets.Output( ),
        'progress'       : widgets.FloatProgress( value = 0, min = 0, \
                                                  max = 100, \
                                                  description = 'Progress:' ),
        'fig_spectrum'   : widgets.Output( ),
        'fig_flux'       : widgets.Output( ),
        'fig_population' : widgets.Output( ),
        'fig_convergence': widgets.Output( ),
    }
