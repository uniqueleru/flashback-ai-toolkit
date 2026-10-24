package dev.flashbackagent.mixin;

import com.moulberry.flashback.exporting.ExportJob;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = ExportJob.class, remap = false)
public interface ExportJobAccessor {
    @Accessor("writtenFrames") int flashbackAgent$writtenFrames();
}
