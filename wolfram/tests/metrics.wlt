(* Containment metrics: coverage, Euclidean boundary distance, arc gap,
   RMSE, path length, control energy, angular uniformity, invariances. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
metData = loadCases["metrics_cases.json"];

coverageRatio[guides_, boundary_, radius_] :=
    Mean[Table[If[Min[Table[Norm[b - g], {g, guides}]] <= radius, 1, 0], {b, boundary}]];

maxEuclideanDistance[guides_, boundary_] :=
    Max[Table[Min[Table[Norm[b - g], {g, guides}]], {b, boundary}]];

(* METRIC-COVERAGE-001: hand-computable case. Boundary points at distance
   1, 1, ~2.83 from the nearest guide with radius 1.5 give ratio 2/3. *)
VerificationTest[
    Module[{h = metData["hand_case"]},
        {coverageRatio[h["guides"], h["boundary"], h["coverage_radius"]] == 2/3,
         crossAgreeQ[2/3, h["python_coverage_ratio"]]}],
    {True, True},
    TestID -> "METRIC-COVERAGE-001"
]

(* METRIC-COVERAGE-002: random cases recomputed independently. *)
VerificationTest[
    AllTrue[metData["random_cases"],
        crossAgreeQ[coverageRatio[#["guides"], #["boundary"], #["coverage_radius"]],
            #["python_coverage_ratio"]] &],
    True,
    TestID -> "METRIC-COVERAGE-002"
]

(* METRIC-MAXDIST-001: hand case (max over min distances = sqrt(8)) and all
   random cases. *)
VerificationTest[
    Module[{h = metData["hand_case"]},
        {crossAgreeQ[maxEuclideanDistance[h["guides"], h["boundary"]], h["python_max_euclidean_distance"]],
         crossAgreeQ[Sqrt[8], h["python_max_euclidean_distance"]],
         AllTrue[metData["random_cases"],
             crossAgreeQ[maxEuclideanDistance[#["guides"], #["boundary"]],
                 #["python_max_euclidean_distance"]] &]}],
    {True, True, True},
    TestID -> "METRIC-MAXDIST-001"
]

(* METRIC-INVAR-001: coverage ratio is invariant under the exported rigid
   transform: Python's transformed value equals the untransformed one, and a
   50-digit Wolfram recomputation of the transformed configuration agrees. *)
VerificationTest[
    AllTrue[metData["random_cases"],
        Module[{rot, guides, boundary, angle = SetPrecision[#["rotation_angle"], $wp],
                shift = SetPrecision[#["shift"], $wp]},
            rot = {{Cos[angle], -Sin[angle]}, {Sin[angle], Cos[angle]}};
            guides = (rot . # + shift) & /@ SetPrecision[#["guides"], $wp];
            boundary = (rot . # + shift) & /@ SetPrecision[#["boundary"], $wp];
            And[
                #["python_coverage_ratio_transformed"] == #["python_coverage_ratio"],
                crossAgreeQ[coverageRatio[guides, boundary, #["coverage_radius"]],
                    #["python_coverage_ratio"]]
            ]] &],
    True,
    TestID -> "METRIC-INVAR-001"
]

(* METRIC-GAP-001: symbolic telescoping — sorted periodic gaps always sum to
   the period (4-site symbolic case, 0 <= s1 < s2 < s3 < s4 < len). *)
VerificationTest[
    Assuming[0 <= s1 < s2 < s3 < s4 < len,
        FullSimplify[(s2 - s1) + (s3 - s2) + (s4 - s3) + (s1 + len - s4) - len]],
    0,
    TestID -> "METRIC-GAP-001"
]

(* METRIC-RMSE-001 is covered by CONTROL-TRACE-002 in controller.wlt (the RMSE
   recomputation over full episodes); here we verify the mini hand case. *)
VerificationTest[
    Module[{p = {{0, 0}, {3, 4}}, z = {{1, 0}, {3, 0}}},
        Sqrt[Mean[{Total[(p[[1]] - z[[1]])^2], Total[(p[[2]] - z[[2]])^2]}]] == Sqrt[17/2]],
    True,
    TestID -> "METRIC-RMSE-001"
]

(* METRIC-PATH-001: path length and control energy on the exported trace. *)
VerificationTest[
    Module[{t = metData["trace_case"], positions, controls, path, energy},
        positions = t["positions"]; controls = t["controls"];
        path = Total[Flatten[Table[
            Norm[positions[[k + 1, g]] - positions[[k, g]]],
            {k, Length[positions] - 1}, {g, Length[positions[[1]]]}]]];
        energy = t["dt"] Total[Flatten[controls]^2];
        {crossAgreeQ[path, t["python_path_length"]],
         crossAgreeQ[energy, t["python_control_energy"]]}],
    {True, True},
    TestID -> "METRIC-PATH-001"
]

(* METRIC-ANGULAR-001: perfectly uniform cross layout has error 0; the uneven
   layout matches an independent recomputation. *)
angularError[guides_, center_] := Module[{theta, gaps, target},
    If[Length[guides] <= 1, 0,
        theta = Sort[Mod[ArcTan @@ (# - center) & /@ guides, 2 Pi]];
        gaps = Differences[Append[theta, First[theta] + 2 Pi]];
        target = 2 Pi/Length[guides];
        Mean[Abs[gaps - target]]/target]];

VerificationTest[
    Module[{a = metData["angular_case"], u = metData["angular_uneven_case"]},
        {a["python_angular_uniformity_error"] == 0.,
         crossAgreeQ[angularError[u["guides"], u["center"]], u["python_angular_uniformity_error"]]}],
    {True, True},
    TestID -> "METRIC-ANGULAR-001"
]
