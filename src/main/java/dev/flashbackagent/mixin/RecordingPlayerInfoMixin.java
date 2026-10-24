package dev.flashbackagent.mixin;

import com.moulberry.flashback.record.Recorder;
import net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import java.util.EnumSet;

/** 0.43.2 snapshots populate gameMode in entries but omit its serialization flag.
 * Replayed actors can inherit the observer's spectator mode and become translucent.
 * Current upstream uses createPlayerInitializing; keep this pinned adapter minimal.
 */
@Mixin(value=Recorder.class,remap=false)
public abstract class RecordingPlayerInfoMixin {
    @ModifyArg(method="writeSnapshot",at=@At(value="INVOKE",target="Lnet/minecraft/network/protocol/game/ClientboundPlayerInfoUpdatePacket;<init>(Ljava/util/EnumSet;Ljava/util/Collection;)V"),index=0,require=1)
    private EnumSet<ClientboundPlayerInfoUpdatePacket.Action> agent$includeGameMode(EnumSet<ClientboundPlayerInfoUpdatePacket.Action> original) {
        EnumSet<ClientboundPlayerInfoUpdatePacket.Action> corrected=original.clone();
        corrected.add(ClientboundPlayerInfoUpdatePacket.Action.UPDATE_GAME_MODE);
        return corrected;
    }
}
