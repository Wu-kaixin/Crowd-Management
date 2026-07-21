(* Safety projection: convexity, constraint construction, one-step
   sufficiency, Dykstra vs 50-digit reference projection, KKT residuals. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
safData = loadCases["safety_cases.json"];

(* SAFETY-HESSIAN-001: Hessian of 1/2||u - u_nom||^2 is the identity, so the
   objective is 1-strongly convex. Verified on a generic 4-dim control. *)
VerificationTest[
    Module[{u = {u1, u2, u3, u4}, un = {n1, n2, n3, n4}, obj},
        obj = 1/2 Total[(u - un)^2];
        Simplify[D[obj, {u, 2}] - IdentityMatrix[4]]],
    ConstantArray[0, {4, 4}],
    TestID -> "SAFETY-HESSIAN-001"
]

(* SAFETY-CONVEX-001: each speed ball is convex (Hessian of the constraint
   function is 2I >= 0) and each half-space is linear; intersections of convex
   sets are convex, so the feasible set is convex. *)
VerificationTest[
    Module[{hess = D[u1^2 + u2^2, {{u1, u2}, 2}]},
        {hess === {{2, 0}, {0, 2}},
         PositiveSemidefiniteMatrixQ[hess],
         D[a1 u1 + a2 u2, {{u1, u2}, 2}] === {{0, 0}, {0, 0}}}],
    {True, True, True},
    TestID -> "SAFETY-CONVEX-001"
]

(* SAFETY-SUFFICIENT-001: one-step sufficiency chain. For unit n and any
   planar x, ||x|| >= n.x (Cauchy-Schwarz); with n = (p-q)/||p-q|| and
   n.u >= (d - ||p-q||)/dt it follows that ||p + dt u - q|| >= d. *)
VerificationTest[
    {Resolve[ForAll[{x1, x2, n1, n2}, n1^2 + n2^2 == 1,
        Sqrt[x1^2 + x2^2] >= n1 x1 + n2 x2], Reals],
     (* algebraic core of the chain: n.(p - q) = ||p - q|| for the unit
        direction, so n.(p + dt u - q) = ||p-q|| + dt n.u >= d *)
     Assuming[dpq > 0 && dt > 0,
        FullSimplify[(dpq + dt ((dsafe - dpq)/dt)) - dsafe]]},
    {True, 0},
    TestID -> "SAFETY-SUFFICIENT-001"
]

(* SAFETY-ROOM-001: room half-space u_x >= (margin - p_x)/dt gives exactly
   p_x + dt u_x >= margin (linear, no approximation). *)
VerificationTest[
    Assuming[dt > 0,
        FullSimplify[(px + dt ((margin - px)/dt)) - margin]],
    0,
    TestID -> "SAFETY-ROOM-001"
]

(* SAFETY-ROWS-001: independent reconstruction of the half-space system (A, b,
   kinds) from raw positions matches the Python-built system for every
   exported instance. *)
VerificationTest[
    AllTrue[safData["instances"],
        Module[{built = buildHalfspaces[#["positions"], #["crowd"], #["room"],
                    safData["dt"], safData["v_max"], #["config"]],
                pyMatrix = #["python_matrix"], pyBounds = #["python_bounds"], pyKinds = #["python_kinds"]},
            And[
                Length[built["rows"]] == Length[pyMatrix],
                built["kinds"] === pyKinds,
                If[Length[pyMatrix] == 0, True,
                    Max[Abs[built["rows"] - pyMatrix]] <= 1*^-9],
                If[Length[pyBounds] == 0, True,
                    Max[Abs[built["bounds"] - pyBounds]] <= 1*^-9 Max[1, Max[Abs[pyBounds]]]]
            ]] &],
    True,
    TestID -> "SAFETY-ROWS-001"
]

(* SAFETY-PRIMAL-001: the applied control of every feasible (VALID/PROJECTED)
   instance satisfies all half-spaces and speed balls within the production
   residual tolerance. *)
VerificationTest[
    AllTrue[Select[safData["instances"], MemberQ[{"VALID", "PROJECTED"}, #["python_status"]] &],
        Module[{u = Flatten[#["python_applied"]], mat = #["python_matrix"], b = #["python_bounds"],
                gc = Length[#["positions"]], vmax = safData["v_max"], tol = #["config"]["residual_tolerance"]},
            And[
                If[Length[b] == 0, True, Max[b - mat . u] <= tol],
                Max[Table[Norm[u[[2 g - 1 ;; 2 g]]], {g, gc}]] <= vmax + tol
            ]] &],
    True,
    TestID -> "SAFETY-PRIMAL-001"
]

(* SAFETY-DYKSTRA-001: the Dykstra output of each PROJECTED instance lies
   within the frozen distance tolerance of the true projection computed
   independently at 50-digit precision. *)
VerificationTest[
    AllTrue[Select[safData["instances"], #["python_status"] === "PROJECTED" &],
        Module[{uref, upy = Flatten[#["python_projected"]],
                mat = #["python_matrix"], b = #["python_bounds"],
                unom = Flatten[#["nominal"]], gc = Length[#["positions"]]},
            uref = referenceProjection[mat, b, unom, gc, safData["v_max"]];
            uref =!= $Failed && Norm[N[uref, $wp] - upy] <= $tolProjectionDist] &],
    True,
    TestID -> "SAFETY-DYKSTRA-001"
]

(* SAFETY-KKT-001: KKT residuals (primal, stationarity, complementarity) at
   the 50-digit reference solutions are below the frozen KKT tolerance. *)
VerificationTest[
    AllTrue[Select[safData["instances"], #["python_status"] === "PROJECTED" &],
        Module[{uref, res, mat = #["python_matrix"], b = #["python_bounds"],
                unom = Flatten[#["nominal"]], gc = Length[#["positions"]]},
            uref = referenceProjection[mat, b, unom, gc, safData["v_max"]];
            If[uref === $Failed, False,
                res = kktResiduals[mat, b, unom, gc, safData["v_max"], uref, 1*^-8];
                res["primal"] <= $tolKKT && res["stationarity"] <= 1*^-8 &&
                res["complementarity"] <= $tolKKT]] &],
    True,
    TestID -> "SAFETY-KKT-001"
]

(* SAFETY-EMERGENCY-001: the deliberately infeasible instance is certified
   infeasible independently (some bound exceeds the maximum achievable row
   value under the speed limit), and Python responded with a finite
   zero-velocity emergency stop. *)
VerificationTest[
    Module[{inst = SelectFirst[safData["instances"], #["name"] === "infeasible_emergency_stop" &],
            mat, b, gc, vmax, rowMax, certified},
        mat = inst["python_matrix"]; b = inst["python_bounds"];
        gc = Length[inst["positions"]]; vmax = safData["v_max"];
        (* max of row.u over the product of per-guide balls: sum of per-guide
           block norms times vmax *)
        rowMax = Table[
            vmax Total[Table[Norm[mat[[r, 2 g - 1 ;; 2 g]]], {g, gc}]],
            {r, Length[b]}];
        certified = Or @@ Table[b[[r]] > rowMax[[r]] + 1*^-9, {r, Length[b]}];
        {certified,
         inst["python_status"] === "SAFETY_INFEASIBLE",
         inst["python_emergency_stop"],
         Max[Abs[Flatten[inst["python_applied"]]]] == 0.}],
    {True, True, True, True},
    TestID -> "SAFETY-EMERGENCY-001"
]
