import os
import requests
from .lamda_format import load_lamda

LAMDA_URL = 'https://home.strw.leidenuniv.nl/~moldata/datafiles/'
CACHE_DIR = os.path.expanduser('~/.line_rt_interface/lamda_cache')


def _get_cache_path(species):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f'{species.lower()}.dat')


def _load_embedded(species):
    from pathlib import Path
    embedded_dir = Path(__file__).parent / 'embedded'
    fname = f'{species.lower()}.dat'
    path = embedded_dir / fname
    if path.exists():
        with open(path) as f:
            return load_lamda(f.read())
    return None


def fetch_species(species, force_download=False):
    cache_path = _get_cache_path(species)

    if not force_download and os.path.exists(cache_path):
        with open(cache_path) as f:
            return load_lamda(f.read())

    result = _load_embedded(species)
    if result is not None:
        return result

    url = f'{LAMDA_URL}{species.lower()}.dat'
    try:
        resp = requests.get(url, timeout=15, proxies={
            'http': 'http://127.0.0.1:7892',
            'https': 'http://127.0.0.1:7892',
        })
        resp.raise_for_status()
        content = resp.text
    except Exception:
        raise RuntimeError(
            f'Failed to download LAMDA data for {species}. '
            f'Available at: {LAMDA_URL}'
        )

    with open(cache_path, 'w') as f:
        f.write(content)
    return load_lamda(content)


def get_cached_species():
    os.makedirs(CACHE_DIR, exist_ok=True)
    return [fn.replace('.dat', '') for fn in os.listdir(CACHE_DIR)
            if fn.endswith('.dat')]


def list_available():
    return ['CO', 'OI', 'OH', 'H2O', 'HCN', 'HCO+', 'CS', 'NH3',
            'H2CO', 'CH3OH', 'SO', 'SO2', 'SiO', 'NO', 'CN', 'CH',
            'H2S', 'N2H+', 'HNC', 'HCS+', 'OCS', 'HDO', 'D2H+',
            'HC3N', 'HC5N', 'HC7N', 'HNCO', 'H3O+', 'C2H', 'C2S',
            'C3H2', 'C4H', 'CH2', 'CH3OCHO', 'CH3CN', 'PH3']
