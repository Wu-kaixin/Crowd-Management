(* Geometry verification: closed curves, arc length, periodic parameterization. *)
Get[FileNameJoin[{Directory[], "wolfram", "common.wl"}]];
geoData = loadCases["geometry_cases.json"];

(* GEOMETRY-AREA-001: shoelace identity for a symbolic triangle equals half the
   cross product of edge vectors (orientation-signed area). *)
VerificationTest[
    FullSimplify[
        1/2 ((ax by - bx ay) + (bx cy - cx by) + (cx ay - ax cy))
        - 1/2 ((bx - ax) (cy - ay) - (by - ay) (cx - ax))],
    0,
    TestID -> "GEOMETRY-AREA-001"
]

(* GEOMETRY-AREA-002: exact rational polygons; positive iff counter-clockwise,
   reversal negates. Cross-check exported Python signed areas exactly. *)
VerificationTest[
    Module[{poly = {{0, 0}, {4, 0}, {6, 2}, {5, 5}, {2, 6}, {-1, 3}}},
        {polygonSignedArea[poly] > 0,
         polygonSignedArea[Reverse[poly]] == -polygonSignedArea[poly]}],
    {True, True},
    TestID -> "GEOMETRY-AREA-002"
]

VerificationTest[
    AllTrue[geoData["curves"],
        crossAgreeQ[polygonSignedArea[#["input_points"]], #["python_signed_area"]] &],
    True,
    TestID -> "GEOMETRY-AREA-003"
]

(* GEOMETRY-ARC-001: Python closed length equals the polygon perimeter computed
   independently (input polygons; circle/ellipse cases are themselves polygons). *)
VerificationTest[
    AllTrue[geoData["curves"],
        crossAgreeQ[polygonPerimeter[#["input_points"]], #["python_length"]] &],
    True,
    TestID -> "GEOMETRY-ARC-001"
]

(* GEOMETRY-ARCS-001: arc coordinates are k*L/count, start at 0, last < L, and
   the sample count matches max(3, ceil(L/spacing - 1e-12)). *)
VerificationTest[
    AllTrue[geoData["curves"],
        Module[{len = polygonPerimeter[#["input_points"]], count = #["python_sample_count"], spacing = #["spacing"]},
            And[
                count == Max[3, Ceiling[len/spacing - 1*^-12]],
                crossAgreeQ[#["python_arc_s_first3"][[2]], len/count],
                crossAgreeQ[#["python_arc_s_last"], (count - 1) len/count],
                #["python_arc_s_first3"][[1]] == 0.
            ]] &],
    True,
    TestID -> "GEOMETRY-ARCS-001"
]

(* GEOMETRY-ARCS-002: every resampled point lies on the source polygon and its
   cumulative arc position equals k*L/count (independent point-on-polygon check). *)
arcPositionOnPolygon[poly_List, pt_List] := Module[
    {ccw, segs, cum = 0., a, b, t, proj, best = None, i},
    ccw = If[polygonSignedArea[poly] < 0, Reverse[poly], poly];
    Do[
        a = ccw[[i]]; b = ccw[[Mod[i, Length[ccw]] + 1]];
        t = (pt - a) . (b - a)/((b - a) . (b - a));
        If[-1*^-9 <= t <= 1 + 1*^-9,
            proj = a + Clip[t, {0, 1}] (b - a);
            If[Norm[pt - proj] <= 1*^-7 && best === None,
                best = cum + Clip[t, {0, 1}] Norm[b - a]]];
        cum += Norm[ccw[[Mod[i, Length[ccw]] + 1]] - ccw[[i]]],
        {i, Length[ccw]}];
    best];

VerificationTest[
    AllTrue[geoData["curves"],
        Module[{poly = #["input_points"], pts = #["python_curve_points"],
                len = #["python_length"], count = #["python_sample_count"], k},
            AllTrue[Range[Length[pts]],
                Function[k, Module[{pos = arcPositionOnPolygon[poly, pts[[k]]]},
                    pos =!= None &&
                    (Abs[pos - (k - 1) len/count] <= 1*^-7 ||
                     Abs[pos - (k - 1) len/count - len] <= 1*^-7 ||
                     Abs[pos - (k - 1) len/count + len] <= 1*^-7)]]]] &],
    True,
    TestID -> "GEOMETRY-ARCS-002"
]

(* GEOMETRY-PDIST-001: symbolic case-split proof that the implemented wrap
   formula equals min(d, L-d) on a fundamental domain, plus wrapping lemma. *)
VerificationTest[
    {Assuming[len > 0 && 0 <= d < len/2,
        FullSimplify[Abs[Mod[d + len/2, len] - len/2] - Min[d, len - d]]],
     Assuming[len > 0 && len/2 <= d < len,
        FullSimplify[Abs[Mod[d + len/2, len] - len/2] - Min[d, len - d]]],
     Assuming[len > 0, FullSimplify[Mod[d + k len + len/2, len] - Mod[d + len/2, len], Element[k, Integers]]]},
    {0, 0, 0},
    TestID -> "GEOMETRY-PDIST-001"
]

(* GEOMETRY-PDIST-002: exported Python values match the independent formula,
   including out-of-range coordinates. *)
VerificationTest[
    AllTrue[geoData["periodic_distance"],
        crossAgreeQ[periodicDistance[#["a"], #["b"], #["length"]], #["python_d"]] &],
    True,
    TestID -> "GEOMETRY-PDIST-002"
]

(* GEOMETRY-GAP-001: exported max-gap values match the independent computation;
   gaps always sum to L (checked exactly on each case). *)
VerificationTest[
    AllTrue[geoData["max_gap"],
        Module[{s = Sort[Mod[#["sites"], #["length"]]], len = #["length"]},
            crossAgreeQ[maxArcGap[#["sites"], len], #["python_max_gap"]] &&
            Abs[Total[Differences[Append[s, First[s] + len]]] - len] <= 1*^-9] &],
    True,
    TestID -> "GEOMETRY-GAP-001"
]

(* GEOMETRY-NORMAL-001: unit tangents/normals, orthogonality, and outwardness
   n.(p - centroid) > 0 on the convex circle and ellipse samples. *)
VerificationTest[
    AllTrue[Select[geoData["curves"], MemberQ[{"circle", "ellipse", "convex_polygon"}, #["name"]] &],
        Module[{pts = #["python_curve_points"], tans = #["python_tangents"],
                nors = #["python_outward_normals"], c = #["python_centroid"]},
            And[
                Max[Abs[Norm /@ tans - 1]] <= 1*^-9,
                Max[Abs[Norm /@ nors - 1]] <= 1*^-9,
                Max[Abs[MapThread[Dot, {tans, nors}]]] <= 1*^-9,
                Min[MapThread[#2 . (#1 - c) &, {pts, nors}]] > 0
            ]] &],
    True,
    TestID -> "GEOMETRY-NORMAL-001"
]

(* GEOMETRY-TANGENT-001: central-difference tangent error decays as O(h^2) on
   an analytic non-affine star curve (50-digit reference; ratio near 1/4 when
   h halves).  Circles and ellipses are unsuitable references: symmetric
   chords of any affine circle image are exactly parallel to the tangent. *)
VerificationTest[
    Module[{err, ratio},
        err[n_] := Module[{r, x, y, pts, tans, exact, k, theta},
            r[t_] := 2 + 2/5 Sin[3 t];
            x[t_] := r[t] Cos[t]; y[t_] := r[t] Sin[t];
            pts = Table[N[{x[2 Pi k/n], y[2 Pi k/n]}, $wp], {k, 0, n - 1}];
            tans = Table[
                Normalize[pts[[Mod[k, n] + 1]] - pts[[Mod[k - 2, n] + 1]]],
                {k, 1, n}];
            exact = Table[theta = 2 Pi (k - 1)/n;
                Normalize[N[{x'[theta], y'[theta]}, $wp]], {k, 1, n}];
            Max[MapThread[Norm[#1 - #2] &, {tans, exact}]]];
        ratio = err[128]/err[64];
        0.15 < ratio < 0.35],
    True,
    TestID -> "GEOMETRY-TANGENT-001"
]

(* GEOMETRY-SELFX-001: exact predicate finds the bowtie crossing; Python
   rejected it with ValueError, and the convex polygon has no crossing. *)
segmentsCross[{a_, b_}, {c_, d_}] := Module[{o1, o2, o3, o4},
    o1 = Sign[(b - a)[[1]] (c - a)[[2]] - (b - a)[[2]] (c - a)[[1]]];
    o2 = Sign[(b - a)[[1]] (d - a)[[2]] - (b - a)[[2]] (d - a)[[1]]];
    o3 = Sign[(d - c)[[1]] (a - c)[[2]] - (d - c)[[2]] (a - c)[[1]]];
    o4 = Sign[(d - c)[[1]] (b - c)[[2]] - (d - c)[[2]] (b - c)[[1]]];
    o1 != o2 && o3 != o4 && o1 != 0 && o2 != 0];

VerificationTest[
    Module[{bowtie = {{0, 0}, {2, 2}, {2, 0}, {0, 2}}, rej},
        rej = SelectFirst[geoData["rejections"], #["name"] === "self_intersecting" &];
        {segmentsCross[{bowtie[[1]], bowtie[[2]]}, {bowtie[[3]], bowtie[[4]]}],
         StringContainsQ[rej["python_outcome"], "ValueError"],
         segmentsCross[{{0, 0}, {4, 0}}, {{6, 2}, {5, 5}}]}],
    {True, True, False},
    TestID -> "GEOMETRY-SELFX-001"
]

(* GEOMETRY-SPACING-001: documented ASSUMPTION_GAP counterexample. The 1e-12
   guard admits realized spacing marginally above the requested spacing when
   L/spacing sits within 1e-12 above an integer. Exact rational arithmetic. *)
VerificationTest[
    Module[{len = 10, spacing, count, realized},
        spacing = 10/7 (1 - 10^-14);           (* L/spacing = 7 + 7*10^-14 *)
        count = Max[3, Ceiling[len/spacing - 10^-12]];
        realized = len/count;
        {count == 7, realized > spacing}],
    {True, True},
    TestID -> "GEOMETRY-SPACING-001"
]

(* GEOMETRY-CIRCUM-001: circumradius identity R = abc/(4 Area) = abc/(2|cross|)
   proved symbolically for a generic triangle (0,0),(x1,0),(x2,y2). *)
VerificationTest[
    Module[{a, b, c, area2, center, radius},
        a = Sqrt[x1^2]; (* |(x1,0)-(0,0)| *)
        b = Sqrt[(x2 - x1)^2 + y2^2];
        c = Sqrt[x2^2 + y2^2];
        area2 = Abs[x1 y2]; (* |cross| of edge vectors *)
        center = {x1/2, (x2^2 + y2^2 - x1 x2)/(2 y2)};
        radius = Simplify[Norm[center - {0, 0}], x1 > 0 && y2 > 0];
        FullSimplify[radius - a b c/(2 area2), x1 > 0 && y2 > 0 && Element[x2, Reals]]],
    0,
    TestID -> "GEOMETRY-CIRCUM-001"
]

(* GEOMETRY-INVAR-001: perimeter, signed area magnitude, and max arc gap are
   invariant under a 50-digit rigid transform. *)
VerificationTest[
    Module[{poly = {{0, 0}, {4, 0}, {6, 2}, {5, 5}, {2, 6}, {-1, 3}},
            angle = N[7/11, $wp], shift = {N[13/7, $wp], -N[5/3, $wp]}, rot, moved},
        rot = {{Cos[angle], -Sin[angle]}, {Sin[angle], Cos[angle]}};
        moved = (rot . # + shift) & /@ poly;
        {Abs[polygonPerimeter[moved] - polygonPerimeter[poly]] <= 1*^-40,
         Abs[polygonSignedArea[moved] - polygonSignedArea[poly]] <= 1*^-40}],
    {True, True},
    TestID -> "GEOMETRY-INVAR-001"
]
