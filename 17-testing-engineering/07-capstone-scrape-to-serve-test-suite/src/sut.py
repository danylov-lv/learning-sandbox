"""Auto-generated SUT shim -- DO NOT EDIT BY HAND.

Exposes the implementation under test as `src.sut`. Learner tests must
import from here (`from src.sut import name` or `import src.sut as sut`),
never from `src.impl` directly -- that indirection is what lets the grading
harness swap in a mutant by setting SUT_IMPL_PATH before this module is
imported. Regenerate with harness.mutation.write_sut_shim if this file is
ever lost or the task's public API changes.
"""

import importlib.util
import os

_impl_path = os.environ.get("SUT_IMPL_PATH")

if _impl_path:
    _spec = importlib.util.spec_from_file_location("_sut_impl_external", _impl_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
else:
    from . import impl as _mod

_PUBLIC_NAMES = ('Price', 'parse_price', 'normalize_record', 'CatalogRepo', 'ProductCache', 'make_app', 'PRODUCT_SCHEMA', 'CATALOG_PAGE_SCHEMA', 'ERROR_SCHEMA',)
globals().update({k: v for k, v in vars(_mod).items() if k in _PUBLIC_NAMES})
