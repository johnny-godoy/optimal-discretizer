import OptimalDiscretizerProofs.KMeans1D.Optimality

/-!
# The axioms of the main theorems

Each main theorem may depend only on `propext`, `Classical.choice` and `Quot.sound`. The CI workflow
`.github/workflows/proofs.yml` reads the lines that `#print axioms` writes and fails on any other axiom, and on
`sorryAx`.
-/

#print axioms OptimalDiscretizerProofs.KMeans1D.Smawk.smawk_isLeftmostMin
#print axioms OptimalDiscretizerProofs.KMeans1D.Cost.cost_quadrangle
#print axioms OptimalDiscretizerProofs.KMeans1D.Cost.codeCost_eq_cost
#print axioms OptimalDiscretizerProofs.KMeans1D.DynamicProgram.layer_isLeast
#print axioms OptimalDiscretizerProofs.KMeans1D.Contiguity.exists_contiguous_le
#print axioms OptimalDiscretizerProofs.KMeans1D.Model.layerMatrix_totallyMonotone
#print axioms OptimalDiscretizerProofs.KMeans1D.Model.codeLayer_eq_layer
#print axioms OptimalDiscretizerProofs.KMeans1D.Model.optimal_starts_isLeast
#print axioms OptimalDiscretizerProofs.KMeans1D.Optimality.codeStarts_le_clusterCost
