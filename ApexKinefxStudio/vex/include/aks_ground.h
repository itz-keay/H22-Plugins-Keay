// ApexKinefxStudio - ground queries against a heightfield or a polygon mesh.
//
// The ground input may contain a HeightField (a volume primitive named
// "height") or polygons. With nothing connected the ground is the plane
// y = fallback.
#ifndef AKS_GROUND_H
#define AKS_GROUND_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

// Height of the ground below/above pos; writes the ground normal to nrm.
float aks_ground(int geo; vector pos; float probe; float fallback; export vector nrm)
{
    nrm = {0, 1, 0};
    if (nprimitives(geo) < 1)
        return fallback;
    int hf = nametoprim(geo, "height");
    if (hf >= 0)
    {
        vector q = set(pos.x, 0, pos.z);
        float h = volumesample(geo, hf, q);
        float e = max(volumevoxeldiameter(geo, hf) * 0.5, 1e-3);
        float hx = volumesample(geo, hf, q + set(e, 0, 0)) - volumesample(geo, hf, q - set(e, 0, 0));
        float hz = volumesample(geo, hf, q + set(0, 0, e)) - volumesample(geo, hf, q - set(0, 0, e));
        nrm = normalize(set(-hx, 2 * e, -hz));
        return h;
    }
    vector hitp, hituv;
    vector orig = set(pos.x, pos.y + probe, pos.z);
    int hitprim = intersect(geo, orig, set(0, -2 * probe, 0), hitp, hituv);
    if (hitprim >= 0)
    {
        nrm = normalize(prim_normal(geo, hitprim, hituv));
        if (nrm.y < 0)
            nrm = -nrm;
        return hitp.y;
    }
    return fallback;
}

float aks_ground_h(int geo; vector pos; float probe; float fallback)
{
    vector n;
    return aks_ground(geo, pos, probe, fallback, n);
}

#endif
