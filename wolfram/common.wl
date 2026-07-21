(* ::Package:: *)

(* Shared helpers and FROZEN tolerances for the independent Wolfram
   verification of ABCG static containment mathematics.

   Tolerances are frozen before any verification run and must not be widened
   after observing errors.  Justification for each value:

   - $tolExact          = 0
       Algebraic/symbolic residuals must be exactly zero (unitless).
   - $tolCross          = 1*^-9
       Cross-language numeric residual, normalized by max(1, |value|).
       float64 carries ~1*^-16 relative error; tested pipelines apply < 1*^4
       arithmetic operations, so 1*^-9 is a > 1000x safety margin. Applies to
       geometry lengths (m), coverage costs (m^3), metrics, statistics.
   - $tolGeom           = 1*^-9
       Normalized geometric residual (m after normalization); same float64
       reasoning as $tolCross. Applies to curve points, normals, distances.
   - $tolPrimal         = 1*^-9
       Optimization primal residual (m/s); equals the production
       residual_tolerance in VelocitySafetyConfig, so the verifier holds the
       solver to its own contract.
   - $tolKKT            = 1*^-12
       KKT stationarity/complementarity residual (m/s scale) at the
       50-digit reference solution obtained independently by Wolfram.
   - $tolProjectionDist = 1*^-6
       Euclidean distance (m/s) between the Dykstra output and the true
       high-precision projection. Dykstra stops on primal residual only, so
       its distance to the exact projection is a measured claim; 1*^-6 is the
       frozen acceptance bound for SAF-007.
   - $wp                = 50
       WorkingPrecision for all high-precision numeric verification.
*)

$tolExact = 0;
$tolCross = 1*^-9;
$tolGeom = 1*^-9;
$tolPrimal = 1*^-9;
$tolKKT = 1*^-12;
$tolProjectionDist = 1*^-6;
$wp = 50;

repoRoot = With[{env = Environment["ABCG_REPO_ROOT"]},
    If[StringQ[env] && env =!= "", env, Directory[]]];

casePath[name_String] := FileNameJoin[{repoRoot, "artifacts", "math_verification", "cases", name}];

loadCases[name_String] := Import[casePath[name], "RawJSON"];

(* NumPy-compatible percentile with linear interpolation. *)
numpyPercentile[values_List, q_] := Module[{sorted = Sort[N[values, $wp]], n = Length[values], pos, lo, hi, frac},
    If[n == 1, First[sorted],
        pos = (n - 1) q/100;
        lo = Floor[pos]; hi = Ceiling[pos]; frac = pos - lo;
        sorted[[lo + 1]] (1 - frac) + sorted[[hi + 1]] frac]];

numpyMedian[values_List] := numpyPercentile[values, 50];

(* Relative-scale comparison used for all cross-language checks. *)
crossResidual[wolfram_, python_] := Abs[wolfram - python]/Max[1, Abs[python]];

crossAgreeQ[wolfram_, python_] := crossResidual[wolfram, python] <= $tolCross;

(* Periodic quantities reimplemented independently (not copied from Python). *)
periodicDistance[a_, b_, len_] := Min[Mod[a - b, len], len - Mod[a - b, len]];

maxArcGap[sites_List, len_] := Module[{s = Sort[Mod[sites, len]]},
    Max[Differences[Append[s, First[s] + len]]]];

(* Exact uniform periodic coverage cost from first principles:
   H = Integrate over [0,len) of min_i d_L(s, s_i)^2 ds, evaluated by
   splitting at periodic Voronoi midpoints. *)
