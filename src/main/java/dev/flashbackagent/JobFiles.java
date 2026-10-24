package dev.flashbackagent;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.*;
import java.util.UUID;

final class JobFiles {
    static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    static JsonObject read(Path path) throws IOException {
        if (Files.size(path) > 1024 * 1024) throw new IOException("Job JSON exceeds 1 MiB");
        return GSON.fromJson(Files.readString(path), JsonObject.class);
    }
    static void write(Path path, Object value) throws IOException {
        Path temporary = path.resolveSibling(path.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try {
            Files.writeString(temporary, GSON.toJson(value), StandardOpenOption.CREATE_NEW);
            // Python/antivirus readers on Windows can briefly omit FILE_SHARE_DELETE.
            // Keep the previous complete JSON visible and retry the atomic replacement.
            for (int attempt = 0; ; attempt++) {
                try {
                    try { Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
                    catch (AtomicMoveNotSupportedException e) { Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING); }
                    break;
                } catch (AccessDeniedException e) {
                    if (attempt >= 19) throw e;
                    try { Thread.sleep(25); }
                    catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IOException("Interrupted writing job status", interrupted); }
                }
            }
        } finally { Files.deleteIfExists(temporary); }
    }
}
