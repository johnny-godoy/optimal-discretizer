import OptimalDiscretizerProofs.KMeans1D.Contiguity
import OptimalDiscretizerProofs.KMeans1D.Model

/-!
# The code finds a global minimum of the k-means objective

`codeStarts_le_clusterCost` joins the parts: for `n` sorted values and `1 ≤ k ≤ n`, the cost of the partition that
`optimal_starts` returns is at most the k-means objective `clusterCost` of every clustering of the values into `k`
clusters, with any labels and any centers, empty clusters included.

The steps:

1. `Contiguity.exists_contiguous_le` rearranges the labels so that the centers along the sorted values increase.
2. `sum_sq_ge_layer` bounds the cost of an increasing assignment of at most `m + 1` distinct centers to the values
   `[0, e)` by `layer m e`: the last run of equal centers costs at least the cost of its interval, and the rest is
   a shorter prefix with fewer centers.
3. `layer_antitone`: a layer with more intervals is not larger, because splitting an interval does not raise its cost
   (`cost_split`).
-/

namespace OptimalDiscretizerProofs.KMeans1D.Optimality

open Finset Cost DynamicProgram Model Contiguity

/-! ## Facts about the cost -/

theorem cost_split (x : ℕ → ℝ) {a b e : ℕ} (hab : a < b) (hbe : b < e) :
    cost x a b + cost x b e ≤ cost x a e := by
  have h1 := cost_le_sum_sq_sub x hab (mean x a e)
  have h2 := cost_le_sum_sq_sub x hbe (mean x a e)
  have hsplit := sum_Ico_consecutive (fun t => (x t - mean x a e) ^ 2) hab.le hbe.le
  unfold cost at hsplit ⊢
  linarith [show cost x a b = ∑ t ∈ Ico a b, (x t - mean x a b) ^ 2 from rfl,
    show cost x b e = ∑ t ∈ Ico b e, (x t - mean x b e) ^ 2 from rfl]

theorem cost_single (x : ℕ → ℝ) (a : ℕ) : cost x a (a + 1) = 0 := by
  simp [cost, mean]

/-! ## Facts about the layers -/

theorem layer_nonneg (x : ℕ → ℝ) : ∀ (m e : ℕ), 0 ≤ layer (cost x) m e
  | 0, e => by
    unfold layer
    split_ifs
    · exact_mod_cast cost_nonneg x 0 e
    · exact le_top
  | m + 1, e => by
    unfold layer
    exact Finset.le_inf fun j _ => add_nonneg (layer_nonneg x m j) (by exact_mod_cast cost_nonneg x j e)

/-- `m + 1` values in `m + 1` intervals cost nothing: each interval holds one value. -/
theorem layer_self (x : ℕ → ℝ) : ∀ m : ℕ, layer (cost x) m (m + 1) = 0
  | 0 => by simp [layer, cost_single]
  | m + 1 => by
    apply le_antisymm _ (layer_nonneg x _ _)
    have hmem : m + 1 ∈ Finset.Ico (m + 1) (m + 1 + 1) := Finset.mem_Ico.2 ⟨le_rfl, Nat.lt_succ_self _⟩
    calc layer (cost x) (m + 1) (m + 1 + 1) ≤ layer (cost x) m (m + 1) + (cost x (m + 1) (m + 1 + 1) : WithTop ℝ) := by
          simp only [layer]
          exact Finset.inf_le (f := fun j => layer (cost x) m j + (cost x j (m + 1 + 1) : WithTop ℝ)) hmem
      _ = 0 := by rw [layer_self x m, cost_single]; simp

