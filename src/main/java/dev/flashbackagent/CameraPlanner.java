package dev.flashbackagent;

/** Deterministic camera mathematics, independent of Minecraft and its render thread. */
public final class CameraPlanner {
    public record Vec(double x, double y, double z) {
        public Vec add(Vec v) { return new Vec(x + v.x, y + v.y, z + v.z); }
        public Vec subtract(Vec v) { return new Vec(x - v.x, y - v.y, z - v.z); }
        public Vec scale(double f) { return new Vec(x * f, y * f, z * f); }
        public double length() { return Math.sqrt(x*x + y*y + z*z); }
    }
    public record Pose(int tick, Vec position, Vec focus, double yaw, double pitch, double fov) {}
    private final double distance, side, height;
    private Vec previousFeet, camera;
    private double heading, previousYaw;
    private int previousTick;
    public CameraPlanner(double distance, double side, double height) {
        if (!Double.isFinite(distance) || distance < 2 || distance > 16 || !Double.isFinite(side) || Math.abs(side) > 8
            || !Double.isFinite(height) || height < .5 || height > 10)
            throw new IllegalArgumentException("Invalid camera settings");
        this.distance = distance;
        this.side = side;
        this.height = height;
    }
    public Pose sample(int tick, Vec feet, double bodyYaw) {
        boolean first = previousFeet == null;
        if (tick < 0 || !Double.isFinite(feet.x) || !Double.isFinite(feet.y) || !Double.isFinite(feet.z) || !Double.isFinite(bodyYaw))
            throw new IllegalArgumentException("Invalid sample");
        if (!first && (tick <= previousTick || feet.subtract(previousFeet).length() > 12))
            throw new IllegalArgumentException("Non-monotonic sample or teleport; split the clip");
        double dt = first ? .1 : (tick - previousTick) / 20.0;
        Vec velocity = first ? new Vec(0, 0, 0) : feet.subtract(previousFeet).scale(1 / dt);
        double speed = Math.hypot(velocity.x, velocity.z);
        double wantedHeading = speed > .6 ? Math.atan2(-velocity.x, velocity.z) : Math.toRadians(bodyYaw);
        if (first) heading = wantedHeading;
        else heading += clamp(wrap(wantedHeading - heading), -2.1 * dt, 2.1 * dt);
        Vec forward = new Vec(-Math.sin(heading), 0, Math.cos(heading));
        Vec right = new Vec(Math.cos(heading), 0, Math.sin(heading));
        // Slow lateral breathing, extra distance/FOV at speed; no random camera shake.
        double lateral = side * (1 + .16 * Math.sin(tick / 20.0 * .5));
        Vec desired = feet.add(forward.scale(-distance - Math.min(speed * .15, 2)))
            .add(right.scale(lateral)).add(new Vec(0, height, 0));
        double alpha = 1 - Math.exp(-dt / .22);
        camera = first ? desired : camera.add(desired.subtract(camera).scale(alpha));
        Vec lead = velocity.scale(.10);
        if (lead.length() > .8) lead = lead.scale(.8 / lead.length());
        Vec focus = feet.add(new Vec(0, 1.35, 0)).add(lead);
        Pose pose = aim(tick, camera, focus, 70 + Math.min(speed * 1.4, 16), first ? null : previousYaw);
        previousFeet = feet;
        previousTick = tick;
        previousYaw = pose.yaw;
        return pose;
    }

    public Pose corrected(Pose pose, Vec position) {
        camera = position;
        Pose corrected = aim(pose.tick, position, pose.focus, pose.fov, previousYaw);
        previousYaw = corrected.yaw;
        return corrected;
    }

    private static Pose aim(int tick, Vec camera, Vec focus, double fov, Double priorYaw) {
        Vec look = focus.subtract(camera);
        double yaw = Math.toDegrees(Math.atan2(-look.x, look.z));
        if (priorYaw != null) yaw = priorYaw + Math.toDegrees(wrap(Math.toRadians(yaw - priorYaw)));
        double pitch = -Math.toDegrees(Math.atan2(look.y, Math.hypot(look.x, look.z)));
        return new Pose(tick, camera, focus, yaw, pitch, fov);
    }
    private static double wrap(double a) { return Math.atan2(Math.sin(a), Math.cos(a)); }
    private static double clamp(double v, double lo, double hi) { return Math.max(lo, Math.min(hi, v)); }
}
