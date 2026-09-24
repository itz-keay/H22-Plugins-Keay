// ApexKinefxStudio - vehicle math (mirrors core/vehicle_math.py).
// Y up, +Z forward, +X left; curvature positive = left turn.
#ifndef AKS_VEHICLE_H
#define AKS_VEHICLE_H

#ifndef AKS_PI
#define AKS_PI 3.14159265358979
#endif

// Wheel spin in radians for distance travelled: d / r  (= 2*pi * d / (2*pi*r)).
float aks_wheel_spin(float distance; float radius)
{
    return distance / max(radius, 1e-6);
}

float aks_clamp_half_pi(float a)
{
    if (a > AKS_PI * 0.5) return a - AKS_PI;
    if (a < -AKS_PI * 0.5) return a + AKS_PI;
    return a;
}

// Ackermann steer angle for a wheel on `side` (+1 left, -1 right).
float aks_ackermann(float wheelbase; float track; float kappa; float side)
{
    return aks_clamp_half_pi(atan2(wheelbase * kappa, 1.0 - side * kappa * track * 0.5));
}

float aks_drift_slip(float lat_accel; float grip; float gain; float max_angle; float amount)
{
    float excess = abs(lat_accel) - grip;
    if (excess <= 0)
        return 0;
    float a = min(max_angle, excess * gain) * amount;
    return lat_accel < 0 ? -a : a;
}

// Least squares plane h = a + b*x + c*z through contacts (x, z, h).
// Outputs height at the local origin, nose-up pitch and left-up roll (radians).
void aks_fit_plane(float xs[]; float zs[]; float hs[];
                   export float height; export float pitch; export float roll)
{
    int n = len(hs);
    height = 0; pitch = 0; roll = 0;
    if (n == 0) return;
    if (n == 1) { height = hs[0]; return; }
    float mx = 0, mz = 0, mh = 0;
    for (int i = 0; i < n; i++) { mx += xs[i]; mz += zs[i]; mh += hs[i]; }
    mx /= n; mz /= n; mh /= n;
    float cxx = 0, czz = 0, cxz = 0, cxh = 0, czh = 0;
    for (int i = 0; i < n; i++)
    {
        float dx = xs[i] - mx, dz = zs[i] - mz, dh = hs[i] - mh;
        cxx += dx * dx; czz += dz * dz; cxz += dx * dz; cxh += dx * dh; czh += dz * dh;
    }
    float det = cxx * czz - cxz * cxz;
    float b = 0, c = 0;
    if (abs(det) < 1e-12)
    {
        if (czz >= cxx) c = czz > 1e-12 ? czh / czz : 0;
        else            b = cxx > 1e-12 ? cxh / cxx : 0;
    }
    else
    {
        b = (cxh * czz - czh * cxz) / det;
        c = (czh * cxx - cxh * cxz) / det;
    }
    height = mh - b * mx - c * mz;
    pitch = atan(c);
    roll = atan(b);
}

// Body rotation from yaw (about +Y), nose-up pitch and left-up roll.
// Tilt is applied in the vehicle's local frame, then yaw.
matrix3 aks_body_rotation(float yaw; float pitch; float roll)
{
    matrix3 rz = ident(); rotate(rz, roll, {0, 0, 1});
    matrix3 rx = ident(); rotate(rx, -pitch, {1, 0, 0});
    matrix3 ry = ident(); rotate(ry, yaw, {0, 1, 0});
    return rz * rx * ry;
}

#endif
