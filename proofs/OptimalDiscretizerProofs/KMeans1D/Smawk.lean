import Mathlib

/-!
# SMAWK, as `smawk` in `optimal_partition.pyx` implements it

The matrix is a function `M : ℕ → ℕ → α` into a linear order: `M row column`. The rows and the columns that the
search covers are lists of indices in increasing order. The code walks the rows as an arithmetic progression
`first_row + row_step * t`; the model uses the list of those indices, which is the same sequence.

* `popWhile` and `reduceStep` are the REDUCE loop: the stack of kept columns, with the top of the stack at the head of
  the list. The row that the code compares at is `rows[kept_count - 1]`, which is `rowAt rows s.length` for a stack
  `t :: s`.
* `odds` is the list of rows at the odd positions, on which the code recurses.
* `scan` and `interp` are the INTERPOLATE loop: `scan` walks the kept columns from the current position to the
  column `stop` and keeps the first strict minimum.

The main theorem `smawk_isLeftmostMin` says: if the matrix is totally monotone on the rows and the columns, then for
each row the result is the leftmost column with the smallest entry. Ties go to the leftmost column, as in the code.
-/

namespace OptimalDiscretizerProofs.KMeans1D.Smawk

variable {α : Type*} [LinearOrder α]

/-! ## Leftmost minima -/

/-- `c` is the leftmost column of `S` with the smallest entry in row `r`. -/
def IsLeftmostMin (M : ℕ → ℕ → α) (r : ℕ) (S : List ℕ) (c : ℕ) : Prop :=
  c ∈ S ∧ (∀ d ∈ S, M r c ≤ M r d) ∧ ∀ d ∈ S, d < c → M r c < M r d

/-- The total monotonicity that SMAWK needs, on the rows `R` and the columns `C`: if a later column is strictly
better than an earlier column in some row, it is strictly better in every later row. -/
def TotallyMonotone (M : ℕ → ℕ → α) (R C : List ℕ) : Prop :=
  ∀ i ∈ R, ∀ i' ∈ R, i < i' → ∀ j ∈ C, ∀ j' ∈ C, j < j' → M i j' < M i j → M i' j' < M i' j

