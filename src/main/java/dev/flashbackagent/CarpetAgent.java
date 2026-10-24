package dev.flashbackagent;

import carpet.fakes.ServerPlayerInterface;
import carpet.helpers.EntityPlayerActionPack;
import carpet.helpers.EntityPlayerActionPack.Action;
import carpet.helpers.EntityPlayerActionPack.ActionType;
import carpet.patches.EntityPlayerMPFake;
import com.google.gson.JsonObject;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.commands.CommandSource;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.util.concurrent.*;

/** All Carpet and world access occurs on the authoritative server thread. */
public final class CarpetAgent implements ModInitializer {
    private ToolInbox inbox;
    private final Map<UUID,Map<String,Lease>> leases=new HashMap<>();
    private record Lease(int until, Runnable stop) {}
    private record Spawn(String name, long deadline, CompletableFuture<Map<String,Object>> future) {}
    private Spawn spawning;

    @Override public void onInitialize() {
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            // Flashback's replay server is not a live world and must never get bots.
            if (server.getClass().getName().startsWith("com.moulberry.flashback.")) return;
            try {
                inbox=new ToolInbox(FabricLoader.getInstance().getGameDir().resolve("carpet-agent"),Versions.minecraft(),(tool,args)-> {
                    CompletableFuture<Map<String,Object>> future=new CompletableFuture<>();
                    server.execute(() -> {
                        try {
                            Map<String,Object> result=call(server,tool,args,future);
                            if (result!=null) future.complete(result);
                        } catch(Exception e) { future.completeExceptionally(e); }
                    });
                    return future;
                });
            } catch(Exception e) { throw new IllegalStateException("Cannot open Carpet tools",e); }
        });
        ServerTickEvents.END_SERVER_TICK.register(this::tick);
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            if(inbox==null) return;
            for (ServerPlayer p:server.getPlayerList().getPlayers())
                if(p instanceof EntityPlayerMPFake && leases.containsKey(p.getUUID())) pack(p).stopAll();
            leases.clear();
            if(spawning!=null) spawning.future.completeExceptionally(new IllegalStateException("Server stopped during spawn"));
            spawning=null; inbox.close(); inbox=null;
        });
    }
    private void tick(MinecraftServer server) {
        if(inbox==null) return;
        int tick=server.getTickCount();
        for(var it=leases.entrySet().iterator();it.hasNext();) {
            var entry=it.next();
            if(server.getPlayerList().getPlayer(entry.getKey())==null) { it.remove(); continue; }
            entry.getValue().entrySet().removeIf(e -> {
                if(tick>=e.getValue().until) { e.getValue().stop.run(); return true; }
                return false;
            });
            if(entry.getValue().isEmpty()) it.remove();
        }
        if(spawning!=null) {
            ServerPlayer p=server.getPlayerList().getPlayerByName(spawning.name);
            if(p!=null) {
                if(p instanceof EntityPlayerMPFake) {
                    // Carpet loads saved data after placeNewPlayer. If the saved
                    // mode already equals the requested mode, changeGameMode is
                    // a no-op and observers can retain the initial server mode.
                    // Refresh vanilla effect/spectator visibility as well; do
                    // not blindly clear invisibility effects from saved actors.
                    p.onUpdateAbilities();
                    server.getPlayerList().broadcastAll(new ClientboundPlayerInfoUpdatePacket(ClientboundPlayerInfoUpdatePacket.Action.UPDATE_GAME_MODE,p));
                    spawning.future.complete(state(server,p));
                }
                else spawning.future.completeExceptionally(new IllegalStateException("Name joined as a real player; no control applied"));
                spawning=null;
            } else if(System.nanoTime()>spawning.deadline) {
                spawning.future.completeExceptionally(new IllegalStateException("Spawn not observed within 60s; inspect before retrying")); spawning=null;
            }
        }
    }
    private static EntityPlayerActionPack pack(ServerPlayer p) { return ((ServerPlayerInterface)p).getActionPack(); }
    private static ServerPlayer bot(MinecraftServer server, ToolArgs a) {
        ServerPlayer p=server.getPlayerList().getPlayerByName(a.name());
        if(!(p instanceof EntityPlayerMPFake)) throw new IllegalArgumentException("Not a live Carpet fake player: "+a.name());
        return p;
    }
    private void lease(MinecraftServer s,ServerPlayer p,String channel,int ticks,Runnable stop) {
        leases.computeIfAbsent(p.getUUID(),k->new HashMap<>()).put(channel,new Lease(s.getTickCount()+ticks,stop));
    }
    private void clearLease(ServerPlayer p,String channel) {
        var map=leases.get(p.getUUID()); if(map!=null) map.remove(channel);
    }
    private Map<String,Object> state(MinecraftServer server,ServerPlayer p) {
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("name",p.getName().getString()); out.put("uuid",p.getUUID().toString());
        out.put("fake",p instanceof EntityPlayerMPFake); out.put("position",List.of(p.getX(),p.getY(),p.getZ()));
        out.put("yaw",p.getYRot()); out.put("pitch",p.getXRot());
        out.put("dimension",p.level().dimension().identifier().toString());
        out.put("onGround",p.onGround()); out.put("health",p.getHealth()); out.put("gameMode",p.gameMode.getGameModeForPlayer().getName());
        out.put("invisible",p.isInvisible());
        out.put("sprinting",p.isSprinting()); out.put("sneaking",p.isShiftKeyDown()); out.put("serverTick",server.getTickCount());
        Map<String,Integer> remaining=new LinkedHashMap<>();
        leases.getOrDefault(p.getUUID(),Map.of()).forEach((k,v)->remaining.put(k,Math.max(0,v.until-server.getTickCount())));
        out.put("controlsRemainingTicks",remaining);
        return out;
    }
    private Map<String,Object> call(MinecraftServer s,String tool,JsonObject j,CompletableFuture<Map<String,Object>> future) throws Exception {
        if(tool.equals("carpet_list")) {
            new ToolArgs(j);
            return Map.of("players",s.getPlayerList().getPlayers().stream().map(p->state(s,p)).toList(),"serverTick",s.getTickCount(),
                "transport","local-file-inbox","navigation",false,"worldDirectory",s.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString());
        }
        if(tool.equals("carpet_spawn")) {
            ToolArgs a=new ToolArgs(j,"name","position","yaw","pitch","dimension","gameMode");
            String name=a.name(); double[] pos=a.vector("position");
            double yaw=a.has("yaw")?a.number("yaw",-360000,360000):0, pitch=a.has("pitch")?a.number("pitch",-90,90):0;
            String dim=a.has("dimension")?a.text("dimension"):"minecraft:overworld";
            if(!dim.matches("[a-z0-9_.-]+:[a-z0-9_./-]+")) throw new IllegalArgumentException("Invalid dimension");
            String mode=a.has("gameMode")?a.choice("gameMode","creative","survival","adventure","spectator"):"creative";
            if(s.getPlayerList().getPlayerByName(name)!=null) throw new IllegalArgumentException("Name already online");
            Map<String,Object> response=command(s,"player "+name+" spawn at "+pos[0]+" "+pos[1]+" "+pos[2]+" facing "+yaw+" "+pitch+" in "+dim+" in "+mode);
            if(((Number)response.get("value")).intValue()==0) throw new IllegalStateException("Carpet rejected spawn: "+response.get("messages"));
            spawning=new Spawn(name,System.nanoTime()+TimeUnit.SECONDS.toNanos(60),future);
            return null;
        }
        if(tool.equals("carpet_command")) {
            ToolArgs a=new ToolArgs(j,"command"); return command(s,a.text("command"));
        }
        ToolArgs a;
        switch(tool) {
            case "carpet_state", "carpet_stop", "carpet_remove", "carpet_inventory" -> a=new ToolArgs(j,"name");
            case "carpet_move" -> a=new ToolArgs(j,"name","forward","strafe","sprint","sneak","ticks");
            case "carpet_look" -> a=new ToolArgs(j,"name","yaw","pitch","at");
            case "carpet_action" -> a=new ToolArgs(j,"name","action","mode","interval","ticks");
            case "carpet_hotbar" -> a=new ToolArgs(j,"name","slot");
            case "carpet_mount" -> a=new ToolArgs(j,"name","dismount");
            case "carpet_teleport" -> a=new ToolArgs(j,"name","position");
            case "carpet_observe" -> a=new ToolArgs(j,"name","radius");
            default -> throw new IllegalArgumentException("Unknown Carpet tool: "+tool);
        }
        ServerPlayer p=bot(s,a); EntityPlayerActionPack ap=pack(p);
        switch(tool) {
            case "carpet_state" -> {}
            case "carpet_move" -> {
                int ticks=a.integer("ticks",1,12000);
                if(!a.has("forward")&&!a.has("strafe")) throw new IllegalArgumentException("Specify forward or strafe");
                float f=(float)(a.has("forward")?a.number("forward",-1,1):0), strafe=(float)(a.has("strafe")?a.number("strafe",-1,1):0);
                boolean sprint=a.has("sprint")&&a.bool("sprint"), sneak=a.has("sneak")&&a.bool("sneak");
                if(sprint&&sneak) throw new IllegalArgumentException("Cannot sprint and sneak together");
                ap.stopMovement(); ap.setForward(f); ap.setStrafing(strafe); ap.setSprinting(sprint); ap.setSneaking(sneak);
                lease(s,p,"move",ticks,ap::stopMovement);
            }
            case "carpet_look" -> {
                if(a.has("at")) {
                    if(a.has("yaw")||a.has("pitch")) throw new IllegalArgumentException("Use at OR yaw/pitch");
                    double[] v=a.vector("at"); ap.lookAt(new Vec3(v[0],v[1],v[2]));
                } else ap.look((float)a.number("yaw",-360000,360000),(float)a.number("pitch",-90,90));
            }
            case "carpet_action" -> {
                String name=a.choice("action","use","attack","jump","drop","dropStack","swapHands");
                ActionType type=switch(name) { case "drop"->ActionType.DROP_ITEM; case "dropStack"->ActionType.DROP_STACK; case "swapHands"->ActionType.SWAP_HANDS; default->ActionType.valueOf(name.toUpperCase(Locale.ROOT)); };
                String mode=a.choice("mode","once","continuous","interval","stop");
                if(!mode.equals("interval")&&a.has("interval")) throw new IllegalArgumentException("interval only applies to interval mode");
                if((mode.equals("once")||mode.equals("stop"))&&a.has("ticks")) throw new IllegalArgumentException("ticks only applies to ongoing actions");
                int ticks=(mode.equals("continuous")||mode.equals("interval"))?a.integer("ticks",1,12000):0;
                Action action=switch(mode) { case "once"->Action.once(); case "continuous"->Action.continuous(); case "interval"->Action.interval(a.integer("interval",1,12000)); default->null; };
                ap.start(type,action); clearLease(p,name);
                if(ticks>0) lease(s,p,name,ticks,()->ap.start(type,null));
            }
            case "carpet_stop" -> { ap.stopAll(); leases.remove(p.getUUID()); }
            case "carpet_remove" -> { ap.stopAll(); leases.remove(p.getUUID()); p.kill(p.level()); return Map.of("removed",a.name()); }
            case "carpet_hotbar" -> ap.setSlot(a.integer("slot",1,9));
            case "carpet_mount" -> { if(a.has("dismount")&&a.bool("dismount")) ap.dismount(); else ap.mount(true); }
            case "carpet_teleport" -> {
                double[] v=a.vector("position"); ap.stopAll(); leases.remove(p.getUUID()); p.teleportTo(v[0],v[1],v[2]);
            }
            case "carpet_inventory" -> {
                List<Map<String,Object>> items=new ArrayList<>(); var inv=p.getInventory();
                for(int i=0;i<inv.getContainerSize();i++) {
                    var item=inv.getItem(i); if(!item.isEmpty()) items.add(Map.of("slot",i,"item",BuiltInRegistries.ITEM.getKey(item.getItem()).toString(),"count",item.getCount()));
                }
                return Map.of("name",a.name(),"selectedHotbar",inv.getSelectedSlot()+1,"items",items);
            }
            case "carpet_observe" -> {
                int radius=a.has("radius")?a.integer("radius",1,8):4;
                List<Map<String,Object>> blocks=new ArrayList<>(); BlockPos origin=p.blockPosition(); int unloaded=0;
                for(BlockPos pos:BlockPos.betweenClosed(origin.offset(-radius,-radius,-radius),origin.offset(radius,radius,radius))) {
                    if(!p.level().hasChunkAt(pos)) { unloaded++; continue; }
                    var b=p.level().getBlockState(pos);
                    if(!b.isAir()) blocks.add(Map.of("position",List.of(pos.getX(),pos.getY(),pos.getZ()),"block",BuiltInRegistries.BLOCK.getKey(b.getBlock()).toString(),"state",b.toString()));
                }
                var entities=p.level().getEntities(p,p.getBoundingBox().inflate(radius));
                return Map.of("player",state(s,p),"blocks",blocks,"unloadedPositions",unloaded,"entitiesTruncated",entities.size()>256,
                    "entities",entities.stream().limit(256).map(e->Map.of("uuid",e.getUUID().toString(),"type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString(),"name",e.getName().getString(),"position",List.of(e.getX(),e.getY(),e.getZ()))).toList());
            }
        }
        return state(s,p);
    }
    private static Map<String,Object> command(MinecraftServer s,String command) throws Exception {
        if(command.isBlank()||command.length()>8192||command.contains("\n")||command.contains("\r")) throw new IllegalArgumentException("Expected one server command");
        List<String> messages=new ArrayList<>();
        CommandSource source=new CommandSource() {
            public void sendSystemMessage(Component c) { messages.add(c.getString()); }
            public boolean acceptsSuccess() { return true; }
            public boolean acceptsFailure() { return true; }
            public boolean shouldInformAdmins() { return false; }
        };
        int value=s.getCommands().getDispatcher().execute(command.startsWith("/")?command.substring(1):command,s.createCommandSourceStack().withSource(source));
        return Map.of("value",value,"messages",messages,"serverTick",s.getTickCount());
    }
}
