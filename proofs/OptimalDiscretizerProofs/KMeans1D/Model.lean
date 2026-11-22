import OptimalDiscretizerProofs.KMeans1D.Cost
import OptimalDiscretizerProofs.KMeans1D.DynamicProgram
import OptimalDiscretizerProofs.KMeans1D.Smawk

/-!
# The model of `optimal_starts`

`optimal_starts` in `src/optimal_discretizer/domain/optimal_partition.pyx` runs, for each layer `layer = m + 1` from
1 to `k - 1`, SMAWK on the matrix `matrix_entry(row, column)`, with the rows and the columns
`layer .. n - 1` (`indices m n`). The entry is `previous[column - 1] + interval_cost(column, row)` for
`column <= row`, and plus infinity otherwise; `previous[e - 1]` holds `layer (cost x) m e`. Then it walks back from
`n - 1` through the chosen columns.

* `layerMatrix_totallyMonotone`: for sorted values, the matrix of each layer is totally monotone, by the quadrangle
  inequality of `Cost.cost_quadrangle`.
* `smawk_choice_spec`: the column that SMAWK returns for a row is a column of the dynamic program with the smallest
  sum, and its entry is the next layer value, as the code stores it in `current`.
* `optimal_starts_isLeast`: the starts of the code give a partition of the `n` sorted values into `k` non-empty,
  contiguous intervals whose cost is the smallest over all such partitions.
-/

namespace OptimalDiscretizerProofs.KMeans1D.Model

open Cost DynamicProgram Smawk

/-- `matrix_entry(row, column)` of the code for the layer `m + 1`. -/
noncomputable def layerMatrix (x : ℕ → ℝ) (m : ℕ) (row column : ℕ) : WithTop ℝ :=
  if column ≤ row then layer (cost x) m column + (cost x column (row + 1) : WithTop ℝ) else ⊤

/-- The rows and the columns of the layer `m + 1`: `m + 1, ..., n - 1`. -/
def indices (m n : ℕ) : List ℕ := List.range' (m + 1) (n - (m + 1))

