"""
Reading NISAR Level-2 HDF5 products without loading whole files.

NISAR products are multi-gigabyte HDF5 files. These helpers find the right
grids by name (so small layout differences between product versions don't
break anything), read only the part that covers an area, and print the file
tree when something unexpected turns up.

Tested against synthetic files built to the published GCOV layout. The first
run on a real product may need a name added to the candidate lists below:
run `python pipeline/water_dance.py inspect FILE.h5` and compare.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

import h5py
import numpy as np
from rasterio.warp import transform_bounds

# Candidate names, most likely first.
POLARISATIONS = {"HH": ["HHHH"], "HV": ["HVHV"], "VV": ["VVVV"]}
X_NAMES = ["xCoordinates", "x_coordinates", "xCoordinate"]
Y_NAMES = ["yCoordinates", "y_coordinates", "yCoordinate"]
TIMESTAMP = re.compile(r"(\d{8})T\d{6}")


@dataclass
class Grid:
    """One product's cropped grid: linear power per polarisation plus georeferencing."""
    acquired: date
    epsg: int
    x: np.ndarray          # pixel-centre x coordinates of the crop
    y: np.ndarray          # pixel-centre y coordinates of the crop
    bands: dict            # {"HH": 2-D float32 array, ...} in linear power (gamma-naught)
    source: str


def list_tree(path):
    """Every dataset in the file with its shape and type, for troubleshooting."""
    lines = []
    with h5py.File(path, "r") as f:
        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                lines.append(f"{name}  {obj.shape}  {obj.dtype}")
        f.visititems(visit)
    return lines


def _find_grid_group(f):
    """The group holding the backscatter rasters, e.g. /science/LSAR/GCOV/grids/frequencyA."""
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Group) and any(n in obj for names in POLARISATIONS.values() for n in names):
            found.append(name)
    f.visititems(visit)
    if not found:
        raise KeyError("No HHHH/HVHV/VVVV rasters found. Run the inspect command and add the names you see.")
    # Prefer frequency A (the main L-band bandwidth) when a product has two.
    found.sort(key=lambda n: (not n.endswith("frequencyA"), len(n)))
    return f[found[0]]


def _first(group, names):
    for n in names:
        if n in group:
            return group[n]
    raise KeyError(f"None of {names} in {group.name}")


def _epsg(group):
    """EPSG code of the grid, stored on the 'projection' dataset in NISAR L2 products."""
    for holder in (group, group.parent):
        if "projection" in holder:
            proj = holder["projection"]
            for key in ("epsg_code", "epsg"):
                if key in proj.attrs:
                    return int(np.asarray(proj.attrs[key]).ravel()[0])
            value = np.asarray(proj[()]).ravel()
            if value.size and 1000 < int(value[0]) < 100000:
                return int(value[0])
    raise KeyError("Could not find the grid's EPSG code (expected a 'projection' dataset).")


def acquisition_date(path, f=None):
    """First timestamp in the ASF file name; falls back to the identification group."""
    hits = TIMESTAMP.findall(str(path))
    if hits:
        return datetime.strptime(hits[0], "%Y%m%d").date()
    if f is not None:
        for key in ("science/LSAR/identification/zeroDopplerStartTime",
                    "science/LSAR/identification/referenceZeroDopplerStartTime"):
            if key in f:
                text = f[key][()].decode() if isinstance(f[key][()], bytes) else str(f[key][()])
                return datetime.fromisoformat(text[:19]).date()
    raise ValueError(f"Could not work out the acquisition date of {path}")


def _index_range(coords, lo, hi):
    """Indices [i0, i1) of coordinates inside [lo, hi], whichever way the axis runs."""
    inside = np.nonzero((coords >= lo) & (coords <= hi))[0]
    if inside.size == 0:
        return None
    return int(inside.min()), int(inside.max()) + 1


