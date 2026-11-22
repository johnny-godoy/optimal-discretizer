import OptimalDiscretizerProofs.Summary.Bounds

/-!
# Axiom check

`lake build` prints the axioms of the main theorems.
Each may use only `propext`, `Classical.choice` and `Quot.sound`.
-/

#print axioms OptimalDiscretizerProofs.Summary.Bounds.mean_between
