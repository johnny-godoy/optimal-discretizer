/-!
# Bounds of a sum

`summarize` in `src/optimal_discretizer/domain/summary.py` returns the mean `sum(values) / len(values)`, the minimum
and the maximum. The theorems below show that the sum lies between the length times a lower bound and the length times
an upper bound. With the minimum and the maximum as the bounds, the mean lies between them. The model uses natural
numbers, so the claim covers exact arithmetic and not floating point.
-/

namespace OptimalDiscretizerProofs.Summary.Bounds

/-- If every value is at least `lo`, the sum is at least `lo` times the number of values. -/
theorem lower_bound (lo : Nat) : ∀ (xs : List Nat), (∀ x ∈ xs, lo ≤ x) → lo * xs.length ≤ xs.sum
  | [], _ => by simp
  | x :: rest, h => by
    have hx : lo ≤ x := h x (by simp)
    have hr := lower_bound lo rest (fun y hy => h y (by simp [hy]))
    simp only [List.length_cons, List.sum_cons, Nat.mul_succ]
    omega

/-- If every value is at most `hi`, the sum is at most `hi` times the number of values. -/
theorem upper_bound (hi : Nat) : ∀ (xs : List Nat), (∀ x ∈ xs, x ≤ hi) → xs.sum ≤ hi * xs.length
  | [], _ => by simp
  | x :: rest, h => by
    have hx : x ≤ hi := h x (by simp)
    have hr := upper_bound hi rest (fun y hy => h y (by simp [hy]))
    simp only [List.length_cons, List.sum_cons, Nat.mul_succ]
    omega

/-- The sum lies between the length times `lo` and the length times `hi`, so the mean lies between `lo` and `hi`. -/
theorem mean_between (lo hi : Nat) (xs : List Nat) (h : ∀ x ∈ xs, lo ≤ x ∧ x ≤ hi) :
    lo * xs.length ≤ xs.sum ∧ xs.sum ≤ hi * xs.length :=
  ⟨lower_bound lo xs (fun x hx => (h x hx).1), upper_bound hi xs (fun x hx => (h x hx).2)⟩

end OptimalDiscretizerProofs.Summary.Bounds
