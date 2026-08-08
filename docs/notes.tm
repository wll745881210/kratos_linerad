<TeXmacs|2.1.2>

<style|<tuple|generic|chinese>>

<\body>
  <doc-data|<doc-title|Notes on the Monte Carlo Line
  Transfer>|<doc-author|<author-data|<author-name|Lile Wang>>>>

  <section|General and Basic Information>

  <subsection|Conventions>

  On the Kratos side, everything with the suffix "_cgs" is in CGS, and in
  code unit otherwise (the quantities on the Kratos side should be
  predominantly in the code unit system).

  The unit system (or dimension, as in the term "dimensional analyses") in
  this note is presented with the bracked lower-case letters in math, the
  dimension of length using <math|<around*|[|l|]>>, time using
  <math|<around*|[|t|]>>, mass in <math|<around*|[|m|]>>. For example, the
  acceleration has unit <math|<around*|[|l|]><around*|[|t|]><rsup|-2>>.
  Specifically, although the photon number does not have units, we can still
  mark it with a special symbol <math|<around*|[|n|]>> to "pretend" that it
  has a specific dimension of "counting", which can be equivalent to
  dimensionless once necessary.\ 

  In this note, we typically refer to "wavelength" or "frequency" of photons
  as "velocity"\Uthe shift of the photon in the velocity space defined by the
  Doppler effect (<math|\<Delta\>v=\<Delta\>\<lambda\>/\<lambda\><rsub|0>=-\<Delta\>\<nu\>/\<nu\><rsub|0>>,
  <math|\<Delta\>v\<gtr\>0> for redshifts, or longer wavelengths, compared to
  the stationary wavelength <math|\<lambda\><rsub|0>>).

  <subsection|Photon packets>

  Each photon packet represents many photons evolved in unit time period,
  carries a lot of "photons per unit time" ("effective luminosity",
  equivalently, or "luminosity" for short). A photon packet assumes Gaussian
  distribution in the velocity space for its own "proper" photons, described
  by:

  <\itemize>
    <item><math|<with|font|cal|L>>, the total photon number per unit time
    ("luminosity") in the packet, described by the photon packet's "proper".

    <item><math|\<Delta\>v>, the velocity-space centroid of the Gaussian
    distribution of the current photon packet. Note that this is a scalar,
    indicating the extent of wavelength shifts.

    <item><math|\<sigma\><rsub|ph>>, the dispersion of the Gaussian profile,
    which has the same unit as velocity.

    <item><math|<wide|d|^>>, the normalized direction vector for the
    propagation direction of the photon packet.

    <item><math|<with|font-series|bold|x>>, the current spatial location
    vector of the photon packet.

    <item>Other necessary information for computations (for example, the
    block index of the mesh on which the photon packet is propagating, and
    the cell index in the mesh-block).
  </itemize>

  The per-unit-time-period photon number ("luminosity") per unit velocity in
  the velocity space, for the photon packet, is described as,

  <\equation>
    <frac|\<delta\><with|font|cal|L>|\<delta\>v>=<frac|<with|font|cal|L>|<sqrt|2\<pi\>>\<sigma\><rsub|ph>>
    exp<around*|[|-<frac|<around*|(|v-\<Delta\>v|)><rsup|2>|2\<sigma\><rsub|ph><rsup|2>>|]>
    .
  </equation>

  <subsection|Physical picture>

  In one sentence: "Optically-thick radiative transfer of a line".\ 

  We use the term "line" for the radiation phenomena related to one specific
  transition of the target particles (molecules, atoms, ions, and even
  electrons if working on inverse Compton scattering\Uwe will use "particles"
  for a generic indication), as in "emission line" and "absorption line".\ 

  The system involves the following physical processes and mechanisms in the
  designated spatial region.

  <subsubsection|"Scattering">

  There are target particles that are involved in the absorption of photons
  of the designated line (by the lower-state particles of the transition),
  and the subsequent re-emission (from the higher state). In steady states
  that this code aims for, the re-emission takes place immediately after the
  absorption relative to the problem timescales, thus this process can be
  treated as scatterings equivalently. Note that:

  <\itemize>
    <item>These methods for the equivalent scattering can be directly used
    for "real" scattering, therefore we do not distinguish these
    "scatterings" mostly. There is one exception, though:\ 

    <\itemize>
      <item>When re-emitted in an equivalent scattering event, the "new"
      (outgoing) photon packet should have almost isotropic distribution of
      direction of propagation, and the\ 

      <item>When actually scattered, the outgoing photon packet should follow
      the energy and momentum conservation relations according to the\ 
    </itemize>

    <item>Only the particles on the lower level of the transition can take
    part in these scatterings. Therefore, the population number of particles
    could be important.
  </itemize>

  <subsubsection|<with|font-series|bold|"Absorption">>\ 

  These are the "real" absorption processes that remove photons entirely from
  the target transition of target particles. In Monte Carlo methods, this
  leads to the deduction of the photon numbers in photon packets. For most
  line transfer, such "real" absorption could be treated as independent of
  <math|\<Delta\>v> (equivalently, wavelength-inedependent).

  <subsubsection|Population numbers of the target particles>\ 

  For the target line, the number densities of the particles on the lower and
  upper levels respectively at each spatial location are of core importance.
  Calculations of the population numbers of the concerned levels are carried
  out on the Python side, not the Kratos side. Note that there could be more
  levels than two to deal with (although only two are directly involved in
  the concerned line transition) to get the population numbers correct.

  These calculations involve:

  <\itemize>
    <item>Collisional excitation and de-excitation. This will require
    collision partner number density profiles, and one of the collisional
    (de-)excitation rate coefficients (the other could be calculated using
    the detailed balance principle)\Umultiplying the coefficients (dimension
    <math|<around*|[|l|]><rsup|3><around*|[|t|]><rsup|-1>>) by the collision
    partner number density (dimension <math|<around*|[|l|]><rsup|-3>>) will
    get us the (de-)exitation rates in transition probability per unit time
    (dimension <math|<around*|[|t|]><rsup|-1>>).

    <item>Spontaneous decay. This will requre the Einstein <math|A>
    coefficients (dimension <math|<around*|[|t|]><rsup|-1>>) of the relevant
    levels to other levels. These could result in the deduction of numbers in
    many "source" levels, and add to the numbers in the levels as the
    destination of the decay (note that these may or may not be the two
    levels involved in the line transition\Utake extra care of the level
    symbols).

    <item>Photon excitation. The Kratos output will include an "effective
    excitation flux" <math|F<rsub|ext>> (already taking the Gaussian profiles
    of the photon packet and thermal broadening into account, see later), in
    photon number per unit area per unit time (dimension
    <math|<around*|[|n|]><around*|[|l|]><rsup|-2><around*|[|t|]><rsup|-1>>),
    which can be multiplied by the line-center excitation cross section
    <math|\<sigma\><rsub|0>> (dimension <math|<around*|[|l|]><rsup|2>>) of
    excitation to get the photon excitation rate in transition probability
    per unit time (dimension <math|<around*|[|t|]><rsup|-1>>). Note that the
    normalized Gaussian profile has already been involved in obtaining
    <math|F<rsub|ext>>, so that the product
    <math|F<rsub|ext>\<sigma\><rsub|0>> will get the photon excitation rate
    directly. Note also that it is very likely that the excitation flux is
    involved <with|font-series|bold|only> in the target transition.
    Additionally, these total cross sections of absorption from lower level
    to higher level, can be calculated via the Einstein <math|A> coefficient
    of spontaneous decay from the upper level to the lower level (see the
    next sub-subsection).
  </itemize>

  One simplification that could be adopted in many situations is that the
  system is a two-level system, and only the lower level and the upper level
  of the target transition are involved. Nevertheless, we should guarantee
  the ability to calculate systems with many levels (but only two of them are
  involved in the Monte Carlo radiative transfer).

  <subsubsection|Scattering cross sections>

  The definition of the line-center excitation cross section
  <math|\<sigma\><rsub|0>> also deserves some discussions. Ignoring the
  intrinsic width, the cross section at velocity <math|v> approximately
  reads, under the thermal broadening <math|\<sigma\><rsub|th>=<sqrt|k<rsub|B>T/\<mu\>>=9.12<text|
  km s><rsup|-1>\<times\><around*|[|T<rsub|4>/<around*|(|\<mu\>/m<rsub|A>|)>|]><rsup|1/2>>
  (<math|k<rsub|B>> the Boltzmann constant, <math|\<mu\>> the dimensional
  particle mass, <math|T<rsub|4>\<equiv\>T/<around*|(|10<rsup|4><text|
  K>|)>>, and <math|m<rsub|A>> the atomic mass unit) in the particle-rest
  frame (eq. 6.39 in Draine 2011),\ 

  <\equation>
    \<sigma\><around*|(|v|)>=<frac|<sqrt|\<pi\>>e<rsup|2>|m<rsub|e>c><frac|f
    \<lambda\><rsub|0>|<sqrt|2>\<sigma\><rsub|th>>
    exp<around*|(|-<frac|v<rsup|2>|2\<sigma\><rsub|th><rsup|2>>|)>,
  </equation>

  where <math|e=4.80321\<times\>10<rsup|-10> <text|
  g><rsup|1/2>cm<rsup|3/2><text|s><rsup|-1>> is the CGS electron charge,
  <math|m<rsub|e>> the mass of electron, <math|c> the speed of light,
  <math|\<lambda\><rsub|0>> the line-center wavelength, and the dimensionless
  oscillator strength <math|f> is related to the Einstein <math|A>
  coefficient by (eq. 6.20 in Draine 2011),

  <\equation>
    A=<frac|8\<pi\><rsup|2>e<rsup|2>\<nu\><rsup|2>|m<rsub|e>c<rsup|3>><frac|g<rsub|l>|g<rsub|u>>f=<frac|0.6670<text|
    cm><rsup|2> <text|s><rsup|-1>|\<lambda\><rsub|0><rsup|2>><frac|g<rsub|l>|g<rsub|u>>f
    .
  </equation>

  where <math|\<nu\><rsub|0>=c/\<lambda\><rsub|0>> is the line-center
  frequency, <math|g<rsub|l>> and <math|g<rsub|u>> the degree of degeneracy
  of the lower and upper levels (<math|g=2J+1> for each level). We can
  re-write the <math|\<sigma\><around*|(|v|)>> expression as
  <math|\<sigma\><around*|(|v|)>=\<sigma\><rsub|0>
  exp<around*|[|-v<rsup|2>/<around*|(|2\<sigma\><rsub|th><rsup|2>|)>|]>>,
  where,

  <\equation>
    \<sigma\><rsub|0>=<frac|<sqrt|\<pi\>>e<rsup|2>|m<rsub|e>c><frac|f
    \<lambda\><rsub|0>|<sqrt|2>\<sigma\><rsub|th>> .
  </equation>

  In the code, <math|b<rsub|sca>\<equiv\><sqrt|2>\<sigma\><rsub|th>> is
  used as the Doppler broadening parameter, so that
  <math|\<sigma\><around*|(|v|)>=\<sigma\><rsub|0>
  H<around*|(|a,x|)>> with <math|x=v/b<rsub|sca>> and
  <math|H<around*|(|0|)>=1>. The dimensionless Voigt damping parameter is
  <math|a=\<Gamma\>/<around*|(|4\<pi\>\<Delta\>\<nu\><rsub|D>|)>>,
  where <math|\<Gamma\>=A<rsub|ul>/<around*|(|2\<pi\>|)>> is the natural
  line width and <math|\<Delta\>\<nu\><rsub|D>=b<rsub|sca>/\<lambda\><rsub|0>>
  is the Doppler width. For <math|a\<rightarrow\>0>, the Hjerting function
  <math|H<around*|(|a,x|)>> reduces to <math|<text|exp><around*|(|-x<rsup|2>|)>>
  (pure Gaussian, the CFR limit). For <math|a\<gtrsim\>0.1>, the Lorentzian
  wing <math|H\<approx\>a/<around*|(|<sqrt|\<pi\>>x<rsup|2>|)>> dominates at
  <math|<around*|\||x|\|>\<gtrsim\>1>, which is essential for the
  frequency-space diffusion in optically thick slabs (Neufeld 1990) and for
  the imaging wing channels.

  In practice, the Python-side pipeline will calculate the oscillator
  strength <math|f> based on the Einstein <math|A> coefficient and the
  degeneracy <math|g<rsub|u>> and <math|g<rsub|l>> based on the <math|J> of
  the corresponding levels, by looking for the data in the database. Then,
  the Python-side pipeline will then calculate this <math|\<sigma\><rsub|0>>
  field based on the temperature distribution in the space, and then
  calculate the <math|\<lambda\><rsub|sca,0><rsup|-1>> (reciprocal of the
  line-center scattering mean free path) by
  <math|\<lambda\><rsub|sca,0><rsup|-1>\<equiv\>\<sigma\><rsub|0>n<rsub|lower>>
  (<math|n<rsub|lower>> the number density of the target particle on the
  lower state of the target transition), feed this as one of the input fields
  to Kratos, within the binary file that contain all necessary fields to be
  read by Kratos.

  <section|Methods on the Kratos side>

  One sentence guideline: Instead of directly emulating the particles and
  photons, Monte Carlo methods sample the differential equations that the
  photons should obey.

  <subsection|Photon packet proper>

  For each photon packet, the "proper" is actually used as the effective
  luminosity <math|<with|font|cal|L>>, in units of
  <math|<around*|[|n|]><around*|[|t|]><rsup|-1>>. When it passes through a
  cell with volume <math|V> using a intra-cell path length <math|\<delta\>l>
  (measured from the entry point into the current cell through the exit point
  of the cell), this packet contributes to the flux (photon number flux, no
  the energy flux, here and in what follows) in the cell by
  <math|\<delta\>F=<with|font|cal|L>\<delta\>l/V> (<math|V/\<delta\>l> is the
  effective surface area of this packet crossing the current cell), and the
  final number of the flux in that cell should be calculated by summing all
  the <math|\<delta\>F> contributed by all photons crossing the cell. It is
  natural to see that the dimension of <math|\<delta\>F> is
  <math|<around*|[|n|]><around*|[|l|]><rsup|-2><around*|[|t|]><rsup|-1>>.

  <subsection|Excitation >

  The excitation flux contributed by one ray, <math|\<delta\>F<rsub|exc>>, is
  just the flux contribution <math|\<delta\>F> multiplied by the
  dimensionless overlap integral <math|<with|font|cal|I>>
  (<math|\<delta\>F<rsub|exc>=<with|font|cal|I> \<delta\>F>), where
  <math|<with|font|cal|I>> is defined as,

  <\eqnarray>
    <tformat|<table|<row|<cell|<with|font|cal|I>>|<cell|=>|<cell|<frac|1|<sqrt|2\<pi\>\<sigma\><rsup|2><rsub|ph>>><big|int><rsub|-\<infty\>><rsup|+\<infty\>>\<mathd\>
    v<rprime|'> \ exp<around*|[|-<frac|<around*|(|v<rprime|'>-\<Delta\>v|)><rsup|2>|2\<sigma\><rsub|ph><rsup|2>>|]>exp<around*|[|-<frac|<around*|(|v<rprime|'>+v<rsub|\<parallel\>>|)><rsup|2>|2\<sigma\><rsub|th><rsup|2>>|]>>>|<row|<cell|>|<cell|=>|<cell|<frac|1|<sqrt|1+\<sigma\><rsub|ph><rsup|2>/\<sigma\><rsub|th><rsup|2>>>
    exp<around*|[|-<frac|<around*|(|\<Delta\>v+v<rsub|\<parallel\>>|)><rsup|2>|2<around*|(|\<sigma\><rsub|ph><rsup|2>+\<sigma\><rsub|th><rsup|2>|)>>|]>,>>>>
  </eqnarray>

  where <math|\<sigma\><rsub|ph>> and <math|\<Delta\>v> are the dispersion
  and line-center velocity (<math|\<Delta\>v> \<gtr\> 0 for redshifts) for
  the Gaussian of the photon packet (one of the member data of the photon
  packet), <math|\<sigma\><rsub|th>> is the thermal-motion Gaussian
  dispersion of the gas (calculated by the temperature and the ),
  <math|v<rsub|\<parallel\>>=<with|font-series|bold|v>\<cdot\><wide|d|^>> is
  the bulk motion velocity of the gas at the current location (denoted by
  <math|<with|font-series|bold|v>>, the data fields that Kratos reads in at
  the beginning of each cycle) projected along the propagation direction of
  the photon. Summing up the <math|\<delta\>F<rsub|ext>> by all photons
  passing through the current cell in the Monte Carlo, one gets the
  <math|F<rsub|ext>> of the current cell. The Python side will read this
  <math|F<rsub|ext>> from the Kratos output, and use
  <math|F<rsub|ext>\<sigma\><rsub|0>> to calculate the population number in
  preparation for the next cycle.

  <subsection|Evolution>

  Again, in this work, "scattering" has a special denotation: absorbed by the
  lower-level and re-emitted instantly by the upper level (already described
  in the previous section).

  <subsubsection|Propagation>

  The scattering event location is determined by the scattering optical
  depth, which uses the opacity profile <math|\<phi\><around*|(|u|)>=H<around*|(|a,u|)>>
  (Voigt/Hjerting function, for <verbatim|ph_mode> 1/2/3) or
  <math|\<phi\><around*|(|u|)>=<text|exp><around*|(|-u<rsup|2>|)>> (Gaussian,
  for <verbatim|ph_mode> 0), where <math|u=<around*|(|\<Delta\>v+v<rsub|<around*|\||\<parallel\>|\|>>|)>/b<rsub|sca>>
  is the gas-frame frequency offset in Doppler-width units and
  <math|a=\<Gamma\>/<around*|(|4\<pi\>\<Delta\>\<nu\><rsub|D>|)>> is the
  Voigt damping parameter (<math|\<Gamma\>> the natural line width,
  <math|\<Delta\>\<nu\><rsub|D>> the Doppler width). After each scattering
  event (or after the photon is generated or read into Kratos, marked as the
  "0th" scattering), a "remaining scattering optical depth"
  <math|\<tau\><rsub|rem>> is generated following exponential distribution of
  parameter <math|1>, which is easy: first generate a uniform distirbution
  <math|Y\<in\><around*|[|0.0001,0.9999|]>> (in theory,
  <math|Y\<in\><around*|[|0,1|]>>, but we use
  <math|<around*|[|0.0001,0.9999|]>> for safety), then assign
  <math|\<tau\><rsub|rem>=ln Y>.

  The photon packet then travels in a straight line along its direction
  vector <math|<wide|d|^>>, from surface to surface of cells. When reaching
  the exit surface of the current cell (the photon gets its exit point) after
  travelling for <math|\<delta\>l> in the current cell, the photon gets a
  <math|\<delta\>\<tau\><rsub|rem>\<equiv\>\<phi\><around*|(|u|)>
  \<lambda\><rsub|sca,0><rsup|-1>\<delta\>l>, then the updated value
  <math|\<tau\><rprime|'><rsub|rem>> is obtained by
  <math|\<tau\><rsub|rem><rprime|'>\<leftarrow\>\<tau\><rsub|rem>-\<delta\>\<tau\><rsub|rem>>
  assuming that the photon will reach the cell-exiting point.\ 

  Note that the overlap integral <math|<with|font|cal|I>> defined in
  \<S\>2.2 is used <with|font-series|bold|only> for the excitation flux
  accumulation, <with|font-series|bold|not> for the propagation. The
  propagation uses the opacity profile <math|\<phi\><around*|(|u|)>> (Voigt
  or Gaussian), which includes the Lorentzian wing for
  <verbatim|ph_mode> 1/2/3.

  Now, if <math|\<tau\><rprime|'><rsub|rem>\<gtr\>0>, then the photon packet
  continues propagation along <math|<wide|d|^>>. The absorption is taken into
  account by updating the photon packet's proper,
  <math|<with|font|cal|L><rprime|'>\<leftarrow\><with|font|cal|L>
  exp<around*|(|- \<delta\>l\<lambda\><rsub|abs><rsup|-1>|)>>, where
  <math|\<lambda\><rsub|abs><rsup|-1>> is the inverse (reciprocal) of the
  ("real") absorption mean free path passed into Kratos by the Python
  pipeline.

  If <math|\<tau\><rprime|'><rsub|rem>\<less\>0>, an linear interpolation is
  carried out to find the location at which the scattering takes place:
  <math|<with|font-series|bold|x>=<with|font-series|bold|x><rsub|enter>+<around*|(|\<tau\><rsub|rem>/\<delta\>\<tau\><rsub|rem>|)><wide|d|^>\<delta\>l>
  (<math|<with|font-series|bold|x><rsub|enter>> is the spatial coordinates
  that the photon packet enters the current cell;
  <math|<with|font-series|bold|x><rsub|exit>=<with|font-series|bold|x><rsub|enter>+<wide|d|^>\<delta\>l>
  gives the location that the photon packet exits the cell if the scattering
  event does not take place in the current cell). The absorption is also
  taken into account, by <math|<with|font|cal|L><rprime|'>\<leftarrow\><with|font|cal|L>
  exp<around*|[|- <around*|(|\<tau\><rsub|rem>/\<delta\>\<tau\><rsub|rem>|)>\<delta\>l\<lambda\><rsub|abs><rsup|-1>|]>>
  (also linear interpolation in the absorption optical depth).

  <subsubsection|Scattering event (CFR, <verbatim|ph_mode>=0)>

  When a scattering event takes place, we must re-assign the direction
  <math|<wide|d|^>>, the broadening <math|\<sigma\><rsub|ph>>, and the
  velocity shift <math|\<Delta\>v>, to the scattered photon packet. Because
  we assume that all scatterings are "quick re-emission after absorption", we
  can use a simplified scheme ignoring the particle recoil:

  <\enumerate>
    <item>Assign <math|<wide|d|^>> by generating
    <math|\<mu\>\<equiv\>cos\<theta\>\<in\><around*|[|-1,1|]>> and
    <math|\<varphi\>\<in\><around*|[|0,2\<pi\>|]>>, obeying uniform
    distributions, respectively, and set <math|<wide|d|^>=<around*|[|sin\<theta\>
    cos\<varphi\>, \ sin\<theta\> sin\<varphi\>, \ cos\<theta\>|]>>.

    <item>Assign <math|\<Delta\>v=-<with|font-series|bold|v>\<cdot\><wide|d|^>>
    according to the bulk motion velocity <math|<with|font-series|bold|v>> of
    the current cell. Note the sign: when <math|<with|font-series|bold|v>>
    and <math|<wide|d|^>> are in the same direction, the photon packet is
    blue shifted (<math|\<Delta\>v\<less\>0>).

    <item>Assign <math|\<sigma\><rsub|ph>=\<sigma\><rsub|th>> according to
    the <math|\<sigma\><rsub|th>> of the current cell.

    <item>Generate a new <math|\<tau\><rsub|rem>> in the same way as the
    previous sub-subsection.
  </enumerate>

  In CFR (Complete Frequency Redistribution), the outgoing photon's
  frequency is drawn from a Gaussian centered at zero (in the gas rest
  frame), with no memory of the incoming photon's frequency. This is the
  simplest redistribution and is valid when the natural line width is
  negligible (<math|a\<ll\>1>).

  <subsubsection|Scattering event (R_IIA, <verbatim|ph_mode>=1/2/3)>

  For <verbatim|ph_mode> 1/2/3, the frequency redistribution uses the
  full R_IIA (Angle-dependent Partial Redistribution) kernel, which
  preserves the <with|font-series|bold|frequency memory> and the
  <with|font-series|bold|angle\Ufrequency correlation> of the scattering
  process. The direction is still sampled isotropically (step 1 above),
  but the frequency is drawn from the USampler table.

  The USampler draws <math|u> from the angle-averaged R_II kernel
  <math|P<around*|(|u\|\|x|)>\<propto\><text|exp><around*|(|-u<rsup|2>|)>/<around*|(|a<rsup|2>+<around*|(|x-u|)><rsup|2>|)>>,
  where <math|x=\<Delta\>v<rsub|lab>/b<rsub|sca>> is the incoming
  frequency in Doppler-width units (gas rest frame). The outgoing
  frequency is then:

  <\equation>
    x<rsub|new>=x+u<rsub|par><around*|(|g-1|)>+<text|sin\<theta\>>\<cdot\>u<rsub|perp>,
  </equation>

  where <math|g=<with|font-series|bold|d><rsub|old>\<cdot\><wide|d|^><rsub|new>>
  is the directional correlation (cosine of the scattering angle),
  <math|u<rsub|par>> is sampled from the USampler (parallel component,
  frequency memory), and <math|u<rsub|perp>\<sim\><with|font|cal|N><around*|(|0,1/2|)>>
  is the perpendicular component (thermal broadening, drawn from a
  Gaussian). The stored velocity shift is then
  <math|\<Delta\>v=x<rsub|new>b<rsub|sca>-<with|font-series|bold|v>\<cdot\><wide|d|^>>,
  so that <math|\<Delta\>v+v<rsub|<around*|\||\<parallel\>|\|>>=x<rsub|new>b<rsub|sca>>
  recovers the gas-frame outgoing frequency.

  The R_IIA kernel is precomputed as a 3-D table
  <math|R<around*|(|x<rsub|out>,<around*|\||x<rsub|pp>|\|>,g|)>>
  (400\<times\>200\<times\>40 = 3.2 M floats) from the USampler CDF, and
  is also used in the imaging source function accumulation (see
  <math|\<S\>4>). The kernel density is defined as:

  <\equation>
    R<around*|(|x<rsub|out>; x<rsub|pp>, g|)>=<big|sum><rsub|k>pdf<around*|[|k|]>\<cdot\><frac|<text|exp><around*|(|-y<rsub|k><rsup|2>/sin<rsup|2>\<theta\><rsub|g>|)>|sin\<theta\><rsub|g>\<cdot\><sqrt|\<pi\>|>>
  </equation>

  where <math|y<rsub|k>=x<rsub|out>-x<rsub|pp>-u<rsub|k><around*|(|g-1|)>>,
  <math|sin\<theta\><rsub|g>=<sqrt|<text|max><around*|(|1-g<rsup|2>,0|)>>>>
  (clamped to <math|\<geq\>10<rsup|-3>>),
  <math|pdf<around*|[|k|]>=<text|CDF><around*|[|k|]>-<text|CDF><around*|[|k-1|]>>
  are discrete probabilities from the USampler CDF row at
  <math|<around*|\||x<rsub|pp>|\|>>, and <math|u<rsub|k>> are the USampler
  grid points (<math|n<rsub|u>=251>, <math|u\<in\><around*|[|-6,+6|]>>,
  <math|\<Delta\>u=0.048>). The USampler conditional is
  <math|P<around*|(|u\|x|)>\<propto\><text|exp><around*|(|-u<rsup|2>|)>/<around*|(|a<rsup|2>+<around*|(|x-u|)><rsup|2>|)>>.
  Normalisation: <math|<big|int>R\<mathd\>x<rsub|out>=1>. Symmetry:
  <math|R<around*|(|x<rsub|out>;-x<rsub|pp>,g|)>=R<around*|(|-x<rsub|out>;x<rsub|pp>,g|)>>.
  The table spans <math|x<rsub|out>\<in\><around*|[|-120,+120|]>>,
  <math|<around*|\||x<rsub|pp>|\|>\<in\><around*|[|0,120|]>>,
  <math|g\<in\><around*|[|-1,+1|]>>.

  <verbatim|ph_mode> 1 uses global-memory tables, <verbatim|ph_mode> 2 uses
  constant-memory tables (fastest exact mode), and <verbatim|ph_mode> 3
  uses an approximate analytic Voigt blend for the opacity profile
  (fastest overall, with <math|<around*|(|1-3|)>%> error in
  <math|<text|med>|x|> at low <math|a\<tau\><rsub|0>>).

  <section|Methods on the Python side>

  The python-side jobs should be relatively straightforward.

  <subsection|Data on mesh>

  <subsubsection|To Kratos>

  The first is to provide the data for the Kratos side, via a binary file
  that includes the following fields on structured mesh:

  <\itemize>
    <item>The inverse (reciprocal) of the effective line-center mean free
    path of scattering (excitation), <math|\<lambda\><rsub|sca,0><rsup|-1>>

    <item>The inverse (reciprocal) of the absorption
    <math|\<lambda\><rsub|abs><rsup|-1>>.

    <item>The thermal broadening velocity <math|\<sigma\><rsub|th>>.

    <item>The bulk motion velocity field <math|<with|font-series|bold|v>>.
  </itemize>

  These values shall be read into Kratos, used in the construction of
  interpolation objects, and set the mesh-block data by calling the
  interpolation fields. The Python interface will accept either the numbers
  (for initializing uniform fields) or callables (for initializing
  spatial-coordinate-dependent feilds) for these fields, all in CGS
  (including dependent and independent variables). Specifically, the Python
  pipeline should also allow the user to specify the species, upper and lower
  energy levels, number density, and temperature of the concerned target
  particles, so that the Python pipeline will calculate
  <math|\<lambda\><rsub|sca,0><rsup|-1>> and <math|\<sigma\><rsub|th>> on its
  own. Also, the Python object should hold these data objects so that the
  user can plot these fields easily.

  Note that all these quantities should be in the code unit system (including
  the independent variables, esp. the coordinates that are used in
  constructing the interpolation objects), converted from other unit systems
  (esp. CGS, presumably the unit system used on the Python side) by the
  Python-side routines (that is, conversion should be finished before feeding
  the data to Kratos). The unit system should be specified under the [unit]
  section in the parameter file to be read by Kratos.

  <subsubsection|From Kratos>

  The Python pipline will read the <math|F<rsub|ext>> from the Kratos output
  (be careful about the units conversion from the code unit to the CGS) and
  calculate the <math|F<rsub|ext>\<sigma\><rsub|0>> for the photon excitation
  rate, as one of the key data used in the calculation of the population of
  particle energy levels.

  <subsection|Particle data>

  <subsubsection|To Kratos>

  The Python side will generate photon packets to be read into Kratos, which
  consist of two parts:

  <\itemize>
    <item>"External" source(s). Photons that are emitted by sources
    <with|font-series|bold|other than> the target particles distributed in
    the space. For example, an isotropic point source for a star, or a
    plane-parallel extended source if one studies a photodissociation region
    (PDR).

    <item>"Internal" sources. Each cell with particles on the upper level of
    the target transition is equivalent to an isotropic point source, whose
    luminosity is equivalent to the volume of the cell multiplied by the
    number density of the upper-level particles times the Einstein <math|A>
    coefficient. There must be at least one photon packet generated per cell,
    and at most <math|N<rsub|ph,cell,max>> photons generated per cell; the
    actual number of photon packets should be determined according to the
    cell's luminosity. The sum of the photons' effective luminosity should
    equal to the total luminosity of the cell.
  </itemize>

  We should take care of the units, paying attention to these things:

  <\itemize>
    <item>Each photon packet carries an "equavalent luminosity", which is in
    photon-number luminosity dimension (<math|<around*|[|n|]><around*|[|t|]><rsup|-1>>).

    <\itemize>
      <item>If dealing with a plane-parallel extended source style, the user
      shall specify the photon direction <math|d> and the photon number flux
      (dimension <math|<around*|[|n|]><around*|[|l|]><rsup|-2><around*|[|t|]><rsup|-1>>)
      of the plane parallel extended source; photon packets' initial location
      should guarantee that the sum of photon packets luminosity
      <with|font-series|bold|per unit area perpandicular to the direction of
      all photon packets> matches the user-designated number.

      <item>If dealing with an isotropic point source, the user shall specify
      the photon number luminosity (dimension
      <math|<around*|[|n|]><around*|[|t|]><rsup|-1>>) of the point source.
      The photon packet directions <math|<wide|d|^>> go through the
      all-<math|4\<pi\>> solid angle uniformly (could be generated by uniform
      distributions for <math|cos \<theta\>\<in\><around*|[|-1,1|]>> and
      <math|\<varphi\>\<in\><around*|[|0,2\<pi\>|]>>), and the sum of
      effective luminosity of all photon packets generated should equal to
      the luminosity of the source.
    </itemize>

    <item>The Python-side routines work on the CGS system, while Kratos works
    on its own code unit system. Make the conversion correctly based on the
    code unit conversion ([unit] section in the parameter file for Kratos).
  </itemize>

  <subsubsection|From Kratos>

  The Python routine will read the particles after the final iteration is
  done, in order to generate the statistics as the output.

  <subsection|Iterations>

  The calculations are calculated iteratively. In each iteration, we conduct
  steps:

  <\enumerate>
    <item>On Python side: Calculate the population number of all relevant
    energy levels of the target particle using the temperature, collisional
    partner density, collsional (de-)excitation rates (calculated as
    functions of temperatures), excitation photon fluxes <math|F<rsub|exc>>
    (and the line-center excitation cross section <math|\<sigma\><rsub|0>>,
    also as a function of temperature) . If this is the first iteration,
    ignore that the photon excitation (by setting <math|F<rsub|exc>=0>
    everywhere) as we don't have <math|F<rsub|exc>>; otherwise, read
    <math|F<rsub|exc>> from the Kratos output of the previous iteration.

    <item>On Python side: Create data cubes of
    <math|\<lambda\><rsub|abs><rsup|-1>>,
    <math|\<lambda\><rsub|sca,0><rsup|-1>>, <math|<with|font-series|bold|v>>,
    <math|\<sigma\><rsub|th>> (pay attention to units!), save them \ in a
    binary file, to be read by Kratos.

    <item>On Python side: Generate photon packets, save them in another
    binary file, to be read by Kratos

    <item>On Kratos side: Conduct Monte Carlo calculations, saving <math|F>
    (photon number flux) and <math|F<rsub|exc>> (effective excitation photon
    number flux) and the final states of photons.
  </enumerate>

  These steps are conducted iteratively until the system converges (or
  certain number of iterations is reached).\ 

  <section|Imaging (Two-Step: Scattering Source Function + Ray Tracing)>

  Imaging produces a position\Uvelocity cube <math|I<around*|(|<text|pixel>,
  <text|channel>|)>> = the specific intensity reaching a distant observer,
  using a two-step method adapted from Yang &amp; Wang (2025, \<S\>2.3 +
  Appendix A).

  <subsection|Principle>

  Direct MC imaging is hopelessly expensive: the camera subtends a tiny
  solid angle and multiple scattering randomises directions. Because RT is
  linear, the contribution of scattered photons to a <with|font-series|bold|fixed>
  viewing direction can instead be accumulated <with|font-series|bold|on the
  grid during the scattering MC>, then a separate
  <with|font-series|bold|non-scattering ray tracing> integrates the transfer
  equation along camera rays\Ua post-processing step that can be repeated for
  any viewing angle/camera at negligible cost.

  The imaging is enabled by setting <verbatim|imaging> in the
  <verbatim|LineRt> constructor or the <verbatim|[imaging]> par section.
  It runs only on the <with|font-series|bold|final> MC cycle. When disabled,
  the <math|s<rsub|cam>> field is not initialised, allocated, or written.

  <subsection|Step 1 --- Scattering source function
  <math|s<rsub|cam>>>

  The per-cell, per-channel field <math|s<rsub|cam>> (Kratos
  <verbatim|rad_t.s_cam>, <math|n<rsub|int>=n<rsub|chan>>) carries the
  <with|font-series|bold|total source function toward the camera
  direction>\Uthe emission seed and the scattering contribution folded
  together.

  <subsubsection|Emission seed>

  On GPU init, the field is seeded with the line source function from the
  local emissivity:

  <\equation>
    S<rsub|emiss>=<frac|j<rsub|emiss>|\<lambda\><rsub|sca,0><rsup|-1>\<sqrt|\<pi\>>
    b<rsub|sca>>,
  </equation>

  where <math|j<rsub|emiss>=n<rsub|u>A<rsub|ul>/<around*|(|4\<pi\>|)>> is the
  photon-number volume emissivity, <math|\<lambda\><rsub|sca,0><rsup|-1>=\<sigma\><rsub|0>n<rsub|lower>>
  the line-center inverse scattering mean free path, and <math|b<rsub|sca>>
  the Doppler broadening velocity. The <math|<sqrt|\<pi\>> b<rsub|sca>>
  factor converts the frequency-integrated source function
  (<math|j/\<lambda\><rsup|-1>>) to the frequency-dependent source function
  <math|S<around*|(|v|)>=j<around*|(|v|)>/\<alpha\><around*|(|v|)>>, which is
  frequency-independent for a two-level atom with CRD. This is applied to
  every channel equally.

  <subsubsection|Scattering accumulation>

  During the MC, each path segment in cell <math|i> also adds the packet's
  contribution to the scattering source function toward the camera:

  <\eqnarray>
    <tformat|<table|<row|<cell|<text|base>>|<cell|=>|<cell|<frac|\<cal-L\>
    \<delta\>l|V><around*|(|1-\<mathd\>e<rsup|-\<delta\>\<tau\><rsub|e>>|)>/<around*|(|\<delta\>\<tau\><rsub|e>|)>\<cdot\><frac|1|4\<pi\>>>>|<row|<cell|s<rsub|cam><around*|[|i,k|]>>|<cell|+=>|<cell|<text|base>\<cdot\>R<rsub|IIA><around*|(|x<rsub|out>,<around*|\||x<rsub|pp>|\|>,g|)>/b<rsub|sca>>>>>
  </eqnarray>

  where <math|\<delta\>\<tau\><rsub|e>=\<delta\>l<around*|(|\<lambda\><rsub|sca,0><rsup|-1>+\<lambda\><rsub|abs><rsup|-1>|)>>
  is the total extinction, <math|x<rsub|out>=<around*|(|v<rsub|chan,k>+<with|font-series|bold|d><rsub|cam>\<cdot\><with|font-series|bold|v>|)>/b<rsub|sca>>
  the camera-resonant frequency offset, <math|x<rsub|pp>=<around*|(|\<Delta\>v+v<rsub|<around*|\||\<parallel\>|\|>>|)>/b<rsub|sca>>
  the photon's own frequency offset, and <math|g=<with|font-series|bold|d><rsub|old>\<cdot\><with|font-series|bold|d><rsub|cam>>
  the directional correlation.

  The <with|font-series|bold|R_IIA kernel> <math|R<around*|(|x<rsub|out>;
  x<rsub|pp>, g|)>> is the full angle-dependent frequency redistribution
  kernel density, precomputed at startup as a 3-D table
  (400\<times\>200\<times\>40 = 3.2 M floats in device global memory) from
  the USampler CDF (see <math|\<S\>2.3.3> for the full definition). It
  correctly captures the angle\Ufrequency correlation of R_IIA: the
  scattered frequency depends on both the incoming frequency
  <math|x<rsub|pp>> and the scattering angle <math|g>. The
  <math|1/b<rsub|sca>> factor converts from dimensionless <math|x> to
  velocity-space density, with <math|<big|int>R \<mathd\>x=1>
  (normalised).

  <subsection|Camera and channel grid>

  <math|dir_cam> (from <verbatim|dir_cam_theta>, <verbatim|dir_cam_phi>)
  defines the line of sight <with|font-series|bold|pointing into the
  domain>. The image plane is rotated into the domain frame by the
  quaternion <math|q<rsub|cam>>. The velocity channel grid uses
  <with|font-series|bold|bin centres>: <math|v<rsub|chan,k>=v<rsub|min>+<around*|(|k+0.5|)>\<delta\>v>,
  <math|\<delta\>v=<around*|(|v<rsub|max>-v<rsub|min>|)>/n<rsub|chan>>.

  <subsection|Step 2 --- Non-scattering ray tracing>

  A second module integrates the transfer equation along each camera ray,
  cell by cell, with the analytic solution of
  <math|\<mathd\>I/\<mathd\>\<tau\>=-I+S> per cell:

  <\eqnarray>
    <tformat|<table|<row|<cell|\<alpha\><rsub|s>>|<cell|=>|<cell|\<lambda\><rsub|sca,0><rsup|-1>\<phi\><around*|(|v<rsub|cam>/b<rsub|sca>|)>>>|<row|<cell|\<alpha\><rsub|t>>|<cell|=>|<cell|\<alpha\><rsub|s>+\<lambda\><rsub|abs><rsup|-1>>>|<row|<cell|\<delta\>\<tau\>>|<cell|=>|<cell|\<alpha\><rsub|t>\<delta\>l>>|<row|<cell|S>|<cell|=>|<cell|<around*|(|\<alpha\><rsub|s>/\<alpha\><rsub|t>|)>s<rsub|cam><around*|[|i,k|]>>>|<row|<cell|I<rsub|k><rprime|'>>|<cell|=>|<cell|I<rsub|k>\<mathd\>e<rsup|-\<delta\>\<tau\>>+S<around*|(|1-\<mathd\>e<rsup|-\<delta\>\<tau\>>|)>>>>>
  </eqnarray>

  When the imaging integrator's Voigt table is not built
  (<verbatim|build_tables=false> to avoid const-memory pool overflow), the
  <math|\<phi\>> fallback blends Gaussian core with Lorentzian wing:
  <math|H=max<around*|(|<text|exp><around*|(|-u<rsup|2>|)>,a/<around*|(|<sqrt|\<pi\>><around*|(|u<rsup|2>+a<rsup|2>|)>|)>|)>>,
  essential for the Lorentzian wing at large frequency offsets.

  <subsection|Validation>

  The imaging module has been validated against Neufeld (1990) eq. (2.24)
  for a plane-parallel scattering slab with isotropic midplane injection:

  <\itemize>
    <item><with|font-series|bold|Escaped photon spectrum>: the angle-averaged
    emergent <math|<text|med>|x|> matches the golden values within 0.3% for
    <math|\<tau\><rsub|0>=200, 500, 2000, 8000>.

    <item><with|font-series|bold|Imaging spectrum>: the formal-transfer
    double-peak <with|font-series|bold|moves outward> with increasing
    <math|\<tau\><rsub|0>>, following the Neufeld
    <math|<around*|(|a\<tau\><rsub|0>|)><rsup|1/3>> scaling:

    <\equation>
      \<tau\><rsub|0>=200\<rightarrow\>\<pm\>2.19,<space|1em>2000\<rightarrow\>\<pm\>5.31,<space|1em>8000\<rightarrow\>\<pm\>9.06<space|1em><around*|(|<text|Neufeld:|space>2.73,\\;5.89,\\;9.34|)>
    </equation>

    <item><with|font-series|bold|Thin-slab normalization>: the imaging cube
    matches the analytic <math|I=j\<cdot\>L> to within 0.01% for optically
    thin, non-absorbing slabs.
  </itemize>

  \;

  \;
</body>

<\initial>
  <\collection>
    <associate|page-medium|paper>
    <associate|prog-scripts|python>
  </collection>
</initial>

<\references>
  <\collection>
    <associate|auto-1|<tuple|1|1>>
    <associate|auto-10|<tuple|2.1|4>>
    <associate|auto-11|<tuple|2.2|4>>
    <associate|auto-12|<tuple|2.3|4>>
    <associate|auto-13|<tuple|2.3.1|4>>
    <associate|auto-14|<tuple|2.3.2|5>>
    <associate|auto-15|<tuple|3|5>>
    <associate|auto-16|<tuple|3.1|5>>
    <associate|auto-17|<tuple|3.1.1|5>>
    <associate|auto-18|<tuple|3.1.2|5>>
    <associate|auto-19|<tuple|3.2|6>>
    <associate|auto-2|<tuple|1.1|1>>
    <associate|auto-20|<tuple|3.2.1|6>>
    <associate|auto-21|<tuple|3.2.2|6>>
    <associate|auto-22|<tuple|3.3|6>>
    <associate|auto-3|<tuple|1.2|1>>
    <associate|auto-4|<tuple|1.3|1>>
    <associate|auto-5|<tuple|1.3.1|2>>
    <associate|auto-6|<tuple|1.3.2|2>>
    <associate|auto-7|<tuple|1.3.3|2>>
    <associate|auto-8|<tuple|1.3.4|3>>
    <associate|auto-9|<tuple|2|3>>
  </collection>
</references>

<\auxiliary>
  <\collection>
    <\associate|toc>
      <vspace*|1fn><with|font-series|<quote|bold>|math-font-series|<quote|bold>|1<space|2spc>General
      and Basic Information> <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-1><vspace|0.5fn>

      <with|par-left|<quote|1tab>|1.1<space|2spc>Conventions
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-2>>

      <with|par-left|<quote|1tab>|1.2<space|2spc>Photon packets
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-3>>

      <with|par-left|<quote|1tab>|1.3<space|2spc>Physical picture
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-4>>

      <with|par-left|<quote|2tab>|1.3.1<space|2spc>"Scattering"
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-5>>

      <with|par-left|<quote|2tab>|1.3.2<space|2spc><with|font-series|<quote|bold>|"Absorption">
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-6>>

      <with|par-left|<quote|2tab>|1.3.3<space|2spc>Population numbers of the
      target particles <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-7>>

      <with|par-left|<quote|2tab>|1.3.4<space|2spc>Scattering cross sections
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-8>>

      <vspace*|1fn><with|font-series|<quote|bold>|math-font-series|<quote|bold>|2<space|2spc>Methods
      on the Kratos side> <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-9><vspace|0.5fn>

      <with|par-left|<quote|1tab>|2.1<space|2spc>Photon packet proper
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-10>>

      <with|par-left|<quote|1tab>|2.2<space|2spc>Excitation
      \ <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-11>>

      <with|par-left|<quote|1tab>|2.3<space|2spc>Evolution
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-12>>

      <with|par-left|<quote|2tab>|2.3.1<space|2spc>Propagation
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-13>>

      <with|par-left|<quote|2tab>|2.3.2<space|2spc>Scattering event
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-14>>

      <vspace*|1fn><with|font-series|<quote|bold>|math-font-series|<quote|bold>|3<space|2spc>Methods
      on the Python side> <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-15><vspace|0.5fn>

      <with|par-left|<quote|1tab>|3.1<space|2spc>Data on mesh
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-16>>

      <with|par-left|<quote|2tab>|3.1.1<space|2spc>To Kratos
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-17>>

      <with|par-left|<quote|2tab>|3.1.2<space|2spc>From Kratos
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-18>>

      <with|par-left|<quote|1tab>|3.2<space|2spc>Particle data
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-19>>

      <with|par-left|<quote|2tab>|3.2.1<space|2spc>To Kratos
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-20>>

      <with|par-left|<quote|2tab>|3.2.2<space|2spc>From Kratos
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-21>>

      <with|par-left|<quote|1tab>|3.3<space|2spc>Iterations
      <datoms|<macro|x|<repeat|<arg|x>|<with|font-series|medium|<with|font-size|1|<space|0.2fn>.<space|0.2fn>>>>>|<htab|5mm>>
      <no-break><pageref|auto-22>>
    </associate>
  </collection>
</auxiliary>