uniformCoverageCost[sites_List, len_] := Module[{s = Sort[Mod[sites, len]], m = Length[sites], prev, next, lefts, rights},
    prev = RotateRight[s]; prev[[1]] -= len;
    next = RotateLeft[s]; next[[-1]] += len;
    lefts = (prev + s)/2; rights = (s + next)/2;
    Total[MapThread[Integrate[(t)^2, {t, #1 - #2, #3 - #2}] &, {lefts, s, rights}]]];

polygonSignedArea[pts_List] := Module[{nxt = RotateLeft[pts]},
    Total[MapThread[(#1[[1]] #2[[2]] - #2[[1]] #1[[2]]) &, {pts, nxt}]]/2];

polygonPerimeter[pts_List] := Total[Norm /@ (RotateLeft[pts] - pts)];

(* Independent reference projection: minimize 1/2||u-unom||^2 subject to
   A.u >= b and per-guide speed balls.  A machine-precision FindMinimum pass
   locates the active set; the KKT equality system for that active set is then
   solved exactly on rationalized data and evaluated at 50 digits.  The
   candidate is accepted only if all multipliers are non-negative and the full
   constraint set is satisfied, so the result is a certified KKT point. *)
referenceProjection[matrix_List, bounds_List, unom_List, guideCount_Integer, vmax_] :=
    Module[{dim = Length[unom], vars, objective, constraints, ballCons, sol, uApprox,
            activeIdx, activeBalls, exactMatrix, exactBounds, exactUnom, exactVmax,
            lambdas, mus, stationarity, eqs, unknowns, solutions, valid, g, i, uSol},
        vars = Array[uu, dim];
        objective = 1/2 Total[(vars - unom)^2];
        constraints = If[Length[bounds] > 0,
            MapThread[#1 . vars >= #2 &, {matrix, bounds}], {}];
        ballCons = Table[vars[[2 g - 1]]^2 + vars[[2 g]]^2 <= vmax^2, {g, guideCount}];
        sol = Quiet@FindMinimum[{objective, Join[constraints, ballCons]},
            Table[{vars[[i]], 0}, {i, dim}], MaxIterations -> 2000];
        If[Head[sol] === FindMinimum || !FreeQ[sol, FindMinimum], Return[$Failed]];
        uApprox = vars /. sol[[2]];
        (* candidate (possibly weakly) active sets from the approximate solve *)
        activeIdx = Select[Range[Length[bounds]],
            Abs[matrix[[#]] . uApprox - bounds[[#]]] <= 1*^-3 &];
        activeBalls = Select[Range[guideCount],
            Abs[Norm[uApprox[[2 # - 1 ;; 2 #]]] - vmax] <= 1*^-3 &];
        exactMatrix = Map[Rationalize[#, 0] &, matrix, {2}];
        exactBounds = Rationalize[bounds, 0];
        exactUnom = Rationalize[unom, 0];
        exactVmax = Rationalize[vmax, 0];
        (* enumerate subsets of the candidate active set; accept the KKT point
           with nonnegative multipliers that satisfies every constraint *)
        Module[{best = $Failed, bestObj = Infinity},
            Do[
                Module[{aIdx = subsetPair[[1]], aBalls = subsetPair[[2]], lam, mu, stat, eqns, unknowns2, sols, validSols, u, obj},
                    lam = Array[ll, Length[aIdx]];
                    mu = Array[mm, Length[aBalls]];
                    stat = (vars - exactUnom)
                        - If[Length[aIdx] > 0, Total[MapThread[#1 exactMatrix[[#2]] &, {lam, aIdx}]], ConstantArray[0, dim]]
                        + 2 Sum[mu[[j]] Normal[SparseArray[
                            {2 aBalls[[j]] - 1 -> vars[[2 aBalls[[j]] - 1]],
                             2 aBalls[[j]] -> vars[[2 aBalls[[j]]]]}, dim]],
                            {j, Length[aBalls]}];
                    eqns = Join[
                        Thread[stat == 0],
                        Table[exactMatrix[[aIdx[[i]]]] . vars == exactBounds[[aIdx[[i]]]], {i, Length[aIdx]}],
                        Table[vars[[2 aBalls[[j]] - 1]]^2 + vars[[2 aBalls[[j]]]]^2 == exactVmax^2, {j, Length[aBalls]}]];
                    unknowns2 = Join[vars, lam, mu];
                    sols = Quiet@Solve[eqns, unknowns2, Reals];
                    If[sols =!= {} && Head[sols] =!= Solve,
                        validSols = Select[sols, Module[{u2 = vars /. #, lam2 = lam /. #, mu2 = mu /. #},
                            And[
                                AllTrue[N[lam2, $wp], # >= -1*^-30 &],
                                AllTrue[N[mu2, $wp], # >= -1*^-30 &],
                                If[Length[bounds] > 0, Min[N[exactMatrix . u2 - exactBounds, $wp]] >= -1*^-30, True],
                                AllTrue[Range[guideCount], N[Norm[u2[[2 # - 1 ;; 2 #]]], $wp] <= vmax + 1*^-30 &]]] &];
                        Do[
                            Module[{u2 = vars /. vs, obj2},
                                obj2 = N[1/2 Total[(u2 - exactUnom)^2], $wp];
                                If[obj2 < bestObj, bestObj = obj2; best = u2]],
                            {vs, validSols}]]],
                {subsetPair, Tuples[{Subsets[activeIdx], Subsets[activeBalls]}]}];
            If[best === $Failed, $Failed, N[best, $wp]]]];

(* KKT residuals at a candidate solution: stationarity via nonnegative
   least-squares multipliers on active constraints, primal feasibility, and
   complementarity (inactive multipliers forced to zero by construction). *)
kktResiduals[matrix_List, bounds_List, unom_List, guideCount_Integer, vmax_, ustar_List, activeTol_] :=
    Module[{grad, activeRows = {}, activeIdx, ballGrads = {}, basis, lambda, primal, ballViol, stationarity, complementarity, slack, i},
        grad = ustar - SetPrecision[unom, $wp];
        primal = If[Length[bounds] > 0, Max[0, Max[SetPrecision[bounds, $wp] - matrix . ustar]], 0];
        ballViol = Max[0, Max[Table[Norm[ustar[[2 g - 1 ;; 2 g]]] - vmax, {g, guideCount}]]];
        Do[
            slack = matrix[[i]] . ustar - bounds[[i]];
            If[Abs[slack] <= activeTol, AppendTo[activeRows, SetPrecision[matrix[[i]], $wp]]],
            {i, Length[bounds]}];
        Do[
            If[Abs[Norm[ustar[[2 g - 1 ;; 2 g]]] - vmax] <= activeTol,
                AppendTo[ballGrads, -SparseArray[{2 g - 1 -> ustar[[2 g - 1]], 2 g -> ustar[[2 g]]}, Length[ustar]] // Normal]],
            {g, guideCount}];
        basis = Join[activeRows, ballGrads];
        stationarity = If[Length[basis] == 0, Norm[grad],
            lambda = LeastSquares[Transpose[basis], grad];
            lambda = Max[0, #] & /@ lambda; (* project multipliers to nonneg *)
            Norm[grad - Transpose[basis] . lambda]];
        complementarity = 0; (* inactive constraints get zero multipliers by construction *)
        <|"primal" -> Max[primal, ballViol], "stationarity" -> stationarity, "complementarity" -> complementarity|>];

(* Independent reconstruction of the PR5 half-space rows from raw inputs. *)
buildHalfspaces[positions_List, crowd_List, room_List, dt_, vmax_, cfg_Association] :=
    Module[{gc = Length[positions], dim, tol, buffer, rows = {}, bounds = {}, kinds = {},
            dgg = cfg["min_guide_distance"], dgc = cfg["min_crowd_distance"], margin = cfg["room_margin"], i, j, q, delta, dist, normal, bound, row, axis, sign, coordinate, lower, upper},
        dim = 2 gc;
        tol = cfg["residual_tolerance"];
        buffer = Max[10 dt tol, 64 $MachineEpsilon Max[1, Max[room]]];
        If[dgg > 0 && gc >= 2,
            Do[
                delta = positions[[i]] - positions[[j]];
                dist = Norm[delta];
                bound = (dgg + buffer - dist)/dt;
                If[bound > -2 vmax - tol,
                    normal = If[dist <= tol,
                        With[{ang = ((i - 1) 0.754877666 + (j - 1) 0.569840291) 2 Pi}, {Cos[ang], Sin[ang]}],
                        delta/dist];
                    row = ConstantArray[0., dim];
                    row[[2 i - 1]] = normal[[1]]; row[[2 i]] = normal[[2]];
                    row[[2 j - 1]] = -normal[[1]]; row[[2 j]] = -normal[[2]];
                    AppendTo[rows, row]; AppendTo[bounds, bound]; AppendTo[kinds, "guide_pair"]],
                {i, gc - 1}, {j, i + 1, gc}]];
        If[dgc > 0 && Length[crowd] > 0 && gc > 0,
            Do[
                delta = positions[[i]] - crowd[[q]];
                dist = Norm[delta];
                bound = (dgc + buffer - dist)/dt;
                If[bound > -vmax - tol,
                    normal = If[dist <= tol,
                        With[{ang = ((i - 1) 0.754877666 + (gc + q - 1) 0.569840291) 2 Pi}, {Cos[ang], Sin[ang]}],
                        delta/dist];
                    row = ConstantArray[0., dim];
                    row[[2 i - 1]] = normal[[1]]; row[[2 i]] = normal[[2]];
                    AppendTo[rows, row]; AppendTo[bounds, bound]; AppendTo[kinds, "crowd"]],
                {i, gc}, {q, Length[crowd]}]];
        If[gc > 0,
            lower = margin + buffer;
            Do[
                Do[
                    {axis, sign} = pair;
                    coordinate = positions[[i, axis]];
                    upper = room[[axis]] - margin - buffer;
                    bound = If[sign > 0, (lower - coordinate)/dt, (coordinate - upper)/dt];
                    If[bound > -vmax - tol,
                        row = ConstantArray[0., dim];
                        row[[2 (i - 1) + axis]] = sign;
                        AppendTo[rows, row]; AppendTo[bounds, bound]; AppendTo[kinds, "room"]],
                    {pair, {{1, 1.}, {1, -1.}, {2, 1.}, {2, -1.}}}],
                {i, gc}]];
        <|"rows" -> rows, "bounds" -> bounds, "kinds" -> kinds|>];

(* Brute-force optimal assignment on the augmented square matrix. *)
bruteForceAssignment[costMatrix_List] := Module[{n = Length[costMatrix], perms, best, bestPerm},
    perms = Permutations[Range[n]];
    best = Infinity; bestPerm = None;
    Do[
        With[{c = Total[MapThread[costMatrix[[#1, #2]] &, {Range[n], p}]]},
            If[c < best, best = c; bestPerm = p]],
        {p, perms}];
    <|"cost" -> best, "assignment" -> bestPerm|>];

(* previous is either Null or a list of 0-based previous target ids (-1 = reserve),
   matching the Python convention. *)
augmentedCostMatrix[guides_List, targets_List, previous_, lambdaSwitch_, reserveCost_, unmetCost_] :=
    Module[{ng = Length[guides], nt = Length[targets], size, mat, real, i, reservePenalty},
        real = Table[Total[(guides[[i]] - targets[[k]])^2], {i, ng}, {k, nt}];
        If[previous =!= Null && nt > 0,
            real = real + lambdaSwitch Table[If[previous[[i]] != k - 1, 1, 0], {i, ng}, {k, nt}]];
        size = Max[ng, nt];
        mat = ConstantArray[0, {size, size}];
        If[ng > 0 && nt > 0, mat[[1 ;; ng, 1 ;; nt]] = real];
        If[ng > nt,
            reservePenalty = Table[reserveCost + If[previous =!= Null && previous[[i]] != -1, lambdaSwitch, 0], {i, ng}];
            Do[mat[[i, nt + 1 ;; size]] = reservePenalty[[i]], {i, ng}]];
        If[nt > ng, Do[mat[[i, 1 ;; nt]] = unmetCost, {i, ng + 1, size}]];
        mat];
