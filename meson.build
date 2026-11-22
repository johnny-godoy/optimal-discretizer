# Build of the package: the Python modules are copied, and the Cython kernel is compiled.
# meson-python reads the version of the distribution from pyproject.toml.
project(
  'optimal-discretizer',
  'c',
  'cython',
  meson_version: '>=1.6.0',
  default_options: ['buildtype=release', 'b_ndebug=if-release', 'c_std=c11'],
)

# A missing Cython or C compiler stops `project()` above with an error, so a build never ships without the kernel.
cython = meson.get_compiler('cython')
if cython.version().version_compare('<3.1.0')
  error('Cython 3.1.0 or later is required, found ' + cython.version())
endif

python = import('python').find_installation(pure: false)

subdir('src/optimal_discretizer')
