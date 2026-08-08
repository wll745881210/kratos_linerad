#include <cfloat>
#include <cfenv>
#include <iostream>
#include <iomanip>
#include <csignal>

#include "../../src/device/general.h"
#ifdef    __MPI__
#include "../../src/comm/mpi/mpi.h"
#endif
#include "../../src/io/binary/binary_io.h"
#include "../../src/types.h"
#include "../../src/mesh/mesh_enroll.h"
#include "../../src/utilities/functions.h"
#include "../../src/utilities/mapping/loop.h"
#include "../../src/utilities/phys/unit.h"
#include "../../src/user/probgen.h"
#include "../../usr/extension/algo/interp.h"

#include "photon.h"
#include "photon_img.h"
#include "block_data.h"
#include "intg.h"
#include "gen.h"
#include "pool.h"
#include "radiation.h"
#include "rad_img.h"
#include "pool_img.h"
#include "photon_gen_img.h"

namespace prob
{

void run
( int argc, char * argv[] )
{
    mesh::mesh_t mesh;
    mesh.enroll_device     <    device_t >(  );
#ifdef    __MPI__
    using binary_io_t = binary_io::mpi_t ;
    mesh.enroll_comm       < comm::mpi_t >(  );
    mesh.enroll_binary_io  < binary_io_t >(  );
#endif
    auto p = mesh.enroll_module< radiation_t >(  );
    // Imaging module (parasite of radiation_t): only active
    // when [imaging] enabled=true in the par file.
    auto q = mesh.enroll_module< rad_img_t   >(  );
    q->parasite( p );

    input args;
    args.set_comm( mesh.p_com );
    cmd ( argc, argv,    args );
    mesh. init         ( args );
    mesh. evolve       (      );
    
    return;
}

}
