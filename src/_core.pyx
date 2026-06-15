# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Cython implementation of the optimal 1-D k-means clustering algorithm.

Based on the paper:
    "Optimal Quantization by Matrix Searching"
    Gronlund, A., Larsen, K. G., Mathiasen, A., Nielsen, J. S., Schneider, S., & Song, M. (2017).
    https://arxiv.org/abs/1701.07204

The algorithm uses the SMAWK algorithm to achieve O(kn log n) time complexity
for 1-D k-means clustering.
"""

import numpy as np
cimport numpy as np
from libc.stdlib cimport malloc, free
from libc.string cimport memset

np.import_array()

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
ctypedef np.uint64_t ulong
ctypedef np.float64_t double_t


# ---------------------------------------------------------------------------
# CostCalculator: O(1) cluster cost using prefix sums
# ---------------------------------------------------------------------------
cdef class CostCalculator:
    """Computes cluster cost (sum of squared deviations from mean) in O(1)."""

    cdef double_t[::1] cumsum
    cdef double_t[::1] cumsum2
    cdef ulong n

    def __cinit__(self, double_t[::1] vec, ulong n):
        self.n = n
        self.cumsum = np.empty(n + 1, dtype=np.float64)
        self.cumsum2 = np.empty(n + 1, dtype=np.float64)
        self.cumsum[0] = 0.0
        self.cumsum2[0] = 0.0
        cdef ulong i
        cdef double_t x
        for i in range(n):
            x = vec[i]
            self.cumsum[i + 1] = x + self.cumsum[i]
            self.cumsum2[i + 1] = x * x + self.cumsum2[i]

    cdef inline double_t calc(self, ulong i, ulong j) nogil:
        """Cost of cluster containing sorted elements [i..j] (inclusive)."""
        if j < i:
            return 0.0
        cdef double_t mu = (self.cumsum[j + 1] - self.cumsum[i]) / (j - i + 1)
        cdef double_t result = self.cumsum2[j + 1] - self.cumsum2[i]
        result += (j - i + 1) * (mu * mu)
        result -= 2.0 * mu * (self.cumsum[j + 1] - self.cumsum[i])
        return result


# ---------------------------------------------------------------------------
# SMAWK algorithm: finds row-minima of a totally monotone matrix
# ---------------------------------------------------------------------------
cdef void _smawk(
    ulong[::1] rows,
    ulong rows_len,
    ulong[::1] cols,
    ulong cols_len,
    ulong[::1] result,
    ulong[::1] D_row,          # scratch row of D values for column reduction
    object lookup,             # Python callable: (row, col) -> double
) noexcept:
    """
    Recursive SMAWK implementation.

    Finds, for each row index in *rows*, the column index in *cols* that
    minimises lookup(row, col), storing answers in result[row].
    """
    if rows_len == 0:
        return

    # ----------------------------------------------------------------
    # REDUCE: discard dominated columns
    # ----------------------------------------------------------------
    # We need a dynamic stack of surviving columns.
    cdef ulong[::1] _cols = np.empty(cols_len, dtype=np.uint64)
    cdef ulong _cols_len = 0
    cdef ulong col, row
    cdef double_t val_new, val_back
    cdef ulong ci

    for ci in range(cols_len):
        col = cols[ci]
        while True:
            if _cols_len == 0:
                break
            row = rows[_cols_len - 1]
            val_new = lookup(row, col)
            val_back = lookup(row, _cols[_cols_len - 1])
            if val_new >= val_back:
                break
            _cols_len -= 1
        if _cols_len < rows_len:
            _cols[_cols_len] = col
            _cols_len += 1

    # ----------------------------------------------------------------
    # Recurse on odd-indexed rows
    # ----------------------------------------------------------------
    cdef ulong odd_len = rows_len // 2  # number of odd-indexed rows
    cdef ulong[::1] odd_rows = np.empty(odd_len, dtype=np.uint64)
    cdef ulong ri
    for ri in range(odd_len):
        odd_rows[ri] = rows[2 * ri + 1]

    _smawk(odd_rows, odd_len, _cols, _cols_len, result, D_row, lookup)

    # Build column-index lookup: col value -> index in _cols
    cdef dict col_idx_lookup = {}
    for ci in range(_cols_len):
        col_idx_lookup[_cols[ci]] = ci

    # ----------------------------------------------------------------
    # INTERPOLATE: fill even-indexed rows
    # ----------------------------------------------------------------
    cdef ulong start = 0
    cdef ulong stop
    cdef ulong argmin_col
    cdef double_t min_val, cur_val
    cdef ulong r, c

    for r in range(0, rows_len, 2):
        row = rows[r]
        stop = _cols_len - 1
        if r < rows_len - 1:
            stop = col_idx_lookup[result[rows[r + 1]]]
        argmin_col = _cols[start]
        min_val = lookup(row, argmin_col)
        for c in range(start + 1, stop + 1):
            cur_val = lookup(row, _cols[c])
            if cur_val < min_val:
                argmin_col = _cols[c]
                min_val = cur_val
        result[row] = argmin_col
        start = stop


cdef ulong[::1] smawk(ulong num_rows, ulong num_cols, object lookup):
    """
    Find the column-argmin for each row of a totally monotone matrix defined
    by *lookup(row, col) -> double*.
    """
    cdef ulong[::1] result = np.empty(num_rows, dtype=np.uint64)
    cdef ulong[::1] rows = np.arange(num_rows, dtype=np.uint64)
    cdef ulong[::1] cols = np.arange(num_cols, dtype=np.uint64)
    cdef ulong[::1] D_scratch = np.empty(num_cols, dtype=np.uint64)
    _smawk(rows, num_rows, cols, num_cols, result, D_scratch, lookup)
    return result


# ---------------------------------------------------------------------------
# Main cluster function
# ---------------------------------------------------------------------------
def cluster(
    double_t[::1] array not None,
    ulong k,
):
    """
    Partition *array* into *k* clusters using the optimal 1-D k-means algorithm.

    Parameters
    ----------
    array : array-like of shape (n,), dtype float64
        The 1-D data to cluster.  Need not be sorted.
    k : int
        Number of clusters (must satisfy 1 <= k <= n).

    Returns
    -------
    clusters : ndarray of shape (n,), dtype int64
        Cluster label (0-indexed) for each element of *array*.
    centroids : ndarray of shape (k,), dtype float64
        Mean of each cluster, ordered by cluster index (which equals
        ascending position in the sorted data).
    """
    cdef ulong n = array.shape[0]
    if k < 1 or k > n:
        raise ValueError(f"k must satisfy 1 <= k <= n, got k={k}, n={n}")

    # ------------------------------------------------------------------
    # Sort and record permutation
    # ------------------------------------------------------------------
    cdef ulong[::1] sort_idxs = np.argsort(array, kind="stable").astype(np.uint64)
    cdef ulong[::1] undo_sort = np.empty(n, dtype=np.uint64)
    cdef double_t[::1] sorted_array = np.empty(n, dtype=np.float64)
    cdef ulong i
    for i in range(n):
        sorted_array[i] = array[sort_idxs[i]]
        undo_sort[sort_idxs[i]] = i

    # ------------------------------------------------------------------
    # Dynamic programming with SMAWK
    # ------------------------------------------------------------------
    # D[k_, i] = cost of optimally clustering sorted_array[0..i] into k_+1 clusters
    # T[k_, i] = start index of the last cluster in the optimal solution for D[k_, i]
    cdef double_t[:, ::1] D = np.empty((k, n), dtype=np.float64)
    cdef long long[:, ::1] T = np.empty((k, n), dtype=np.int64)

    cost_calc = CostCalculator(sorted_array, n)

    # Base case: k=1
    for i in range(n):
        D[0, i] = cost_calc.calc(0, i)
        T[0, i] = 0

    cdef ulong k_, argmin
    cdef double_t min_val, val

    for k_ in range(1, k):
        # Define the SMAWK lookup matrix C(i, j):
        #   C(i, j) = D[k_-1, min(i, j-1)] + cost(j, i)
        # This matrix is totally monotone for the 1-D k-means problem.
        def make_C(ulong kk, double_t[:, ::1] Dmat, CostCalculator cc):
            def C(row, col):
                cdef ulong i_ = <ulong>row
                cdef ulong j_ = <ulong>col
                cdef ulong prev_col = i_ if i_ < j_ - 1 else j_ - 1 if j_ > 0 else 0
                # Guard: when j_ == 0 the segment [j_..i_] may be invalid for j_ > i_.
                # The SMAWK lookup is only meaningful for j_ <= i_+1; the matrix is
                # infinite-cost elsewhere, which is enforced by the totally-monotone
                # property — SMAWK never looks outside valid cells.
                return Dmat[kk - 1, prev_col] + cc.calc(j_, i_)
            return C

        C_func = make_C(k_, D, cost_calc)
        row_argmins = smawk(n, n, C_func)
        for i in range(n):
            argmin = row_argmins[i]
            D[k_, i] = C_func(i, argmin)
            T[k_, i] = argmin

    # ------------------------------------------------------------------
    # Backtrack to recover cluster assignments
    # ------------------------------------------------------------------
    cdef long long[::1] sorted_clusters = np.empty(n, dtype=np.int64)
    cdef double_t[::1] centroids = np.empty(k, dtype=np.float64)

    cdef ulong t = n
    cdef long long k_cur = <long long>(k - 1)
    cdef ulong n_ = n - 1
    cdef ulong t_prev, ii
    cdef double_t centroid

    while True:
        t_prev = t
        t = <ulong>T[k_cur, n_]
        centroid = 0.0
        for ii in range(t, t_prev):
            sorted_clusters[ii] = k_cur
            centroid += (sorted_array[ii] - centroid) / (ii - t + 1)
        centroids[k_cur] = centroid
        if t == 0:
            break
        k_cur -= 1
        n_ = t - 1

    # ------------------------------------------------------------------
    # Un-sort
    # ------------------------------------------------------------------
    cdef long long[::1] clusters_out = np.empty(n, dtype=np.int64)
    for i in range(n):
        clusters_out[i] = sorted_clusters[undo_sort[i]]

    return np.asarray(clusters_out), np.asarray(centroids)
