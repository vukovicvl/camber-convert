"""Dewesoft reader (.dxd / .d7d) -- STUB.

Not implemented yet. Dewesoft's native formats are proprietary/binary. The two
realistic paths:

  A) Ask users to export to a supported open format from DewesoftX (CSV or,
     ideally, a well-defined columnar export), then use the CSV reader. This is
     the pragmatic near-term option and needs no new code.

  B) Implement true native reading. Dewesoft publishes a DWDataReaderLib
     (a C library with a Python wrapper) for reading .dxd/.d7d files. If native
     support is wanted, wrap that library here, map channels -> Sensors and
     samples -> Measurements (same shape as the other readers), and return a
     Dataset.

Until then this raises a helpful error pointing the user to option A.
"""

from __future__ import annotations

from ..model import Dataset
from .base import register


@register(".dxd", ".d7d")
def read_dewesoft(path: str) -> Dataset:  # pragma: no cover - stub
    raise NotImplementedError(
        "Native Dewesoft reading is not implemented yet. For now, export the "
        "recording to CSV from DewesoftX and convert that. Native .dxd/.d7d "
        "support would wrap Dewesoft's DWDataReaderLib -- see the module "
        "docstring."
    )
