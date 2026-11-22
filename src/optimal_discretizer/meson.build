# The Python sources of the package and the compiled kernel of the domain layer.
package_dir = python.get_install_dir() / 'optimal_discretizer'

python.install_sources(['__init__.py', 'py.typed'], subdir: 'optimal_discretizer')

foreach layer : ['core', 'domain', 'adapters']
  install_subdir(
    layer,
    install_dir: package_dir,
    exclude_directories: ['__pycache__'],
    exclude_files: ['optimal_partition.pyx'],
  )
endforeach

python.extension_module(
  'optimal_partition',
  'domain/optimal_partition.pyx',
  install: true,
  subdir: 'optimal_discretizer/domain',
)
