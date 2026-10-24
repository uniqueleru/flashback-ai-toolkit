package dev.flashbackagent;

final class FrameSchedule {
    static double[] normalSpeed(int durationTicks, int fps) {
        return atSpeed(durationTicks, fps, 1);
    }
    static double[] atSpeed(int durationTicks, int fps, double speed) {
        if (durationTicks <= 0 || (fps != 24 && fps != 30 && fps != 60)) throw new IllegalArgumentException("Invalid frame schedule");
        if (!Double.isFinite(speed) || speed < .1 || speed > 8) throw new IllegalArgumentException("Invalid playback speed");
        double total = Math.ceil(durationTicks * (double)fps / (20 * speed));
        if (total > Integer.MAX_VALUE) throw new IllegalArgumentException("Frame schedule too large");
        int count = (int)total;
        double[] ticks = new double[count];
        for (int i = 0; i < count; i++) ticks[i] = i * 20.0 * speed / fps;
        return ticks;
    }
}
