package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
import java.nio.file.*;
import java.nio.channels.FileChannel;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class JobFilesTest {
    @TempDir Path root;
    @Test @EnabledOnOs(OS.WINDOWS)
    void statusUpdateSurvivesShortLivedWindowsReaderLock() throws Exception {
        Path status = root.resolve("status.json");
        JobFiles.write(status, Map.of("state", "sampling"));
        var reader = FileChannel.open(status, StandardOpenOption.READ, com.sun.nio.file.ExtendedOpenOption.NOSHARE_DELETE);
        Thread release = Thread.startVirtualThread(() -> {
            try { Thread.sleep(150); reader.close(); } catch (Exception e) { throw new RuntimeException(e); }
        });
        try {
            JobFiles.write(status, Map.of("state", "completed"));
            assertEquals("completed", JobFiles.read(status).get("state").getAsString());
        } finally { release.join(); reader.close(); }
    }
}
