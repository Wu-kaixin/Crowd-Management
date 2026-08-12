(* Guide-target assignment: cost model, brute-force global optimality
   cross-check, tie documentation, dummy-cost domination. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
asgData = loadCases["assignment_cases.json"];

exactify[x_] := Rationalize[x, 0];

buildCase[case_] := Module[{guides, targets, previous},
    guides = Map[exactify, case["guides"], {2}];
    targets = Map[exactify, case["targets"], {2}];
    previous = If[KeyExistsQ[case, "previous"] && case["previous"] =!= Null, case["previous"], Null];
    augmentedCostMatrix[guides, targets, previous,
        exactify[case["lambda_switch"]],
        exactify[Lookup[case, "reserve_cost", 0]],
        exactify[Lookup[case, "unmet_target_cost", 10^6]]]];

(* ASSIGNMENT-COST-001: the total cost reported by Python equals the cost of
   Python's own assignment evaluated on the independently rebuilt exact-rational
   augmented matrix (validates the documented cost model C_ik). *)
pythonAssignmentCost[case_, mat_] := Module[
    {g2t = case["python_guide_to_target"], ng, nt, size, cols, used, freeCols, reserves},
    ng = Length[case["guides"]]; nt = Length[case["targets"]]; size = Length[mat];
    cols = ConstantArray[0, size];
    used = {};
    Do[If[g2t[[i]] >= 0, cols[[i]] = g2t[[i]] + 1; AppendTo[used, g2t[[i]] + 1]], {i, ng}];
    freeCols = Complement[Range[size], used];
    (* reserve guides / dummy rows take remaining columns; those augmented
       entries are constant per row, so any completion has the same cost *)
    reserves = Select[Range[size], cols[[#]] == 0 &];
    Do[cols[[reserves[[j]]]] = freeCols[[j]], {j, Length[reserves]}];
    Total[Table[mat[[i, cols[[i]]]], {i, size}]]];

VerificationTest[
    AllTrue[asgData["cases"],
        Module[{mat = buildCase[#]},
            crossAgreeQ[pythonAssignmentCost[#, mat], #["python_total_cost"]]] &],
    True,
    TestID -> "ASSIGNMENT-COST-001"
]

(* ASSIGNMENT-BRUTEFORCE-001: brute-force enumeration of all permutations of
   the augmented square matrix yields the same optimal value as SciPy for
   every exported instance (exact rational arithmetic, n <= 7). *)
VerificationTest[
    AllTrue[asgData["cases"],
        Module[{mat = buildCase[#], brute},
            brute = bruteForceAssignment[mat];
            crossAgreeQ[brute["cost"], #["python_total_cost"]]] &],
    True,
    TestID -> "ASSIGNMENT-BRUTEFORCE-001"
]

(* ASSIGNMENT-TIE-001: the symmetric tie instance has (at least) two distinct
   optimal permutations with identical cost, and Python returned one of them.
   This documents ASG-003: determinism comes from the solver, not a stated rule. *)
VerificationTest[
    Module[{tc = asgData["tie_case"], mat, perms, costs, optima, pyPerm},
        mat = augmentedCostMatrix[
            Map[exactify, tc["guides"], {2}],
            Map[exactify, tc["targets"], {2}],
            Null, exactify[tc["lambda_switch"]], 0, 10^6];
        perms = Permutations[Range[Length[mat]]];
        costs = Table[Total[MapThread[mat[[#1, #2]] &, {Range[Length[mat]], p}]], {p, perms}];
        optima = Pick[perms, costs, Min[costs]];
        pyPerm = tc["python_guide_to_target"] + 1;
        {Length[optima] >= 2,
         MemberQ[optima, pyPerm],
         crossAgreeQ[Min[costs], tc["python_total_cost"]]}],
    {True, True, True},
    TestID -> "ASSIGNMENT-TIE-001"
]

(* ASSIGNMENT-DOMINATE-001: inside the 20 x 14 m room the maximal real cost is
   20^2 + 14^2 + lambda = 596.25 << 10^6, so the unmet dummy cost dominates;
   outside that domain a counterexample exists (documented domain limit). *)
VerificationTest[
    {Reduce[ForAll[{px, py, zx, zy},
        0 <= px <= 20 && 0 <= py <= 14 && 0 <= zx <= 20 && 0 <= zy <= 14,
        (px - zx)^2 + (py - zy)^2 + 1/4 < 10^6], Reals],
     FindInstance[(px - zx)^2 + (py - zy)^2 > 10^6, {px, py, zx, zy}, Reals] =!= {}},
    {True, True},
    TestID -> "ASSIGNMENT-DOMINATE-001"
]
