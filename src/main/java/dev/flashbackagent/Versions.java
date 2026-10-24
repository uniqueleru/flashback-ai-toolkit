package dev.flashbackagent;

import net.fabricmc.loader.api.FabricLoader;

/** Versions of the running game and mods, read from Fabric so the bridge names no version itself. */
final class Versions {
    private Versions() {}

    static String of(String modId) {
        return FabricLoader.getInstance().getModContainer(modId)
            .map(mod -> mod.getMetadata().getVersion().getFriendlyString()).orElse("unknown");
    }

    static String minecraft() { return of("minecraft"); }
}
