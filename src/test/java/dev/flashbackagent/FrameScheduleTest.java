package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FrameScheduleTest {
    @Test void retimingChangesOutputLengthWithoutChangingSourceRange() {
        double[] fast = FrameSchedule.atSpeed(40, 30, 2);
        double[] slow = FrameSchedule.atSpeed(40, 30, .5);
        assertEquals(30, fast.length);
        assertEquals(120, slow.length);
        assertEquals(40.0/30, fast[1]);
        assertTrue(slow[119] < 40);
        assertThrows(IllegalArgumentException.class, () -> FrameSchedule.atSpeed(40, 30, 0));
    }
    @Test void twoSecondsAtThirtyFpsIsSixtyMonotonicFrames() {
        double[] ticks = FrameSchedule.normalSpeed(40, 30);
        assertEquals(60, ticks.length);
        assertEquals(0, ticks[0]);
        for (int i = 1; i < ticks.length; i++) {
            assertTrue(ticks[i] > ticks[i-1]);
            assertTrue(ticks[i] < 40);
            assertEquals(20.0 / 30, ticks[i] - ticks[i-1], 1e-10);
        }
    }
    @Test void supportedFrameRatesAndSubsecondIntervalsStayWithinSourceRange() {
        for (int fps : new int[]{24,30,60}) for (int duration : new int[]{1,20,223,2400}) {
            double[] ticks = FrameSchedule.normalSpeed(duration, fps);
            assertEquals((int)Math.ceil(duration * fps / 20.0), ticks.length);
            assertTrue(ticks[ticks.length-1] < duration);
        }
    }
}
