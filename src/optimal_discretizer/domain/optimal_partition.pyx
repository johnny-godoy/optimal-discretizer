# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, initializedcheck=False
# cython: freethreading_compatible=True
"""The compiled kernel: the dynamic program of 1-D k-means, with SMAWK for each layer.

``optimal_starts`` partitions sorted values into a given number of contiguous, non-empty intervals with the smallest
sum of squared deviations from the interval means. It follows the dynamic program of Grønlund et al. (2017,
arXiv:1701.07204):

    cost[0][row] = interval_cost(0, row)
    cost[layer][row] = min over column in [layer, row] of cost[layer - 1][column - 1] + interval_cost(column, row)

The matrix of layer ``layer`` has the rows and the columns ``layer .. n - 1``. Its entry is the sum above for
``column <= row``, and plus infinity for ``column > row``. SMAWK finds the leftmost minimum of each row of that matrix.
``proofs/papers/kmeans-1d/paper.typ`` proves, for exact arithmetic, that this gives the minimum over all contiguous
partitions, and that this minimum is the optimum of 1-D k-means.

The module has no Python objects in its loops: it reads typed memoryviews, works on C buffers, and releases the GIL.
The workspace holds ``k * n`` indices for the walk back and ``8 * n + 2`` numbers and indices besides.
"""

from libc.math cimport INFINITY
from cpython.mem cimport PyMem_RawFree, PyMem_RawMalloc


cdef struct LayerMatrix:
    # The matrix of one layer of the dynamic program.
    const double* sums  # prefix sums of the centered values, n + 1 entries
    const double* squares  # prefix sums of their squares, n + 1 entries
    const double* previous  # the costs of the layer before, n entries


cdef inline double interval_cost(
    const double* sums, const double* squares, Py_ssize_t first, Py_ssize_t last
) noexcept nogil:
    """Return the sum of squared deviations from the mean of the sorted values ``first .. last``, both included."""
    cdef Py_ssize_t count = last - first + 1
    cdef double total = sums[last + 1] - sums[first]
    cdef double cost = squares[last + 1] - squares[first] - total * total / count
    # Rounding can make the difference of two prefix sums a little negative. The exact value is never negative.
    return cost if cost > 0.0 else 0.0


cdef inline double matrix_entry(const LayerMatrix* matrix, Py_ssize_t row, Py_ssize_t column) noexcept nogil:
    """Return the cost of the values ``0 .. row`` when the last interval starts at ``column``."""
    if column > row:
        return INFINITY
    return matrix.previous[column - 1] + interval_cost(matrix.sums, matrix.squares, column, row)


