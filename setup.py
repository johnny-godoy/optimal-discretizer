"""Setup script for building the Cython extension module."""
from setuptools import Extension, setup

try:
    import numpy as np
    from Cython.Build import cythonize

    extensions = cythonize(
        [
            Extension(
                "src._core",
                sources=["src/_core.pyx"],
                include_dirs=[np.get_include()],
                extra_compile_args=["-O3"],
            ),
        ],
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
        },
    )
except ImportError:
    extensions = []

setup(ext_modules=extensions)
