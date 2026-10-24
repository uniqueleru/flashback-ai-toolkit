package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import dev.flashbackagent.CameraPlanner.Vec;

class CameraPlannerTest {
    @Test void cameraFollowsMovingPlayerAndKeepsThemInFrame() {
        var planner = new CameraPlanner(5, 2, 2.5);
        var first = planner.sample(0, new Vec(0, 64, 0), 0);
        var last = first;
        for (int t = 2; t <= 100; t += 2)
            last = planner.sample(t, new Vec(0, 64, t * .2), 0);
        assertTrue(last.position().z() > first.position().z() + 10);
        assertTrue(last.position().z() < 20, "camera trails the player");
        assertTrue(last.focus().subtract(last.position()).length() < 12);
        assertTrue(Double.isFinite(last.yaw()) && Double.isFinite(last.pitch()));
    }
    @Test void rejectsNonMonotonicTicksAndTeleportsInsteadOfFlyingThroughWorld() {
        var planner = new CameraPlanner(5, 2, 2.5);
        planner.sample(20, new Vec(0, 64, 0), 0);
        assertThrows(IllegalArgumentException.class, () -> planner.sample(20, new Vec(0, 64, 0), 0));
        assertThrows(IllegalArgumentException.class, () -> planner.sample(22, new Vec(100, 64, 0), 0));
    }
    @Test void yawWrapDoesNotCreateAFullSpin() {
        var planner = new CameraPlanner(5, 0, 2.5);
        var a = planner.sample(0, new Vec(0, 64, 0), 179);
        var b = planner.sample(2, new Vec(0, 64, 0), -179);
        assertTrue(Math.abs(a.yaw() - b.yaw()) < 10);
    }
    @Test void rejectsInvalidCoordinatesAndSettings() {
        assertThrows(IllegalArgumentException.class, () -> new CameraPlanner(Double.NaN, 0, 2));
        var planner = new CameraPlanner(5, 2, 2.5);
        assertThrows(IllegalArgumentException.class, () -> planner.sample(0, new Vec(Double.NaN, 0, 0), 0));
    }
}
