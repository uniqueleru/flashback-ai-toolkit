package dev.flashbackagent.mixin;

import dev.flashbackagent.BackgroundMode;
import com.mojang.blaze3d.platform.FramerateLimitTracker;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(FramerateLimitTracker.class)
public abstract class BackgroundFramerateMixin {
    @Inject(method="getFramerateLimit", at=@At("HEAD"), cancellable=true)
    private void backgroundFps(CallbackInfoReturnable<Integer> ci) { if (BackgroundMode.enabled()) ci.setReturnValue(BackgroundMode.fps()); }
    @Inject(method="isHeavilyThrottled", at=@At("HEAD"), cancellable=true)
    private void backgroundNotIdle(CallbackInfoReturnable<Boolean> ci) { if (BackgroundMode.enabled()) ci.setReturnValue(false); }
}
