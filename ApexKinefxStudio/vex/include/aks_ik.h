// ApexKinefxStudio - analytic IK.
#ifndef AKS_IK_H
#define AKS_IK_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

// Two-bone IK (law of cosines). root/mid/end with bone lengths l1, l2 reach
// toward target; the chain bends toward the pole point. Outputs new mid & end.
void aks_two_bone_ik(vector root; float l1; float l2; vector target; vector pole;
                     export vector mid; export vector end)
{
    vector d = target - root;
    float dist = length(d);
    float maxr = (l1 + l2) * 0.9999;
    float minr = abs(l1 - l2) * 1.0001 + 1e-6;
    float r = clamp(dist, minr, maxr);
    vector dir = dist > 1e-8 ? d / dist : set(0, -1, 0);
    end = root + dir * r;
    float cosa = clamp((l1 * l1 + r * r - l2 * l2) / (2 * l1 * r), -1, 1);
    float a = acos(cosa);
    vector pv = pole - root;
    vector bend = pv - dir * dot(pv, dir);
    if (length(bend) < 1e-6)
    {
        bend = cross(dir, {1, 0, 0});
        if (length(bend) < 1e-6)
            bend = cross(dir, {0, 0, 1});
    }
    bend = normalize(bend);
    mid = root + dir * (cos(a) * l1) + bend * (sin(a) * l1);
}

#endif
