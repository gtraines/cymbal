"""
Cython header file for cymbal.utils.config.

IMPORTANT — all config types (SystemConfig, GPSConfig, OSDConfig, etc.) are
Python *dataclasses*, not Cython extension types (cdef class).  A Cython .pxd
file cannot declare Python dataclasses as typed Cython types; attempting to do
so would require rewriting them as cdef classes, which would break the
dataclass semantics (field defaults, from_dict, asdict, etc.).

What this file IS useful for:
  - Documents that config.pyx exports no cdef-level symbols.
  - Acts as a placeholder so that ``from cymbal.utils.config cimport ...``
    syntax gives a clear compile error rather than a silent fallback when
    someone attempts to use Cython typing for config objects.
  - Tracks future work: if individual sub-configs (e.g. SBUSConfig, OSDConfig)
    are ever converted to lightweight cdef structs/classes for hot-path use,
    their declarations belong here.

Callers that need config objects should use the normal Python import:
    from cymbal.utils.config import SystemConfig

There is no cdef typing available for these types at this time.
"""

# No cdef/cpdef declarations — config types are Python dataclasses.
# This file intentionally left without extension-type declarations.
