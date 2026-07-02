"""National Instruments TDMS reader -- STUB.

Not implemented yet. This file marks the extension point and documents how to
finish it, so the coding agent (or a contributor) has a clear target.

Implementation plan:
  1. Add the optional dependency `npTDMS` (see pyproject.toml [project.optional
     -dependencies] -> "tdms"). Install with:  pip install "camber-convert[tdms]"
  2. from nptdms import TdmsFile
     tdms = TdmsFile.read(path)
  3. TDMS is hierarchical: file -> groups -> channels. Map each channel to a
     Sensor (channel name -> sensor id; channel properties often carry unit and
     axis). Map channel samples to Measurements. TDMS channels usually store a
     wf_start_time property and a wf_increment (sample spacing) -- build the
     timestamp for sample n as start + n * increment rather than storing a
     timestamp per row in the source.
  4. Return a Dataset just like read_csv does.

Keep the heavy import inside the function so importing camber_convert never
requires npTDMS unless a .tdms file is actually read.
"""

from __future__ import annotations

from ..model import Dataset
from .base import register


@register(".tdms")
def read_tdms(path: str) -> Dataset:  # pragma: no cover - stub
    raise NotImplementedError(
        "TDMS reading is not implemented yet. Install the optional dependency "
        "with `pip install camber-convert[tdms]` and implement read_tdms() "
        "using nptdms.TdmsFile. See the module docstring for the plan."
    )