/-- One more interval does not raise the smallest cost. -/
theorem layer_succ_le (x : ℕ → ℝ) : ∀ {m e : ℕ}, m + 2 ≤ e → layer (cost x) (m + 1) e ≤ layer (cost x) m e
  | 0, e, he => by
    have hmem : 1 ∈ Finset.Ico 1 e := Finset.mem_Ico.2 ⟨le_rfl, by omega⟩
    calc layer (cost x) 1 e ≤ layer (cost x) 0 1 + (cost x 1 e : WithTop ℝ) := by
          simp only [layer]
          exact Finset.inf_le (f := fun j => layer (cost x) 0 j + (cost x j e : WithTop ℝ)) hmem
      _ = ((cost x 0 1 + cost x 1 e : ℝ) : WithTop ℝ) := by simp [layer]
      _ ≤ layer (cost x) 0 e := by
          simp only [layer, show 0 < e by omega, ite_true]
          exact_mod_cast cost_split x (by omega : 0 < 1) (by omega : 1 < e)
  | m + 1, e, he => by
    -- the smallest sum of layer m + 1 is reached at some column j
    obtain ⟨j, hj, hjmin⟩ := Finset.exists_min_image (Finset.Ico (m + 1 + 1) e)
      (fun j => layer (cost x) (m + 1) j + (cost x j e : WithTop ℝ)) ⟨m + 2, Finset.mem_Ico.2 ⟨le_rfl, by omega⟩⟩
    have hval : layer (cost x) (m + 1 + 1) e = layer (cost x) (m + 1) j + (cost x j e : WithTop ℝ) := by
      conv_lhs => simp only [layer]
      exact le_antisymm (Finset.inf_le (f := fun j => layer (cost x) (m + 1) j + (cost x j e : WithTop ℝ)) hj)
        (Finset.le_inf hjmin)
    obtain ⟨j', hj', hj'min⟩ := Finset.exists_min_image (Finset.Ico (m + 1) e)
      (fun j => layer (cost x) m j + (cost x j e : WithTop ℝ)) ⟨m + 1, Finset.mem_Ico.2 ⟨le_rfl, by omega⟩⟩
    have hval' : layer (cost x) (m + 1) e = layer (cost x) m j' + (cost x j' e : WithTop ℝ) := by
      conv_lhs => simp only [layer]
      exact le_antisymm (Finset.inf_le (f := fun j => layer (cost x) m j + (cost x j e : WithTop ℝ)) hj')
        (Finset.le_inf hj'min)
    rw [hval, hval']
    have hj'range := Finset.mem_Ico.1 hj'
    rcases Nat.lt_or_ge (m + 1) j' with hlt | hle
    · -- the best start of layer m + 1 is a column of layer m + 2 too
      have hmem : j' ∈ Finset.Ico (m + 1 + 1) e := Finset.mem_Ico.2 ⟨hlt, hj'range.2⟩
      calc layer (cost x) (m + 1) j + (cost x j e : WithTop ℝ)
          ≤ layer (cost x) (m + 1) j' + (cost x j' e : WithTop ℝ) := hjmin j' hmem
        _ ≤ layer (cost x) m j' + (cost x j' e : WithTop ℝ) := by
            gcongr; exact layer_succ_le x (by omega)
    · -- the best start is m + 1: the prefix costs nothing, and a shorter last interval costs no more
      have hj'eq : j' = m + 1 := le_antisymm hle hj'range.1
      subst hj'eq
      have hmem : m + 2 ∈ Finset.Ico (m + 1 + 1) e := Finset.mem_Ico.2 ⟨le_rfl, by omega⟩
      calc layer (cost x) (m + 1) j + (cost x j e : WithTop ℝ)
          ≤ layer (cost x) (m + 1) (m + 2) + (cost x (m + 2) e : WithTop ℝ) := hjmin _ hmem
        _ = ((cost x (m + 2) e : ℝ) : WithTop ℝ) := by rw [layer_self x (m + 1)]; simp
        _ ≤ ((cost x (m + 1) (m + 2) + cost x (m + 2) e : ℝ) : WithTop ℝ) := by
            rw [cost_single]; simp
        _ ≤ layer (cost x) m (m + 1) + (cost x (m + 1) e : WithTop ℝ) := by
            rw [layer_self x m, zero_add]
            exact_mod_cast cost_split x (by omega : m + 1 < m + 2) (by omega : m + 2 < e)

theorem layer_antitone (x : ℕ → ℝ) {e : ℕ} :
    ∀ {m m' : ℕ}, m ≤ m' → m' < e → layer (cost x) m' e ≤ layer (cost x) m e := by
  intro m m' hmm' hm'e
  induction m', hmm' using Nat.le_induction with
  | base => exact le_rfl
  | succ m' hle ih => exact le_trans (layer_succ_le x (by omega)) (ih (by omega))

/-! ## The lower bound for increasing assignments of centers -/

/-- If the centers `ν` along the values `[0, e)` increase and take at most `m + 1` distinct values, their cost is at
least `layer m e`. -/
theorem sum_sq_ge_layer (x : ℕ → ℝ) :
    ∀ (e m : ℕ) (ν : ℕ → ℝ), m < e → (∀ i j, i ≤ j → j < e → ν i ≤ ν j) →
      ((range e).image ν).card ≤ m + 1 →
      layer (cost x) m e ≤ ((∑ i ∈ range e, (x i - ν i) ^ 2 : ℝ) : WithTop ℝ) := by
  intro e
  induction e using Nat.strong_induction_on with
  | _ e ih =>
  intro m ν hme hmono hcard
  have he : 0 < e := by omega
  -- the run of the last center starts at the smallest start j0 of a run that reaches the last value
  classical
  let starts := (range e).filter fun j => ∀ i, j ≤ i → i < e → ν i = ν (e - 1)
  have hlast_start : e - 1 ∈ starts := mem_filter.2 ⟨mem_range.2 (by omega), fun i hi hie => by
    rw [show i = e - 1 by omega]⟩
  let j0 := starts.min' ⟨e - 1, hlast_start⟩
  have hj0mem := (mem_filter.1 (starts.min'_mem ⟨e - 1, hlast_start⟩))
  have hj0 : j0 < e ∧ ∀ i, j0 ≤ i → i < e → ν i = ν (e - 1) := ⟨mem_range.1 hj0mem.1, hj0mem.2⟩
  have hbefore : ∀ i < j0, ν i ≠ ν (e - 1) := by
    intro i hi heq
    have hstart : i ∈ starts := mem_filter.2 ⟨mem_range.2 (by omega), fun l hil hle =>
      le_antisymm (hmono l (e - 1) (by omega) (by omega)) (heq ▸ hmono i l hil hle)⟩
    exact absurd (starts.min'_le i hstart) (not_le.2 hi)
  -- the cost splits at j0, and the last run costs at least the cost of its interval
  have hsplit : ∑ i ∈ range e, (x i - ν i) ^ 2 =
      ∑ i ∈ range j0, (x i - ν i) ^ 2 + ∑ i ∈ Ico j0 e, (x i - ν (e - 1)) ^ 2 := by
    rw [← sum_range_add_sum_Ico _ hj0.1.le]
    congr 1
    exact sum_congr rfl fun i hi => by rw [hj0.2 i (mem_Ico.1 hi).1 (mem_Ico.1 hi).2]
  have hlast : cost x j0 e ≤ ∑ i ∈ Ico j0 e, (x i - ν (e - 1)) ^ 2 := cost_le_sum_sq_sub x hj0.1 _
  have hprefix_nonneg : 0 ≤ ∑ i ∈ range j0, (x i - ν i) ^ 2 := sum_nonneg fun _ _ => sq_nonneg _
  rw [hsplit]
  rcases Nat.eq_zero_or_pos j0 with hzero | hpos
  · -- one run: the cost of the whole interval bounds the cost, and layer 0 is that cost
    rw [hzero] at hlast ⊢
    calc layer (cost x) m e ≤ layer (cost x) 0 e := layer_antitone x (Nat.zero_le m) hme
      _ = ((cost x 0 e : ℝ) : WithTop ℝ) := by simp [layer, he]
      _ ≤ _ := by simp only [range_zero, sum_empty, zero_add]; exact_mod_cast hlast
  · -- the prefix [0, j0) has fewer distinct centers
    have hcard' : ((range j0).image ν).card ≤ m := by
      have hsub : (range j0).image ν ⊆ ((range e).image ν).erase (ν (e - 1)) := by
        intro v hv
        obtain ⟨i, hi, rfl⟩ := mem_image.1 hv
        exact mem_erase.2 ⟨hbefore i (mem_range.1 hi), mem_image.2 ⟨i, mem_range.2 (by
          have := mem_range.1 hi; omega), rfl⟩⟩
      have hmem : ν (e - 1) ∈ (range e).image ν := mem_image.2 ⟨e - 1, mem_range.2 (by omega), rfl⟩
      have := card_le_card hsub
      rw [card_erase_of_mem hmem] at this
      omega
    obtain ⟨m', hm'⟩ : ∃ m', m = m' + 1 := ⟨m - 1, by
      have : 1 ≤ ((range j0).image ν).card := card_pos.2 ⟨ν 0, mem_image.2 ⟨0, mem_range.2 hpos, rfl⟩⟩
      omega⟩
    subst hm'
    rcases Nat.lt_or_ge m' j0 with hlt | hge
    · -- a long prefix: use the induction hypothesis on it, with one center fewer
      have hprefix := ih j0 hj0.1 m' ν hlt (fun i j hij hj => hmono i j hij (by omega)) hcard'
      have hmem : j0 ∈ Finset.Ico (m' + 1) e := Finset.mem_Ico.2 ⟨hlt, hj0.1⟩
      calc layer (cost x) (m' + 1) e ≤ layer (cost x) m' j0 + (cost x j0 e : WithTop ℝ) := by
            simp only [layer]
            exact Finset.inf_le (f := fun j => layer (cost x) m' j + (cost x j e : WithTop ℝ)) hmem
        _ ≤ ((∑ i ∈ range j0, (x i - ν i) ^ 2 : ℝ) : WithTop ℝ) + ((cost x j0 e : ℝ) : WithTop ℝ) := by
            gcongr
        _ ≤ _ := by rw [← WithTop.coe_add]; exact_mod_cast add_le_add_right hlast _
    · -- a short prefix: one interval for each value of it costs nothing
      obtain ⟨p, hp⟩ : ∃ p, j0 = p + 1 := ⟨j0 - 1, by omega⟩
      have hmem : j0 ∈ Finset.Ico (p + 1) e := Finset.mem_Ico.2 ⟨by omega, hj0.1⟩
      calc layer (cost x) (m' + 1) e ≤ layer (cost x) (p + 1) e := layer_antitone x (by omega) hme
        _ ≤ layer (cost x) p j0 + (cost x j0 e : WithTop ℝ) := by
            simp only [layer]
            exact Finset.inf_le (f := fun j => layer (cost x) p j + (cost x j e : WithTop ℝ)) hmem
        _ = ((cost x j0 e : ℝ) : WithTop ℝ) := by rw [hp, layer_self x p]; simp
        _ ≤ _ := by exact_mod_cast le_add_of_nonneg_of_le hprefix_nonneg hlast

/-! ## The k-means objective -/

/-- **Every clustering costs at least `layer (k - 1) n`.** For `n` sorted values and `1 ≤ k ≤ n`, the k-means
objective of every clustering into `k` clusters is at least the value of the last layer. -/
theorem layer_le_clusterCost (x : ℕ → ℝ) (hx : Monotone x) {n k : ℕ} (hk : 1 ≤ k) (hkn : k ≤ n)
    (labels : Fin n → Fin k) (centers : Fin k → ℝ) :
    layer (cost x) (k - 1) n ≤ ((clusterCost (fun i : Fin n => x i) labels centers : ℝ) : WithTop ℝ) := by
  obtain ⟨σ, _, hmono, hle⟩ := exists_contiguous_le (fun i : Fin n => x i) (fun i j hij => hx hij) labels centers
  -- the centers along the sorted values, as a function on ℕ
  let ν : ℕ → ℝ := fun i => if h : i < n then (centers ∘ labels ∘ σ) ⟨i, h⟩ else 0
  have hν : ∀ i j, i ≤ j → j < n → ν i ≤ ν j := by
    intro i j hij hj
    simp only [ν, dite_eq_left (lt_of_le_of_lt hij hj), dite_eq_left hj]
    exact hmono (Fin.mk_le_mk.2 hij)
  have hcard : ((range n).image ν).card ≤ k - 1 + 1 := by
    have hsub : (range n).image ν ⊆ Finset.univ.image centers := by
      intro v hv
      obtain ⟨i, hi, rfl⟩ := mem_image.1 hv
      have hi' := mem_range.1 hi
      exact mem_image.2 ⟨labels (σ ⟨i, hi'⟩), mem_univ _, by simp [ν, hi']⟩
    calc ((range n).image ν).card ≤ (Finset.univ.image centers).card := card_le_card hsub
      _ ≤ Finset.univ.card := card_image_le
      _ = k := by simp
      _ = k - 1 + 1 := by omega
  have hsum : clusterCost (fun i : Fin n => x i) (labels ∘ σ) centers = ∑ i ∈ range n, (x i - ν i) ^ 2 := by
    unfold clusterCost
    rw [← Fin.sum_univ_eq_sum_range (fun i => (x i - ν i) ^ 2)]
    exact sum_congr rfl fun i _ => by simp [ν, i.isLt]
  have hbound := sum_sq_ge_layer x n (k - 1) ν (by omega) hν hcard
  rw [← hsum] at hbound
  exact le_trans hbound (by exact_mod_cast hle)

/-- **The code finds a global minimum of the k-means objective.** For `n` sorted values and `1 ≤ k ≤ n`, the partition
that `optimal_starts` returns costs no more than any clustering of the values into `k` clusters. -/
theorem codeStarts_le_clusterCost (x : ℕ → ℝ) (hx : Monotone x) {n k : ℕ} (hk : 1 ≤ k) (hkn : k ≤ n)
    (labels : Fin n → Fin k) (centers : Fin k → ℝ) :
    partCost (cost x) (codeStarts x n k) n ≤ clusterCost (fun i : Fin n => x i) labels centers := by
  have h := layer_le_clusterCost x hx hk hkn labels centers
  rw [← codeLayer_eq_layer x hx n (k - 1) n (by omega) le_rfl, (optimal_starts_isLeast x hx hk hkn).2.2.1] at h
  exact_mod_cast h

end OptimalDiscretizerProofs.KMeans1D.Optimality
