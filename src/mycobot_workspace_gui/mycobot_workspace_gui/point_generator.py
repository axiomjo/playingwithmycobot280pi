import math

Z_LAYERS = [40.0, 100.0, 150.0, 200.0]
MAX_RADIUS = 200.0
RADIUS_STEP = 20.0
ANGLE_STEPS = 12
RX_FIXED, RY_FIXED, RZ_FIXED = 180.0, 0.0, 0.0
MAX_REACH = 280.0  # MyCobot 280 Pi reach

def generate_points():
    points = []
    for z in Z_LAYERS:
        radius = RADIUS_STEP
        while radius <= MAX_RADIUS:
            for i in range(ANGLE_STEPS):
                angle_rad = 2 * math.pi * i / ANGLE_STEPS
                x = round(radius * math.cos(angle_rad), 2)
                y = round(radius * math.sin(angle_rad), 2)
                dist = math.sqrt(x**2 + y**2 + z**2)
                if dist <= MAX_REACH:
                    points.append([x, y, z, RX_FIXED, RY_FIXED, RZ_FIXED])
            radius += RADIUS_STEP
    return points

