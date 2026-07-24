import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class SpeciesData:
    name: str
    n_levels: int
    levels: np.ndarray
    n_transitions: int
    transitions: np.ndarray
    collision_partners: List[Dict] = field(default_factory=list)

    def get_Einstein_A(self, upper, lower):
        mask = (self.transitions[:, 0] == upper) & (self.transitions[:, 1] == lower)
        match = self.transitions[mask]
        return float(match[0, 2]) if len(match) > 0 else 0.0

    def get_level_energy(self, level_idx):
        return float(self.levels[level_idx, 0])

    def get_level_weight(self, level_idx):
        return float(self.levels[level_idx, 1])

    def get_nu(self, upper, lower):
        mask = (self.transitions[:, 0] == upper) & (self.transitions[:, 1] == lower)
        match = self.transitions[mask]
        return float(match[0, 3]) if len(match) > 0 else 0.0

    def get_collision_rate(self, upper, lower, T, partner='H2'):
        for cp in self.collision_partners:
            if cp['species'] == partner:
                idx = np.where((cp['trans_indices'][:, 0] == upper)
                               & (cp['trans_indices'][:, 1] == lower))[0]
                if len(idx) == 0:
                    return 0.0
                rates = cp['rates'][idx[0]]
                return float(np.interp(T, cp['temps'], rates))
        return 0.0


def _find_section(lines, marker, start=0):
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if line and not line.startswith('!'):
            return i
        if marker in line:
            return i
        i += 1
    return -1


def _skip_non_section_header(lines, i):
    while i < len(lines) and lines[i].strip().startswith('!'):
        i += 1
    return i


def load_lamda(content):
    if isinstance(content, str):
        lines = content.splitlines()
    else:
        lines = [ln.decode() if isinstance(ln, bytes) else ln for ln in content]

    lines = [ln.strip() for ln in lines]
    mol_idx = -1
    for i, ln in enumerate(lines):
        if ln.startswith('!MOLECULE') or ln.startswith('! MOLECULE'):
            mol_idx = i + 1
            break
    name = lines[mol_idx] if mol_idx >= 0 and mol_idx < len(lines) else 'unknown'

    nlev_idx = -1
    for i in range(mol_idx, len(lines)):
        if 'NUMBER OF ENERGY LEVELS' in lines[i]:
            nlev_idx = i
            break
    n_levels = int(lines[nlev_idx + 1]) if nlev_idx >= 0 else 0

    ntrans_idx = -1
    for i in range(nlev_idx + 1, len(lines)):
        if 'NUMBER OF RADIATIVE TRANSITIONS' in lines[i]:
            ntrans_idx = i
            break
    n_transitions = int(lines[ntrans_idx + 1]) if ntrans_idx >= 0 else 0

    levels = []
    lev_start = nlev_idx + 3
    for i in range(n_levels):
        parts = lines[lev_start + i].split()
        if len(parts) >= 3:
            levels.append([float(parts[1]), float(parts[2])])
    levels = np.array(levels, dtype=np.float64)

    transitions = []
    trans_start = ntrans_idx + 3
    for i in range(n_transitions):
        parts = lines[trans_start + i].split()
        if len(parts) >= 4:
            transitions.append([int(parts[1]) - 1, int(parts[2]) - 1,
                                float(parts[3]), float(parts[4])])
    transitions = np.array(transitions, dtype=np.float64)

    coll_partners = []
    cp_idx = trans_start + n_transitions
    while cp_idx < len(lines):
        line = lines[cp_idx].strip()
        if 'NUMBER OF COLL PARTNERS' in line or 'NUMBER OF COLLISION PARTNERS' in line:
            break
        cp_idx += 1

    if cp_idx < len(lines):
        n_coll_partners = int(lines[cp_idx + 1])
        ci = cp_idx + 2
        for _ in range(n_coll_partners):
            while ci < len(lines) and (
                lines[ci].strip().startswith('!') or not lines[ci].strip()):
                ci += 1
            if ci >= len(lines):
                break
            partner_name = lines[ci].strip()
            ci += 1
            while ci < len(lines) and ('NUMBER OF COLL TRANSITIONS' not in lines[ci]):
                ci += 1
            n_coll_trans = int(lines[ci + 1])
            ci += 2
            while ci < len(lines) and ('NUMBER OF COLL TEMPS' not in lines[ci]):
                ci += 1
            n_coll_temps = int(lines[ci + 1])
            ci += 2
            coll_temps = np.array(
                [float(x) for x in lines[ci].split()])
            ci += 1

            rates = []
            for _ in range(n_coll_trans):
                vals = [float(x) for x in lines[ci].split()]
                rates.append(vals)
                ci += 1
            rates = np.array(rates, dtype=np.float64)

            trans_indices = []
            for n in range(n_coll_trans):
                trans_indices.append(
                    [int(transitions[n, 0]), int(transitions[n, 1])])
            trans_indices = np.array(trans_indices, dtype=np.int64)

            coll_partners.append({
                'species': partner_name,
                'n_trans': n_coll_trans,
                'n_temps': n_coll_temps,
                'temps': coll_temps,
                'rates': rates,
                'trans_indices': trans_indices,
            })

    return SpeciesData(
        name=name,
        n_levels=n_levels,
        levels=levels,
        n_transitions=n_transitions,
        transitions=transitions,
        collision_partners=coll_partners,
    )
