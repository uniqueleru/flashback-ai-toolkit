package dev.flashbackagent;

import com.google.gson.JsonObject;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import org.slf4j.LoggerFactory;

/** File I/O is off the game thread; dispatchers marshal world access themselves. */
final class ToolInbox implements AutoCloseable {
    interface Handler { CompletableFuture<Map<String,Object>> call(String tool, JsonObject arguments); }
    private final Path root;
    private final String minecraft;
    private final String session = UUID.randomUUID().toString();
    private final ScheduledExecutorService io;
    private final FileChannel channel;
    private final FileLock lock;
    private final Handler handler;
    private volatile CompletableFuture<Map<String,Object>> pending;
    private Path active;
    private volatile boolean closed;

    ToolInbox(Path root, String minecraft, Handler handler) throws Exception {
        this.root = root; this.minecraft = minecraft; this.handler = handler;
        Files.createDirectories(root.resolve("jobs"));
        channel = FileChannel.open(root.resolve("bridge.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        lock = channel.tryLock();
        if (lock == null) { channel.close(); throw new IllegalStateException("Tool inbox already in use: " + root); }
        try (var jobs = Files.list(root.resolve("jobs"))) {
            for (Path p : jobs.filter(Files::isDirectory).toList()) {
                if (Files.exists(p.resolve("claimed")) && !Files.exists(p.resolve("result.json")))
                    writeResult(p, "failed", Map.of("error", "Bridge restarted; previous action may have executed. Inspect world before retrying."));
            }
        }
        io = Executors.newSingleThreadScheduledExecutor(r -> { Thread t=new Thread(r,"agent-tool-inbox"); t.setDaemon(true); return t; });
        io.scheduleWithFixedDelay(this::poll, 0, 100, TimeUnit.MILLISECONDS);
    }
    private void writeResult(Path dir, String state, Map<String,Object> data) throws Exception {
        Map<String,Object> out = new LinkedHashMap<>(data);
        out.put("id",dir.getFileName().toString()); out.put("state",state);
        JobFiles.write(dir.resolve("result.json"),out);
    }
    private void poll() {
        if (closed) return;
        try {
            JobFiles.write(root.resolve("bridge.json"), Map.of("protocolVersion",1,"bridgeVersion","0.4.0",
                "minecraft",minecraft,"session",session,"updatedAt",System.currentTimeMillis(),"state",pending==null?"ready":"busy"));
            if (pending != null) {
                if (!pending.isDone()) return;
                try { writeResult(active,"completed",Map.of("result",pending.join())); }
                catch (CompletionException e) { writeResult(active,"failed",Map.of("error",String.valueOf(e.getCause().getMessage()))); }
                pending=null; active=null;
            }
            try (var dirs=Files.list(root.resolve("jobs"))) {
                for (Path p : dirs.filter(Files::isDirectory).sorted().toList()) {
                    if (!p.getFileName().toString().matches("[0-9a-f]{32}") || !Files.isRegularFile(p.resolve("request.json")) || Files.exists(p.resolve("claimed"))) continue;
                    Files.createFile(p.resolve("claimed"));
                    try {
                        JsonObject request=JobFiles.read(p.resolve("request.json"));
                        if (!session.equals(request.get("session").getAsString())) throw new IllegalArgumentException("Stale server session; inspect current world before resubmitting");
                        if (request.get("expiresAt").getAsLong() < System.currentTimeMillis()) throw new IllegalArgumentException("Request expired before execution");
                        if (Files.exists(p.resolve("cancel.json"))) { writeResult(p,"cancelled",Map.of()); continue; }
                        active=p;
                        JobFiles.write(p.resolve("status.json"),Map.of("id",p.getFileName().toString(),"state","running"));
                        pending=handler.call(request.get("tool").getAsString(),request.getAsJsonObject("arguments"));
                    } catch (Exception e) { writeResult(p,"failed",Map.of("error",String.valueOf(e.getMessage()))); active=null; pending=null; }
                    return;
                }
            }
        } catch (Exception e) { LoggerFactory.getLogger("agent-tools").error("Tool inbox I/O failed",e); }
    }
    @Override public void close() {
        shutdown();
    }
    void shutdown() {
        closed=true;
        io.execute(() -> {
            try {
                if (active != null) writeResult(active,"failed",Map.of("error","World/client closed; inspect state before retrying"));
                JobFiles.write(root.resolve("bridge.json"),Map.of("state","stopped","updatedAt",0));
                lock.release(); channel.close();
            } catch(Exception e) { LoggerFactory.getLogger("agent-tools").error("Closing inbox",e); }
        });
        io.shutdown();
    }
}