theorem mem_indices {m n j : ℕ} : j ∈ indices m n ↔ m + 1 ≤ j ∧ j < n := by
  unfold indices
  rw [List.mem_range'_1]
  omega

theorem indices_pairwise (m n : ℕ) : (indices m n).Pairwise (· < ·) := by
  unfold indices
  exact List.pairwise_lt_range'

/-- **Total monotonicity.** For sorted values, the matrix of each layer is totally monotone. -/
theorem layerMatrix_totallyMonotone (x : ℕ → ℝ) (hx : Monotone x) (m : ℕ) (R C : List ℕ) :
    TotallyMonotone (layerMatrix x m) R C := by
  intro i _ i' _ hii j _ j' _ hjj h
  unfold layerMatrix at h ⊢
  by_cases hj'i : j' ≤ i
  · have hji : j ≤ i := by omega
    rw [ite_eq_left hj'i, ite_eq_left hji] at h
    rw [ite_eq_left (by omega : j' ≤ i'), ite_eq_left (by omega : j ≤ i')]
    have hquad := cost_quadrangle x hx (a := j) (b := j') (c := i + 1) (d := i' + 1) hjj (by omega) (by omega)
    cases hL' : layer (cost x) m j' with
    | top => rw [hL'] at h; simp at h
    | coe a =>
      cases hL : layer (cost x) m j with
      | top => simp
      | coe b =>
        rw [hL', hL] at h
        rw [← WithTop.coe_add, ← WithTop.coe_add, WithTop.coe_lt_coe] at h ⊢
        linarith
  · rw [ite_eq_right hj'i] at h
    exact absurd h (not_lt.2 le_top)

/-- The column that SMAWK returns for the row `e - 1` of the layer `m + 1`. -/
noncomputable def smawkChoice (x : ℕ → ℝ) (n m : ℕ) (row : ℕ) : ℕ :=
  smawk (layerMatrix x m) (indices m n) (indices m n) (fun _ => 0) row

/-- **One layer.** For a row `i` with `m + 1 ≤ i < n`, the SMAWK column is in `[m + 1, i]`, it has the smallest sum of
the dynamic program, and its entry is the value of the next layer. -/
theorem smawk_choice_spec (x : ℕ → ℝ) (hx : Monotone x) {n m i : ℕ} (hmi : m + 1 ≤ i) (hin : i < n) :
    smawkChoice x n m i ∈ Finset.Ico (m + 1) (i + 1) ∧
      (∀ j ∈ Finset.Ico (m + 1) (i + 1), layer (cost x) m (smawkChoice x n m i) +
        (cost x (smawkChoice x n m i) (i + 1) : WithTop ℝ) ≤ layer (cost x) m j + (cost x j (i + 1) : WithTop ℝ)) ∧
      layerMatrix x m i (smawkChoice x n m i) = layer (cost x) (m + 1) (i + 1) := by
  have hi : i ∈ indices m n := mem_indices.2 ⟨hmi, hin⟩
  have hne : indices m n ≠ [] := List.ne_nil_of_mem hi
  have hlm : IsLeftmostMin (layerMatrix x m) i (indices m n) (smawkChoice x n m i) :=
    smawk_isLeftmostMin (layerMatrix x m) (indices m n) (indices m n) (fun _ => 0)
      (layerMatrix_totallyMonotone x hx m _ _) (indices_pairwise m n) (indices_pairwise m n) hne i hi
  set c := smawkChoice x n m i with hc
  have hcmem := mem_indices.1 hlm.1
  -- the first column of the layer has a finite entry, so the chosen column is not right of the row
  have hfirst : m + 1 ∈ indices m n := mem_indices.2 ⟨le_rfl, by omega⟩
  have hfinite : layerMatrix x m i (m + 1) ≠ ⊤ := by
    unfold layerMatrix
    rw [ite_eq_left hmi]
    exact WithTop.add_ne_top.2 ⟨layer_ne_top (cost x) (Nat.lt_succ_self m), WithTop.coe_ne_top⟩
  have hci : c ≤ i := by
    by_contra hci
    have hle := hlm.2.1 (m + 1) hfirst
    have htop : layerMatrix x m i c = ⊤ := by unfold layerMatrix; rw [ite_eq_right hci]
    rw [htop, top_le_iff] at hle
    exact hfinite hle
  have hentry : ∀ j, j ≤ i → layerMatrix x m i j = layer (cost x) m j + (cost x j (i + 1) : WithTop ℝ) := by
    intro j hj; unfold layerMatrix; rw [ite_eq_left hj]
  have hmin : ∀ j ∈ Finset.Ico (m + 1) (i + 1), layer (cost x) m c + (cost x c (i + 1) : WithTop ℝ) ≤
      layer (cost x) m j + (cost x j (i + 1) : WithTop ℝ) := by
    intro j hj
    have hj' := Finset.mem_Ico.1 hj
    have := hlm.2.1 j (mem_indices.2 ⟨hj'.1, by omega⟩)
    rwa [hentry c hci, hentry j (by omega)] at this
  have hcIco : c ∈ Finset.Ico (m + 1) (i + 1) := Finset.mem_Ico.2 ⟨hcmem.1, by omega⟩
  refine ⟨hcIco, hmin, ?_⟩
  rw [hentry c hci]
  simp only [layer]
  exact le_antisymm (Finset.le_inf hmin) (Finset.inf_le (f := fun j => layer (cost x) m j +
    (cost x j (i + 1) : WithTop ℝ)) hcIco)

/-! ## The arrays of the code -/

/-- `matrix_entry(row, column)` of the code, built from the array `previous` of the layer before. -/
noncomputable def entryOf (x : ℕ → ℝ) (previous : ℕ → WithTop ℝ) (row column : ℕ) : WithTop ℝ :=
  if column ≤ row then previous column + (cost x column (row + 1) : WithTop ℝ) else ⊤

/-- The arrays of the code: `codeLayer x n m e` is `cost[m][e - 1]`, as the loops of `optimal_starts` compute it.
Layer 0 is `interval_cost(0, e - 1)`; layer `m + 1` is the entry at the column that SMAWK returns on the matrix built
from layer `m`. -/
noncomputable def codeLayer (x : ℕ → ℝ) (n : ℕ) : ℕ → ℕ → WithTop ℝ
  | 0, e => if 0 < e then (cost x 0 e : WithTop ℝ) else ⊤
  | m + 1, e => entryOf x (codeLayer x n m) (e - 1)
      (smawk (entryOf x (codeLayer x n m)) (indices m n) (indices m n) (fun _ => 0) (e - 1))

/-- Total monotonicity reads only the entries of its rows and columns. -/
theorem TotallyMonotone.congr {M M' : ℕ → ℕ → WithTop ℝ} {R C : List ℕ} (htm : TotallyMonotone M R C)
    (hagree : ∀ i ∈ R, ∀ j ∈ C, M' i j = M i j) : TotallyMonotone M' R C := by
  intro i hi i' hi' hii j hj j' hj' hjj h
  rw [hagree i hi j hj, hagree i hi j' hj'] at h
  rw [hagree i' hi' j hj, hagree i' hi' j' hj']
  exact htm i hi i' hi' hii j hj j' hj' hjj h

/-- If the array of layer `m` holds the model values, SMAWK on the matrix of the code returns the model column. -/
theorem codeSmawk_eq (x : ℕ → ℝ) (hx : Monotone x) {n m i : ℕ} (hmi : m + 1 ≤ i) (hin : i < n)
    (hlayer : ∀ j, m < j → j ≤ n → codeLayer x n m j = layer (cost x) m j) :
    smawk (entryOf x (codeLayer x n m)) (indices m n) (indices m n) (fun _ => 0) i = smawkChoice x n m i ∧
      entryOf x (codeLayer x n m) i (smawkChoice x n m i) = layerMatrix x m i (smawkChoice x n m i) := by
  have hagree : ∀ i ∈ indices m n, ∀ j ∈ indices m n,
      entryOf x (codeLayer x n m) i j = layerMatrix x m i j := by
    intro i _ j hj
    have hj' := mem_indices.1 hj
    unfold entryOf layerMatrix
    split_ifs
    · rw [hlayer j (by omega) (by omega)]
    · rfl
  have hi : i ∈ indices m n := mem_indices.2 ⟨hmi, hin⟩
  have hne : indices m n ≠ [] := List.ne_nil_of_mem hi
  have htm := TotallyMonotone.congr (layerMatrix_totallyMonotone x hx m (indices m n) (indices m n)) hagree
  have hlm := smawk_isLeftmostMin (entryOf x (codeLayer x n m)) (indices m n) (indices m n) (fun _ => 0) htm
    (indices_pairwise m n) (indices_pairwise m n) hne i hi
  -- the leftmost minimum does not change when the entries of the row agree on the columns
  have hlm' : IsLeftmostMin (layerMatrix x m) i (indices m n)
      (smawk (entryOf x (codeLayer x n m)) (indices m n) (indices m n) (fun _ => 0) i) := by
    refine ⟨hlm.1, fun d hd => ?_, fun d hd hlt => ?_⟩
    · rw [← hagree i hi d hd, ← hagree i hi _ hlm.1]; exact hlm.2.1 d hd
    · rw [← hagree i hi d hd, ← hagree i hi _ hlm.1]; exact hlm.2.2 d hd hlt
  have hmodel : IsLeftmostMin (layerMatrix x m) i (indices m n) (smawkChoice x n m i) :=
    smawk_isLeftmostMin (layerMatrix x m) (indices m n) (indices m n) (fun _ => 0)
      (layerMatrix_totallyMonotone x hx m _ _) (indices_pairwise m n) (indices_pairwise m n) hne i hi
  have hsame := hlm'.unique hmodel
  exact ⟨hsame, hagree i hi _ (hsame ▸ hlm.1)⟩

/-- **The arrays of the code hold the layers of the model.** -/
theorem codeLayer_eq_layer (x : ℕ → ℝ) (hx : Monotone x) (n : ℕ) :
    ∀ (m e : ℕ), m < e → e ≤ n → codeLayer x n m e = layer (cost x) m e
  | 0, e, he, _ => by simp [codeLayer, layer, he]
  | m + 1, e, he, hen => by
    have ih : ∀ j, m < j → j ≤ n → codeLayer x n m j = layer (cost x) m j :=
      fun j hj hjn => codeLayer_eq_layer x hx n m j hj hjn
    obtain ⟨hsame, hentry⟩ := codeSmawk_eq x hx (n := n) (m := m) (i := e - 1) (by omega) (by omega) ih
    have hspec := (smawk_choice_spec x hx (n := n) (m := m) (i := e - 1) (by omega) (by omega)).2.2
    rw [show e - 1 + 1 = e by omega] at hspec
    simp only [codeLayer]
    rw [hsame, hentry, hspec]

/-- The choices of the code: `choices[layer][e - 1]`, the column that SMAWK returns on the matrix of the code. -/
noncomputable def codeChoice (x : ℕ → ℝ) (n : ℕ) (layerIndex e : ℕ) : ℕ :=
  smawk (entryOf x (codeLayer x n (layerIndex - 1))) (indices (layerIndex - 1) n) (indices (layerIndex - 1) n)
    (fun _ => 0) (e - 1)

/-- The starts that `optimal_starts` writes, last interval first (`starts[k - 1], ..., starts[0]`). -/
noncomputable def codeStarts (x : ℕ → ℝ) (n k : ℕ) : List ℕ :=
  backtrack (codeChoice x n) (k - 1) n

theorem codeChoice_spec (x : ℕ → ℝ) (hx : Monotone x) (n : ℕ) :
    ∀ m e, m + 1 < e → e ≤ n → codeChoice x n (m + 1) e ∈ Finset.Ico (m + 1) e ∧
      ∀ j ∈ Finset.Ico (m + 1) e, layer (cost x) m (codeChoice x n (m + 1) e) +
        (cost x (codeChoice x n (m + 1) e) e : WithTop ℝ) ≤ layer (cost x) m j + (cost x j e : WithTop ℝ) := by
  intro m e hme hen
  have hsame := (codeSmawk_eq x hx (n := n) (m := m) (i := e - 1) (by omega) (by omega)
    (fun j hj hjn => codeLayer_eq_layer x hx n m j hj hjn)).1
  have h := smawk_choice_spec x hx (n := n) (m := m) (i := e - 1) (by omega) (by omega)
  rw [show e - 1 + 1 = e by omega] at h
  have hchoice : codeChoice x n (m + 1) e = smawkChoice x n m (e - 1) := by
    unfold codeChoice; rw [show m + 1 - 1 = m by omega]; exact hsame
  rw [hchoice]
  exact ⟨h.1, h.2.1⟩

/-- **The code is optimal.** For `n` sorted values and `1 ≤ k ≤ n`, the starts of `optimal_starts` form a partition
into `k` non-empty, contiguous intervals, its cost is the value `cost[k - 1][n - 1]` that the code returns, and no
partition into `k` intervals costs less. -/
theorem optimal_starts_isLeast (x : ℕ → ℝ) (hx : Monotone x) {n k : ℕ} (hk : 1 ≤ k) (hkn : k ≤ n) :
    IsPartition (codeStarts x n k) n ∧ (codeStarts x n k).length = k ∧
      codeLayer x n (k - 1) n = (partCost (cost x) (codeStarts x n k) n : WithTop ℝ) ∧
      ∀ rs, IsPartition rs n → rs.length = k → codeLayer x n (k - 1) n ≤ (partCost (cost x) rs n : WithTop ℝ) := by
  obtain ⟨hpart, hlen, hval⟩ := backtrack_spec (cost x) (codeChoice x n) n (codeChoice_spec x hx n) (k - 1) n
    (by omega) le_rfl
  have hcode := codeLayer_eq_layer x hx n (k - 1) n (by omega) le_rfl
  refine ⟨hpart, by unfold codeStarts; rw [hlen]; omega, hcode ▸ hval, fun rs hrs hrslen => ?_⟩
  rw [hcode]
  exact layer_le_partCost (cost x) (k - 1) rs n hrs (by omega)

end OptimalDiscretizerProofs.KMeans1D.Model
