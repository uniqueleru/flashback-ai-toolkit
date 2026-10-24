package dev.flashbackagent;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class JobSpecTest {
    @TempDir Path temp;
    @Test void entityQueryAcceptsAnExplicitNullCameraPlan() throws Exception {
        Path replay = Files.createFile(temp.resolve("replay.zip"));
        Path job = Files.createDirectory(temp.resolve("0123456789abcdef0123456789abcdef"));
        var json = new com.google.gson.JsonObject();
        json.addProperty("schemaVersion", 2); json.addProperty("id", job.getFileName().toString());
        json.addProperty("operation", "sample"); json.addProperty("replay", replay.toString());
        json.addProperty("startTick", 20); json.addProperty("endTick", 60); json.addProperty("sampleIntervalTicks", 10);
        json.add("plan", com.google.gson.JsonNull.INSTANCE);
        Files.writeString(job.resolve("request.json"), json.toString());
        assertNull(JobSpec.load(job).plan());
    }
}
