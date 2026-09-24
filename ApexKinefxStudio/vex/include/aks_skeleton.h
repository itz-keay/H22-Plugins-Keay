// ApexKinefxStudio - KineFX skeleton helpers.
//
// KineFX skeletons are points (joints) with s@name, v@P, 3@transform (world
// rotation/scale) and 4@localtransform, connected by polylines running
// parent -> child. All matrices here use VEX's row-vector convention:
// p_world = p_local * M, so "apply A then B" is A * B.
//
// Pattern used by the animation snippets (run over Detail):
//   matrix W[] = aks_load_world(0);        // world matrices, indexed by ptnum
//   ... compute new W[i] ...
//   aks_commit(W);                          // writes P, transform, localtransform
#ifndef AKS_SKELETON_H
#define AKS_SKELETON_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

// ---- matrix helpers --------------------------------------------------------

matrix aks_compose(matrix3 r; vector p)
{
    matrix m = matrix(r);
    setcomp(m, p.x, 3, 0);
    setcomp(m, p.y, 3, 1);
    setcomp(m, p.z, 3, 2);
    return m;
}

vector aks_pos(matrix m)
{
    return set(getcomp(m, 3, 0), getcomp(m, 3, 1), getcomp(m, 3, 2));
}

matrix3 aks_rot(matrix m)
{
    return matrix3(m);
}

matrix aks_set_pos(matrix m; vector p)
{
    matrix r = m;
    setcomp(r, p.x, 3, 0);
    setcomp(r, p.y, 3, 1);
    setcomp(r, p.z, 3, 2);
    return r;
}

matrix3 aks_axis_angle(vector axis; float angle)
{
    matrix3 r = ident();
    rotate(r, angle, normalize(axis));
    return r;
}

// Rotation taking the frame (rest_fwd, rest_up) onto (cur_fwd, cur_up).
matrix3 aks_frame_delta(vector rest_fwd; vector rest_up; vector cur_fwd; vector cur_up)
{
    matrix3 fr = maketransform(normalize(rest_fwd), normalize(rest_up));
    matrix3 fc = maketransform(normalize(cur_fwd), normalize(cur_up));
    return invert(fr) * fc;
}

// Rotation for a bone whose rest direction/up are (rest_dir, rest_up) and whose
// animated direction/up are (new_dir, new_up). Falls back to `alt_*` up
// vectors when the bone is (nearly) parallel to its up vector.
matrix3 aks_bone_rot(vector rest_dir; vector rest_up; vector new_dir; vector new_up;
                     vector alt_rest_up; vector alt_new_up)
{
    vector ru = rest_up;
    vector nu = new_up;
    if (abs(dot(normalize(rest_dir), normalize(rest_up))) > 0.98)
    {
        ru = alt_rest_up;
        nu = alt_new_up;
    }
    return aks_frame_delta(rest_dir, ru, new_dir, nu);
}

// Point number of the joint on `chain` with the given chain_index (-1 if none).
int aks_chain_joint(int geo; string chain; int index)
{
    int n = npoints(geo);
    for (int i = 0; i < n; i++)
    {
        string c = point(geo, "chain", i);
        int ci = point(geo, "chain_index", i);
        if (c == chain && ci == index)
            return i;
    }
    return -1;
}

// Rotate a world matrix so its bone direction old_dir now points along
// new_dir (minimal rotation, position kept).
matrix aks_aim_world(matrix w; vector old_dir; vector new_dir)
{
    if (length(old_dir) < 1e-9 || length(new_dir) < 1e-9)
        return w;
    matrix3 d = dihedral(normalize(old_dir), normalize(new_dir));
    return aks_compose(aks_rot(w) * d, aks_pos(w));
}

// ---- reading the skeleton -----------------------------------------------------

matrix aks_world(int geo; int pt)
{
    matrix3 r = point(geo, "transform", pt);
    vector p = point(geo, "P", pt);
    return aks_compose(r, p);
}

matrix[] aks_load_world(int geo)
{
    int n = npoints(geo);
    matrix w[];
    resize(w, n);
    for (int i = 0; i < n; i++)
        w[i] = aks_world(geo, i);
    return w;
}

// Parent joint = previous point on any polyline through pt (-1 for roots).
int aks_parent(int geo; int pt)
{
    int prims[] = pointprims(geo, pt);
    foreach (int pr; prims)
    {
        int pts[] = primpoints(geo, pr);
        int idx = find(pts, pt);
        if (idx > 0)
            return pts[idx - 1];
    }
    return -1;
}

int[] aks_parents(int geo)
{
    int n = npoints(geo);
    int par[];
    resize(par, n);
    for (int i = 0; i < n; i++)
        par[i] = aks_parent(geo, i);
    return par;
}

// Point numbers sorted so parents always come before children.
int[] aks_topo_order(int par[])
{
    int n = len(par);
    int depth[];
    resize(depth, n);
    for (int i = 0; i < n; i++)
    {
        int d = 0;
        int p = par[i];
        while (p >= 0 && d < 100000)
        {
            d++;
            p = par[p];
        }
        depth[i] = d;
    }
    return argsort(depth);
}

int aks_is_descendant(int par[]; int pt; int ancestor)
{
    int p = par[pt];
    int guard = 0;
    while (p >= 0 && guard < 100000)
    {
        if (p == ancestor)
            return 1;
        p = par[p];
        guard++;
    }
    return 0;
}

int aks_find(int geo; string name)
{
    return findattribval(geo, "point", "name", name);
}

// True when the joint name matches a space separated list of patterns
// (Houdini wildcard syntax, e.g. "tail_* antenna_*").
int aks_name_matches(string name; string patterns)
{
    if (patterns == "" || patterns == "*")
        return 1;
    foreach (string pat; split(patterns, " "))
        if (match(pat, name))
            return 1;
    return 0;
}

// ---- writing the skeleton --------------------------------------------------------

// Rigidly carry un-driven joints along with their parents, keeping their rest
// local transform. driven[i] = 1 marks joints whose W[i] was already set.
void aks_follow_rest(int geo; int par[]; int order[]; int driven[]; matrix W[])
{
    foreach (int j; order)
    {
        if (driven[j] || par[j] < 0)
            continue;
        matrix rest_j = aks_world(geo, j);
        matrix rest_p = aks_world(geo, par[j]);
        W[j] = rest_j * invert(rest_p) * W[par[j]];
    }
}

// After changing some joints (changed[i] = 1), move their descendants so each
// child keeps its previous transform relative to its parent.
void aks_propagate(int par[]; int order[]; int changed[]; matrix w_old[]; matrix W[])
{
    int moved[] = changed;
    foreach (int j; order)
    {
        int p = par[j];
        if (moved[j] || p < 0 || !moved[p])
            continue;
        W[j] = w_old[j] * invert(w_old[p]) * W[p];
        moved[j] = 1;
    }
}

// Write world matrices back as P / transform / localtransform on geoself.
void aks_commit(int par[]; matrix W[])
{
    int n = len(W);
    for (int i = 0; i < n; i++)
    {
        setpointattrib(0, "P", i, aks_pos(W[i]));
        setpointattrib(0, "transform", i, aks_rot(W[i]));
        matrix l = par[i] >= 0 ? W[i] * invert(W[par[i]]) : W[i];
        setpointattrib(0, "localtransform", i, l);
    }
}

#endif
