"""High-level interface for line radiative transfer simulations.

Provides a single-entry-point abstraction over the low-level iterate()
pipeline. Users configure geometry, species, sources, and RT parameters
via __init__ and add_source(), then call run() to execute.

Usage:
    from molecular.transition_info import TransitionInfo
    ti = TransitionInfo( "CO", 0 )
    rt = LineRt( transition_info = ti, \
                 n_species = 1e4, temperature = 100.0 )
    rt.add_source( n_photon = 50000, luminosity = 0.8 * Lsun )
    results = rt.run()
"""

import os
from numpy import asarray, zeros, full, arange, meshgrid, sqrt, maximum, \
                  mean, abs, arccos, sin, cos, pi, exp, vstack, array, \
                  ones_like, random, ndarray, float64, linspace, \
                  concatenate, cumsum, interp;

from .source import make_cartesian_mesh
from .consistency import check_consistency
from .pipeline import DEFAULT_RUN_ROOT

h_cgs = 6.62607015e-27;    # Planck constant [ erg s ]
c_cgs = 2.99792458e10;     # speed of light [ cm / s ]


############################################################
# LineRt class

class LineRt:
    """High-level orchestrator for a line radiative-transfer simulation.

    All __init__ parameters are optional — LineRt() creates a valid
    (empty) object. Use add_source() to add photon sources, then call
    run() to execute.

    Parameters
    ----------
    n_cell : tuple[int, int, int]
        Number of cells in (x, y, z).
    x_min, x_max : tuple[float, float, float]
        Domain bounds in code units (for unit_l0=1.5e13 cm, these are AU).
    unit_l0 : float
        Length unit in CGS (cm per code-length).
    unit_t0 : float
        Time unit in CGS (s per code-time).
    transition_info : TransitionInfo or None
        Species + transition + molecular mass bundle (see
        molecular.transition_info). Pass it to use the species-based
        (Group 1) configuration; LineRt then resolves the transition
        index, molecular mass, and auto-wavelength from it.
    n_species : float | callable | None
        Number density of the scatterer [cm⁻³]. If callable, receives an
        ``(n_tot, 3)`` array of CGS cell-centre coordinates and returns an
        ndarray of length ``n_tot``.
    temperature : float | callable | None
        Gas temperature [K]. Required when species is given. If callable,
        receives ``(n_tot, 3)`` CGS coords and returns ``(n_tot,)`` array.
    b_sca : float | callable | None
        Doppler b-parameter [cm/s]. Only for Group 2 (no species).
        In Group 1 (species + temperature), b_sca is derived from T
        and mol_mass; passing it here raises a ConsistencyError.
    mfp_i_sca_0 : float | callable | None
        Inverse scattering mean free path [cm⁻¹]. Required if no species.
        If callable, receives ``(n_tot, 3)`` CGS coords.
    mfp_i_abs_0 : float | callable | None
        Inverse absorption mean free path [cm⁻¹] (default 0).
        If callable, receives ``(n_tot, 3)`` CGS coords.
    vel : tuple | None
        Bulk velocity (vx, vy, vz) [cm/s]. Each component: float | callable.
        Callables receive ``(n_tot, 3)`` CGS coords.
    a_voigt : float or None
        Voigt damping parameter a. If None (default), uses pure Gaussian
        profile.
    ph_mode : int
        0=CFR (Gaussian), 1/2/3=R_IIA (USampler). See AGENTS.md for details.
    n_step, n_scat : int
        Max path segments and scattering events per photon packet.
    n_fld : int
        Number of flux/field components (default 1).
    n_cycles : int
        Number of MC -> population -> MC cycles.
    path : str or None
        Working directory. Default: per-run subdir under /dev/shm/line_rt/
        (falls back to /tmp/line_rt/ if /dev/shm is unavailable).
    visualize : bool
        If True, automatically plot results after run().
    n_emission_max : int
        Max internal emission photons per cell per cycle.
    colliders : dict or None
        Collider densities for collisional excitation, keyed by partner
        name (e.g. ``{'H2': {'density': 1e4}}``). Each density may be a
        float or a callable receiving ``(n_tot, 3)`` CGS coords. Used to
        thermalise the initial (LTE) populations and in the per-cycle
        statistical-equilibrium update. Requires a species with
        collision-partner data.
    snapshot : callable or None
        Called after each cycle: fn(results=output, cycle=cycle,
                                    populations=pops).
    proper_scale : float
        Rescaling factor applied to every photon's ``proper`` weight
        before writing the photon binary (default 1.0 = no rescale).
        Kratos MCRT is linear in photon weights, so a constant factor
        scales all output fields (flx, excitation_flux) by the same
        amount.  Use a small value (< 1) when the physical flux is so
        large that the FP32 output fields would overflow (>= 3.4e38),
        e.g. proper_scale=1e-30 for YSO-scale fluxes.  The read-back
        flux is automatically divided by this factor.
    kratos_root : str or None
        Path to the Kratos build tree root (containing ``bin/kratos``).
        If None, falls back to the ``KRATOS_ROOT`` env var.  One of the
        two MUST be set (no default).
    keep_intermediate : bool
        If True (default), all per-cycle binary files and the run
        directory are kept on disk.  If False, each cycle's files are
        deleted as soon as its data is read back into RAM, and the whole
        auto-created run directory is removed at the end of run() (only
        when ``path`` was not set explicitly), freeing /dev/shm tmpfs.
    retain_cycles : int or None
        If set, only the last ``retain_cycles`` cycle dicts are kept in
        ``out['results']`` (older ones are dropped) to bound RAM usage.
        None (default) keeps every cycle.
    """

    def __init__( self, *, n_cell = ( 64, 2, 2 ), \
                  x_min = ( -5., 0., 0. ), x_max = ( 5., 0.2, 0.2 ), \
                  unit_l0 = 1.49598e13, unit_t0 = 1.0, \
                  transition_info = None, \
                  n_species = None, temperature = None, \
                  b_sca = None, mfp_i_sca_0 = None, \
                  mfp_i_abs_0 = 0.0, vel = None, \
                  a_voigt = None, ph_mode = 0, n_step = 10000, \
                  n_scat = 10000, n_fld = 1, n_cycles = 1, \
                  path = None, visualize = True, n_emission_max = 10, \
                  colliders = None, snapshot = None, \
                  proper_scale = 1.0, keep_intermediate = True, \
                  retain_cycles = None, kratos_root = None, \
                  imaging = None ):
        """
        imaging : dict or None
            Camera configuration for line imaging.  When set, the
            final cycle runs an extra non-scattering ray-tracing
            pass that produces a per-channel image cube.  Keys:
            'dir_cam'   : (theta, phi) [rad] or 3-vector (direction
                          into the domain).
            'n_chan'    : number of velocity channels (default 32).
            'v_chan'    : (v_min, v_max) [cm/s, CGS] channel range.
            'img_xmin'  : (x0, y0) image-plane corner [code units].
            'img_xmax'  : (x1, y1) image-plane corner [code units].
            'img_resol' : (nx, ny) pixel resolution.
            The image cube is returned in out['image'].
        """
        self._n_cell         = tuple( n_cell );
        self._x_min          = tuple( x_min );
        self._x_max          = tuple( x_max );
        self._unit_l0        = unit_l0;
        self._unit_t0        = unit_t0;
        self._transition_info = transition_info;
        self._species_obj    = None;
        self._transition_idx = 0;
        self._n_species      = n_species;
        self._temperature    = temperature;
        self._b_sca          = b_sca;
        self._mfp_i_sca_0    = mfp_i_sca_0;
        self._mfp_i_abs_0    = mfp_i_abs_0;
        self._vel            = vel;
        self._mol_mass       = None;
        self._colliders      = colliders;
        self._a_voigt        = a_voigt;
        self._ph_mode        = ph_mode;
        self._n_step         = n_step;
        self._n_scat         = n_scat;
        self._n_fld          = n_fld;
        self._n_cycles       = n_cycles;
        self._path           = path;
        self._visualize      = visualize;
        self._n_emission_max = n_emission_max;
        self._snapshot       = snapshot;
        self._proper_scale   = proper_scale;
        self._keep_intermediate = keep_intermediate;
        self._retain_cycles  = retain_cycles;
        self._kratos_root    = kratos_root;
        self._imaging        = imaging;
        self._sources        = [ ];
        self._boundary_kinds = 'fre fre fre fre fre fre';
        self._results        = None;

    ########################################################
    # Boundary configuration

    def set_boundary( self, kinds ):
        """Set boundary conditions for all 6 faces.

        Parameters
        ----------
        kinds : str
            6 space-separated boundary kinds: -x +x -y +y -z +z.
            Each is "fre" (free/escape) or "per" (periodic).
            Example: "fre fre per per per per" for free x-faces,
            periodic y,z (plane-parallel slab).
        """
        kr = kinds.lower( ).split( );
        if len( kr ) != 6:
            raise ValueError( \
                "Need 6 boundary kinds (got %d): " \
                "-x +x -y +y -z +z" % len( kr ) );
        for k in kr:
            if k not in ( 'fre', 'per' ):
                raise ValueError( \
                    "Boundary kind must be 'fre' or 'per', got '%s'" % k );
        self._boundary_kinds = ' '.join( kr );
        return self;

    ########################################################
    # Source registration

    def add_source( self, *, type = 'slab', n_photon = 50000, \
                    luminosity = None, flux = None, \
                    units = None, x = None, \
                    direction = '+x', y_range = None, \
                    z_range = None, position = None, r_random = 0.0, \
                    vel_offset = 0.0, sigma = 0.0, \
                    vel_range = None, vel_pdf = 'uniform', \
                    vel_sigma = None ):
        """Add an external photon source.

        Parameters
        ----------
        type : str
            "slab" — plane source at a given x-coordinate. Must provide
            **flux** [photons cm⁻² s⁻¹] (or erg cm⁻² s⁻¹ with
            units='energy').
            "point" — point source at (x, y, z). Must provide **luminosity**
            [photons/s] (or erg/s with units='energy').
        n_photon : int
            Number of photon packets.
        luminosity : float or None
            Luminosity (point source only). Photon number [photons/s]
            by default, or erg/s with ``units='energy'``.
        flux : float or None
            Flux (slab source only). Photon number [photons cm⁻² s⁻¹]
            by default, or erg cm⁻² s⁻¹ with ``units='energy'``.
            For a slab source: proper = flux × source_area / n_photon.
        units : str or None
            "photon" (default, when None) — flux/luminosity are photon
            number. "energy" — flux/luminosity are erg-based; the
            transition wavelength (from transition_info) is used to
            convert erg to photons via E_ph = hc/λ.
        x : float or None (slab)
            x-coordinate of the source plane.
        direction : str (slab)
            "+x" or "-x" photon direction.
        y_range : tuple or None (slab)
            (y_min, y_max) for uniform distribution. None → full domain.
        z_range : tuple or None (slab)
            (z_min, z_max) for uniform distribution. None → full domain.
        position : tuple or None (point)
            (x, y, z) of point source.
        r_random : float (point)
            Radius [cm] of the sphere around ``position`` within which
            each photon's initial position is drawn uniformly (volume-
            weighted).  0.0 (default) → all photons start exactly at
            ``position``.
        vel_offset : float
            Velocity offset of emitted photons [cm/s].
        sigma : float
            Initial photon intrinsic Doppler width [cm/s] (sv).
            0 → monochromatic at line centre.
        vel_range : tuple or None
            (v_lo, v_hi) [cm/s] — per-photon initial velocity shifts
            drawn from ``vel_pdf`` over this interval and ADDED to
            ``vel_offset``. None (default) → no randomization, all
            photons get exactly ``vel_offset``.
        vel_pdf : str or callable
            Distribution of the per-photon velocity shift:
              "uniform" (default) — uniform over [v_lo, v_hi].
              "gaussian" — Gaussian centred on the interval midpoint
                  (v_lo+v_hi)/2, width ``vel_sigma``, truncated to
                  [v_lo, v_hi].
              callable f(v) — arbitrary (possibly unnormalized)
                  probability density; integrated numerically to a CDF,
                  normalized, and sampled by inverse transform.
        vel_sigma : float or None
            Gaussian width [cm/s]; required when ``vel_pdf='gaussian'``.

        Raises
        ------
        ValueError
            If ``flux`` is given for a point source, ``luminosity`` is
            given for a slab source, the type-required quantity is
            missing, or ``units='energy'`` is used without a transition.
        """
        if units is not None and units not in ( 'photon', 'energy' ):
            raise ValueError( \
                "units must be 'photon' or 'energy', got '%s'" % units );

        if type == 'slab':
            if luminosity is not None:
                raise ValueError( \
                    "luminosity is for point sources only; "
                    "use flux for a slab source" );
            if flux is None:
                raise ValueError( \
                    "slab source requires flux (photons cm⁻² s⁻¹, "
                    "or erg cm⁻² s⁻¹ with units='energy')" );
        elif type == 'point':
            if flux is not None:
                raise ValueError( \
                    "flux is for slab sources only; "
                    "use luminosity for a point source" );
            if luminosity is None:
                raise ValueError( \
                    "point source requires luminosity (photons/s, "
                    "or erg/s with units='energy')" );
        else:
            raise ValueError( \
                "source type must be 'slab' or 'point', got '%s'" % type );

        if r_random is None:
            r_random = 0.0;
        r_random = float( r_random );
        if r_random < 0.0:
            raise ValueError( \
                "r_random must be >= 0, got %g" % r_random );
        if type == 'slab' and r_random > 0.0:
            raise ValueError( \
                "r_random is for point sources only; "
                "slab sources emit from the plane x=%.6g" % x );

        wavelength = None;
        if units == 'energy':
            if self._transition_info is None:
                raise ValueError( \
                    "units='energy' requires a transition_info "
                    "(wavelength comes from the transition) to convert "
                    "erg to photons" );
            wavelength = c_cgs / \
                         ( self._transition_info.transition.freq_GHz * 1e9 );

        if vel_range is not None:
            v_lo, v_hi = float( vel_range[ 0 ] ), float( vel_range[ 1 ] );
            if v_hi < v_lo:
                raise ValueError( \
                    "vel_range must satisfy v_lo <= v_hi, "
                    "got (%s, %s)" % ( v_lo, v_hi ) );
            if not ( vel_pdf == 'uniform' or vel_pdf == 'gaussian' \
                     or callable( vel_pdf ) ):
                raise ValueError( \
                    "vel_pdf must be 'uniform', 'gaussian', or a "
                    "callable, got %r" % ( vel_pdf, ) );
            if vel_pdf == 'gaussian':
                if vel_sigma is None or float( vel_sigma ) <= 0:
                    raise ValueError( \
                        "vel_pdf='gaussian' requires vel_sigma > 0 "
                        "[cm/s]" );

        src = { 'type'      : type, \
                'n_photon'  : n_photon, \
                'luminosity': luminosity, \
                'flux'      : flux, \
                'wavelength': wavelength, \
                'units'     : units or 'photon', \
                'x'         : x, \
                'direction' : direction, \
                'y_range'   : y_range, \
                'z_range'   : z_range, \
                'position'  : position, \
                'r_random'  : r_random, \
                'vel_offset': vel_offset, \
                'sigma'     : sigma, \
                'vel_range' : vel_range, \
                'vel_pdf'   : vel_pdf, \
                'vel_sigma' : vel_sigma, };
        self._sources.append( src );
        return self;

    def clear_sources( self ):
        self._sources.clear(  );
        return self;
    #

    def show_sources( self ):
        """Print a summary of all registered photon sources."""
        if not self._sources:
            print( "No sources registered." );
            return self;
        print( "=== Sources (%d) ===" % len( self._sources ) );
        for i, src in enumerate( self._sources ):
            s_type = src.get( 'type', '?' );
            n_ph = src.get( 'n_photon', '?' );
            units = src.get( 'units', 'photon' );
            flux = src.get( 'flux', None );
            lum = src.get( 'luminosity', None );
            wl = src.get( 'wavelength', None );

            if s_type == 'slab':
                qty = "flux = %s %s" % ( flux, \
                      'erg cm⁻² s⁻¹' if units == 'energy' \
                      else 'photons cm⁻² s⁻¹' );
                x_pos = src.get( 'x' ) if src.get( 'x' ) is not None \
                        else 'mesh min';
                geo = "x=%s, dir=%s, y=%s, z=%s" % \
                      ( x_pos, src.get( 'direction', '+x' ), \
                        src.get( 'y_range' ) or 'full', \
                        src.get( 'z_range' ) or 'full' );
            else:
                qty = "luminosity = %s %s" % ( lum, \
                      'erg/s' if units == 'energy' else 'photons/s' );
                r_rand = src.get( 'r_random', 0.0 );
                geo = "pos=%s" % ( src.get( 'position' ) \
                                   or ( 0, 0, 0 ), );
                if r_rand:
                    geo += ", r_random=%.4e cm" % r_rand;
            if units == 'energy' and wl is not None:
                wl_str = ", λ=%.4e cm" % wl;
            else:
                wl_str = "";
            print( "  [%d] %s, %s packets, %s%s" % \
                   ( i, s_type, n_ph, qty, wl_str ) );
            vel_info = "vel_offset=%.3e cm/s, sigma=%.3e cm/s" % \
                       ( src.get( 'vel_offset', 0.0 ), \
                         src.get( 'sigma', 0.0 ) );
            vr = src.get( 'vel_range', None );
            if vr is not None:
                pdf = src.get( 'vel_pdf', 'uniform' );
                vs = src.get( 'vel_sigma', None );
                vel_info += ", vel_range=(%.3e, %.3e) cm/s, vel_pdf=%s%s" % \
                            ( vr[ 0 ], vr[ 1 ], pdf, \
                              ( ", vel_sigma=%.3e" % vs ) \
                              if pdf == 'gaussian' else "" );
            print( "      %s, %s" % ( geo, vel_info ) );
        return self;

    def plot_input( self, fields = None, slice_plane = 'z', \
                    slice_idx = None, ax = None, figsize = None, \
                    output_path = None, dyn_range = False ):
        """Plot slices of the configured input fields (no Kratos run).

        Resolves the user-supplied field definitions — n_species,
        temperature (Group 1), mfp_i_sca_0, b_sca, mfp_i_abs_0, and
        velocity components — at cell centres in CGS and renders them
        with default_plot. Use this to verify the geometry / field
        inputs before running.

        Default field set (2-column grid):
          Group 1 (species set): n_species, temperature, mfp_i_sca_0,
              b_sca, mfp_i_abs_0, vel_0, vel_1, vel_2.
          Group 2: mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0, vel_1, vel_2
              (vel only when ``vel`` is configured).
        Fields not configured appear as '(no data)' panels.

        Parameters mirror default_plot():
            fields : list[str] or None
            slice_plane : str  "x"|"y"|"z"
            slice_idx : int or None
            ax : array of Axes or None
            figsize : tuple or None
            output_path : str or None
            dyn_range : bool

        Returns
        -------
        (fig, axes) as returned by default_plot.
        """
        self._resolve_species( );
        mesh = self._build_mesh( );
        XYZ = self._cell_centers_cgs( mesh );

        data = self._plot_input_data( mesh, XYZ );

        if fields is None:
            fields = self._input_default_fields( );

        from .visualize import default_plot
        return default_plot( data, fields = fields, \
                             slice_plane = slice_plane, \
                             slice_idx = slice_idx, ax = ax, \
                             figsize = figsize, \
                             output_path = output_path, \
                             dyn_range = dyn_range );

    def _plot_input_data( self, mesh = None, XYZ = None ):
        """Resolve configured input fields to CGS 3D arrays.

        Returns a pseudo-results dict (mesh, unit_l0, unit_t0, plus
        resolved field arrays) suitable for default_plot.  Only fields
        that are actually configured are included.
        """
        if mesh is None:
            mesh = self._build_mesh( );
        if XYZ is None:
            XYZ = self._cell_centers_cgs( mesh );
        self._resolve_species( );

        data = { 'mesh' : mesh, \
                 'unit_l0' : self._unit_l0, \
                 'unit_t0' : self._unit_t0 };

        if self._species_obj is not None:
            if self._n_species is not None:
                data[ 'n_species' ] = self._resolve_field( \
                    self._n_species, XYZ );
            if self._temperature is not None:
                data[ 'temperature' ] = self._resolve_field( \
                    self._temperature, XYZ );

        b_sca_val = self._resolve_b_sca( XYZ );
        data[ 'b_sca' ] = b_sca_val;

        if self._species_obj is not None:
            n_species_val = ( self._resolve_field( self._n_species, XYZ ) \
                              if self._n_species is not None else None );
            if n_species_val is not None:
                mfp_sca_0, _ = self._resolve_mfp_species( \
                    self._species_obj, mesh[ 'n_tot' ], b_sca_val, \
                    n_species_val );
                data[ 'mfp_i_sca_0' ] = mfp_sca_0;
        elif self._mfp_i_sca_0 is not None:
            data[ 'mfp_i_sca_0' ] = self._resolve_field( \
                self._mfp_i_sca_0, XYZ );

        data[ 'mfp_i_abs_0' ] = self._resolve_field( \
            self._mfp_i_abs_0, XYZ );

        if self._vel is not None:
            vel_vals = self._resolve_vel( XYZ );
            for i, k in enumerate( ( 'vel_0', 'vel_1', 'vel_2' ) ):
                data[ k ] = vel_vals[ i ];

        return data;

    def _input_default_fields( self ):
        """Default field list for plot_input based on configured inputs."""
        fields = [ ];
        if self._species_obj is not None:
            fields += [ 'n_species', 'temperature' ];
        fields += [ 'mfp_i_sca_0', 'b_sca', 'mfp_i_abs_0' ];
        if self._vel is not None:
            fields += [ 'vel_0', 'vel_1', 'vel_2' ];
        return fields;

    def plot_results( self, out = None, fields = None, slice_plane = 'z', \
                      slice_idx = None, ax = None, figsize = None, \
                      output_path = None, dyn_range = False ):
        """Plot run() results via default_plot.

        Parameters
        ----------
        out : dict, optional  the dict returned by LineRt.run().  When
            omitted, plots the cached results of the most recent run().
        All other parameters mirror default_plot().

        Returns
        -------
        (fig, axes) as returned by default_plot.

        Notes
        -----
        ``run()`` caches its return value in ``self._results``, so
        ``out`` may be omitted to plot the most recent run.  Raises
        ``ValueError`` if neither ``out`` nor a cached result exists.
        """
        from .visualize import default_plot
        data = out if out is not None else self._results;
        if data is None:
            raise ValueError( \
                "plot_results(): no results to plot — call run() " \
                "first or pass out=" );
        return default_plot( data, \
                             fields = fields, \
                             slice_plane = slice_plane, \
                             slice_idx = slice_idx, ax = ax, \
                             figsize = figsize, \
                             output_path = output_path, \
                             dyn_range = dyn_range, \
                             transition_info = self._transition_info );

    def plot_channel_maps( self, out = None, channels = None, \
                           n_cols = 6, dyn_range = True, ax = None, \
                           figsize = None, output_path = None, \
                           cmap = 'magma' ):
        """Plot a grid of single-channel spatial maps from the
        imaging cube.  All panels share a logarithmic colour
        scale with dynamic range clipped to <= 6 dex.

        Parameters
        ----------
        out : dict, optional  the dict returned by LineRt.run().
            When omitted, uses the cached results of the most
            recent run().
        channels : list[int] or None  channel indices to plot.
            If None, selects ``n_cols`` channels centred on the
            spectral peak.
        n_cols : int  number of columns (and channels when
            ``channels`` is None).
        dyn_range : bool  apply 6-dex log clipping (default True).
        cmap : str  colormap (default 'magma').
        """
        from .visualize import plot_channel_maps
        data = out if out is not None else self._results;
        if data is None:
            raise ValueError( \
                "plot_channel_maps(): no results to plot - call " \
                "run() first or pass out=" );
        return plot_channel_maps( data, \
                                  channels = channels, \
                                  n_cols = n_cols, \
                                  dyn_range = dyn_range, \
                                  ax = ax, \
                                  figsize = figsize, \
                                  output_path = output_path, \
                                  cmap = cmap, \
                                  transition_info = \
                                      self._transition_info );

    ########################################################
    # Run

    def run( self, n_cycles = None, **overrides ):
        """Run the RT simulation and return results.

        Returns
        -------
        dict with keys:
            'results'       — list[dict] (one per cycle)
            'populations'   — final population dict
            'mesh'          — mesh dict
            'exc_flux_flat' — final CGS excitation flux (1D)
            'flx'           — final CGS flux (1D)
            'spectrum'      — {"vel": ..., "n": proper-weighted escaped
                               photon counts (surviving photons/s per
                               packet, CGS)}
            'sources'       — list[dict] (source configs used)
        """
        self._resolve_species( );
        self._check( );

        if n_cycles is not None:
            self._n_cycles = n_cycles;
        #

        mesh = self._build_mesh( );
        species = self._species_obj;
        n_tot = mesh[ 'n_tot' ];
        XYZ = self._cell_centers_cgs( mesh );

        if species is not None and self._n_species is not None:
            n_species_val = self._resolve_field( self._n_species, XYZ );
        else:
            n_species_val = None;

        b_sca_val = self._resolve_b_sca( XYZ );
        self._b_sca_resolved = b_sca_val;
        mfp_abs_val = self._resolve_field( self._mfp_i_abs_0, XYZ );
        vel_vals = self._resolve_vel( XYZ );

        fields = { 'b_sca'       : b_sca_val, \
                   'temp'        : self._resolve_field( self._temperature, \
                                                        XYZ ), \
                   'vel_0'       : vel_vals[ 0 ], \
                   'vel_1'       : vel_vals[ 1 ], \
                   'vel_2'       : vel_vals[ 2 ], \
                   'mfp_i_abs_0' : mfp_abs_val, };

        if species is not None:
            mfp_sca_0, mfp_abs_0_in = self._resolve_mfp_species( \
                species, n_tot, b_sca_val, n_species_val );
            if mfp_abs_0_in is not None:
                fields[ 'mfp_i_abs_0' ] = mfp_abs_0_in;
            fields[ 'mfp_i_sca_0' ] = mfp_sca_0;
        elif self._mfp_i_sca_0 is not None:
            fields[ 'mfp_i_sca_0' ] = self._resolve_field( \
                self._mfp_i_sca_0, XYZ );

        v_factor = self._unit_t0 / self._unit_l0;
        if species is None:
            for key in list( fields ):
                if key.startswith( 'mfp_i_' ):
                    fields[ key ] = asarray( fields[ key ], \
                                             dtype = float64 ) * self._unit_l0;
                elif key in ( 'b_sca', ) or key.startswith( 'vel_' ):
                    fields[ key ] = asarray( fields[ key ], \
                                             dtype = float64 ) * v_factor;

        photons = self._generate_photons( n_tot, mesh, b_sca_val );

        # Resolve collider densities (float or callable) to per-cell
        # arrays before handing them to the iterator.
        colliders_val = None;
        if self._colliders:
            colliders_val = { };
            for pname, pcfg in self._colliders.items( ):
                colliders_val[ pname ] = { 'density' : \
                    self._resolve_field( pcfg[ 'density' ], XYZ ) };

        work_dir = self._resolve_path( );

        from .iterator import iterate
        a_voigt_val = self._resolve_a_voigt( b_sca_val );
        par_overrides = { 'kinds'   : self._boundary_kinds, \
                          'a_voigt' : str( float( a_voigt_val ) ), \
                          'n_fld'   : str( int( self._n_fld ) ) };
        results, final_pops = iterate( \
            photons, species, fields, mesh, \
            n_cycles = self._n_cycles, n_step = self._n_step, \
            n_scat = self._n_scat, ph_mode = self._ph_mode, \
            work_dir = work_dir, n_species = n_species_val, \
            transition_idx = self._transition_idx, \
            mol_mass = self._mol_mass or 28.0, \
            unit_l0 = self._unit_l0, unit_t0 = self._unit_t0, \
            n_emission_max = self._n_emission_max, \
            colliders = colliders_val, \
            proper_scale = self._proper_scale, \
            keep_intermediate = self._keep_intermediate, \
            retain_cycles = self._retain_cycles, \
            callback = self._snapshot, par_overrides = par_overrides, \
            kratos_root = self._kratos_root, \
            imaging = self._imaging );

        spectrum = { 'vel' : array( [ ] ), 'n' : array( [ ] ) };
        if results and results[ -1 ].get( 'photons' ):
            phot = results[ -1 ][ 'photons' ];
            if 'vel' in phot:
                weights = asarray( phot.get( 'proper', \
                                 ones_like( phot[ 'vel' ] ) ) );
                spectrum = { 'vel' : asarray( phot[ 'vel' ] ), \
                             'n'   : weights };  # proper-weighted

        out = { 'results'      : results, \
                'populations'  : final_pops, \
                'mesh'         : mesh, \
                'run_dir'      : work_dir, \
                'unit_l0'      : self._unit_l0, \
                'unit_t0'      : self._unit_t0, \
                'b_sca'        : getattr( self, '_b_sca_resolved', None ), \
                'exc_flux_flat': ( results[ -1 ].get( 'exc_flux_flat', None ) \
                                   if results else None ), \
                'flx'          : ( results[ -1 ].get( 'flx', None ) \
                                   if results else None ), \
                'spectrum'     : spectrum, \
                'sources'      : list( self._sources ), };
        if results and 'image' in results[ -1 ]:
            out[ 'image' ] = results[ -1 ][ 'image' ];

        if self._visualize:
            self._plot_results( out );
        self._results = out;

        if not self._keep_intermediate and self._path is None:
            # Memory-saving mode: remove the auto-created run directory
            # (per-cycle files were already deleted as we went; the final
            # cycle's outputs have been read into RAM).  Only auto-created
            # dirs are removed - an explicit `path` is left untouched.
            import shutil
            if os.path.isdir( work_dir ):
                shutil.rmtree( work_dir, ignore_errors = True );
                print( '[LineRt] Removed run directory: %s' % work_dir );

        return out;

    ########################################################
    # Helpers

    def _cell_centers_cgs( self, mesh ):
        """Return (n_tot, 3) array of cell-centre positions in CGS [cm].

        Ordering matches the Kratos field-binary convention: 1D arrays
        are laid out as (nz, ny, nx) in C-order (z slowest, x fastest),
        consistent with ``write_field_data``'s ``reshape(nz, ny, nx)``.
        """
        n_cell = asarray( mesh[ 'n_cell' ] );
        x_min = asarray( mesh[ 'x_min' ], dtype = float64 );
        dx = asarray( mesh[ 'dx' ], dtype = float64 );
        nx, ny, nz = int( n_cell[ 0 ] ), int( n_cell[ 1 ] ), \
                     int( n_cell[ 2 ] );
        # Cell centres in CGS [cm]
        cx = ( x_min[ 0 ] + ( arange( nx ) + 0.5 ) * dx[ 0 ] ) * self._unit_l0;
        cy = ( x_min[ 1 ] + ( arange( ny ) + 0.5 ) * dx[ 1 ] ) * self._unit_l0;
        cz = ( x_min[ 2 ] + ( arange( nz ) + 0.5 ) * dx[ 2 ] ) * self._unit_l0;
        # (nz, ny, nx) C-order: z slowest, x fastest
        Z, Y, X = meshgrid( cz, cy, cx, indexing = 'ij' );
        return X, Y, Z;

    def _resolve_species( self ):
        if self._transition_info is None:
            return;
        self._species_obj = self._transition_info.species_data;
        self._transition_idx = self._transition_info.transition_idx;
        if self._mol_mass is None:
            self._mol_mass = self._transition_info.mol_mass;

    def _check( self ):
        check_consistency( \
            species = self._species_obj, \
            transition_idx = self._transition_idx, \
            n_species = self._n_species, \
            temperature = self._temperature, \
            b_sca = self._b_sca, \
            mfp_i_sca_0 = self._mfp_i_sca_0, \
            sources = self._sources, \
            mol_mass = self._mol_mass or 28.0, \
            unit_l0 = self._unit_l0, unit_t0 = self._unit_t0 );

    def _build_mesh( self ):
        return make_cartesian_mesh( \
            n_cell = self._n_cell, x_min = self._x_min, \
            x_max = self._x_max );

    def _resolve_field( self, value, XYZ ):
        if value is None:
            return zeros( XYZ[ 0 ].shape, dtype = float64 );
        if isinstance( value, ndarray ):
            return asarray( value, dtype = float64 );
        if callable( value ) and not isinstance( value, ( int, float ) ):
            return asarray( value( *XYZ ), dtype = float64 );
        return full( XYZ[ 0 ].shape, float( value ), dtype = float64 );

    def _resolve_b_sca( self, XYZ ):
        if self._b_sca is not None:
            return self._resolve_field( self._b_sca, XYZ );
        if self._species_obj is not None:
            temp_vals = self._resolve_field( self._temperature, XYZ );
            b_vals = sqrt( 2.0 * 1.380649e-16 * \
                           maximum( temp_vals, 0.1 ) / \
                           ( ( self._mol_mass or 28.0 ) * \
                             1.67262192e-24 ) );
            return b_vals;
        return full( XYZ[ 0 ].shape, 1e5, dtype = float64 );

    def _resolve_a_voigt( self, b_sca_val ):
        """Resolve Voigt damping parameter a = A_ul * lambda / (4 * pi * b)."""
        if self._a_voigt is not None:
            return float( self._a_voigt );
        if self._species_obj is not None and \
           self._species_obj.transitions is not None:
            t = self._species_obj.transitions[ self._transition_idx ];
            A_ul = float( t[ 2 ] );
            freq_GHz = float( t[ 3 ] );
            if freq_GHz > 0 and A_ul > 0:
                wavelength_cm = c_cgs / ( freq_GHz * 1e9 );
                b_mean = float( mean( abs( asarray( b_sca_val ) ) ) );
                if b_mean > 0:
                    return A_ul * wavelength_cm / ( 4.0 * pi * b_mean );
        return 0.0;

    def _resolve_vel( self, XYZ ):
        shape = XYZ[ 0 ].shape;
        if self._vel is None:
            return ( zeros( shape, dtype = float64 ), \
                     zeros( shape, dtype = float64 ), \
                     zeros( shape, dtype = float64 ) );
        out = [ ];
        for i, v in enumerate( self._vel ):
            if callable( v ) and not isinstance( v, ( int, float, ndarray ) ):
                out.append( asarray( v( *XYZ ), dtype = float64 ) );
            else:
                out.append( full( shape, float( v ), dtype = float64 ) );
        return tuple( out );

    def _resolve_mfp_species( self, species, n_tot, b_sca_val, \
                              n_species_val ):
        pops = species.initial_populations( n_species_val );
        mfp_sca = species.compute_opacity( pops, b_sca = b_sca_val, \
                                           transition_idx = \
                                             self._transition_idx );
        mfp_sca_0 = asarray( mfp_sca, dtype = float64 );
        return mfp_sca_0, None;

    def _resolve_path( self ):
        if self._path is not None:
            os.makedirs( self._path, exist_ok = True );
            return self._path;
        base = DEFAULT_RUN_ROOT;
        os.makedirs( base, exist_ok = True );
        import time
        ts = time.strftime( '%Y%m%d_%H%M%S' );
        run_dir = os.path.join( base, 'rt_%s' % ts );
        os.makedirs( run_dir, exist_ok = True );
        print( '[LineRt] Run directory: %s' % run_dir );
        return run_dir;

    def _sample_vel( self, n, v_lo, v_hi, pdf, sigma = None ):
        """Draw n velocity shifts in [v_lo, v_hi] from a distribution.

        pdf may be 'uniform', 'gaussian' (centred on the interval
        midpoint, width ``sigma``), or a callable probability density
        (which need not be normalized). Callables are sampled by
        numerical inverse transform: integrate on a fine grid to a CDF,
        normalize, then invert with linear interpolation.
        """
        if pdf == 'uniform':
            return random.uniform( v_lo, v_hi, int( n ) );
        if pdf == 'gaussian':
            if sigma is None or float( sigma ) <= 0.0:
                raise ValueError( \
                    "vel_pdf='gaussian' requires vel_sigma > 0 [cm/s]" );
            mu = 0.5 * ( v_lo + v_hi );
            s = float( sigma );
            # Inverse-transform a truncated Gaussian via its CDF.
            from scipy.stats import norm
            cdf = lambda x: norm.cdf( ( x - mu ) / s );
            p_lo = cdf( v_lo );
            p_hi = cdf( v_hi );
            u = p_lo + ( p_hi - p_lo ) * random.random( int( n ) );
            return ( norm.ppf( u ) * s + mu );
        # callable PDF: numerical inverse transform
        grid = linspace( v_lo, v_hi, 4097 );
        dens = asarray( [ float( pdf( x ) ) for x in grid ], \
                        dtype = float64 );
        dens = maximum( dens, 0.0 );
        cdf = concatenate( [ [ 0.0 ], \
                             cumsum( 0.5 * ( dens[ 1 : ] + dens[ : -1 ] ) * \
                                     ( grid[ 1 : ] - grid[ : -1 ] ) ) ] );
        if cdf[ -1 ] <= 0.0:
            raise ValueError( "vel_pdf callable integrates to zero "
                              "over vel_range" );
        cdf = cdf / cdf[ -1 ];
        u = random.random( int( n ) );
        return interp( u, cdf, grid );

    def _generate_photons( self, n_tot, mesh, b_sca_val ):
        parts = [ ];
        for src in self._sources:
            parts.append( self._generate_one_source( src, mesh, b_sca_val ) );
        if not parts:
            return zeros( ( 0, 10 ), dtype = float64 );
        return vstack( parts );

    def _generate_one_source( self, src, mesh, b_sca_val ):
        n_ph = int( src.get( 'n_photon', 50000 ) );
        s_type = src.get( 'type', 'slab' );
        wavelength = src.get( 'wavelength', None );
        luminosity = src.get( 'luminosity', None );
        flux = src.get( 'flux', None );
        units = src.get( 'units', 'photon' );
        vel_offset = float( src.get( 'vel_offset', 0.0 ) );
        sigma = float( src.get( 'sigma', 0.0 ) );
        vel_range = src.get( 'vel_range', None );
        vel_pdf = src.get( 'vel_pdf', 'uniform' );
        vel_sigma = src.get( 'vel_sigma', None );

        n_col = 9 if sigma != 0.0 else 8;

        if vel_range is not None:
            vel_draw = self._sample_vel( \
                n_ph, float( vel_range[ 0 ] ), float( vel_range[ 1 ] ), \
                vel_pdf, vel_sigma );
        else:
            vel_draw = None;

        if units == 'energy':
            E_ph = h_cgs * c_cgs / float( wavelength );

        if s_type == 'slab':
            x_min = mesh[ 'x_min' ];
            x_max_vals = array( mesh[ 'x_min' ] ) + \
                         array( mesh[ 'dx' ] ) * array( mesh[ 'n_cell' ] );

            x_pos = src.get( 'x' ) if src.get( 'x' ) is not None \
                    else x_min[ 0 ];
            x_pos = float( x_pos );
            y_rng = src.get( 'y_range', None );
            z_rng = src.get( 'z_range', None );
            y_lo = y_rng[ 0 ] if y_rng is not None else x_min[ 1 ];
            y_lo = float( y_lo );
            y_hi = y_rng[ 1 ] if y_rng is not None else x_max_vals[ 1 ];
            y_hi = float( y_hi );
            z_lo = z_rng[ 0 ] if z_rng is not None else x_min[ 2 ];
            z_lo = float( z_lo );
            z_hi = z_rng[ 1 ] if z_rng is not None else x_max_vals[ 2 ];
            z_hi = float( z_hi );
            direction = src.get( 'direction', '+x' );
            dx_sign = 1.0 if direction == '+x' else -1.0;

            source_area_cm2 = ( y_hi - y_lo ) * ( z_hi - z_lo ) * \
                              self._unit_l0 * self._unit_l0;

            if units == 'energy':
                proper = ( float( flux ) / E_ph ) * \
                         source_area_cm2 / n_ph;
            else:
                proper = float( flux ) * source_area_cm2 / n_ph;

            ph = zeros( ( n_ph, n_col ), dtype = float64 );
            ph[ :, 6 ] = proper;
            ph[ :, 7 ] = vel_offset + ( vel_draw if vel_draw is not None \
                                        else 0.0 );
            if n_col >= 9:
                ph[ :, 8 ] = sigma;
            ph[ :, 0 ] = x_pos;
            ph[ :, 1 ] = random.uniform( y_lo, y_hi, n_ph );
            ph[ :, 2 ] = random.uniform( z_lo, z_hi, n_ph );
            ph[ :, 3 ] = dx_sign;
            ph[ :, 4 ] = 0.0;
            ph[ :, 5 ] = 0.0;
        elif s_type == 'point':
            if units == 'energy':
                proper = float( luminosity ) / E_ph / n_ph;
            else:
                proper = float( luminosity ) / n_ph;

            ph = zeros( ( n_ph, n_col ), dtype = float64 );
            ph[ :, 6 ] = proper;
            ph[ :, 7 ] = vel_offset + ( vel_draw if vel_draw is not None \
                                        else 0.0 );
            if n_col >= 9:
                ph[ :, 8 ] = sigma;

            pos = src.get( 'position' ) or ( 0.0, 0.0, 0.0 );
            r_rand = float( src.get( 'r_random', 0.0 ) );
            if r_rand > 0.0:
                # Uniform (volume-weighted) position within the sphere.
                # r = r_rand * u^(1/3) gives dV-uniform sampling; the
                # offset direction is drawn independently of the flight
                # direction below.
                u_r = random.random( n_ph ) ** ( 1.0 / 3.0 );
                r = r_rand * u_r;
                th_o = arccos( 2.0 * random.random( n_ph ) - 1.0 );
                ph_o = 2.0 * pi * random.random( n_ph );
                ph[ :, 0 ] = float( pos[ 0 ] ) + r * sin( th_o ) * cos( ph_o );
                ph[ :, 1 ] = float( pos[ 1 ] ) + r * sin( th_o ) * sin( ph_o );
                ph[ :, 2 ] = float( pos[ 2 ] ) + r * cos( th_o );
            else:
                ph[ :, 0 ] = float( pos[ 0 ] );
                ph[ :, 1 ] = float( pos[ 1 ] );
                ph[ :, 2 ] = float( pos[ 2 ] );
            theta = arccos( 2.0 * random.random( n_ph ) - 1.0 );
            phi = 2.0 * pi * random.random( n_ph );
            ph[ :, 3 ] = sin( theta ) * cos( phi );
            ph[ :, 4 ] = sin( theta ) * sin( phi );
            ph[ :, 5 ] = cos( theta );
        else:
            raise ValueError( "Unknown source type: %s" % s_type );

        return ph;

    def _plot_results( self, out ):
        self.plot_results( out );
