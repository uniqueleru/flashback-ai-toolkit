package dev.flashbackagent;

import com.google.gson.JsonObject;
import com.moulberry.flashback.Flashback;
import com.moulberry.flashback.record.Recorder;
import com.moulberry.flashback.record.ReplayExporter;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.zip.ZipFile;

/** Recording and explicit world lifecycle, separate from replay rendering jobs. */
final class RecordingTools {
    private final Path gameDir=FabricLoader.getInstance().getGameDir();
    private ToolInbox inbox;
    private Recorder owned;
    private String recordingId;
    private CompletableFuture<Map<String,Object>> opening;
    private long openDeadline;
    private volatile boolean exportingRecording;

    void initialize() {
        ClientLifecycleEvents.CLIENT_STARTED.register(mc -> {
            try { inbox=new ToolInbox(gameDir.resolve("flashback-agent/live"),Versions.minecraft(),(tool,args)-> {
                CompletableFuture<Map<String,Object>> future=new CompletableFuture<>();
                mc.execute(()-> {
                    try { Map<String,Object> result=call(mc,tool,args,future); if(result!=null) future.complete(result); }
                    catch(Exception e) { future.completeExceptionally(e); }
                });
                return future;
            }); } catch(Exception e) { throw new IllegalStateException("Cannot initialize recording tools",e); }
        });
        ClientLifecycleEvents.CLIENT_STOPPING.register(mc->{ if(inbox!=null) inbox.close(); });
        ClientTickEvents.END_CLIENT_TICK.register(mc->{
            if(opening==null) return;
            if(mc.level!=null && mc.player!=null && mc.gui.overlay()==null) {
                opening.complete(status(mc)); opening=null;
            } else if(System.nanoTime()>openDeadline) {
                opening.completeExceptionally(new IllegalStateException("World not ready; inspect Minecraft for a load/registry prompt before retrying")); opening=null;
            }
        });
    }
    private Map<String,Object> status(Minecraft mc) {
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("inWorld",mc.level!=null); out.put("inReplay",Flashback.isInReplay()); out.put("paused",mc.isPaused());
        out.put("recording",Flashback.RECORDER!=null); out.put("owned",owned!=null && owned==Flashback.RECORDER);
        out.put("exportingRecording",exportingRecording);
        out.put("background",BackgroundMode.status(mc));
        out.put("screen",mc.gui.screen()==null ? "" : mc.gui.screen().getClass().getName());
        if(owned!=null && owned==Flashback.RECORDER) out.put("recordingId",recordingId);
        if(Flashback.RECORDER!=null) out.put("recordingPaused",Flashback.RECORDER.isPaused());
        if(mc.player!=null) out.put("observer",Map.of("name",mc.player.getName().getString(),"position",List.of(mc.player.getX(),mc.player.getY(),mc.player.getZ()),"dimension",mc.player.level().dimension().identifier().toString()));
        if(mc.level!=null) out.put("visiblePlayers",mc.level.players().stream().map(p->{
            var info=mc.getConnection()==null?null:mc.getConnection().getPlayerInfo(p.getUUID());
            return Map.of("name",p.getName().getString(),"uuid",p.getUUID().toString(),"position",List.of(p.getX(),p.getY(),p.getZ()),
                "invisible",p.isInvisible(),"spectator",p.isSpectator(),"gameMode",info==null?"unknown":info.getGameMode().getName());
        }).toList());
        return out;
    }
    private Map<String,Object> call(Minecraft mc,String tool,JsonObject j,CompletableFuture<Map<String,Object>> future) throws Exception {
        if(BackgroundMode.stopping() && !tool.equals("record_status")) throw new IllegalStateException("Background worker is stopping");
        switch(tool) {
            case "record_status" -> { new ToolArgs(j); return status(mc); }
            case "runtime_shutdown" -> {
                ToolArgs a=new ToolArgs(j,"launchId");
                if(!BackgroundMode.enabled() || !a.text("launchId").equals(System.getProperty("flashback.agent.launchId", "")))
                    throw new IllegalStateException("Only the matching managed background process can be stopped");
                if(Flashback.RECORDER!=null || exportingRecording || Flashback.EXPORT_JOB!=null || FlashbackAgent.hasActiveJob() || opening!=null)
                    throw new IllegalStateException("Finish the active recording, export or world load before stopping");
                BackgroundMode.requestStop();
                CompletableFuture.delayedExecutor(1,TimeUnit.SECONDS).execute(()->mc.execute(mc::stop));
                return Map.of("stopping",true,"launchId",a.text("launchId"));
            }
            case "world_open" -> {
                ToolArgs a=new ToolArgs(j,"save");
                if(mc.level!=null || Flashback.EXPORT_JOB!=null || FlashbackAgent.hasActiveJob() || opening!=null) throw new IllegalStateException("Client already has a world or replay job; close it explicitly first");
                Path saves=gameDir.resolve("saves").toRealPath(), save=saves.resolve(a.text("save")).toRealPath();
                if(!save.getParent().equals(saves)||!Files.isRegularFile(save.resolve("level.dat"))) throw new IllegalArgumentException("save must name an existing direct child of the profile saves folder");
                opening=future; openDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(120);
                mc.createWorldOpenFlows().openWorld(save.getFileName().toString(),()->{
                    if(opening!=null) opening.completeExceptionally(new IllegalStateException("World opening was cancelled")); opening=null;
                });
                return null;
            }
            case "world_close" -> {
                new ToolArgs(j);
                if(Flashback.RECORDER!=null||Flashback.EXPORT_JOB!=null||FlashbackAgent.hasActiveJob()) throw new IllegalStateException("Finish recording/replay job before closing the world");
                mc.disconnectWithSavingScreen(); mc.gui.setScreen(new TitleScreen());
                return status(mc);
            }
            case "record_start" -> {
                new ToolArgs(j);
                if(mc.level==null||mc.player==null||Flashback.isInReplay()||Flashback.EXPORT_JOB!=null) throw new IllegalStateException("Join a live world before recording");
                if(Flashback.RECORDER!=null) throw new IllegalStateException("A recording already exists; tool will not take ownership of it");
                Flashback.startRecordingReplay();
                if(Flashback.RECORDER==null) throw new IllegalStateException("Flashback refused recording; inspect incompatible-mod warning");
                owned=Flashback.RECORDER; recordingId=UUID.randomUUID().toString();
                return status(mc);
            }
            case "record_stop" -> {
                ToolArgs a=new ToolArgs(j,"recordingId","output"); requireOwned(a);
                Path output=Path.of(a.text("output")).toAbsolutePath().normalize();
                if(!output.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".zip")||Files.exists(output)) throw new IllegalArgumentException("Use a new .zip output path");
                Files.createDirectories(output.getParent());
                Recorder recorder=owned; Flashback.RECORDER=null; owned=null;
                recorder.endTickWithContext(true);
                Path raw=recorder.finish();
                String id=recordingId; recordingId=null;
                exportingRecording=true;
                Thread.startVirtualThread(()-> {
                    Path temp=output.resolveSibling(output.getFileName()+"."+UUID.randomUUID()+".partial.zip");
                    try {
                        // Native exporter can log-and-return on failure; verify the archive before publication.
                        ReplayExporter.export(raw,temp,null);
                        int ticks;
                        try(ZipFile zip=new ZipFile(temp.toFile())) {
                            var entry=zip.getEntry("metadata.json");
                            if(entry==null||entry.getSize()>1048576) throw new IllegalStateException("Missing replay metadata");
                            var meta=JobFiles.GSON.fromJson(new String(zip.getInputStream(entry).readAllBytes(),java.nio.charset.StandardCharsets.UTF_8),JsonObject.class);
                            ticks=meta.get("total_ticks").getAsInt();
                            if(ticks<=0 || !meta.has("chunks") || meta.getAsJsonObject("chunks").isEmpty()) throw new IllegalStateException("Recording contains no ticks/chunks");
                            for(String name:meta.getAsJsonObject("chunks").keySet()) if(zip.getEntry(name)==null) throw new IllegalStateException("Missing replay chunk: "+name);
                        }
                        Files.createLink(output,temp); Files.delete(temp);
                        future.complete(Map.of("output",output.toString(),"recordingId",id,"totalTicks",ticks,"durationSeconds",ticks/20.0));
                    } catch(Exception e) {
                        future.completeExceptionally(new IllegalStateException("Recording stopped but export failed: "+e.getMessage()+". Recovery paths: "+raw+" ; "+temp,e));
                    } finally { exportingRecording=false; }
                });
                return null;
            }
            default -> throw new IllegalArgumentException("Unknown recording tool: "+tool);
        }
    }
    private void requireOwned(ToolArgs a) {
        if(owned==null||owned!=Flashback.RECORDER||!Objects.equals(recordingId,a.text("recordingId")))
            throw new IllegalStateException("recordingId does not identify this tool's active recording");
    }
}
