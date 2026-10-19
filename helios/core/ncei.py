"""
DSCOVR Faraday cup plasma from NOAA's own archive at NCEI, for the years CDAWeb does not
carry (CDAWeb's DSCOVR_H1_FC ends 27 June 2019).

The NCEI space weather archive (https://www.ngdc.noaa.gov/dscovr/, served from
https://archive.data.noaa.gov/satellite-spaceweather) holds one gzipped netCDF file per UTC
day and product. The f1m product is NOAA's 1-minute proton moments (density, bulk velocity
in GSE, temperature) with an overall quality flag, the definitive counterpart of the
real-time solar wind stream. The files are netCDF-3 ("classic"), read here with numpy so
no netCDF library is needed.
"""
import gzip
import re
import struct
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd

NCEI_BUCKET = "https://archive.data.noaa.gov/satellite-spaceweather"
F1M_PREFIX = "DSCOVR/DSCOVR/FC/f1m"

_NC_TYPES = {1: ">i1", 2: "S1", 3: ">i2", 4: ">i4", 5: ">f4", 6: ">f8"}


def read_netcdf3(data: bytes) -> Dict[str, Tuple[np.ndarray, Dict[str, Any]]]:
    """Variables of a netCDF-3 classic or 64-bit-offset file: {name: (values, attributes)}."""
    if data[:3] != b"CDF" or data[3] not in (1, 2):
        raise ValueError("not a netCDF-3 file")
    offset_size = 8 if data[3] == 2 else 4
    pos = 4

    def ints(n=1):
        nonlocal pos
        out = struct.unpack_from(f">{n}i", data, pos)
        pos += 4 * n
        return out if n > 1 else out[0]

    def name():
        nonlocal pos
        n = ints()
        s = data[pos:pos + n].decode("utf-8")
        pos += (n + 3) // 4 * 4
        return s

    def values(nc_type, n):
        nonlocal pos
        dt = np.dtype(_NC_TYPES[nc_type])
        size = dt.itemsize * n
        arr = np.frombuffer(data, dt, n, pos)
        pos += (size + 3) // 4 * 4
        return arr.tobytes().decode("utf-8", "replace") if nc_type == 2 else arr

    def attributes():
        tag, n = ints(2)
        out = {}
        for _ in range(n if tag else 0):
            key = name()
            nc_type, count = ints(2)
            out[key] = values(nc_type, count)
        return out

    numrecs = ints()
    tag, ndims = ints(2)
    dims = []
    for _ in range(ndims if tag else 0):
        dims.append((name(), ints()))
    attributes()  # global attributes are not needed
    tag, nvars = ints(2)
    specs = []
    for _ in range(nvars if tag else 0):
        vname = name()
        ndim = ints()
        dimids = struct.unpack_from(f">{ndim}i", data, pos)
        pos += 4 * ndim
        attrs = attributes()
        nc_type, vsize = ints(2)
        begin = struct.unpack_from(">q" if offset_size == 8 else ">i", data, pos)[0]
        pos += offset_size
        specs.append((vname, dimids, attrs, nc_type, vsize, begin))

    record_vars = [s for s in specs if s[1] and dims[s[1][0]][1] == 0]
    # Records interleave the record variables; with only one, there is no padding.
    recsize = record_vars[0][4] if len(record_vars) == 1 else sum(s[4] for s in record_vars)
    out = {}
    for vname, dimids, attrs, nc_type, vsize, begin in specs:
        dt = np.dtype(_NC_TYPES[nc_type])
        shape = [dims[d][1] for d in dimids]
        if dimids and shape[0] == 0:  # record variable
            per_record = int(np.prod(shape[1:])) if len(shape) > 1 else 1
            arr = np.concatenate([np.frombuffer(data, dt, per_record, begin + r * recsize)
                                  for r in range(numrecs)]) if numrecs else np.empty(0, dt)
            shape[0] = numrecs
        else:
            arr = np.frombuffer(data, dt, int(np.prod(shape)) if shape else 1, begin)
        out[vname] = (arr.reshape(shape).astype(dt.newbyteorder("=")), attrs)
    return out


def f1m_listing_url(day: datetime) -> str:
    """S3 listing of the f1m file(s) of one UTC day (the name carries the processing time)."""
    return f"{NCEI_BUCKET}?list-type=2&prefix={F1M_PREFIX}/{day:%Y/%m}/oe_f1m_dscovr_s{day:%Y%m%d}"


def f1m_frame(nc_gz: bytes) -> pd.DataFrame:
    """Proton speed, density and temperature of one f1m file (empty bytes: no file). Missing values
    (-99999) and minutes NOAA flags as not good (overall_quality != 0) or of reduced proton quality
    become missing, and so do good minutes with fewer than three good ones in the five centred on them.
    Both matter: in fast wind (above about 650 km/s) the speeds NOAA leaves at overall_quality 0 read
    30-70 % below WIND's (storms of 2024-2026); the reduced-quality flag marks those minutes (and 30 %
    of the good ones) except single minutes of about 270 km/s inside long flagged stretches."""
    if not nc_gz:
        return pd.DataFrame()
    v = read_netcdf3(gzip.decompress(nc_gz))
    index = pd.to_datetime(v["time"][0], unit="ms", utc=True)
    good = pd.Series((v["overall_quality"][0] == 0) & (v["reduced_proton_quality_flag"][0] == 0)
                     & (v["proton_speed"][0] > -99999.0))
    good = (good & (good.astype(float).rolling(5, center=True, min_periods=1).sum() >= 3)).to_numpy()
    out = pd.DataFrame(index=index)
    for col, var in (("speed", "proton_speed"), ("density", "proton_density"), ("temperature", "proton_temperature")):
        x = v[var][0].astype(float)
        out[col] = np.where(good & (x > -99999.0), x, np.nan)
    out.index.name = "time"
    return out


async def fetch_f1m_day(fetch_text: Callable, fetch_bytes: Callable, day: datetime) -> Optional[bytes]:
    """The gzipped f1m file of one UTC day; b"" when NCEI has none for the day, None when unreachable."""
    listing = await fetch_text(f1m_listing_url(day))
    if listing is None:
        return None
    keys = sorted(re.findall(r"<Key>([^<]+\.nc\.gz)</Key>", listing))
    if not keys:
        return b""
    return await fetch_bytes(f"{NCEI_BUCKET}/{keys[-1]}")  # newest processing last
