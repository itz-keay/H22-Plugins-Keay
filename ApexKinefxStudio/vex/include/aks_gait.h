// ApexKinefxStudio - distance driven gait (mirrors core/gait.py).
#ifndef AKS_GAIT_H
#define AKS_GAIT_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

// Gait ids: 0 auto, 1 tripod, 2 wave, 3 tetrapod, 4 walk, 5 trot, 6 gallop, 7 metachronal
// Leg order: left legs front->back, then right legs front->back.
float aks_gait_offset(int gait; int leg; int nlegs; export float duty)
{
    int g = gait;
    if (g == 0)
        g = nlegs == 6 ? 1 : (nlegs == 4 ? 5 : (nlegs == 2 ? 5 : 7));
    int per_side = max(1, (nlegs + 1) / 2);
    int side = leg < per_side ? 0 : 1;
    int idx = side == 0 ? leg : leg - per_side;
    if (g == 1)   // tripod: L1 R2 L3 | R1 L2 R3 (alternating per side)
    {
        duty = 0.5;
        return ((idx + side) % 2) * 0.5;
    }
    if (g == 2)   // wave: ripple back->front, right half a cycle later
    {
        duty = 5.0 / 6.0;
        return frac((per_side - 1 - idx) / float(nlegs) + side * 0.5);
    }
    if (g == 3)   // tetrapod: three phase groups
    {
        duty = 2.0 / 3.0;
        return ((idx + side * 2) % 3) / 3.0;
    }
    if (g == 4)   // quadruped walk: LF .25 LH 0 RF .75 RH .5
    {
        duty = 0.75;
        float t[] = {0.25, 0.0, 0.75, 0.5};
        return t[clamp(leg, 0, 3)];
    }
    if (g == 5)   // trot / alternating (diagonal pairs)
    {
        duty = 0.5;
        return ((idx + side) % 2) * 0.5;
    }
    if (g == 6)   // gallop
    {
        duty = 0.35;
        float t[] = {0.5, 0.0, 0.6, 0.1};
        return t[clamp(leg, 0, 3)];
    }
    duty = 0.7;   // metachronal
    return frac((per_side - 1 - idx) / float(per_side) + 0.5 * side);
}

// Closed-form foot: returns the path distance at which to evaluate the foot's
// home position, the swing lift (0..1) and whether the foot is planted.
void aks_foot(float distance; float stride; float offset; float duty;
              export float plant_d; export float lift; export int stance)
{
    float dty = clamp(duty, 0.05, 0.95);
    float u = distance / max(stride, 1e-6) + offset;
    float ph = u - floor(u);
    float plant = distance - ph * stride + dty * stride * 0.5;
    if (ph < dty)
    {
        plant_d = plant;
        lift = 0;
        stance = 1;
    }
    else
    {
        float t = (ph - dty) / (1 - dty);
        float e = t * t * (3 - 2 * t);
        plant_d = plant + e * stride;
        lift = sin(AKS_PI * t);
        stance = 0;
    }
}

#endif
