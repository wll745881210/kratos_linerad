"""ph_mode=1 (Voigt) comparison: Kratos vs Python reference MCRT."""
import subprocess, sys, os, math, json, importlib;
from numpy import array, zeros, full, column_stack, sqrt, maximum, \
                 abs, cos, sin, median, mean, std, bincount, float32, \
                 float64, int32, random, savetxt;

sys.path.insert( 0, \
    '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline' );
sys.path.insert( 0, \
    '/home/lilew/Seafile/seafile_sync/code/kratos/visual' );

from pipeline.kratos_io import write_field_data, \
    write_photon_data, read_output;

random.seed( 42 );

############################################################
#  Parameters

A_VOIGT = 0.01;
B_SCA_CGS = 1e5;
L_HALF = 5.0;
TAU0_HALF = 500;   # total tau0=1000
MFP_I_SCA_0 = TAU0_HALF / L_HALF;
N_CELL = 64;
N_PHOTONS = 5000;
N_STEP = int( 5e6 );

# Units
UNIT_L0 = 1.49597870691e13;   # code → CGS
UNIT_T0 = 1.0;
B_SCA_CODE = B_SCA_CGS * UNIT_T0 / UNIT_L0;  \
    # 1e5 * 1/1.49598e13 ≈ 6.68e-9

# Coarse grid
L_SLAB = 2 * L_HALF;
dx = L_SLAB / N_CELL;
x0 = -L_HALF;

# Geometry dict
geo = {
    'n_cell' : array( [ N_CELL, 2, 2 ], dtype = int32 ),
    'x_min'  : array( [ x0, 0., 0. ], dtype = float32 ),
    'dx'     : array( [ dx, 1., 1. ], dtype = float32 ),
};

# Field arrays (Kratos uses nz,ny,nx)
shape = ( geo[ 'n_cell' ][ 2 ], geo[ 'n_cell' ][ 1 ], \
          geo[ 'n_cell' ][ 0 ] );
mfp_i = full( shape, MFP_I_SCA_0, dtype = float32 );
b_sca = full( shape, B_SCA_CODE, dtype = float32 );

fields = {
    'mfp_i_sca_0_' : mfp_i,
    'b_sca_'       : b_sca,
    'vel_0_'       : zeros( shape, dtype = float32 ),
    'vel_1_'       : zeros( shape, dtype = float32 ),
    'vel_2_'       : zeros( shape, dtype = float32 ),
    'temp_'        : full( shape, 1e4, dtype = float32 ),
};

# Source: midplane isotropic
ox = full( N_PHOTONS, -L_HALF + L_SLAB * 0.5, dtype = float64 );
oy = random.uniform( 0., 1., N_PHOTONS );
oz = random.uniform( 0., 1., N_PHOTONS );
mu = 2 * random.uniform( 0., 1., N_PHOTONS ) - 1;
phi = 2 * math.pi * random.uniform( 0., 1., N_PHOTONS );
sm = sqrt( maximum( 0., 1. - mu * mu ) );
odx = sm * cos( phi );
ody = sm * sin( phi );
odz = mu;
op = full( N_PHOTONS, 1.0, dtype = float64 );   # unit proper

# photon array: x,y,z, dx,dy,dz, proper
photons = column_stack( [ ox, oy, oz, odx, ody, odz, op ] );

############################################################
#  Setup working dir

workdir = '/tmp/ph_mode1_test';
os.makedirs( workdir, exist_ok = True );

############################################################
#  Run Kratos

savetxt( os.path.join( workdir, 'bc_flags.txt' ), [ 0 ], \
         fmt = '%d' );
write_field_data( os.path.join( workdir, 'fields_cycle0.bin' ), \
                  fields, geo );
write_photon_data( os.path.join( workdir, 'photons_cycle0.bin' ), \
                   photons );

par_content = '''# Kratos parameter file for a=0 Voigt test

[unit]
length  = %.12e
time    = 1.0
density = 1.0

[mesh]
x_min = %s 0 0
x_max = %s 1 1
n_cell_global = %d 2 2

[cycle]
prefix_output = test
n_cycle_lim   = 0
t_lim         = 2
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = %d
n_scat = %d
output = 1
n_radiation = %d

[line_rt]
field_file  = fields_cycle0.bin
photon_file = photons_cycle0.bin
ph_mode     = 1
b_sca       = %.10e
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = %s

[boundary]
kinds = fre fre per per per per
''' % ( UNIT_L0, -L_HALF, L_HALF, N_CELL, N_STEP, N_STEP, \
        N_PHOTONS, B_SCA_CODE, A_VOIGT );
with open( os.path.join( workdir, 'a0.par' ), 'w' ) as f:
    f.write( par_content );

# Copy par to scratch and run
scratch = os.path.expanduser( '~/scratch/line_rt' );
for f in os.listdir( workdir ):
    if f.endswith( '.bin' ) or f.endswith( '.par' ) \
            or f == 'bc_flags.txt':
        os.makedirs( scratch, exist_ok = True );
        # Always copy to scratch
        subprocess.run( 'cp %s %s/' % ( os.path.join( workdir, f ), \
                                        scratch ), shell = True, \
                        check = True );

KRATOS_BIN = os.path.expanduser( \
    '~/apps/kratos_line_rt/bin/kratos' );
result = subprocess.run(
    [ KRATOS_BIN, 'a0.par' ],
    capture_output = True, text = True, timeout = 120,
    cwd = scratch
);
print( '=== Kratos stdout ===' );
print( result.stdout[ -2000 : ] );
if result.stderr:
    print( '=== stderr ===' );
    print( result.stderr[ -2000 : ] );

# Read output: use the last output file (final state)
out_files = sorted( [ f for f in os.listdir( scratch ) \
                      if f.startswith( 'test_' ) ] );