cdef void smawk(
    const LayerMatrix* matrix,
    Py_ssize_t first_row,
    Py_ssize_t row_step,
    Py_ssize_t row_count,
    const Py_ssize_t* columns,
    Py_ssize_t column_count,
    Py_ssize_t* scratch,
    Py_ssize_t* argmin,
) noexcept nogil:
    """Write the leftmost minimum column of each row into ``argmin[row]``.

    The rows are ``first_row + row_step * t`` for ``t`` in ``0 .. row_count - 1``. The columns are the increasing
    indices ``columns[0 .. column_count - 1]``. ``scratch`` holds at least ``2 * row_count`` free entries.
    """
    if row_count == 0:
        return
    # REDUCE: keep at most one column for each row. A kept column at position p is no better than the kept column
    # before it for the rows above row p, and a column is removed only where a later column is strictly better.
    cdef Py_ssize_t* kept = scratch
    cdef Py_ssize_t kept_count = 0
    cdef Py_ssize_t column_index, column, row
    for column_index in range(column_count):
        column = columns[column_index]
        while kept_count > 0:
            row = first_row + row_step * (kept_count - 1)
            if matrix_entry(matrix, row, column) < matrix_entry(matrix, row, kept[kept_count - 1]):
                kept_count -= 1
            else:
                break
        if kept_count < row_count:
            kept[kept_count] = column
            kept_count += 1

    # Recurse on the rows at the odd positions.
    smawk(matrix, first_row + row_step, 2 * row_step, row_count // 2, kept, kept_count, scratch + kept_count, argmin)

    # INTERPOLATE: the leftmost minimum of a row at an even position lies between the minima of its two neighbours.
    cdef Py_ssize_t position = 0
    cdef Py_ssize_t row_position, stop_column, best_column
    cdef double best_value, value
    for row_position in range(0, row_count, 2):
        row = first_row + row_step * row_position
        if row_position + 1 < row_count:
            stop_column = argmin[row + row_step]
        else:
            stop_column = kept[kept_count - 1]
        best_column = kept[position]
        best_value = matrix_entry(matrix, row, best_column)
        while kept[position] != stop_column:
            position += 1
            value = matrix_entry(matrix, row, kept[position])
            if value < best_value:
                best_value = value
                best_column = kept[position]
        argmin[row] = best_column


cdef void* checked_malloc(size_t count, size_t size) except NULL:
    """Allocate ``count`` items of ``size`` bytes, or raise ``MemoryError``.

    ``PyMem_RawMalloc`` needs no GIL, and ``tracemalloc`` sees it, so a test can measure the workspace.
    """
    if size != 0 and count > (<size_t> -1) // size:
        raise MemoryError("the workspace of the dynamic program is too large")
    cdef void* pointer = PyMem_RawMalloc(count * size if count * size > 0 else 1)
    if pointer == NULL:
        raise MemoryError("the workspace of the dynamic program does not fit in memory")
    return pointer


def optimal_starts(const double[::1] sorted_values not None, Py_ssize_t[::1] starts not None):
    """Partition sorted values into ``len(starts)`` contiguous intervals with the smallest total squared error.

    Parameters
    ----------
    sorted_values : memoryview of float64, shape (n,)
        Finite values in increasing order.
    starts : memoryview of intp, shape (k,)
        The output: the index of the first value of each interval, in increasing order. ``starts[0]`` is 0.
        ``1 <= k <= n`` must hold.

    Returns
    -------
    float
        The total squared error of the partition, as the dynamic program computes it.

    Raises
    ------
    ValueError
        If ``k`` is not between 1 and ``n``.
    MemoryError
        If the workspace of ``k * n`` indices does not fit in memory.
    """
    cdef Py_ssize_t value_count = sorted_values.shape[0]
    cdef Py_ssize_t interval_count = starts.shape[0]
    if interval_count < 1 or interval_count > value_count:
        raise ValueError(
            f"the number of intervals must be between 1 and the number of values ({value_count}), "
            f"got {interval_count}"
        )

    cdef double* sums = NULL
    cdef double* squares = NULL
    cdef double* previous = NULL
    cdef double* current = NULL
    cdef double* swap_costs
    cdef Py_ssize_t* choices = NULL
    cdef Py_ssize_t* columns = NULL
    cdef Py_ssize_t* scratch = NULL
    cdef Py_ssize_t* argmin = NULL
    cdef LayerMatrix matrix
    cdef Py_ssize_t index, layer, last, first
    cdef double center = 0.0
    cdef double centered, total_cost
    try:
        sums = <double*> checked_malloc(value_count + 1, sizeof(double))
        squares = <double*> checked_malloc(value_count + 1, sizeof(double))
        previous = <double*> checked_malloc(value_count, sizeof(double))
        current = <double*> checked_malloc(value_count, sizeof(double))
        choices = <Py_ssize_t*> checked_malloc(<size_t> interval_count * <size_t> value_count, sizeof(Py_ssize_t))
        columns = <Py_ssize_t*> checked_malloc(value_count, sizeof(Py_ssize_t))
        scratch = <Py_ssize_t*> checked_malloc(2 * value_count, sizeof(Py_ssize_t))
        argmin = <Py_ssize_t*> checked_malloc(value_count, sizeof(Py_ssize_t))
        with nogil:
            # Center the values on their mean, so that the prefix sums lose fewer digits to cancellation.
            for index in range(value_count):
                center += sorted_values[index]
            center /= value_count
            sums[0] = 0.0
            squares[0] = 0.0
            for index in range(value_count):
                centered = sorted_values[index] - center
                sums[index + 1] = sums[index] + centered
                squares[index + 1] = squares[index] + centered * centered

            # Layer 0: one interval that starts at the first value.
            for index in range(value_count):
                previous[index] = interval_cost(sums, squares, 0, index)
                choices[index] = 0

            matrix.sums = sums
            matrix.squares = squares
            for layer in range(1, interval_count):
                matrix.previous = previous
                for index in range(layer, value_count):
                    columns[index - layer] = index
                smawk(&matrix, layer, 1, value_count - layer, columns, value_count - layer, scratch, argmin)
                for index in range(layer, value_count):
                    current[index] = matrix_entry(&matrix, index, argmin[index])
                    choices[layer * value_count + index] = argmin[index]
                swap_costs = previous
                previous = current
                current = swap_costs

            total_cost = previous[value_count - 1]
            # Walk back from the last value: the chosen column of each layer is the start of its last interval.
            last = value_count - 1
            for layer in range(interval_count - 1, -1, -1):
                first = choices[layer * value_count + last]
                starts[layer] = first
                last = first - 1
    finally:
        PyMem_RawFree(sums)
        PyMem_RawFree(squares)
        PyMem_RawFree(previous)
        PyMem_RawFree(current)
        PyMem_RawFree(choices)
        PyMem_RawFree(columns)
        PyMem_RawFree(scratch)
        PyMem_RawFree(argmin)
    return total_cost
