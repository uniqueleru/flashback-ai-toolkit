package dev.flashbackagent.mixin;

import dev.flashbackagent.BackgroundMode;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(Minecraft.class)
public abstract class BackgroundMinecraftMixin {
    @Inject(method="pauseIfInactive", at=@At("HEAD"), cancellable=true)
    private void backgroundNoFocusPause(CallbackInfo ci) { if (BackgroundMode.enabled()) ci.cancel(); }
}
