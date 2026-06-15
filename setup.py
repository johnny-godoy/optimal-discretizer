from setuptools import setup, Extension

try:
    from Cython.Build import cythonize
    import numpy as np

    extensions = cythonize(
        [
            Extension(
                "optimal_discretizer._core",
                sources=["src/optimal_discretizer/_core.pyx"],
                include_dirs=[np.get_include()],
                extra_compile_args=["-O3"],
            )
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
