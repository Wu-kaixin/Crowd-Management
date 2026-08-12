(* Periodic equal-arc coverage: cell integrals, H* derivation, optimality,
   cross-language cost checks, and Lloyd monotonicity property. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
covData = loadCases["coverage_cases.json"];

(* PERIODIC-CELL-001: the analytic cell integral used by the implementation. *)
VerificationTest[
    FullSimplify[Integrate[(s - c)^2, {s, lo, hi}] - ((hi - c)^3 - (lo - c)^3)/3],
    0,
    TestID -> "PERIODIC-CELL-001"
]

(* PERIODIC-HSTAR-001: full derivation of the uniform-density optimum. With m
   equally spaced sites on a period-L arc, each periodic Voronoi cell is an
   interval of half-width L/(2m) centred on its site, so
   H = m * Integrate[t^2, {t, -L/(2m), L/(2m)}] = L^3/(12 m^2). *)
VerificationTest[
    FullSimplify[
        mm Integrate[t^2, {t, -len/(2 mm), len/(2 mm)}] - len^3/(12 mm^2),
        Assumptions -> len > 0 && mm > 0],
    0,
    TestID -> "PERIODIC-HSTAR-001"
]

(* PERIODIC-HSTAR-002: gap decomposition. A cell whose site sees left half-gap
   g1/2 and right half-gap g2/2 contributes (g1^3+g2^3)/24; summing over equal
   gaps g_i = L/m recovers H* exactly. *)
VerificationTest[
    {FullSimplify[Integrate[t^2, {t, -g1/2, g2/2}] - (g1^3 + g2^3)/24,
        Assumptions -> g1 > 0 && g2 > 0],
     FullSimplify[mm ((len/mm)^3 + (len/mm)^3)/24 - len^3/(12 mm^2),
        Assumptions -> len > 0 && mm > 0]},
    {0, 0},
    TestID -> "PERIODIC-HSTAR-002"
]

(* PERIODIC-OPT-001: scaling lemma. H scales cubically, so WLOG L = 1 in the
   optimality proof below. *)
VerificationTest[
    FullSimplify[Integrate[(s - k c)^2, {s, k lo, k hi}] - k^3 Integrate[(s - c)^2, {s, lo, hi}],
        Assumptions -> k > 0],
    0,
    TestID -> "PERIODIC-OPT-001"
]

(* PERIODIC-OPT-002: with H = Sum g_i^3 / 12 over gaps summing to L = 1, equal
   gaps are optimal. Resolved exactly for m = 2..6 site counts. *)
VerificationTest[
    {Resolve[ForAll[{g1, g2}, g1 >= 0 && g2 >= 0 && g1 + g2 == 1, g1^3 + g2^3 >= 1/4], Reals],
     Resolve[ForAll[{g1, g2, g3}, g1 >= 0 && g2 >= 0 && g3 >= 0 && g1 + g2 + g3 == 1, g1^3 + g2^3 + g3^3 >= 1/9], Reals],
     Resolve[ForAll[{g1, g2, g3, g4}, g1 >= 0 && g2 >= 0 && g3 >= 0 && g4 >= 0 && g1 + g2 + g3 + g4 == 1, g1^3 + g2^3 + g3^3 + g4^3 >= 1/16], Reals],
     Resolve[ForAll[{g1, g2, g3, g4, g5}, g1 >= 0 && g2 >= 0 && g3 >= 0 && g4 >= 0 && g5 >= 0 && g1 + g2 + g3 + g4 + g5 == 1, g1^3 + g2^3 + g3^3 + g4^3 + g5^3 >= 1/25], Reals],
     Resolve[ForAll[{g1, g2, g3, g4, g5, g6}, g1 >= 0 && g2 >= 0 && g3 >= 0 && g4 >= 0 && g5 >= 0 && g6 >= 0 && g1 + g2 + g3 + g4 + g5 + g6 == 1, g1^3 + g2^3 + g3^3 + g4^3 + g5^3 + g6^3 >= 1/36], Reals]},
    {True, True, True, True, True},
    TestID -> "PERIODIC-OPT-002"
]

(* PERIODIC-OPT-003: uniqueness of the minimizer for m = 3 (L = 1). *)
VerificationTest[
    Module[{min},
        min = Minimize[{g1^3 + g2^3 + g3^3,
            g1 >= 0 && g2 >= 0 && g3 >= 0 && g1 + g2 + g3 == 1}, {g1, g2, g3}];
        {min[[1]] == 1/9, Sort[{g1, g2, g3} /. min[[2]]] == {1/3, 1/3, 1/3}}],
    {True, True},
    TestID -> "PERIODIC-OPT-003"
]

(* PERIODIC-GAP-001: equal-arc sites have max consecutive gap exactly L/m
   (checked on all exported equal-arc cases). *)
VerificationTest[
    AllTrue[Select[covData["cases"], #["kind"] === "equal_arc" &],
        crossAgreeQ[#["length"]/#["m"], #["python_max_gap"]] &],
    True,
    TestID -> "PERIODIC-GAP-001"
]

(* PERIODIC-HSTAR-003: exported equal-arc H values equal L^3/(12 m^2). *)
VerificationTest[
    AllTrue[Select[covData["cases"], #["kind"] === "equal_arc" &],
        crossAgreeQ[#["length"]^3/(12 #["m"]^2), #["python_H"]] &],
    True,
    TestID -> "PERIODIC-HSTAR-003"
]

(* PERIODIC-CROSS-001: Wolfram recomputes H by symbolic integration over
   periodic Voronoi cells for every exported site set (incl. random ones) and
   matches the Python implementation. *)
VerificationTest[
    AllTrue[covData["cases"],
        crossAgreeQ[uniformCoverageCost[#["sites"], #["length"]], #["python_H"]] &],
    True,
    TestID -> "PERIODIC-CROSS-001"
]

(* PERIODIC-CROSS-002: exported max gaps match the independent computation. *)
VerificationTest[
    AllTrue[covData["cases"],
        crossAgreeQ[maxArcGap[#["sites"], #["length"]], #["python_max_gap"]] &],
    True,
    TestID -> "PERIODIC-CROSS-002"
]

(* PERIODIC-MONO-001: recorded Lloyd H history is non-increasing within the
   frozen monotonic tolerance, ends at the recomputed final-site cost, and
   never drops below the analytic lower bound L^3/(12 m^2). *)
VerificationTest[
    Module[{lc = covData["lloyd_case"], hist, len, m},
        hist = lc["python_h_history"]; len = lc["length"]; m = lc["m"];
        {Max[Differences[hist]] <= lc["monotonic_tolerance"],
         crossAgreeQ[uniformCoverageCost[lc["python_final_sites"], len], Last[hist]],
         Min[hist] >= len^3/(12 m^2) - 1*^-9}],
    {True, True, True},
    TestID -> "PERIODIC-MONO-001"
]
