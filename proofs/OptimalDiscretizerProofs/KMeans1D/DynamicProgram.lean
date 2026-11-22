import Mathlib

/-!
# The dynamic program over contiguous partitions

The cost of an interval `[a, e)` is any function `w a e`. A partition of the prefix `[0, e)` into `p` non-empty,
contiguous intervals is the list of the starts of its intervals, last interval first, as the walk back of the code
writes them: `[s_{p-1}, ..., s_1, s_0]` with `s_0 = 0` and `s_0 < s_1 < ... < s_{p-1} < e`.

`layer m e` is `cost[m][e - 1]` of the code: the smallest cost of `[0, e)` in `m + 1` intervals, with `⊤` where no
partition exists. The column `j` of the code, the start of the last interval, runs over `[m, e - 1]`.

* `layer_le_partCost`: no partition into `m + 1` intervals costs less than `layer m e`.
* `backtrack_spec`: if each choice is a column with the smallest sum, as SMAWK returns, the walk back of the code gives a
  partition into `m + 1` intervals whose cost is `layer m e`.
-/

namespace OptimalDiscretizerProofs.KMeans1D.DynamicProgram

/-- The cost of the partition with the starts `rs` (last interval first) of the prefix `[0, e)`. -/
def partCost (w : ℕ → ℕ → ℝ) : List ℕ → ℕ → ℝ
  | [], _ => 0
  | s :: ss, e => w s e + partCost w ss s

/-- `rs` are the starts of a partition of `[0, e)` into non-empty contiguous intervals, last interval first. -/
def IsPartition : List ℕ → ℕ → Prop
  | [], _ => False
  | [s], e => s = 0 ∧ s < e
  | s :: s' :: ss, e => s < e ∧ IsPartition (s' :: ss) s

theorem IsPartition.length_le : ∀ {rs : List ℕ} {e : ℕ}, IsPartition rs e → rs.length ≤ e
  | [], _, h => h.elim
  | [_], _, h => by have := h.2; simp; omega
  | _ :: _ :: _, _, h => by
    have h1 := h.1
    have := IsPartition.length_le h.2
    simp only [List.length_cons] at this ⊢
    omega

/-- The value of each layer of the dynamic program, with `⊤` where no partition exists. -/
noncomputable def layer (w : ℕ → ℕ → ℝ) : ℕ → ℕ → WithTop ℝ
  | 0, e => if 0 < e then (w 0 e : WithTop ℝ) else ⊤
  | m + 1, e => (Finset.Ico (m + 1) e).inf fun j => layer w m j + (w j e : WithTop ℝ)

/-- Each layer is finite where a partition exists. -/
theorem layer_ne_top (w : ℕ → ℕ → ℝ) : ∀ {m e : ℕ}, m < e → layer w m e ≠ ⊤
  | 0, e, he => by simp [layer, he]
  | m + 1, e, he => by
    have hmem : m + 1 ∈ Finset.Ico (m + 1) e := Finset.mem_Ico.2 ⟨le_rfl, he⟩
    have hle : layer w (m + 1) e ≤ layer w m (m + 1) + (w (m + 1) e : WithTop ℝ) := by
      simp only [layer]
      exact Finset.inf_le (f := fun j => layer w m j + (w j e : WithTop ℝ)) hmem
    intro htop
    rw [htop, top_le_iff, WithTop.add_eq_top] at hle
    rcases hle with h | h
    · exact layer_ne_top w (Nat.lt_succ_self m) h
    · exact WithTop.coe_ne_top h

