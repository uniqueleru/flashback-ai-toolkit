package dev.flashbackagent.mixin;

import com.moulberry.flashback.exporting.ExportJob;
import com.mojang.blaze3d.pipeline.RenderTarget;
import com.moulberry.flashback.playback.ReplayServer;
import dev.flashbackagent.FlashbackAgent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import com.moulberry.flashback.state.EditorState;
import java.util.List;

@Mixin(value = ExportJob.class, remap = false)
public abstract class ExportCancellationMixin {
    @Inject(method = "calculateTicks", at = @At("HEAD"), cancellable = true)
    private static void agentFrameSchedule(EditorState state, int start, int end, double fps, CallbackInfoReturnable<List<?>> cir) {
        List<?> schedule = FlashbackAgent.frameSchedule(state, start, end, fps);
        if (schedule != null) cir.setReturnValue(schedule);
    }
    @Inject(method = "setServerTickAndWait", at = @At("HEAD"))
    private void updateProgress(ReplayServer server, int tick, boolean unused, CallbackInfo ci) {
        FlashbackAgent.updateExportProgress((ExportJob)(Object)this);
    }
    // Use the native loop's cancellation branch. Throwing from a tick boundary
    // skips pending GPU downloads and leaves callbacks targeting released PBOs.
    @Inject(method = "finishFrameNormal", at = @At("RETURN"), cancellable = true)
    private void cancelAfterFrame(RenderTarget target, int frame, int total, CallbackInfoReturnable<Boolean> cir) {
        if (FlashbackAgent.isExportCancellationRequested((ExportJob)(Object)this)) cir.setReturnValue(true);
    }
}
