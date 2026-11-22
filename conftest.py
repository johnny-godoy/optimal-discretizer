"""Give pytest the collection hook of the documentation examples.

pytest calls the ``pytest_collect_file`` hook of a ``conftest.py`` only for the files below that ``conftest.py``. The
examples are in ``README.md``, ``docs/`` and ``src/``, so the hook must be in the root ``conftest.py``.
``tests/docs/conftest.py`` holds the configuration.
"""

from tests.docs.conftest import pytest_collect_file

__all__ = ["pytest_collect_file"]
