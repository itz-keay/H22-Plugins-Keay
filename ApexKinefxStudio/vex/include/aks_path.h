// ApexKinefxStudio - arc-length parameterised path evaluation.
//
// Paths are the first primitive of an input (polyline or any curve converted
// to polygons). We load its points once per cook into arrays and evaluate by
// distance with a binary search, so nothing depends on primuv parameterisation.
// Distances beyond the ends extrapolate along the end tangents so creatures
// and vehicles can drive on/off the curve.
//
// If the input has no primitives the path is the +Z axis through the origin.
#ifndef AKS_PATH_H
#define AKS_PATH_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

struct aks_Path
{
    vector pts[];
    float cum[];
    float heading[];   // unwrapped yaw (atan2(dx, dz)) per point, for wheel travel
    float close_heading; // heading of the closing segment (closed paths)
    float loop_turn;   // total heading change per lap (closed paths, ~ +-2pi)
    float total;
    int closed;
    int valid;
}

aks_Path aks_path_load(int geo)
{
    aks_Path path;
    path.valid = 0;
    path.total = 0;
    path.closed = 0;
    if (nprimitives(geo) < 1)
        return path;
    int pp[] = primpoints(geo, 0);
    if (len(pp) < 2)
        return path;
    path.closed = primintrinsic(geo, "closed", 0);
    float acc = 0;
    float prev_h = 0;
    for (int i = 0; i < len(pp); i++)
    {
        vector p = point(geo, "P", pp[i]);
        if (i > 0)
            acc += distance(p, path.pts[i - 1]);
        append(path.pts, p);
        append(path.cum, acc);
    }
    // unwrapped heading per point (segment i-1 -> i; point 0 uses segment 0)
    int n = len(path.pts);
    for (int i = 0; i < n; i++)
    {
        int a = max(i - 1, 0);
        int b = max(i, 1);
        vector d = path.pts[b] - path.pts[a];
        float h = atan2(d.x, d.z);
        if (i > 0)
        {
            float dh = h - prev_h;
            dh -= 2 * AKS_PI * rint(dh / (2 * AKS_PI));
            h = prev_h + dh;
        }
        append(path.heading, h);
        prev_h = h;
    }
    path.total = acc;
    path.close_heading = prev_h;
    path.loop_turn = 0;
    if (path.closed)
    {
        path.total += distance(path.pts[n - 1], path.pts[0]);
        vector dc = path.pts[0] - path.pts[n - 1];
        float hc = atan2(dc.x, dc.z);
        float dh = hc - prev_h;
        dh -= 2 * AKS_PI * rint(dh / (2 * AKS_PI));
        hc = prev_h + dh;
        float h0 = path.heading[0];
        float dh0 = h0 - hc;
        dh0 -= 2 * AKS_PI * rint(dh0 / (2 * AKS_PI));
        path.close_heading = hc;
        path.loop_turn = (hc + dh0) - h0;
    }
    path.valid = 1;
    return path;
}

// Index of the segment containing distance d (lo such that cum[lo] <= d < cum[lo+1]).
int aks_path_segment(aks_Path path; float d)
{
    int lo = 0;
    int hi = len(path.cum) - 1;
    while (hi - lo > 1)
    {
        int mid = (lo + hi) / 2;
        if (path.cum[mid] <= d)
            lo = mid;
        else
            hi = mid;
    }
    return lo;
}

vector aks_path_pos(aks_Path path; float d)
{
    if (!path.valid)
        return set(0, 0, d);
    int n = len(path.pts);
    if (path.closed)
    {
        d = d - floor(d / path.total) * path.total;
        if (d >= path.cum[n - 1])
        {
            float seg = path.total - path.cum[n - 1];
            float t = seg > 0 ? (d - path.cum[n - 1]) / seg : 0;
            return lerp(path.pts[n - 1], path.pts[0], t);
        }
    }
    else
    {
        if (d <= 0)
            return path.pts[0] + normalize(path.pts[1] - path.pts[0]) * d;
        if (d >= path.total)
            return path.pts[n - 1] + normalize(path.pts[n - 1] - path.pts[n - 2]) * (d - path.total);
    }
    int lo = aks_path_segment(path, d);
    int hi = min(lo + 1, n - 1);
    float seg = path.cum[hi] - path.cum[lo];
    float t = seg > 0 ? (d - path.cum[lo]) / seg : 0;
    return lerp(path.pts[lo], path.pts[hi], t);
}

// Unit tangent by central difference over +-h.
vector aks_path_tangent(aks_Path path; float d; float h)
{
    vector t = aks_path_pos(path, d + h) - aks_path_pos(path, d - h);
    if (length(t) < 1e-9)
        return {0, 0, 1};
    return normalize(t);
}

// Signed curvature in the XZ plane (positive = turning left, i.e. toward +X
// when facing +Z), averaged over a window of +-h.
float aks_path_curvature(aks_Path path; float d; float h)
{
    vector t0 = aks_path_tangent(path, d - h, h * 0.5);
    vector t1 = aks_path_tangent(path, d + h, h * 0.5);
    float a0 = atan2(t0.x, t0.z);
    float a1 = atan2(t1.x, t1.z);
    float da = a1 - a0;
    da -= 2 * AKS_PI * rint(da / (2 * AKS_PI));
    return da / max(2 * h, 1e-6);
}

// Unwrapped heading at distance d (constant beyond open ends; closed loops
// accumulate loop_turn per lap so wheel travel stays continuous).
float aks_path_heading(aks_Path path; float d)
{
    if (!path.valid)
        return 0;
    int n = len(path.pts);
    float laps = 0;
    if (path.closed)
    {
        float lap = floor(d / path.total);
        laps = lap * path.loop_turn;
        d = d - lap * path.total;
        if (d >= path.cum[n - 1])
            return path.close_heading + laps;
    }
    if (d <= 0)
        return path.heading[0] + laps;
    if (d >= path.cum[n - 1])
        return path.heading[n - 1] + laps;
    int lo = aks_path_segment(path, d);
    // heading is constant along a polyline segment (lo -> lo+1)
    return path.heading[min(lo + 1, n - 1)] + laps;
}

// Distance travelled by a point offset `lateral` units to the left of the path
// centre (see core/vehicle_math.offset_arc_lengths): s' = s - w * dtheta.
float aks_path_offset_distance(aks_Path path; float d; float lateral)
{
    return d - lateral * (aks_path_heading(path, d) - aks_path_heading(path, 0));
}

#endif
