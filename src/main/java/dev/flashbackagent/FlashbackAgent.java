package dev.flashbackagent;

import com.moulberry.flashback.Flashback;
import com.moulberry.flashback.combo_options.*;
import com.moulberry.flashback.exporting.*;
import com.moulberry.flashback.keyframe.impl.CameraKeyframe;
import com.moulberry.flashback.keyframe.impl.FOVKeyframe;
import com.moulberry.flashback.keyframe.interpolation.InterpolationType;
import com.moulberry.flashback.keyframe.types.CameraKeyframeType;
import com.moulberry.flashback.keyframe.types.FOVKeyframeType;
import com.moulberry.flashback.playback.ReplayServer;
import com.moulberry.flashback.state.*;
import com.moulberry.flashback.visuals.AccurateEntityPositionHandler;
import dev.flashbackagent.CameraPlanner.Pose;
import dev.flashbackagent.CameraPlanner.Vec;
import dev.flashbackagent.mixin.ExportJobAccessor;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.*;
import org.joml.Vector3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** All replay/world access is confined to the Minecraft client thread. */
public final class FlashbackAgent implements ClientModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("flashback-agent");
    private static FlashbackAgent instance;
    private enum Phase { IDLE, OPENING, SEEKING, EXPORTING }
    private volatile Phase phase = Phase.IDLE;
    private Path root;
    private volatile Path job;
    private JobSpec spec;
    private FileChannel lockChannel;
    private FileLock lock;
    private ScheduledExecutorService io;
    private volatile boolean cancel;
    private volatile Throwable asyncFailure;
    private volatile AgentExport export;
    private final Map<UUID, Map<String, Object>> players = new LinkedHashMap<>();
    private final List<Pose> poses = new ArrayList<>();
    private CameraPlanner planner;
    private CameraPlan customPlan;
    private final List<Map<String, Object>> samples = new ArrayList<>();
    private UUID target;
    private Vec lastFeet;
    private String dimension;
    private int sampleTick, stableTicks;
    private long deadline, nextScan;
    private boolean clientStarted;
    private int originalTick;
    private boolean originalPaused;
    private ReplayServer restoreServer;
    private ReplayServer openingPreviousServer;
    private boolean pendingRestore;
    private int collisionCorrections;
    private long lastExportProgress;
    private Path temporaryVideo;

    static boolean hasActiveJob() { return instance != null && instance.job != null; }

    @Override public void onInitializeClient() {
        if (BackgroundMode.enabled() && !"active".equals(System.getProperty("flashback.agent.guard.glfw"))) {
            // GLFW may load later; the Java agent enforces the native boundary before window creation.
            LOG.info("Background process requested; waiting for guarded GLFW initialization");
        }
        new RecordingTools().initialize();
        instance = this;
        root = FabricLoader.getInstance().getGameDir().resolve("flashback-agent");
        try {
            Files.createDirectories(root.resolve("jobs"));
            lockChannel = FileChannel.open(root.resolve("bridge.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
            lock = lockChannel.tryLock();
            if (lock == null) throw new IOException("Another bridge owns this profile");
            recoverInterruptedJobs();
        } catch (IOException e) { throw new IllegalStateException("Cannot initialize Flashback Agent inbox", e); }
        io = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "flashback-agent-status"); t.setDaemon(true); return t;
        });
        io.scheduleAtFixedRate(this::heartbeat, 0, 1, TimeUnit.SECONDS);
        ClientLifecycleEvents.CLIENT_STARTED.register(mc -> clientStarted = true);
        ClientLifecycleEvents.CLIENT_STOPPING.register(mc -> {
            io.shutdownNow();
            try { if (job != null) finish("failed", "Minecraft stopped before the job finished", Map.of()); }
            catch (Exception e) { LOG.error("Unable to record shutdown", e); }
            try { lock.release(); lockChannel.close(); } catch (IOException e) { LOG.error("Lock close failed", e); }
        });
        ClientTickEvents.END_CLIENT_TICK.register(this::tick);
    }

    private void recoverInterruptedJobs() throws IOException {
        try (var dirs = Files.list(root.resolve("jobs"))) {
            for (Path p : dirs.filter(Files::isDirectory).toList()) {
                if (!Files.exists(p.resolve("claimed"))) continue;
                Path statusFile = Files.exists(p.resolve("result.json")) ? p.resolve("result.json") : p.resolve("status.json");
                String state = Files.exists(statusFile)
                    ? JobFiles.read(statusFile).get("state").getAsString() : "unknown";
                if (!Set.of("completed", "failed", "cancelled").contains(state))
                    JobFiles.write(p.resolve("result.json"), Map.of("id", p.getFileName().toString(), "state", "failed",
                        "error", "Bridge restarted during this job; submit a new job"));
            }
        }
    }

    private void heartbeat() {
        try {
            JobFiles.write(root.resolve("bridge.json"), Map.of("schemaVersion", 2, "minecraft", Versions.minecraft(),
                "flashback", Versions.of("flashback"), "bridgeVersion", "0.4.0", "protocolVersion", 2, "updatedAt", System.currentTimeMillis(),
                "state", phase.name().toLowerCase(), "jobId", job == null ? "" : job.getFileName().toString()));
            Path active = job;
            if (active != null && Files.exists(active.resolve("cancel.json"))) cancel = true;
        } catch (Exception e) { LOG.error("Status I/O failed", e); }
    }

    private void tick(Minecraft mc) {
        if (!clientStarted || BackgroundMode.stopping()) return;
        try {
            if (pendingRestore && Flashback.EXPORT_JOB == null) {
                pendingRestore = false;
                if (Flashback.getReplayServer() == restoreServer && restoreServer != null) {
                    restoreServer.goToReplayTick(originalTick);
                    restoreServer.replayPaused = originalPaused;
                }
            }
            if (phase == Phase.IDLE) {
                if (System.nanoTime() < nextScan || Flashback.EXPORT_JOB != null || mc.gui.overlay() != null) return;
                nextScan = System.nanoTime() + 500_000_000L;
                scan(mc);
                return;
            }
            if (phase == Phase.EXPORTING) return; // Export runs its own nested client ticks.
            if (asyncFailure != null) throw new IllegalStateException("Could not open replay", asyncFailure);
            if (cancel) throw new CancellationException("Cancelled by CLI");
            if (System.nanoTime() > deadline) throw new IllegalStateException("Timed out while " + phase.name().toLowerCase());
            ReplayServer server = Flashback.getReplayServer();
            if (phase == Phase.OPENING) {
                // World opening is asynchronous. An already-open replay is not
                // the new request, even when it has the same duration/version.
                if (server == null || server == openingPreviousServer || mc.level == null || mc.player == null || mc.gui.overlay() != null) return;
                if (spec.endTick() > server.getTotalReplayTicks()) throw new IllegalArgumentException("Range exceeds replay duration");
                if (!Versions.minecraft().equals(server.getMetadata().versionString))
                    throw new IllegalArgumentException("Replay was recorded in Minecraft " + server.getMetadata().versionString
                        + "; this client runs " + Versions.minecraft());
                originalTick = server.getReplayTick(); originalPaused = server.replayPaused; restoreServer = server;
                sampleTick = spec.startTick();
                seek(server);
            } else if (phase == Phase.SEEKING) {
                if (server == null || mc.level == null || mc.player == null) throw new IllegalStateException("Replay was closed");
                if (server.getReplayTick() != sampleTick || server.jumpToTick >= 0 || server.fastForwarding || server.isProcessingSnapshot) {
                    stableTicks = 0; return;
                }
                if (++stableTicks < 3) return; // Allow the client packet queue to catch up after the server seek.
                sample(mc, server);
            }
        } catch (CancellationException e) { fail("cancelled", e); }
        catch (Exception e) { fail("failed", e); }
    }

    private void scan(Minecraft mc) throws IOException {
        try (var dirs = Files.list(root.resolve("jobs"))) {
            for (Path candidate : dirs.filter(Files::isDirectory).sorted().toList()) {
                if (!candidate.getFileName().toString().matches("[0-9a-f]{32}") ||
                    !Files.isRegularFile(candidate.resolve("request.json")) || Files.exists(candidate.resolve("claimed"))) continue;
                Files.createFile(candidate.resolve("claimed"));
                job = candidate; cancel = Files.exists(candidate.resolve("cancel.json")); asyncFailure = null;
                if (cancel) throw new CancellationException("Cancelled before execution");
                spec = JobSpec.load(job);
                if (mc.level != null && !Flashback.isInReplay())
                    throw new IllegalStateException("Leave the live world/server before submitting a render job");
                poses.clear(); players.clear(); samples.clear(); lastFeet = null; dimension = null; target = null; collisionCorrections = 0;
                customPlan = spec.plan() == null ? null : CameraPlan.parse(spec.plan(), spec.startTick(), spec.endTick());
                planner = spec.operation().equals("render") && customPlan == null ? new CameraPlanner(spec.distance(), spec.side(), spec.heightOffset()) : null;
                openingPreviousServer = Flashback.getReplayServer();
                phase = Phase.OPENING;
                deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(180);
                status("opening", Map.of());
                // Submit outside the client callback to avoid reentrant world-load code.
                JobSpec request = spec;
                Path activeJob = job;
                Thread.startVirtualThread(() -> mc.submit(() -> {
                    if (job != activeJob || cancel || phase != Phase.OPENING) return;
                    try { Flashback.openReplayWorld(Path.of(request.replay())); }
                    catch (Exception e) { if (job == activeJob) asyncFailure = e; }
                }));
                return;
            }
        }
    }

    private void seek(ReplayServer server) throws IOException {
        server.replayPaused = true;
        server.goToReplayTick(sampleTick);
        stableTicks = 0;
        phase = Phase.SEEKING;
        deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        status("sampling", Map.of("tick", sampleTick, "endTick", spec.endTick()));
    }

    private void sample(Minecraft mc, ReplayServer server) throws IOException {
        if (spec.operation().equals("render") && customPlan != null) {
            beginExport(mc, server);
            return;
        }
        List<? extends Player> visible = mc.level.players().stream()
            .filter(p -> ReplayIds.isRecordedPlayer(p.getId(), ReplayServer.REPLAY_VIEWER_IDS_START)).toList();
        for (Player p : visible) players.putIfAbsent(p.getUUID(), Map.of("uuid", p.getUUID().toString(), "name", p.getName().getString()));
        if (spec.operation().equals("sample")) {
            List<Map<String, Object>> entities = new ArrayList<>();
            for (Entity entity : mc.level.entitiesForRendering()) {
                if (entity instanceof Player && !ReplayIds.isRecordedPlayer(entity.getId(), ReplayServer.REPLAY_VIEWER_IDS_START)) continue;
                if (spec.target() != null && !spec.target().equalsIgnoreCase(entity.getUUID().toString()) && !spec.target().equals(entity.getName().getString())) continue;
                Vector3d recorded = AccurateEntityPositionHandler.getAccuratePosition(entity, 0);
                entities.add(Map.of("uuid", entity.getUUID().toString(), "name", entity.getName().getString(),
                    "type", BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString(), "player", entity instanceof Player,
                    "position", recorded == null ? List.of(entity.getX(), entity.getY(), entity.getZ()) : List.of(recorded.x, recorded.y, recorded.z),
                    "yaw", entity.getYRot(), "pitch", entity.getXRot(), "onGround", entity.onGround()));
            }
            samples.add(Map.of("tick", sampleTick, "dimension", mc.level.dimension().toString(), "entities", entities));
        }
        if (spec.operation().equals("render")) {
            if (target == null) {
                var matches = visible.stream().filter(p -> p.getUUID().toString().equalsIgnoreCase(spec.target())
                    || p.getName().getString().equals(spec.target())).toList();
                if (matches.size() != 1) throw new IllegalArgumentException("Target must match one recorded player at start tick. Available: " + players.values());
                target = matches.getFirst().getUUID();
            }
            Player player = visible.stream().filter(p -> p.getUUID().equals(target)).findFirst()
                .orElseThrow(() -> new IllegalStateException("Target not recorded at tick " + sampleTick));
            String here = mc.level.dimension().toString();
            // Read the recorded position at the tick boundary, not a render-dependent
            // interpolated entity pose. Fall back for captures without accurate packets.
            Vector3d accurate = AccurateEntityPositionHandler.getAccuratePosition(player, 0);
            Vec feet = accurate == null ? new Vec(player.getX(), player.getY(), player.getZ())
                : new Vec(accurate.x, accurate.y, accurate.z);
            if (dimension != null && !dimension.equals(here)) throw new IllegalStateException("Dimension change: split this range into separate clips");
            if (lastFeet != null && feet.subtract(lastFeet).length() > 12)
                throw new IllegalStateException("Teleport/discontinuity at tick " + sampleTick + "; split the range");
            dimension = here; lastFeet = feet;
            Pose pose = planner.sample(sampleTick, feet, player.getYRot());
            poses.add(avoidCollision(mc, player, pose));
        }
        if (sampleTick == spec.endTick()) {
            if (spec.operation().equals("players")) {
                finish("completed", null, Map.of("players", players.values(), "sampleIntervalTicks", 20));
            } else if (spec.operation().equals("sample")) {
                JobFiles.write(job.resolve("samples.json"), Map.of("samples", samples, "sampleIntervalTicks", spec.sampleIntervalTicks()));
                finish("completed", null, Map.of("samplesFile", job.resolve("samples.json").toString(), "sampleCount", samples.size()));
            } else beginExport(mc, server);
            return;
        }
        sampleTick = Math.min(spec.endTick(), sampleTick + (spec.operation().equals("players") ? 20 : spec.operation().equals("sample") ? spec.sampleIntervalTicks() : 2));
        seek(server);
    }

    private Pose avoidCollision(Minecraft mc, Player player, Pose pose) {
        Vec3 focus = vec(pose.focus()), desired = vec(pose.position());
        if (!mc.level.hasChunkAt(BlockPos.containing(desired))) throw new IllegalStateException("Camera leaves recorded chunks at tick " + sampleTick);
        BlockHitResult hit = mc.level.clip(new ClipContext(focus, desired, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, player));
        Vec3 corrected = desired;
        if (hit.getType() != HitResult.Type.MISS) {
            corrected = hit.getLocation().add(focus.subtract(desired).normalize().scale(.45));
            collisionCorrections++;
        }
        if (corrected.distanceTo(focus) < .8 || !mc.level.noCollision(player,
                new AABB(corrected.x-.18, corrected.y-.18, corrected.z-.18, corrected.x+.18, corrected.y+.18, corrected.z+.18)))
            throw new IllegalStateException("No clear camera position at tick " + sampleTick + "; try a shorter distance/side offset");
        return planner.corrected(pose, new Vec(corrected.x, corrected.y, corrected.z));
    }

    private void beginExport(Minecraft mc, ReplayServer server) throws IOException {
        if (Flashback.EXPORT_JOB != null) throw new IllegalStateException("Another export is already running");
        EditorState state = new EditorState(); // Dedicated snapshot: never overwrite the user's editor state.
        state.replayVisuals.renderNametags = false;
        state.replayVisuals.showHotbar = false;
        state.replayVisuals.showChat = false;
        state.replayVisuals.overrideFov = true;
        if (customPlan != null) {
            state.replayVisuals.renderNametags = customPlan.visuals().getOrDefault("nametags", false);
            state.replayVisuals.showHotbar = customPlan.visuals().getOrDefault("hotbar", false);
            state.replayVisuals.showChat = customPlan.visuals().getOrDefault("chat", false);
        }
        List<CameraPlan.Key> keys = customPlan == null ? poses.stream().map(p -> new CameraPlan.Key(p.tick(),
            new double[]{p.position().x(), p.position().y(), p.position().z()}, p.yaw(), p.pitch(), 0, p.fov(), "linear")).toList() : customPlan.camera();
        if (keys.size() == 1) {
            CameraPlan.Key k = keys.getFirst();
            keys = List.of(new CameraPlan.Key(spec.startTick(), k.position(), k.yaw(), k.pitch(), k.roll(), k.fov(), k.interpolation()),
                new CameraPlan.Key(spec.endTick(), k.position(), k.yaw(), k.pitch(), k.roll(), k.fov(), k.interpolation()));
        }
        long stamp = state.acquireWrite();
        try {
            EditorScene scene = state.getCurrentScene(stamp);
            KeyframeTrack camera = new KeyframeTrack(CameraKeyframeType.INSTANCE);
            KeyframeTrack fov = new KeyframeTrack(FOVKeyframeType.INSTANCE);
            for (CameraPlan.Key p : keys) {
                InterpolationType interpolation = InterpolationType.valueOf(p.interpolation().toUpperCase(Locale.ROOT));
                camera.keyframesByTick.put(p.tick(), new CameraKeyframe(new Vector3d(p.position()),
                    (float)p.yaw(), (float)p.pitch(), (float)p.roll(), interpolation));
                fov.keyframesByTick.put(p.tick(), new FOVKeyframe((float)p.fov(), interpolation));
            }
            scene.keyframeTracks.add(camera); scene.keyframeTracks.add(fov);
        } finally { state.release(stamp); }
        state.setExportTicks(spec.startTick(), spec.endTick(), server.getTotalReplayTicks());
        state.save(job.resolve("camera-state.json"));
        JobFiles.write(job.resolve("camera-plan.json"), customPlan == null
            ? Map.of("target", target, "poses", poses, "collisionCorrections", collisionCorrections) : spec.plan());
        Path output = Path.of(spec.output());
        if (Files.exists(output)) throw new FileAlreadyExistsException(output.toString());
        Files.createDirectories(output.getParent());
        temporaryVideo = output.resolveSibling("." + output.getFileName() + "." + spec.id() + ".partial.mp4");
        if (Files.exists(temporaryVideo)) throw new FileAlreadyExistsException(temporaryVideo.toString());
        String encoder = EncoderSelection.h264(VideoCodec.H264.getEncoders());
        LOG.info("Agent selected H.264 encoder {}", encoder);
        CameraPlan.Key first = keys.getFirst();
        ExportSettings settings = new ExportSettings(customPlan == null ? "Follow " + spec.target() : customPlan.name(), state,
            new Vec3(first.position()[0], first.position()[1], first.position()[2]), (float)first.yaw(), (float)first.pitch(), spec.width(), spec.height(), spec.startTick(), spec.endTick(),
            ExportProjection.PERSPECTIVE, 1, spec.fps(), true, false, VideoContainer.MP4, VideoCodec.H264, encoder,
            20_000_000, false, false, true, true, spec.audio() ? AudioCodec.AAC : null, temporaryVideo, null);
        mc.gui.setScreen(null);
        phase = Phase.EXPORTING;
        status("rendering", Map.of("output", spec.output(), "cameraPlan", job.resolve("camera-plan.json").toString()));
        export = new AgentExport(settings);
        Flashback.EXPORT_JOB = export;
    }

    private final class AgentExport extends ExportJob {
        AgentExport(ExportSettings settings) { super(settings); }
        @Override public void run() {
            try {
                if (cancel) throw new CancellationException("Cancelled before rendering");
                super.run();
                if (cancel) throw new CancellationException("Cancelled during rendering");
                int written = ((ExportJobAccessor)(Object)this).flashbackAgent$writtenFrames();
                int expected = expectedFrames();
                if (written != expected || !Files.isRegularFile(temporaryVideo) || Files.size(temporaryVideo) < 32)
                    throw new IllegalStateException("Incomplete export: " + written + "/" + expected + " frames");
                Files.move(temporaryVideo, Path.of(spec.output())); // No replacement of an existing output.
                finish("completed", null, Map.of("output", spec.output(), "frames", written,
                    "durationSeconds", written / (double)spec.fps(), "targetUuid", target == null ? "" : target.toString(),
                    "cameraState", job.resolve("camera-state.json").toString(),
                    "cameraPlan", job.resolve("camera-plan.json").toString(), "collisionCorrections", collisionCorrections));
            } catch (CancellationException e) { fail("cancelled", e); }
            catch (Exception e) { fail("failed", e); }
        }
    }

    public static boolean isExportCancellationRequested(ExportJob job) {
        FlashbackAgent agent = instance;
        return agent != null && agent.export == job && agent.cancel;
    }

    public static void updateExportProgress(ExportJob job) {
        FlashbackAgent agent = instance;
        if (agent != null && agent.export == job) {
            if (System.nanoTime() - agent.lastExportProgress > TimeUnit.SECONDS.toNanos(1)) {
                agent.lastExportProgress = System.nanoTime();
                try { agent.status("rendering", Map.of("frames", ((ExportJobAccessor)(Object)job).flashbackAgent$writtenFrames(),
                    "expectedFrames", agent.expectedFrames())); }
                catch (IOException e) { LOG.warn("Cannot publish render progress", e); }
            }
        }
    }

    /** Version-pinned adapter for the private Flashback TickInfo record. Normal GUI exports are untouched. */
    public static List<?> frameSchedule(EditorState state, int start, int end, double fps) {
        FlashbackAgent agent = instance;
        if (agent == null || agent.export == null || agent.export.getSettings().editorState() != state) return null;
        try {
            var constructor = Class.forName("com.moulberry.flashback.exporting.ExportJob$TickInfo")
                .getDeclaredConstructor(double.class, double.class, boolean.class);
            constructor.setAccessible(true);
            List<Object> result = new ArrayList<>();
            for (double tick : FrameSchedule.atSpeed(end - start, (int)fps, agent.customPlan == null ? 1 : agent.customPlan.speed()))
                result.add(constructor.newInstance(tick, tick, false));
            return result;
        } catch (ReflectiveOperationException e) { throw new IllegalStateException("Flashback TickInfo compatibility mismatch", e); }
    }

    private int expectedFrames() {
        return (int)Math.ceil((spec.endTick() - spec.startTick()) * (double)spec.fps() / (20 * (customPlan == null ? 1 : customPlan.speed())));
    }

    private void status(String state, Map<String, ?> extra) throws IOException {
        Map<String, Object> value = new LinkedHashMap<>(extra);
        value.put("id", job.getFileName().toString()); value.put("state", state); value.put("updatedAt", System.currentTimeMillis());
        JobFiles.write(job.resolve("status.json"), value);
    }

    private void finish(String state, String error, Map<String, ?> extra) throws IOException {
        Map<String, Object> result = new LinkedHashMap<>(extra);
        if (error != null) result.put("error", error);
        result.put("id", job.getFileName().toString()); result.put("state", state); result.put("updatedAt", System.currentTimeMillis());
        JobFiles.write(job.resolve("result.json"), result);
        try { status(state, result); } catch (IOException e) { LOG.warn("Terminal result saved; progress refresh failed", e); }
        if (temporaryVideo != null) { Files.deleteIfExists(temporaryVideo); temporaryVideo = null; }
        pendingRestore = true;
        phase = Phase.IDLE; job = null; export = null; cancel = false;
    }

    private void fail(String state, Exception e) {
        LOG.error("Agent job {}", state, e);
        try { if (job != null) finish(state, e.getMessage() == null ? e.toString() : e.getMessage(), Map.of()); }
        catch (IOException ioError) { LOG.error("Could not write terminal job status", ioError); phase = Phase.IDLE; job = null; }
    }

    private static Vec3 vec(Vec v) { return new Vec3(v.x(), v.y(), v.z()); }
}
