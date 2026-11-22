import Mathlib

/-!
# Some optimal clustering of sorted values uses contiguous intervals

A clustering of `n` values into `k` clusters is a label `labels i : Fin k` for each value and a center
`centers c : ℝ` for each cluster. Its cost is the sum of the squared distances from each value to the center of its
cluster: the k-means objective.

`exists_contiguous_le` says: for sorted values, every clustering has a rearrangement of its labels with the same
centers and the same cluster sizes, whose cost is not larger, in which each cluster is a run of consecutive values
and the centers increase along the values. So if a clustering is optimal, a contiguous one is optimal too.

The proof sorts the values `(centers (labels i), labels i)` in lexicographic order and uses the rearrangement
inequality: the sum of the products of two sequences is largest when both are sorted the same way.
-/

namespace OptimalDiscretizerProofs.KMeans1D.Contiguity

open Finset

/-- The k-means objective of a clustering. -/
def clusterCost {n k : ℕ} (x : Fin n → ℝ) (labels : Fin n → Fin k) (centers : Fin k → ℝ) : ℝ :=
  ∑ i, (x i - centers (labels i)) ^ 2

/-- Each cluster is a run of consecutive values: a value between two values of a cluster is in that cluster. -/
def Contiguous {n k : ℕ} (labels : Fin n → Fin k) : Prop :=
  ∀ i j l : Fin n, i ≤ j → j ≤ l → labels i = labels l → labels j = labels i

/-- A permutation of the values gives a clustering of the sorted values with a cost that is not larger, when the
centers along the permuted values increase. -/
theorem clusterCost_comp_le {n k : ℕ} (x : Fin n → ℝ) (hx : Monotone x) (labels : Fin n → Fin k)
    (centers : Fin k → ℝ) (σ : Equiv.Perm (Fin n)) (hmono : Monotone (centers ∘ labels ∘ σ)) :
    clusterCost x (labels ∘ σ) centers ≤ clusterCost x labels centers := by
  set sorted := centers ∘ labels ∘ σ with hsorted
  have hsq : ∑ i, sorted i ^ 2 = ∑ i, centers (labels i) ^ 2 :=
    Equiv.sum_comp σ (fun i => centers (labels i) ^ 2)
  -- the rearrangement inequality, with the permutation that undoes σ
  have hrearr : ∑ i, x i * sorted (σ.symm i) ≤ ∑ i, x i * sorted i :=
    (hx.monovary hmono).sum_mul_comp_perm_le_sum_mul
  have hback : ∀ i, sorted (σ.symm i) = centers (labels i) := by
    intro i; simp [hsorted]
  simp_rw [hback] at hrearr
  have hexpand : ∀ (c : Fin n → ℝ), ∑ i, (x i - c i) ^ 2 = ∑ i, x i ^ 2 - 2 * ∑ i, x i * c i + ∑ i, c i ^ 2 := by
    intro c
    simp_rw [sub_sq, sum_add_distrib, sum_sub_distrib, mul_sum]
    congr 1; congr 1
    exact sum_congr rfl fun i _ => by ring
  unfold clusterCost
  rw [hexpand (fun i => centers ((labels ∘ σ) i)), hexpand (fun i => centers (labels i))]
  have h1 : ∑ i, x i * centers ((labels ∘ σ) i) = ∑ i, x i * sorted i := rfl
  have h2 : ∑ i, centers ((labels ∘ σ) i) ^ 2 = ∑ i, sorted i ^ 2 := rfl
  rw [h1, h2, hsq]
  linarith

/-- **Contiguity.** For sorted values, each clustering has a contiguous clustering with the same centers and a cost
that is not larger. -/
theorem exists_contiguous_le {n k : ℕ} (x : Fin n → ℝ) (hx : Monotone x) (labels : Fin n → Fin k)
    (centers : Fin k → ℝ) :
    ∃ σ : Equiv.Perm (Fin n), Contiguous (labels ∘ σ) ∧ Monotone (centers ∘ labels ∘ σ) ∧
      clusterCost x (labels ∘ σ) centers ≤ clusterCost x labels centers := by
  -- sort the values by the key (center, label), in lexicographic order
  let key : Fin n → ℝ ×ₗ Fin k := fun i => toLex (centers (labels i), labels i)
  let σ := Tuple.sort key
  have hkey : Monotone (key ∘ σ) := Tuple.monotone_sort key
  have hcenters : Monotone (centers ∘ labels ∘ σ) := by
    intro i j hij
    have h := hkey hij
    simp only [Function.comp, key] at h ⊢
    rcases (Prod.Lex.toLex_le_toLex.1 h) with h | ⟨h, _⟩
    · exact le_of_lt h
    · exact le_of_eq h
  refine ⟨σ, ?_, hcenters, clusterCost_comp_le x hx labels centers σ hcenters⟩
  intro i j l hij hjl hil
  have h1 := hkey hij
  have h2 := hkey hjl
  have heq : key (σ i) = key (σ l) := by simp only [key, Function.comp] at hil ⊢; rw [hil]
  have hj : key (σ j) = key (σ i) :=
    le_antisymm (by rw [heq]; exact h2) h1
  simp only [key, Function.comp] at hj ⊢
  exact (Prod.ext_iff.1 (toLex.injective hj)).2

end OptimalDiscretizerProofs.KMeans1D.Contiguity
