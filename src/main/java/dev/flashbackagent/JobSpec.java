package dev.flashbackagent;

import java.nio.file.*;
import java.io.IOException;
import java.util.Set;
import com.google.gson.JsonObject;

record JobSpec(int schemaVersion, String id, String operation, String replay, int startTick, int endTick,
               String target, String output, int width, int height, int fps,
               double distance, double side, double heightOffset, boolean audio,
               JsonObject plan, int sampleIntervalTicks) {
    static JobSpec load(Path job) throws IOException {
        JsonObject request = JobFiles.read(job.resolve("request.json"));
        if (request.has("plan") && request.get("plan").isJsonNull()) request.remove("plan");
        JobSpec s = JobFiles.GSON.fromJson(request, JobSpec.class);
        if (s == null || (s.schemaVersion != 1 && s.schemaVersion != 2) || !job.getFileName().toString().equals(s.id))
            throw new IllegalArgumentException("Invalid job schema or ID");
        if (!Set.of("render", "players", "sample").contains(s.operation)) throw new IllegalArgumentException("Unknown operation");
        if (s.startTick < 0 || s.endTick <= s.startTick) throw new IllegalArgumentException("Invalid tick range");
        if (s.replay == null || !Path.of(s.replay).isAbsolute() || !Files.isRegularFile(Path.of(s.replay)))
            throw new IllegalArgumentException("Replay must be an absolute file path");
        if (s.operation.equals("render")) {
            if (s.plan == null && (s.target == null || s.target.isBlank())) throw new IllegalArgumentException("Camera plan or follow target required");
            if (s.plan != null) {
                if (s.target != null) throw new IllegalArgumentException("A camera plan does not take a follow target");
                CameraPlan.parse(s.plan, s.startTick, s.endTick);
            }
            if (s.output == null || !Path.of(s.output).isAbsolute() || !s.output.toLowerCase().endsWith(".mp4"))
                throw new IllegalArgumentException("Absolute MP4 output required");
            if (Files.exists(Path.of(s.output))) throw new FileAlreadyExistsException(s.output);
            if (s.width < 64 || s.width > 4096 || s.width % 2 != 0 || s.height < 64 || s.height > 4096 || s.height % 2 != 0)
                throw new IllegalArgumentException("Invalid resolution");
            if (!Set.of(24, 30, 60).contains(s.fps)) throw new IllegalArgumentException("Invalid FPS");
            if (s.plan == null) { bounded(s.distance, 2, 16); bounded(s.side, -8, 8); bounded(s.heightOffset, .5, 10); }
        }
        if (s.operation.equals("sample") && (s.sampleIntervalTicks < 1 || s.sampleIntervalTicks > 200))
            throw new IllegalArgumentException("Sample interval must be 1..200 ticks");
        return s;
    }
    private static void bounded(double value, double min, double max) {
        if (!Double.isFinite(value) || value < min || value > max) throw new IllegalArgumentException("Invalid camera settings");
    }
}
