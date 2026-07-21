(* Velocity feedback controller: error recursion, stability regions, Lyapunov
   decrease, saturation dynamics, and 50-digit trace cross-checks. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
ctrlData = loadCases["controller_cases.json"];

(* CONTROL-RECURSION-001: p' = p + dt kp (z - p) gives e' = (1 - kp dt) e,
   componentwise for planar vectors. *)
VerificationTest[
    FullSimplify[
        ({zx, zy} - ({px, py} + dt kp ({zx, zy} - {px, py})))
        - (1 - kp dt) ({zx, zy} - {px, py})],
    {0, 0},
    TestID -> "CONTROL-RECURSION-001"
]

(* CONTROL-STABILITY-001: |1 - kp dt| < 1 is exactly 0 < kp dt < 2. *)
VerificationTest[
    Reduce[Abs[1 - x] < 1, x, Reals],
    0 < x < 2,
    SameTest -> (TrueQ[Simplify[Equivalent[#1, #2]]] &),
    TestID -> "CONTROL-STABILITY-001"
]

(* CONTROL-MONOTONE-001: contraction without sign flip is 0 < kp dt <= 1,
   matching the code guard dt*k_p <= 1. *)
VerificationTest[
    Reduce[Abs[1 - x] < 1 && 1 - x >= 0, x, Reals],
    0 < x <= 1,
    SameTest -> (TrueQ[Simplify[Equivalent[#1, #2]]] &),
    TestID -> "CONTROL-MONOTONE-001"
]

(* CONTROL-LYAPUNOV-001: V = 1/2||e||^2, dV = 1/2((1-x)^2 - 1)||e||^2. The
   factor (1-x)^2 - 1 is negative exactly on 0 < x < 2, zero at x = 0, 2. *)
VerificationTest[
    {FullSimplify[1/2 ((1 - x)^2) e2 - 1/2 e2 - 1/2 ((1 - x)^2 - 1) e2],
     Reduce[(1 - x)^2 - 1 < 0, x, Reals]},
    {0, 0 < x < 2},
    SameTest -> (TrueQ[Simplify[#1[[1]] == #2[[1]] && Equivalent[#1[[2]], #2[[2]]]]] &),
    TestID -> "CONTROL-LYAPUNOV-001"
]

(* CONTROL-SATURATED-001: while saturated with u = vmax e/||e||, one Euler step
   shortens the error norm by exactly dt vmax (no overshoot when
   dt vmax <= ||e||). Proved on the norm: ||e - dt vmax e/||e|| || =
   |1 - dt vmax/||e||| ||e|| = ||e|| - dt vmax. *)
VerificationTest[
    Assuming[en > 0 && vmax > 0 && dt > 0 && dt vmax <= en,
        FullSimplify[Abs[1 - dt vmax/en] en - (en - dt vmax)]],
    0,
    TestID -> "CONTROL-SATURATED-001"
]

(* CONTROL-SATBOUND-001: all 200 exported saturation samples respect
   ||u|| <= v_max in float64 (records CTRL-006). *)
VerificationTest[
    AllTrue[ctrlData["saturation_samples"],
        #["python_speed"] <= #["v_max"] &],
    True,
    TestID -> "CONTROL-SATBOUND-001"
]

(* CONTROL-SATBOUND-002: the saturation samples equal the closed-form
   sat_vmax(kp (z - p)) recomputed independently at 50 digits (the nextafter
   scaling is inside the frozen cross tolerance). *)
VerificationTest[
    AllTrue[ctrlData["saturation_samples"],
        Module[{p = SetPrecision[#["p"], $wp], z = SetPrecision[#["z"], $wp],
                kp = SetPrecision[#["k_p"], $wp], vmax = SetPrecision[#["v_max"], $wp], u, speed},
            u = kp (z - p);
            speed = Norm[u];
            If[speed > vmax, u = u vmax/speed];
            Max[Abs[u - #["python_u"]]]/Max[1, Norm[#["python_u"]]] <= $tolCross] &],
    True,
    TestID -> "CONTROL-SATBOUND-002"
]

(* CONTROL-TRACE-001: independent 50-digit re-simulation of every exported
   episode (saturation model included, safety disabled) reproduces the Python
   position traces within the frozen cross tolerance. *)
simulateEpisode[case_] := Module[
    {dt = SetPrecision[case["dt"], $wp], kp = SetPrecision[case["k_p"], $wp],
     vmax = SetPrecision[case["v_max"], $wp], targets = SetPrecision[case["targets"], $wp],
     mapping = case["guide_to_target"], pos, traj, steps, u, speed, i, t},
    pos = SetPrecision[case["initial"], $wp];
    steps = Length[case["python_positions"]] - 1;
    traj = {pos};
    Do[
        u = Table[
            If[mapping[[i]] >= 0,
                kp (targets[[mapping[[i]] + 1]] - pos[[i]]),
                {0, 0}],
            {i, Length[pos]}];
        u = Table[
            speed = Norm[u[[i]]];
            If[speed > vmax, u[[i]] vmax/speed, u[[i]]],
            {i, Length[pos]}];
        pos = pos + dt u;
        AppendTo[traj, pos],
        {t, steps}];
    traj];

VerificationTest[
    AllTrue[ctrlData["episodes"],
        Module[{traj = simulateEpisode[#], py = #["python_positions"], scale},
            scale = Max[1, Max[Abs[py]]];
            Max[Abs[traj - py]]/scale <= $tolCross] &],
    True,
    TestID -> "CONTROL-TRACE-001"
]

(* CONTROL-TRACE-002: the recorded tracking RMSE per frame matches
   sqrt(mean_active ||p - z||^2) recomputed from the recorded positions. *)
VerificationTest[
    AllTrue[ctrlData["episodes"],
        Module[{targets = #["targets"], mapping = #["guide_to_target"], active, rmse},
            active = Flatten[Position[mapping, _?NonNegative, {1}, Heads -> False]];
            rmse = Table[
                Sqrt[Mean[Table[
                    Total[(frame[[i]] - targets[[mapping[[i]] + 1]])^2],
                    {i, active}]]],
                {frame, #["python_positions"]}];
            Max[Abs[rmse - #["python_tracking_rmse"]]] <= $tolCross Max[1, Max[Abs[#["python_tracking_rmse"]]]]] &],
    True,
    TestID -> "CONTROL-TRACE-002"
]

(* CONTROL-RESERVE-001: reserve guides (mapping -1) never move and always
   receive zero control in the exported episode. *)
VerificationTest[
    Module[{ep = SelectFirst[ctrlData["episodes"], #["name"] === "with_reserve_guide" &],
            reserveIds, frames, controls},
        reserveIds = Flatten[Position[ep["guide_to_target"], -1]];
        frames = ep["python_positions"]; controls = ep["python_applied_controls"];
        {AllTrue[reserveIds, Function[g, Length[Union[frames[[All, g]]]] == 1]],
         AllTrue[reserveIds, Function[g, Max[Abs[controls[[All, g]]]] == 0.]]}],
    {True, True},
    TestID -> "CONTROL-RESERVE-001"
]

(* CONTROL-MONOTONE-002: with kp dt = 0.15 <= 1 the recorded tracking error is
   monotonically non-increasing in the unsaturated episode. *)
VerificationTest[
    Module[{ep = SelectFirst[ctrlData["episodes"], #["name"] === "unsaturated_contraction" &]},
        Max[Differences[ep["python_tracking_rmse"]]] <= 1*^-12],
    True,
    TestID -> "CONTROL-MONOTONE-002"
]

(* CONTROL-GUARD-001: Python rejects dt*k_p > 1 (recorded ValueError). *)
VerificationTest[
    StringContainsQ[ctrlData["python_kp_dt_guard"], "ValueError"],
    True,
    TestID -> "CONTROL-GUARD-001"
]
