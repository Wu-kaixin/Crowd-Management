(* Statistics: summary stats, bootstrap CI, Cohen d_z, win rate, failure
   denominator, missing pairs, bootstrap-uncertainty formulas. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
statData = loadCases["statistics_cases.json"];

(* STAT-SUMMARY-001: mean, median, p95 (NumPy linear interpolation), and
   worst-5% mean (direction lower => worst = largest ceil(0.05 n) values). *)
VerificationTest[
    Module[{s = statData["summary_case"], values, worstCount, ordered},
        values = s["values"];
        worstCount = Max[1, Ceiling[0.05 Length[values]]];
        ordered = Sort[values];
        {crossAgreeQ[Mean[values], s["python_mean"]],
         crossAgreeQ[numpyMedian[values], s["python_median"]],
         crossAgreeQ[numpyPercentile[values, 95], s["python_p95"]],
         crossAgreeQ[Mean[ordered[[-worstCount ;;]]], s["python_worst5_mean"]]}],
    {True, True, True, True},
    TestID -> "STAT-SUMMARY-001"
]

(* STAT-BOOT-001: percentile bootstrap CI of the mean recomputed from the
   exported resample indices (0-based from NumPy). *)
VerificationTest[
    Module[{s = statData["summary_case"], values, means},
        values = s["values"];
        means = Mean[values[[# + 1]]] & /@ s["resample_indices"];
        {crossAgreeQ[numpyPercentile[means, 2.5], s["python_ci95_low"]],
         crossAgreeQ[numpyPercentile[means, 97.5], s["python_ci95_high"]]}],
    {True, True},
    TestID -> "STAT-BOOT-001"
]

(* STAT-DZ-001: Cohen d_z with sample std (ddof = 1); degenerate all-equal
   sample yields std 0 and Python reports None. *)
VerificationTest[
    Module[{p = statData["paired_case"], d, dz},
        d = p["differences"];
        dz = Mean[d]/StandardDeviation[d];
        {crossAgreeQ[dz, p["python_cohen_dz"]],
         statData["degenerate_case"]["python_std_ddof1"] == 0.,
         statData["degenerate_case"]["python_cohen_dz"] === Null}],
    {True, True, True},
    TestID -> "STAT-DZ-001"
]

(* STAT-WINRATE-001: win rate and paired-difference summaries. *)
VerificationTest[
    Module[{p = statData["paired_case"], d, means},
        d = p["differences"];
        means = Mean[d[[# + 1]]] & /@ p["resample_indices"];
        {crossAgreeQ[Mean[d], p["python_mean_difference"]],
         crossAgreeQ[numpyMedian[d], p["python_median_difference"]],
         crossAgreeQ[N[Count[d, _?Negative]/Length[d]], p["python_win_rate"]],
         crossAgreeQ[numpyPercentile[means, 2.5], p["python_ci95_low"]],
         crossAgreeQ[numpyPercentile[means, 97.5], p["python_ci95_high"]]}],
    {True, True, True, True, True},
    TestID -> "STAT-WINRATE-001"
]

(* STAT-DENOM-001: failure accounting keeps every record in the denominator.
   Synthetic set: 6 abcg_v2 records with 2 failures => rate exactly 1/3. *)
VerificationTest[
    Module[{a = statData["aggregation_case"], records, failures},
        records = Select[a["records"], #["method"] === "abcg_v2" &];
        failures = Count[records, r_ /; r["success"] === False];
        {Length[records] == a["python_run_count"],
         failures == a["python_failure_count"],
         crossAgreeQ[failures/Length[records], a["python_failure_rate"]]}],
    {True, True, True},
    TestID -> "STAT-DENOM-001"
]

(* STAT-MISSING-001: pairs with a missing side are skipped and reported, not
   imputed; complete metrics keep all pairs and the mean difference matches an
   independent recomputation. *)
VerificationTest[
    Module[{a = statData["aggregation_case"], bySeed, diffs},
        bySeed = GroupBy[a["records"], {#["seed"], #["method"]} &];
        diffs = Table[
            Module[{full = First[bySeed[{seed, "abcg_v2"}]], other = First[bySeed[{seed, "uniform_arc"}]]},
                If[full["path_length_m"] === Null || other["path_length_m"] === Null,
                    Nothing,
                    full["path_length_m"] - other["path_length_m"]]],
            {seed, 0, 5}];
        {a["python_paired_count_rmse"] == 4,
         a["python_missing_pair_count_rmse"] == 2,
         a["python_paired_count_path"] == 6,
         crossAgreeQ[Mean[diffs], a["python_mean_difference_path"]]}],
    {True, True, True, True},
    TestID -> "STAT-MISSING-001"
]

(* STAT-BOOTRMS-001: per-arc bootstrap uncertainty = sqrt of the mean of
   squared nearest distances across replicas, recomputed at 50 digits. *)
VerificationTest[
    Module[{b = statData["bootstrap_case"], base, replicas, dists, uncertainty},
        base = SetPrecision[b["base_curve"], $wp];
        replicas = SetPrecision[#, $wp] & /@ b["replicas"];
        dists = Table[
            Table[Min[Table[Norm[base[[k]] - rp], {rp, replica}]], {k, Length[base]}],
            {replica, replicas}];
        uncertainty = Sqrt[Mean[dists^2]];
        Max[Abs[uncertainty - b["python_uncertainty"]]] <= $tolCross],
    True,
    TestID -> "STAT-BOOTRMS-001"
]

(* STAT-CONF-001: bounded exponential confidence transform, its scale rule,
   and symbolic monotonicity d/du exp(-u/s) < 0 for s > 0. *)
VerificationTest[
    Module[{b = statData["bootstrap_case"], u, scale, conf},
        u = b["python_uncertainty"];
        scale = Max[b["sample_spacing"], numpyMedian[u], 1*^-12];
        conf = Clip[Exp[-#/scale], {b["confidence_floor"], 1}] & /@ u;
        {crossAgreeQ[scale, b["python_confidence_scale"]],
         Max[Abs[conf - b["python_confidence"]]] <= $tolCross,
         TrueQ[Simplify[D[Exp[-uu/ss], uu] < 0, ss > 0 && Element[uu, Reals]]]}],
    {True, True, True},
    TestID -> "STAT-CONF-001"
]

(* STAT-BOOTINV-001: nearest-distance statistics are invariant when base and
   replicas undergo the same rigid transform (50-digit check). *)
VerificationTest[
    Module[{b = statData["bootstrap_case"], base, replicas, rot, shift, moveAll, dist, before, after,
            angle = N[3/7, $wp]},
        base = SetPrecision[b["base_curve"], $wp];
        replicas = SetPrecision[#, $wp] & /@ b["replicas"];
        rot = {{Cos[angle], -Sin[angle]}, {Sin[angle], Cos[angle]}};
        shift = {N[11/3, $wp], N[-4/9, $wp]};
        moveAll[pts_] := (rot . # + shift) & /@ pts;
        dist[bs_, reps_] := Sqrt[Mean[Table[
            Table[Min[Table[Norm[bs[[k]] - rp], {rp, replica}]], {k, Length[bs]}]^2,
            {replica, reps}]]];
        before = dist[base, replicas];
        after = dist[moveAll[base], moveAll /@ replicas];
        Max[Abs[before - after]] <= 1*^-40],
    True,
    TestID -> "STAT-BOOTINV-001"
]