escaped = None;
if out_files:
    out_path = os.path.join( scratch, out_files[ -1 ] ); \
        # last = final
    output = read_output( out_path );
    print( '\nOutput file: %s' % out_files[ -1 ] );
    n_cell_r = output.get( 'n_cell' );
    if n_cell_r is not None:
        print( '  n_cell = %s' % ( n_cell_r, ) );
    phot = output.get( 'photons', { } );
    if phot:
        x_flat = phot.get( 'x', array( [ ], dtype = float32 ) );
        vel_raw = phot.get( 'vel', array( [ ], dtype = float32 ) );
        l_raw = phot.get( 'l', array( [ ], dtype = float32 ) );
        n_esc = len( l_raw );
        if n_esc > 0 and x_flat.size >= 3:
            esc_x = x_flat[ 0::3 ];   # x component
            esc_y = x_flat[ 1::3 ];
            esc_z = x_flat[ 2::3 ];
            # vel is in code units → x_freq = vel_code / b_sca_code
            x_freq_kratos = vel_raw / B_SCA_CODE;
            escaped = {
                'n_esc'     : n_esc,
                'x'         : esc_x,
                'y'         : esc_y,
                'z'         : esc_z,
                'vel_code'  : vel_raw,
                'x_freq'    : x_freq_kratos,
                'proper'    : l_raw,
            };
            print( '  escaped: %d' % n_esc );
            print( '  x range: [%.3f, %.3f]' \
                   % ( esc_x.min( ), esc_x.max( ) ) );
            print( '  x_freq range: [%.2e, %.2e]' \
                   % ( x_freq_kratos.min( ), x_freq_kratos.max( ) ) );
        else:
            print( '  No escaped photons found' );
    else:
        print( '  No escaped photons in output' );

############################################################
#  Run Python reference

print( '\n=== Python reference (ph_mode=1) ===' );
sys.path.insert( 0, '/home/lilew/Seafile/seafile_sync/code/' \
                  'line_rt_pipeline/docs/reference_mcrt' );
ref = importlib.import_module( 'mcrt' );
py_res = ref.mcrt_slab(
    L_slab = L_SLAB, tau0 = TAU0_HALF * 2, tau_abs = 0,
    b_sca = B_SCA_CGS, n_photons = N_PHOTONS, seed = 42,
    ph_mode = 1, a_voigt = A_VOIGT, n_cell = N_CELL,
);
# escaped[n_esc, 3]: col0=vel_CGS, col1=proper, col2=sv
esc_py = py_res[ 'escaped' ];
term_py = py_res[ 'term_reason' ];
x_freq_py = esc_py[ :, 0 ] / B_SCA_CGS;
print( '  Escaped: %d / %d' % ( esc_py.shape[ 0 ], N_PHOTONS ) );
print( '  x_freq range: [%.2e, %.2e]' \
       % ( x_freq_py.min( ), x_freq_py.max( ) ) );
n_term = bincount( term_py.astype( int ) ) \
         if term_py.max( ) > 0 else { };
print( '  Termination: %s' \
       % ( { k : int( v ) for k, v in enumerate( n_term ) \
             if v > 0 }, ) );

############################################################
#  Compare

print( '\n=== Comparison ===' );
if escaped is not None:
    xf_k = escaped[ 'x_freq' ];
    xf_p = x_freq_py;
    print( '  %-20s %10s %10s %10s' \
           % ( 'Metric', 'Kratos', 'Python', 'Diff%' ) );
    print( '  %s' % ( '-' * 52 ) );
    for name, k, p in [
        ( 'n_escaped', escaped[ 'n_esc' ], esc_py.shape[ 0 ] ),
        ( 'median|x_freq|', float( median( abs( xf_k ) ) ), \
          float( median( abs( xf_p ) ) ) ),
        ( 'mean|x_freq|', float( mean( abs( xf_k ) ) ), \
          float( mean( abs( xf_p ) ) ) ),
        ( 'std(x_freq)', float( std( xf_k ) ), \
          float( std( xf_p ) ) ),
        ( 'P(|x_freq|>3)', float( mean( abs( xf_k ) > 3 ) ), \
          float( mean( abs( xf_p ) > 3 ) ) ),
    ]:
        dp = ( k - p ) / p * 100 if p != 0 else 0;
        print( '  %-20s %10.4g %10.4g %+9.2f%%' % ( name, k, p, dp ) );
else:
    print( '  No Kratos escaped photons available' );

# Save for later analysis
result_data = {
    'a_voigt' : A_VOIGT,
    'tau0'    : int( TAU0_HALF * 2 ),
    'params'  : {
        'L_slab'    : L_SLAB,
        'n_photons' : N_PHOTONS,
        'n_step'    : N_STEP,
        'n_cell'    : N_CELL,
    },
};
if escaped is not None:
    result_data[ 'kratos' ] = {
        'n_esc'  : escaped[ 'n_esc' ],
        'x_freq' : [ float( median( abs( escaped[ 'x_freq' ] ) ) ), \
                     float( std( escaped[ 'x_freq' ] ) ) ],
        'p_gt3'  : float( mean( abs( escaped[ 'x_freq' ] ) > 3 ) ),
    };
result_data[ 'python' ] = {
    'n_esc'  : esc_py.shape[ 0 ],
    'x_freq' : [ float( median( abs( x_freq_py ) ) ), \
                 float( std( x_freq_py ) ) ],
    'p_gt3'  : float( mean( abs( x_freq_py ) > 3 ) ),
};
with open( os.path.join( workdir, 'comparison.json' ), 'w' ) as f:
    json.dump( result_data, f, indent = 2 );
print( '\nSaved to %s/comparison.json' % workdir );
