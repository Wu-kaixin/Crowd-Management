(* Adaptive guide-resource policy: ceiling bound, minimality, clipping,
   hysteresis invariants. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
resData = loadCases["resources_cases.json"];
resConfig = resData["config"];

(* RESOURCE-CEILING-001: symbolic ceiling properties that carry the coverage
   guarantee: x <= Ceiling[x] < x + 1 for all reals. From m = Ceiling[L/g] >=
   L/g > 0 follows L/m <= g; from Ceiling[L/g] < L/g + 1 follows the
   minimality L/(m-1) > g whenever m >= 2. *)
VerificationTest[
    {FullSimplify[Ceiling[x] >= x, Element[x, Reals]],
     FullSimplify[Ceiling[x] < x + 1, Element[x, Reals]],
     (* chain: if m >= L/g and m,g,L > 0 then L/m <= g *)
     Resolve[ForAll[{m, len, g}, m >= len/g && len > 0 && g > 0 && m > 0, len/m <= g], Reals],
     (* minimality: if m - 1 < L/g then L/(m-1) > g *)
     Resolve[ForAll[{m, len, g}, m - 1 < len/g && len > 0 && g > 0 && m > 1, len/(m - 1) > g], Reals]},
    {True, True, True, True},
    TestID -> "RESOURCE-CEILING-001"
]

(* RESOURCE-CEILING-002: exported requested counts equal Ceiling[L/g_req]
   (rationalized to avoid float-boundary ambiguity at exact multiples). *)
VerificationTest[
    AllTrue[resData["grid"],
        #["python_requested"] == Ceiling[Rationalize[#["length"], 1*^-12]/Rationalize[resConfig["g_req"], 1*^-12]] &],
    True,
    TestID -> "RESOURCE-CEILING-002"
]

(* RESOURCE-CLIP-001: active/reserve/unmet arithmetic and shortfall status. *)
VerificationTest[
    AllTrue[resData["grid"],
        Module[{desired = #["python_desired"], available = #["available"]},
            And[
                #["python_active"] == Min[desired, available],
                #["python_reserve"] == Max[available - Min[desired, available], 0],
                #["python_unmet"] == Max[desired - available, 0],
                #["python_status"] === If[Max[desired - available, 0] > 0, "CAPACITY_SHORTFALL", "VALID"]
            ]] &],
    True,
    TestID -> "RESOURCE-CLIP-001"
]

(* RESOURCE-HYST-001: independent reimplementation of the hysteresis loop
   reproduces every exported desired count. *)
hystDesired[len_, previous_, cfg_] := Module[
    {greq = cfg["g_req"], mmin = cfg["m_min"], hinc = cfg["increase_hysteresis"],
     hdec = cfg["decrease_hysteresis"], requested, baseline, desired},
    requested = Ceiling[Rationalize[len, 1*^-12]/Rationalize[greq, 1*^-12]];
    baseline = Max[requested, mmin];
    desired = baseline;
    If[previous =!= Null,
        desired = Max[previous, mmin];
        Which[
            baseline > desired,
            While[desired < baseline && len > desired greq + hinc, desired += 1],
            baseline < desired,
            While[desired > baseline && len < (desired - 1) greq - hdec, desired -= 1]]];
    desired];

VerificationTest[
    AllTrue[resData["grid"],
        hystDesired[#["length"], #["previous"], resConfig] == #["python_desired"] &],
    True,
    TestID -> "RESOURCE-HYST-001"
]

(* RESOURCE-HYST-002: hysteresis invariant. Whenever the policy holds the
   count away from baseline, the held count stays within the configured
   margins: increase case L <= desired*g_req + h_inc, decrease case
   L >= (desired-1)*g_req - h_dec. Realized gap therefore obeys
   L/desired <= g_req + h_inc/desired in the increase case. *)
VerificationTest[
    AllTrue[resData["grid"],
        Module[{len = #["length"], desired = #["python_desired"], baseline},
            baseline = Max[Ceiling[Rationalize[len, 1*^-12]/Rationalize[resConfig["g_req"], 1*^-12]], resConfig["m_min"]];
            Which[
                desired < baseline, len <= desired resConfig["g_req"] + resConfig["increase_hysteresis"] + 1*^-12,
                desired > baseline, len >= (desired - 1) resConfig["g_req"] - resConfig["decrease_hysteresis"] - 1*^-12,
                True, True]] &],
    True,
    TestID -> "RESOURCE-HYST-002"
]

(* RESOURCE-EDGE-001: Python rejected all invalid inputs (recorded outcomes). *)
VerificationTest[
    AllTrue[resData["rejections"],
        StringContainsQ[#["python_outcome"], "Error"] &],
    True,
    TestID -> "RESOURCE-EDGE-001"
]