def read_crop(path, bbox_lonlat, polarisations=("HH", "HV"), margin_m=2000):
    """Read only the part of a GCOV product that covers bbox (west, south, east, north)."""
    with h5py.File(path, "r") as f:
        group = _find_grid_group(f)
        epsg = _epsg(group)
        x = np.asarray(_first(group, X_NAMES)[()], dtype="float64")
        y = np.asarray(_first(group, Y_NAMES)[()], dtype="float64")
        west, south, east, north = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox_lonlat, densify_pts=21)
        pad = margin_m if epsg != 4326 else margin_m / 111_000
        xr = _index_range(x, west - pad, east + pad)
        yr = _index_range(y, south - pad, north + pad)
        if xr is None or yr is None:
            return None  # this product does not touch the area
        bands = {}
        for pol in polarisations:
            names = POLARISATIONS[pol]
            name = next((n for n in names if n in group), None)
            if name is None:
                continue
            raw = group[name][yr[0]:yr[1], xr[0]:xr[1]].astype("float32")
            raw[~np.isfinite(raw) | (raw <= 0)] = np.nan   # fill and invalid pixels
            bands[pol] = raw
        if "HH" not in bands and "VV" not in bands:
            raise KeyError(f"{path}: no co-polarised band (HH or VV) found")
        return Grid(
            acquired=acquisition_date(path, f),
            epsg=epsg,
            x=x[xr[0]:xr[1]],
            y=y[yr[0]:yr[1]],
            bands=bands,
            source=str(path),
        )


# ---------------------------------------------------------------- GUNW (Part 3)

DEFAULT_CENTER_FREQUENCY = 1.257e9   # NISAR L-band, Hz (about 24 cm wavelength)
SPEED_OF_LIGHT = 299_792_458.0


@dataclass
class PairGrid:
    """One interferogram's cropped layers. Phase is in radians."""
    reference: date
    secondary: date
    epsg: int
    x: np.ndarray
    y: np.ndarray
    phase: np.ndarray
    coherence: np.ndarray | None
    components: np.ndarray | None
    ionosphere: np.ndarray | None
    wavelength: float
    source: str


def _find_datasets(f, names):
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.rsplit("/", 1)[-1] in names:
            found.append(name)
    f.visititems(visit)
    found.sort(key=lambda n: ("frequencyA" not in n, len(n)))
    return found


def pair_dates(path):
    stamps = sorted({datetime.strptime(d, "%Y%m%d").date() for d in TIMESTAMP.findall(str(path))})
    if len(stamps) < 2:
        raise ValueError(f"Could not find two acquisition dates in {path}")
    first = stamps[0]
    later = [d for d in stamps if (d - first).days >= 6]   # skip timestamps that only cross midnight
    return first, (later[0] if later else stamps[-1])


def read_gunw_crop(path, bbox_lonlat, margin_m=2000):
    """Read only the part of a GUNW product (unwrapped interferogram) that covers bbox."""
    with h5py.File(path, "r") as f:
        hits = _find_datasets(f, {"unwrappedPhase"})
        if not hits:
            raise KeyError("No unwrappedPhase dataset. Run the inspect command and add the name you see.")
        phase_ds = f[hits[0]]
        layers = phase_ds.parent
        grid = layers
        while grid.name != "/" and not any(n in grid for n in X_NAMES):
            grid = grid.parent
        if not any(n in grid for n in X_NAMES):
            raise KeyError("Could not find xCoordinates/yCoordinates for the interferogram grid.")
        epsg = _epsg(grid)
        x = np.asarray(_first(grid, X_NAMES)[()], dtype="float64")
        y = np.asarray(_first(grid, Y_NAMES)[()], dtype="float64")
        west, south, east, north = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox_lonlat, densify_pts=21)
        pad = margin_m if epsg != 4326 else margin_m / 111_000
        xr, yr = _index_range(x, west - pad, east + pad), _index_range(y, south - pad, north + pad)
        if xr is None or yr is None:
            return None

        def layer(names):
            name = next((n for n in names if n in layers), None)
            if name is None or layers[name].shape != phase_ds.shape:
                return None
            return layers[name][yr[0]:yr[1], xr[0]:xr[1]].astype("float32")

        phase = phase_ds[yr[0]:yr[1], xr[0]:xr[1]].astype("float32")
        phase[~np.isfinite(phase)] = np.nan
        freq_hits = _find_datasets(f, {"centerFrequency"})
        frequency = float(np.asarray(f[freq_hits[0]][()]).ravel()[0]) if freq_hits else DEFAULT_CENTER_FREQUENCY
        reference, secondary = pair_dates(path)
        return PairGrid(
            reference=reference, secondary=secondary, epsg=epsg,
            x=x[xr[0]:xr[1]], y=y[yr[0]:yr[1]], phase=phase,
            coherence=layer(["coherenceMagnitude", "coherence"]),
            components=layer(["connectedComponents"]),
            ionosphere=layer(["ionospherePhaseScreen"]),
            wavelength=SPEED_OF_LIGHT / frequency,
            source=str(path),
        )