/-- **Lower bound.** Every partition of `[0, e)` into `m + 1` intervals costs at least `layer m e`. -/
theorem layer_le_partCost (w : ℕ → ℕ → ℝ) :
    ∀ (m : ℕ) (rs : List ℕ) (e : ℕ), IsPartition rs e → rs.length = m + 1 → layer w m e ≤ (partCost w rs e : WithTop ℝ)
  | 0, [s], e, h, _ => by
    obtain ⟨rfl, he⟩ := h
    simp [layer, he, partCost]
  | 0, [], _, h, _ => h.elim
  | 0, _ :: _ :: _, _, _, hlen => by simp at hlen
  | m + 1, [], _, h, _ => h.elim
  | m + 1, [_], _, _, hlen => by simp at hlen
  | m + 1, s :: s' :: ss, e, h, hlen => by
    have hlen' : (s' :: ss).length = m + 1 := by simpa using hlen
    have ih := layer_le_partCost w m (s' :: ss) s h.2 hlen'
    have hs : s ∈ Finset.Ico (m + 1) e := by
      have := h.2.length_le
      rw [hlen'] at this
      exact Finset.mem_Ico.2 ⟨this, h.1⟩
    calc layer w (m + 1) e ≤ layer w m s + (w s e : WithTop ℝ) := by
          simp only [layer]
          exact Finset.inf_le (f := fun j => layer w m j + (w j e : WithTop ℝ)) hs
      _ ≤ (partCost w (s' :: ss) s : WithTop ℝ) + (w s e : WithTop ℝ) := by gcongr
      _ = (partCost w (s :: s' :: ss) e : WithTop ℝ) := by
          rw [show partCost w (s :: s' :: ss) e = w s e + partCost w (s' :: ss) s from rfl, WithTop.coe_add,
            add_comm]

/-- The walk back of the code: the last interval starts at `choice m e`, and the rest is the walk back of
`[0, choice m e)` with one interval fewer. -/
def backtrack (choice : ℕ → ℕ → ℕ) : ℕ → ℕ → List ℕ
  | 0, _ => [0]
  | m + 1, e => choice (m + 1) e :: backtrack choice m (choice (m + 1) e)

/-- **The walk back is optimal.** If each `choice (m + 1) e` with `e ≤ N` is a column of `[m + 1, e)` with the
smallest `layer m j + w j e`, the walk back gives a partition of `[0, e)` into `m + 1` intervals with the cost
`layer m e`. -/
theorem backtrack_spec (w : ℕ → ℕ → ℝ) (choice : ℕ → ℕ → ℕ) (N : ℕ)
    (hchoice : ∀ m e, m + 1 < e → e ≤ N → choice (m + 1) e ∈ Finset.Ico (m + 1) e ∧
      ∀ j ∈ Finset.Ico (m + 1) e, layer w m (choice (m + 1) e) + (w (choice (m + 1) e) e : WithTop ℝ) ≤
        layer w m j + (w j e : WithTop ℝ)) :
    ∀ (m e : ℕ), m < e → e ≤ N → IsPartition (backtrack choice m e) e ∧ (backtrack choice m e).length = m + 1 ∧
      layer w m e = (partCost w (backtrack choice m e) e : WithTop ℝ)
  | 0, e, he, _ => by
    refine ⟨⟨rfl, he⟩, rfl, ?_⟩
    simp [layer, he, backtrack, partCost]
  | m + 1, e, he, heN => by
    obtain ⟨hmem, hmin⟩ := hchoice m e he heN
    set j := choice (m + 1) e
    have hj := Finset.mem_Ico.1 hmem
    obtain ⟨hpart, hlen, hval⟩ := backtrack_spec w choice N hchoice m j (by omega) (by omega)
    have hunfold : backtrack choice (m + 1) e = j :: backtrack choice m j := rfl
    rw [hunfold]
    refine ⟨?_, by simp [hlen], ?_⟩
    · cases hb : backtrack choice m j with
      | nil => rw [hb] at hpart; exact hpart.elim
      | cons s ss => rw [hb] at hpart; exact ⟨hj.2, hpart⟩
    · have hinf : layer w (m + 1) e = layer w m j + (w j e : WithTop ℝ) := by
        simp only [layer]
        apply le_antisymm (Finset.inf_le (f := fun j => layer w m j + (w j e : WithTop ℝ)) hmem)
        exact Finset.le_inf fun k hk => hmin k hk
      rw [hinf, hval, partCost, WithTop.coe_add, add_comm]

/-- **The dynamic program is optimal.** If `m < e`, `layer m e` is the smallest cost of a partition of `[0, e)` into
`m + 1` non-empty contiguous intervals: a lower bound that some partition reaches. -/
theorem layer_isLeast (w : ℕ → ℕ → ℝ) (choice : ℕ → ℕ → ℕ) (N : ℕ)
    (hchoice : ∀ m e, m + 1 < e → e ≤ N → choice (m + 1) e ∈ Finset.Ico (m + 1) e ∧
      ∀ j ∈ Finset.Ico (m + 1) e, layer w m (choice (m + 1) e) + (w (choice (m + 1) e) e : WithTop ℝ) ≤
        layer w m j + (w j e : WithTop ℝ))
    {m e : ℕ} (he : m < e) (heN : e ≤ N) :
    IsLeast {c : WithTop ℝ | ∃ rs, IsPartition rs e ∧ rs.length = m + 1 ∧ c = (partCost w rs e : WithTop ℝ)}
      (layer w m e) := by
  obtain ⟨hpart, hlen, hval⟩ := backtrack_spec w choice N hchoice m e he heN
  refine ⟨⟨_, hpart, hlen, hval⟩, ?_⟩
  rintro c ⟨rs, hrs, hrslen, rfl⟩
  exact layer_le_partCost w m rs e hrs hrslen

end OptimalDiscretizerProofs.KMeans1D.DynamicProgram