theorem IsLeftmostMin.unique {M : ℕ → ℕ → α} {r : ℕ} {S : List ℕ} {c c' : ℕ}
    (hc : IsLeftmostMin M r S c) (hc' : IsLeftmostMin M r S c') : c = c' := by
  rcases lt_trichotomy c c' with h | h | h
  · exact absurd (hc'.2.2 c hc.1 h) (not_lt.2 (hc.2.1 c' hc'.1))
  · exact h
  · exact absurd (hc.2.2 c' hc'.1 h) (not_lt.2 (hc'.2.1 c hc.1))

/-- A leftmost minimum of a list is a leftmost minimum of each sublist that holds it. -/
theorem IsLeftmostMin.of_subset {M : ℕ → ℕ → α} {r : ℕ} {S T : List ℕ} {c : ℕ}
    (hc : IsLeftmostMin M r S c) (hT : ∀ d ∈ T, d ∈ S) (hcT : c ∈ T) : IsLeftmostMin M r T c :=
  ⟨hcT, fun d hd => hc.2.1 d (hT d hd), fun d hd hlt => hc.2.2 d (hT d hd) hlt⟩

/-- A column of the list that is strictly better, or as good and further left, is not the leftmost minimum. -/
theorem not_isLeftmostMin_of_better {M : ℕ → ℕ → α} {r : ℕ} {S : List ℕ} {c d : ℕ} (hd : d ∈ S)
    (hbetter : M r d < M r c ∨ (d < c ∧ M r d ≤ M r c)) : ¬ IsLeftmostMin M r S c := by
  intro hc
  rcases hbetter with h | ⟨hlt, hle⟩
  · exact absurd (hc.2.1 d hd) (not_le.2 h)
  · exact absurd (hc.2.2 d hd hlt) (not_lt.2 hle)

/-- One step of the search for the first strict minimum: the code replaces the best column only on `<`. -/
def argminStep (M : ℕ → ℕ → α) (r best c : ℕ) : ℕ := if M r c < M r best then c else best

theorem argminStep_isLeftmostMin {M : ℕ → ℕ → α} {r : ℕ} {A : List ℕ} {best c : ℕ}
    (h : IsLeftmostMin M r A best) (hlt : ∀ a ∈ A, a < c) :
    IsLeftmostMin M r (A ++ [c]) (argminStep M r best c) := by
  unfold argminStep
  split_ifs with hcb
  · refine ⟨by simp, fun d hd => ?_, fun d hd hdc => ?_⟩
    · rcases List.mem_append.1 hd with hd | hd
      · exact le_of_lt (lt_of_lt_of_le hcb (h.2.1 d hd))
      · simp only [List.mem_singleton] at hd; subst hd; exact le_rfl
    · rcases List.mem_append.1 hd with hd | hd
      · exact lt_of_lt_of_le hcb (h.2.1 d hd)
      · simp only [List.mem_singleton] at hd; subst hd; exact absurd hdc (lt_irrefl _)
  · refine ⟨List.mem_append_left _ h.1, fun d hd => ?_, fun d hd hdb => ?_⟩
    · rcases List.mem_append.1 hd with hd | hd
      · exact h.2.1 d hd
      · simp only [List.mem_singleton] at hd; subst hd; exact not_lt.1 hcb
    · rcases List.mem_append.1 hd with hd | hd
      · exact h.2.2 d hd hdb
      · simp only [List.mem_singleton] at hd; subst hd
        exact absurd (hlt best h.1) (not_lt.2 (le_of_lt hdb))

theorem foldl_argminStep_isLeftmostMin (M : ℕ → ℕ → α) (r : ℕ) :
    ∀ (cs A : List ℕ) (best : ℕ), cs.Pairwise (· < ·) → IsLeftmostMin M r A best →
      (∀ a ∈ A, ∀ c ∈ cs, a < c) → IsLeftmostMin M r (A ++ cs) (cs.foldl (argminStep M r) best)
  | [], A, best, _, h, _ => by simpa using h
  | c :: cs, A, best, hs, h, hlt => by
    rw [List.foldl_cons]
    have hstep : IsLeftmostMin M r (A ++ [c]) (argminStep M r best c) :=
      argminStep_isLeftmostMin h (fun a ha => hlt a ha c (by simp))
    have := foldl_argminStep_isLeftmostMin M r cs (A ++ [c]) _ (List.pairwise_cons.1 hs).2 hstep (by
      intro a ha d hd
      rcases List.mem_append.1 ha with ha | ha
      · exact hlt a ha d (by simp [hd])
      · simp only [List.mem_singleton] at ha; subst ha
        exact (List.pairwise_cons.1 hs).1 d hd)
    simpa using this

/-- The first strict minimum of a list, as the scans of the code compute it. -/
def leftmostMin (M : ℕ → ℕ → α) (r : ℕ) : List ℕ → ℕ
  | [] => 0
  | c :: cs => cs.foldl (argminStep M r) c

theorem leftmostMin_spec (M : ℕ → ℕ → α) (r : ℕ) {S : List ℕ} (hs : S.Pairwise (· < ·)) (hne : S ≠ []) :
    IsLeftmostMin M r S (leftmostMin M r S) := by
  cases S with
  | nil => exact absurd rfl hne
  | cons c cs =>
    have h := foldl_argminStep_isLeftmostMin M r cs [c] c (List.pairwise_cons.1 hs).2
      ⟨by simp, by simp, by simp⟩ (by simpa using (List.pairwise_cons.1 hs).1)
    simpa [leftmostMin] using h

/-- In a totally monotone matrix, the leftmost minimum of a later row is not to the left of that of an earlier row. -/
theorem IsLeftmostMin.mono {M : ℕ → ℕ → α} {R C S : List ℕ} (htm : TotallyMonotone M R C)
    (hS : ∀ d ∈ S, d ∈ C) {p r a b : ℕ} (hp : p ∈ R) (hr : r ∈ R) (hpr : p < r)
    (ha : IsLeftmostMin M p S a) (hb : IsLeftmostMin M r S b) : a ≤ b := by
  by_contra hba
  rw [not_le] at hba
  have h1 : M p a < M p b := ha.2.2 b hb.1 hba
  have h2 : M r a < M r b := htm p hp r hr hpr b (hS b hb.1) a (hS a ha.1) hba h1
  exact absurd (hb.2.1 a ha.1) (not_le.2 h2)

/-- Total monotonicity holds on every sublist of the rows and of the columns. -/
theorem TotallyMonotone.mono {M : ℕ → ℕ → α} {R C R' C' : List ℕ} (htm : TotallyMonotone M R C)
    (hR : ∀ i ∈ R', i ∈ R) (hC : ∀ j ∈ C', j ∈ C) : TotallyMonotone M R' C' :=
  fun i hi i' hi' hii j hj j' hj' hjj h => htm i (hR i hi) i' (hR i' hi') hii j (hC j hj) j' (hC j' hj') hjj h

/-! ## REDUCE -/

/-- The row of the stack position `p`: `rows[p]` in the code. -/
def rowAt (rows : List ℕ) (p : ℕ) : ℕ := rows.getD p 0

/-- The `while` loop of REDUCE: pop the top `t` of the stack `t :: s` while the new column `c` is strictly better in
the row of the position of `t`, which is `rows[kept_count - 1] = rowAt rows s.length`. -/
def popWhile (M : ℕ → ℕ → α) (rows : List ℕ) (c : ℕ) : List ℕ → List ℕ
  | [] => []
  | t :: s => if M (rowAt rows s.length) c < M (rowAt rows s.length) t then popWhile M rows c s else t :: s

/-- One column of REDUCE: pop, then push the column if the stack has fewer entries than there are rows. -/
def reduceStep (M : ℕ → ℕ → α) (rows stack : List ℕ) (c : ℕ) : List ℕ :=
  if (popWhile M rows c stack).length < rows.length then c :: popWhile M rows c stack
  else popWhile M rows c stack

/-- REDUCE: the kept columns, in increasing order (the code's array `kept`). -/
def reduce (M : ℕ → ℕ → α) (rows cols : List ℕ) : List ℕ :=
  (cols.foldl (reduceStep M rows) []).reverse

/-- The order of the stack, top first: each column is no better than the column below it, in every row above its
position. -/
def Chain (M : ℕ → ℕ → α) (rows : List ℕ) : List ℕ → Prop
  | [] => True
  | [_] => True
  | t :: t' :: s => t' < t ∧ (∀ q ≤ s.length, M (rowAt rows q) t' ≤ M (rowAt rows q) t) ∧ Chain M rows (t' :: s)

theorem Chain.tail {M : ℕ → ℕ → α} {rows : List ℕ} {t : ℕ} {s : List ℕ} (h : Chain M rows (t :: s)) :
    Chain M rows s := by
  cases s with
  | nil => trivial
  | cons t' s => exact h.2.2

theorem Chain.pairwise {M : ℕ → ℕ → α} {rows : List ℕ} :
    ∀ {s : List ℕ}, Chain M rows s → s.Pairwise (· > ·)
  | [], _ => List.Pairwise.nil
  | [_], _ => List.pairwise_singleton _ _
  | t :: t' :: s, h => by
    have hrest := Chain.pairwise h.2.2
    refine List.Pairwise.cons (fun y hy => ?_) hrest
    rcases List.mem_cons.1 hy with rfl | hy
    · exact h.1
    · exact lt_trans ((List.pairwise_cons.1 hrest).1 y hy) h.1

theorem rowAt_mem {rows : List ℕ} {q : ℕ} (hq : q < rows.length) : rowAt rows q ∈ rows := by
  unfold rowAt
  rw [List.getD_eq_getElem _ _ hq]
  exact List.getElem_mem hq

theorem rowAt_lt {rows : List ℕ} (hrows : rows.Pairwise (· < ·)) {q q' : ℕ} (hqq : q < q')
    (hq' : q' < rows.length) : rowAt rows q < rowAt rows q' := by
  unfold rowAt
  rw [List.getD_eq_getElem _ _ (lt_trans hqq hq'), List.getD_eq_getElem _ _ hq']
  exact List.pairwise_iff_getElem.1 hrows q q' (lt_trans hqq hq') hq' hqq

/-- Total monotonicity, read at stack positions. -/
theorem tm_pos {M : ℕ → ℕ → α} {rows C : List ℕ} (htm : TotallyMonotone M rows C)
    (hrows : rows.Pairwise (· < ·)) {q q' : ℕ} (hqq : q ≤ q') (hq' : q' < rows.length) {j j' : ℕ} (hj : j ∈ C)
    (hj' : j' ∈ C) (hjj : j < j') (h : M (rowAt rows q) j' < M (rowAt rows q) j) :
    M (rowAt rows q') j' < M (rowAt rows q') j := by
  rcases lt_or_eq_of_le hqq with hlt | rfl
  · exact htm _ (rowAt_mem (lt_trans hlt hq')) _ (rowAt_mem hq') (rowAt_lt hrows hlt hq') j hj j' hj' hjj h
  · exact h

theorem tm_pos_le {M : ℕ → ℕ → α} {rows C : List ℕ} (htm : TotallyMonotone M rows C)
    (hrows : rows.Pairwise (· < ·)) {q q' : ℕ} (hqq : q ≤ q') (hq' : q' < rows.length) {j j' : ℕ} (hj : j ∈ C)
    (hj' : j' ∈ C) (hjj : j < j') (h : M (rowAt rows q') j ≤ M (rowAt rows q') j') :
    M (rowAt rows q) j ≤ M (rowAt rows q) j' := by
  by_contra hcon
  exact absurd h (not_le.2 (tm_pos htm hrows hqq hq' hj hj' hjj (lt_of_not_ge hcon)))

theorem popWhile_suffix (M : ℕ → ℕ → α) (rows : List ℕ) (c : ℕ) :
    ∀ s : List ℕ, popWhile M rows c s <:+ s
  | [] => List.suffix_refl _
  | t :: s => by
    unfold popWhile
    split_ifs
    · exact (popWhile_suffix M rows c s).trans (List.suffix_cons t s)
    · exact List.suffix_refl _

theorem Chain.of_suffix {M : ℕ → ℕ → α} {rows : List ℕ} :
    ∀ {s s' : List ℕ}, s' <:+ s → Chain M rows s → Chain M rows s'
  | [], s', hs', _ => by rw [List.suffix_nil.1 hs']; trivial
  | t :: s, s', hs', h => by
    rcases List.suffix_cons_iff.1 hs' with rfl | hs'
    · exact h
    · exact Chain.of_suffix hs' h.tail

/-- The top of the stack after the pops is not worse than the new column in the row of its position. -/
theorem popWhile_stop (M : ℕ → ℕ → α) (rows : List ℕ) (c : ℕ) :
    ∀ (s : List ℕ) (t : ℕ) (s' : List ℕ), popWhile M rows c s = t :: s' →
      ¬ M (rowAt rows s'.length) c < M (rowAt rows s'.length) t
  | [], t, s', h => by simp [popWhile] at h
  | u :: s, t, s', h => by
    unfold popWhile at h
    split_ifs at h with hc
    · exact popWhile_stop M rows c s t s' h
    · obtain ⟨rfl, rfl⟩ := List.cons.inj h
      exact hc

/-- The pops remove no leftmost minimum: a popped column is strictly worse than the new column in the rows at and
below its position, and no better than the column below it in the rows above. -/
theorem popWhile_keeps {M : ℕ → ℕ → α} {rows C : List ℕ} (htm : TotallyMonotone M rows C)
    (hrows : rows.Pairwise (· < ·)) {c : ℕ} (hc : c ∈ C) {P : List ℕ} {q x : ℕ} (hq : q < rows.length)
    (hx : IsLeftmostMin M (rowAt rows q) (P ++ [c]) x) :
    ∀ s : List ℕ, Chain M rows s → s.length ≤ rows.length → (∀ y ∈ s, y ∈ P ∧ y ∈ C ∧ y < c) → x ∈ s →
      x ∈ popWhile M rows c s
  | [], _, _, _, hxs => absurd hxs List.not_mem_nil
  | t :: s, hch, hlen, hs, hxs => by
    unfold popWhile
    split_ifs with hpop
    · have hxt : x ≠ t := by
        rintro rfl
        have hxC := (hs x List.mem_cons_self).2.1
        have hxc := (hs x List.mem_cons_self).2.2
        rcases le_or_gt s.length q with hle | hlt
        · have hbetter := tm_pos htm hrows hle hq hxC hc hxc hpop
          exact not_isLeftmostMin_of_better (d := c) (by simp) (Or.inl hbetter) hx
        · cases s with
          | nil => simp at hlt
          | cons t' s'' =>
            have hle' : q ≤ s''.length := by simp at hlt; omega
            have hbetter := hch.2.1 q hle'
            exact not_isLeftmostMin_of_better (d := t')
              (List.mem_append_left _ (hs t' (by simp)).1) (Or.inr ⟨hch.1, hbetter⟩) hx
      have hxs' : x ∈ s := by
        rcases List.mem_cons.1 hxs with h | h
        · exact absurd h hxt
        · exact h
      exact popWhile_keeps htm hrows hc hq hx s hch.tail (by simp at hlen; omega)
        (fun y hy => hs y (List.mem_cons_of_mem _ hy)) hxs'
    · exact hxs

/-- The invariant of REDUCE after the columns `P`. -/
structure ReduceInv (M : ℕ → ℕ → α) (rows P stack : List ℕ) : Prop where
  chain : Chain M rows stack
  length_le : stack.length ≤ rows.length
  mem : ∀ y ∈ stack, y ∈ P
  keeps : ∀ q < rows.length, ∀ x, IsLeftmostMin M (rowAt rows q) P x → x ∈ stack

theorem reduceStep_inv {M : ℕ → ℕ → α} {rows C : List ℕ} (htm : TotallyMonotone M rows C)
    (hrows : rows.Pairwise (· < ·)) {P stack : List ℕ} {c : ℕ} (hinv : ReduceInv M rows P stack)
    (hc : c ∈ C) (hP : ∀ y ∈ P, y ∈ C ∧ y < c) :
    ReduceInv M rows (P ++ [c]) (reduceStep M rows stack c) := by
  set s' := popWhile M rows c stack with hs'
  have hsuf : s' <:+ stack := popWhile_suffix M rows c stack
  have hch' : Chain M rows s' := Chain.of_suffix hsuf hinv.chain
  have hmem' : ∀ y ∈ s', y ∈ P := fun y hy => hinv.mem y (hsuf.subset hy)
  have hlen' : s'.length ≤ rows.length := le_trans hsuf.length_le hinv.length_le
  -- the column at the top of s' is no better than c in every row up to its position
  have htop : ∀ t s'', s' = t :: s'' → ∀ q ≤ s''.length, M (rowAt rows q) t ≤ M (rowAt rows q) c := by
    intro t s'' heq q hq
    have hstop := popWhile_stop M rows c stack t s'' (hs'.symm.trans heq)
    have hlt : s''.length < rows.length := by
      have := hlen'; rw [heq] at this; simp at this; omega
    have ht : t ∈ P := hmem' t (by rw [heq]; simp)
    exact tm_pos_le htm hrows hq hlt (hP t ht).1 hc (hP t ht).2 (not_lt.1 hstop)
  unfold reduceStep
  rw [← hs']
  split_ifs with hroom
  · refine ⟨?_, by simp only [List.length_cons]; omega, ?_, ?_⟩
    · cases hcase : s' with
      | nil => trivial
      | cons t s'' =>
        rw [hcase] at hch'
        exact ⟨(hP t (hmem' t (by rw [hcase]; simp))).2, htop t s'' hcase, hch'⟩
    · intro y hy
      rcases List.mem_cons.1 hy with rfl | hy
      · simp
      · exact List.mem_append_left _ (hmem' y hy)
    · intro q hq x hx
      by_cases hxc : x = c
      · rw [hxc]; exact List.mem_cons_self
      · have hxP : x ∈ P := by
          rcases List.mem_append.1 hx.1 with h | h
          · exact h
          · simp at h; exact absurd h hxc
        have hxP' := hinv.keeps q hq x (hx.of_subset (fun d hd => List.mem_append_left _ hd) hxP)
        exact List.mem_cons_of_mem _ (popWhile_keeps htm hrows hc hq hx stack hinv.chain hinv.length_le
          (fun y hy => ⟨hinv.mem y hy, (hP y (hinv.mem y hy)).1, (hP y (hinv.mem y hy)).2⟩) hxP')
  · refine ⟨hch', hlen', fun y hy => List.mem_append_left _ (hmem' y hy), ?_⟩
    intro q hq x hx
    by_cases hxc : x = c
    · exfalso
      cases hcase : s' with
      | nil => rw [hcase] at hroom; simp only [List.length_nil, not_lt, nonpos_iff_eq_zero] at hroom; omega
      | cons t s'' =>
        have hfull : s''.length = rows.length - 1 := by
          have := hlen'; rw [hcase] at this hroom; simp only [List.length_cons, not_lt] at this hroom; omega
        have htP : t ∈ P := hmem' t (by rw [hcase]; simp)
        have hle := htop t s'' hcase q (by omega)
        rw [hxc] at hx
        exact not_isLeftmostMin_of_better (d := t) (List.mem_append_left _ htP)
          (Or.inr ⟨(hP t htP).2, hle⟩) hx
    · have hxP : x ∈ P := by
        rcases List.mem_append.1 hx.1 with h | h
        · exact h
        · simp at h; exact absurd h hxc
      have hxP' := hinv.keeps q hq x (hx.of_subset (fun d hd => List.mem_append_left _ hd) hxP)
      exact popWhile_keeps htm hrows hc hq hx stack hinv.chain hinv.length_le
        (fun y hy => ⟨hinv.mem y hy, (hP y (hinv.mem y hy)).1, (hP y (hinv.mem y hy)).2⟩) hxP'

theorem reduce_fold_inv {M : ℕ → ℕ → α} {rows C : List ℕ} (htm : TotallyMonotone M rows C)
    (hrows : rows.Pairwise (· < ·)) :
    ∀ (cs P stack : List ℕ), ReduceInv M rows P stack → (∀ y ∈ P ++ cs, y ∈ C) →
      (P ++ cs).Pairwise (· < ·) → ReduceInv M rows (P ++ cs) (cs.foldl (reduceStep M rows) stack)
  | [], P, stack, hinv, _, _ => by simpa using hinv
  | c :: cs, P, stack, hinv, hC, hsorted => by
    rw [List.foldl_cons]
    have hc : c ∈ C := hC c (by simp)
    have hP : ∀ y ∈ P, y ∈ C ∧ y < c := fun y hy =>
      ⟨hC y (List.mem_append_left _ hy), (List.pairwise_append.1 hsorted).2.2 y hy c (by simp)⟩
    have hstep := reduceStep_inv htm hrows hinv hc hP
    have := reduce_fold_inv htm hrows cs (P ++ [c]) _ hstep (by simpa using hC) (by simpa using hsorted)
    simpa using this

/-- What REDUCE gives: increasing columns of `cols`, at most one for each row, that hold the leftmost minimum of
each row over `cols`. -/
theorem reduce_spec {M : ℕ → ℕ → α} {rows cols : List ℕ} (htm : TotallyMonotone M rows cols)
    (hrows : rows.Pairwise (· < ·)) (hcols : cols.Pairwise (· < ·)) :
    (reduce M rows cols).Pairwise (· < ·) ∧ (∀ y ∈ reduce M rows cols, y ∈ cols) ∧
      (reduce M rows cols).length ≤ rows.length ∧
      ∀ q < rows.length, ∀ x, IsLeftmostMin M (rowAt rows q) cols x → x ∈ reduce M rows cols := by
  have hinv := reduce_fold_inv htm hrows cols [] [] ⟨trivial, by simp, by simp, fun _ _ x hx => by
    simpa using hx.1⟩ (by simp) (by simpa using hcols)
  simp only [List.nil_append] at hinv
  refine ⟨?_, fun y hy => hinv.mem y (List.mem_reverse.1 hy), by simpa [reduce] using hinv.length_le,
    fun q hq x hx => List.mem_reverse.2 (hinv.keeps q hq x hx)⟩
  unfold reduce
  exact List.pairwise_reverse.2 (by simpa [flip] using hinv.chain.pairwise)

/-! ## The recursion on the odd rows -/

/-- The rows at the odd positions: `rows[2 * t + 1]` in the code. -/
def odds : List ℕ → List ℕ
  | [] => []
  | [_] => []
  | _ :: b :: rest => b :: odds rest

theorem odds_sublist : ∀ rows : List ℕ, List.Sublist (odds rows) rows
  | [] => List.Sublist.slnil
  | [_] => List.nil_sublist _
  | a :: b :: rest => ((odds_sublist rest).cons_cons b).cons a

theorem odds_length_lt : ∀ {rows : List ℕ}, rows ≠ [] → (odds rows).length < rows.length
  | [], h => absurd rfl h
  | [_], _ => by simp [odds]
  | _ :: b :: rest, _ => by
    have := (odds_sublist rest).length_le
    simp [odds]; omega

/-! ## INTERPOLATE -/

theorem le_getLast_of_pairwise : ∀ {l : List ℕ} (_ : l.Pairwise (· < ·)) (hne : l ≠ []) {x : ℕ}, x ∈ l →
    x ≤ l.getLast hne
  | [], _, hne, _, _ => absurd rfl hne
  | [a], _, _, x, hx => by simp at hx; simp [hx]
  | a :: b :: t, h, _, x, hx => by
    rw [List.getLast_cons_cons]
    rcases List.mem_cons.1 hx with rfl | hx
    · exact le_of_lt (lt_of_lt_of_le ((List.pairwise_cons.1 h).1 b (by simp))
        (le_getLast_of_pairwise (List.pairwise_cons.1 h).2 (by simp) (by simp)))
    · exact le_getLast_of_pairwise (List.pairwise_cons.1 h).2 _ hx

/-- The last kept column, `kept[kept_count - 1]` in the code, is in the list and right of every other column. -/
theorem getLastD_spec {l : List ℕ} (h : l.Pairwise (· < ·)) (hne : l ≠ []) :
    l.getLastD 0 ∈ l ∧ ∀ x ∈ l, x ≤ l.getLastD 0 := by
  rw [List.getLastD_eq_getLast?, List.getLast?_eq_some_getLast hne, Option.getD_some]
  exact ⟨List.getLast_mem hne, fun x hx => le_getLast_of_pairwise h hne hx⟩

/-- The inner loop of INTERPOLATE. `ks` holds the kept columns from the current position on, and `best` is the best
column so far. The loop moves right until the column `stop`, and it replaces `best` only on a strictly smaller
entry. It returns the best column and the columns from `stop` on, which is the next start position. -/
def scan (M : ℕ → ℕ → α) (r stop best : ℕ) : List ℕ → ℕ × List ℕ
  | [] => (best, [])
  | [k] => (best, [k])
  | k :: k' :: ks => if k = stop then (best, k :: k' :: ks) else scan M r stop (argminStep M r best k') (k' :: ks)

theorem scan_spec (M : ℕ → ℕ → α) (r stop : ℕ) :
    ∀ (rest : List ℕ) (k : ℕ) (A : List ℕ) (best : ℕ), (k :: rest).Pairwise (· < ·) → stop ∈ k :: rest →
      IsLeftmostMin M r A best → (∀ a ∈ A, ∀ d ∈ rest, a < d) →
      (scan M r stop best (k :: rest)).2 = (k :: rest).filter (fun d => stop ≤ d) ∧
        IsLeftmostMin M r (A ++ rest.filter (fun d => d ≤ stop)) (scan M r stop best (k :: rest)).1
  | [], k, A, best, _, hstop, h, _ => by
    simp only [List.mem_singleton] at hstop
    subst hstop
    simpa [scan] using h
  | k' :: rest, k, A, best, hs, hstop, h, hlt => by
    have hkrest := (List.pairwise_cons.1 hs).1
    unfold scan
    split_ifs with hk
    · subst hk
      refine ⟨?_, ?_⟩
      · symm; rw [List.filter_eq_self]; intro d hd
        rcases List.mem_cons.1 hd with rfl | hd
        · simp
        · simpa using le_of_lt (hkrest d hd)
      · have : (k' :: rest).filter (fun d => decide (d ≤ k)) = [] := by
          rw [List.filter_eq_nil_iff]; intro d hd; simpa using hkrest d hd
        simpa [this] using h
    · have hstop' : stop ∈ k' :: rest := by
        rcases List.mem_cons.1 hstop with h' | h'
        · exact absurd h'.symm hk
        · exact h'
      have hkstop : k < stop := hkrest stop hstop'
      have hk'stop : k' ≤ stop := by
        rcases List.mem_cons.1 hstop' with h' | h'
        · exact le_of_eq h'.symm
        · exact le_of_lt ((List.pairwise_cons.1 (List.pairwise_cons.1 hs).2).1 stop h')
      have hstep := argminStep_isLeftmostMin (c := k') h (fun a ha => hlt a ha k' (by simp))
      have ih := scan_spec M r stop rest k' (A ++ [k']) (argminStep M r best k') (List.pairwise_cons.1 hs).2
        hstop' hstep (by
          intro a ha d hd
          rcases List.mem_append.1 ha with ha | ha
          · exact hlt a ha d (by simp [hd])
          · simp only [List.mem_singleton] at ha; subst ha
            exact (List.pairwise_cons.1 (List.pairwise_cons.1 hs).2).1 d hd)
      refine ⟨?_, ?_⟩
      · rw [ih.1]; simp [List.filter_cons, not_le.2 hkstop]
      · have := ih.2
        simpa [List.filter_cons, hk'stop] using this

/-- INTERPOLATE: for each row at an even position, scan from the current position to the leftmost minimum of the
next row, which the recursion found, or to the last kept column for the last row. -/
def interp (M : ℕ → ℕ → α) (f : ℕ → ℕ) (lastCol : ℕ) : List ℕ → List ℕ → (ℕ → ℕ) → (ℕ → ℕ)
  | [], _, g => g
  | [r], ks, g => Function.update g r (scan M r lastCol (ks.headD 0) ks).1
  | r :: r' :: rs, ks, g =>
    interp M f lastCol rs (scan M r (f r') (ks.headD 0) ks).2
      (Function.update g r (scan M r (f r') (ks.headD 0) ks).1)

theorem interp_not_mem (M : ℕ → ℕ → α) (f : ℕ → ℕ) (lastCol : ℕ) :
    ∀ (rs ks : List ℕ) (g : ℕ → ℕ) (x : ℕ), x ∉ rs → interp M f lastCol rs ks g x = g x
  | [], _, _, _, _ => rfl
  | [r], ks, g, x, hx => by
    simp only [List.mem_singleton] at hx
    simp [interp, Function.update_of_ne hx]
  | r :: r' :: rs, ks, g, x, hx => by
    simp only [List.mem_cons, not_or] at hx
    simp only [interp]
    rw [interp_not_mem M f lastCol rs _ _ x hx.2.2, Function.update_of_ne hx.1]

/-- The scan of a row over the columns from a start column `lo` that is not right of the leftmost minimum, up to a
column `stop` that is not left of it, finds the leftmost minimum. -/
theorem scan_isLeftmostMin {M : ℕ → ℕ → α} {kept : List ℕ} (hkept : kept.Pairwise (· < ·)) {r lo stop x : ℕ}
    (hx : IsLeftmostMin M r kept x) (hlo : lo ≤ x) (hxstop : x ≤ stop) (hstop : stop ∈ kept) :
    IsLeftmostMin M r kept (scan M r stop ((kept.filter (fun d => lo ≤ d)).headD 0)
      (kept.filter (fun d => lo ≤ d))).1 ∧
    (scan M r stop ((kept.filter (fun d => lo ≤ d)).headD 0) (kept.filter (fun d => lo ≤ d))).2 =
      kept.filter (fun d => stop ≤ d) := by
  have hks : (kept.filter (fun d => lo ≤ d)).Pairwise (· < ·) := hkept.filter _
  have hstopks : stop ∈ kept.filter (fun d => lo ≤ d) := by simp [hstop, le_trans hlo hxstop]
  cases hcase : kept.filter (fun d => lo ≤ d) with
  | nil => rw [hcase] at hstopks; simp at hstopks
  | cons k rest =>
    rw [hcase] at hks hstopks
    have hspec := scan_spec M r stop rest k [k] k hks hstopks ⟨by simp, by simp, by simp⟩
      (by simpa using (List.pairwise_cons.1 hks).1)
    have hwindow : ∀ d ∈ [k] ++ rest.filter (fun d => d ≤ stop), d ∈ kept := by
      intro d hd
      have : d ∈ k :: rest := by
        rcases List.mem_append.1 hd with h | h
        · simp at h; simp [h]
        · exact List.mem_cons_of_mem _ (List.mem_of_mem_filter h)
      rw [← hcase] at this
      exact List.mem_of_mem_filter this
    have hxwin : x ∈ [k] ++ rest.filter (fun d => d ≤ stop) := by
      have : x ∈ k :: rest := by rw [← hcase]; simp [hx.1, hlo]
      rcases List.mem_cons.1 this with h | h
      · simp [h]
      · simp [h, hxstop]
    have hxw := hx.of_subset hwindow hxwin
    simp only [List.headD_cons]
    refine ⟨?_, ?_⟩
    · rw [hspec.2.unique hxw]; exact hx
    · rw [hspec.1, ← hcase, List.filter_filter]
      apply List.filter_congr
      intro d _
      by_cases hd : stop ≤ d
      · simp [hd, le_trans hlo (le_trans hxstop hd)]
      · simp [hd]

theorem interp_spec {M : ℕ → ℕ → α} {kept : List ℕ} (hkept : kept.Pairwise (· < ·)) (hne : kept ≠ [])
    (f : ℕ → ℕ) :
    ∀ (rs : List ℕ) (lo : ℕ) (g : ℕ → ℕ), TotallyMonotone M rs kept → rs.Pairwise (· < ·) →
      (∀ r ∈ rs, ∀ x, IsLeftmostMin M r kept x → lo ≤ x) →
      (∀ r ∈ odds rs, IsLeftmostMin M r kept (f r) ∧ g r = f r) →
      ∀ r ∈ rs, IsLeftmostMin M r kept
        (interp M f (kept.getLastD 0) rs (kept.filter (fun d => lo ≤ d)) g r)
  | [], _, _, _, _, _, _, r, hr => absurd hr List.not_mem_nil
  | [r], lo, g, _, _, hlo, _, x, hx => by
    simp only [List.mem_singleton] at hx
    subst hx
    have hlm := leftmostMin_spec M x hkept hne
    have hlast : kept.getLastD 0 ∈ kept := (getLastD_spec hkept hne).1
    have hmax : leftmostMin M x kept ≤ kept.getLastD 0 := (getLastD_spec hkept hne).2 _ hlm.1
    have hscan := scan_isLeftmostMin hkept hlm (hlo x (by simp) _ hlm) hmax hlast
    simp only [interp, Function.update_self]
    exact hscan.1
  | r :: r' :: rs, lo, g, htm, hrs, hlo, hodd, x, hx => by
    have hrr' : r < r' := (List.pairwise_cons.1 hrs).1 r' (by simp)
    have hodd' : IsLeftmostMin M r' kept (f r') ∧ g r' = f r' := hodd r' (by simp [odds])
    have hlm := leftmostMin_spec M r hkept hne
    have hmono : leftmostMin M r kept ≤ f r' :=
      hlm.mono htm (fun d hd => hd) (by simp) (by simp) hrr' hodd'.1
    have hscan := scan_isLeftmostMin hkept hlm (hlo r (by simp) _ hlm) hmono hodd'.1.1
    have hr_notin : r ∉ rs := fun h => absurd ((List.pairwise_cons.1 hrs).1 r (by simp [h])) (lt_irrefl r)
    have hr'_notin : r' ∉ rs := fun h =>
      absurd ((List.pairwise_cons.1 (List.pairwise_cons.1 hrs).2).1 r' h) (lt_irrefl r')
    simp only [interp]
    rw [hscan.2]
    rcases List.mem_cons.1 hx with rfl | hx
    · rw [interp_not_mem M f _ rs _ _ _ hr_notin, Function.update_self]; exact hscan.1
    rcases List.mem_cons.1 hx with rfl | hx
    · rw [interp_not_mem M f _ rs _ _ _ hr'_notin, Function.update_of_ne (ne_of_gt hrr'), hodd'.2]
      exact hodd'.1
    · refine interp_spec hkept hne f rs (f r') _ (htm.mono (fun i hi => by simp [hi]) (fun j hj => hj))
        (List.pairwise_cons.1 (List.pairwise_cons.1 hrs).2).2 ?_ ?_ x hx
      · intro r'' hr'' y hy
        have hr'r'' : r' < r'' := (List.pairwise_cons.1 (List.pairwise_cons.1 hrs).2).1 r'' hr''
        exact hodd'.1.mono htm (fun d hd => hd) (by simp) (by simp [hr'']) hr'r'' hy
      · intro r'' hr''
        have hr''rs : r'' ∈ rs := (odds_sublist rs).subset hr''
        have hne' : r'' ≠ r := fun h => hr_notin (h ▸ hr''rs)
        refine ⟨(hodd r'' (by simp [odds, hr''])).1, ?_⟩
        rw [Function.update_of_ne hne']
        exact (hodd r'' (by simp [odds, hr''])).2

/-! ## SMAWK -/

/-- `smawk` of the code. The function `g` is the array `argmin` before the call; the result is the array after it.
REDUCE keeps the columns, the recursive call fills the rows at the odd positions, and INTERPOLATE fills the rows at
the even positions. -/
def smawk (M : ℕ → ℕ → α) : List ℕ → List ℕ → (ℕ → ℕ) → (ℕ → ℕ)
  | [], _, g => g
  | r :: rs, cols, g =>
    interp M (smawk M (odds (r :: rs)) (reduce M (r :: rs) cols) g) ((reduce M (r :: rs) cols).getLastD 0)
      (r :: rs) (reduce M (r :: rs) cols) (smawk M (odds (r :: rs)) (reduce M (r :: rs) cols) g)
termination_by rows => rows.length
decreasing_by exact odds_length_lt (List.cons_ne_nil r rs)

/-- **SMAWK is correct.** If the matrix is totally monotone on the increasing rows and the increasing, non-empty
columns, then `smawk` gives each row its leftmost column with the smallest entry. -/
theorem smawk_isLeftmostMin (M : ℕ → ℕ → α) :
    ∀ (rows cols : List ℕ) (g : ℕ → ℕ), TotallyMonotone M rows cols → rows.Pairwise (· < ·) →
      cols.Pairwise (· < ·) → cols ≠ [] → ∀ r ∈ rows, IsLeftmostMin M r cols (smawk M rows cols g r)
  | [], _, _, _, _, _, _, r, hr => absurd hr List.not_mem_nil
  | r₀ :: rs, cols, g, htm, hrows, hcols, hne, r, hr => by
    set rows := r₀ :: rs with hrows_def
    set kept := reduce M rows cols with hkept_def
    obtain ⟨hks, hksub, _, hkeeps⟩ := reduce_spec htm hrows hcols
    rw [← hkept_def] at hks hksub hkeeps
    -- the leftmost minimum of each row over cols is kept
    have hkept_lm : ∀ x ∈ rows, IsLeftmostMin M x kept (leftmostMin M x cols) := by
      intro x hx
      obtain ⟨q, hq, hqx⟩ := List.mem_iff_getElem.1 hx
      have hrow : rowAt rows q = x := by unfold rowAt; rw [List.getD_eq_getElem _ _ hq]; exact hqx
      have hlm := leftmostMin_spec M x hcols hne
      have hin := hkeeps q hq (leftmostMin M x cols) (by rw [hrow]; exact hlm)
      exact hlm.of_subset hksub hin
    have hkne : kept ≠ [] := List.ne_nil_of_mem (hkept_lm r₀ List.mem_cons_self).1
    have htm_kept : TotallyMonotone M rows kept := htm.mono (fun i hi => hi) hksub
    have hodd_sub : ∀ x ∈ odds rows, x ∈ rows := fun x hx => (odds_sublist rows).subset hx
    have ih := smawk_isLeftmostMin M (odds rows) kept g (htm_kept.mono hodd_sub (fun j hj => hj))
      (hrows.sublist (odds_sublist rows)) hks hkne
    have hfilter : kept.filter (fun d => 0 ≤ d) = kept := by rw [List.filter_eq_self]; simp
    have hspec := interp_spec hks hkne (smawk M (odds rows) kept g) rows 0 (smawk M (odds rows) kept g) htm_kept
      hrows (fun _ _ _ _ => Nat.zero_le _) (fun x hx => ⟨ih x hx, rfl⟩) r hr
    rw [hfilter] at hspec
    have heq : smawk M rows cols g r = leftmostMin M r cols := by
      rw [smawk]
      exact hspec.unique (hkept_lm r hr)
    rw [heq]
    exact leftmostMin_spec M r hcols hne
termination_by rows => rows.length
decreasing_by exact odds_length_lt (List.cons_ne_nil r₀ rs)

end OptimalDiscretizerProofs.KMeans1D.Smawk
