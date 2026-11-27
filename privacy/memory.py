import ctypes
import logging

import numpy as np
from .timing import measure

_libc = ctypes.CDLL(None, use_errno=True)
_locked = set()
_warned = False


def lock(array: np.ndarray) -> np.ndarray:
    """Best effort for contiguous, application-visible buffers on Linux."""
    global _warned
    if array.flags.c_contiguous and array.nbytes:
        address = array.ctypes.data
        if _libc.mlock(ctypes.c_void_p(address), ctypes.c_size_t(array.nbytes)) == 0:
            _locked.add((address, array.nbytes))
        elif not _warned:
            logging.warning("mlock unavailable; continuing with unlocked memory.")
            _warned = True
    return array


@measure("wipe")
def wipe(array: np.ndarray) -> None:
    """Overwrite before releasing any best-effort memory lock."""
    array.fill(0)
    region = (array.ctypes.data, array.nbytes)
    if region in _locked:
        _libc.munlock(ctypes.c_void_p(region[0]), ctypes.c_size_t(region[1]))
        _locked.discard(region)
