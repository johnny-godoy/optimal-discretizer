"""Let the tools import the package from ``src`` in a meson-python editable install.

The editable install of meson-python puts its own finder first in ``sys.meta_path``. That finder loads the Python
modules of the package itself and reports a virtual path as the location of each package. Two tools break on it:
beartype checks only the modules that the standard path finder loads, and import-linter reads the files under the
reported path, which does not exist. ``prefer_source_tree`` puts ``src`` first on ``sys.path`` and moves the
meson-python finder behind the path finder. The path finder then loads each Python module from ``src``, and only the
compiled kernel, which ``src`` does not hold, comes from the meson-python finder, which rebuilds it when its source
changes. Without an editable install, for example in a test of a built wheel, the function changes nothing.
"""

import importlib
import importlib.util
import sys
from pathlib import Path

# meson-python names the loader module of the editable install after the package.
EDITABLE_LOADER = "_optimal_discretizer_editable_loader"


def prefer_source_tree(source_directory: Path) -> bool:
    """Put ``source_directory`` first on the path, and the meson-python finder behind the path finder.

    Parameters
    ----------
    source_directory : Path
        The directory that holds the package, ``src`` of the repository.

    Returns
    -------
    bool
        ``True`` if an editable install was found and the finders were reordered.

    """
    if importlib.util.find_spec(EDITABLE_LOADER) is None:
        return False
    finder_class = importlib.import_module(EDITABLE_LOADER).MesonpyMetaFinder
    meson_finders = [finder for finder in sys.meta_path if isinstance(finder, finder_class)]
    sys.path.insert(0, str(source_directory))
    sys.meta_path[:] = [finder for finder in sys.meta_path if finder not in meson_finders] + meson_finders
    return True
