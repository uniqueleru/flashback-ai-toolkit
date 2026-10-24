package dev.flashbackagent;

import net.minecraft.client.Minecraft;
import org.lwjgl.glfw.GLFW;
import java.util.*;

/** Per-process policy only: never rewrites the user's options or changes another client. */
public final class BackgroundMode {
    private static volatile boolean stopping;
    public static boolean stopping() { return stopping; }
    public static void requestStop() { stopping = true; }
    public static boolean enabled() { return Boolean.getBoolean("flashback.agent.background"); }
    public static int fps() { return Math.clamp(Integer.getInteger("flashback.agent.backgroundFps", 30), 20, 120); }
    public static Map<String,Object> status(Minecraft mc) {
        if (!enabled()) return Map.of("enabled", false);
        long handle = mc.getWindow().handle();
        return Map.of("enabled", true, "guard", System.getProperty("flashback.agent.guard.glfw", "missing"),
            "visible", GLFW.glfwGetWindowAttrib(handle, GLFW.GLFW_VISIBLE) != 0,
            "focused", GLFW.glfwGetWindowAttrib(handle, GLFW.GLFW_FOCUSED) != 0,
            "fullscreen", GLFW.glfwGetWindowMonitor(handle) != 0,
            "desktopAudio", System.getenv().getOrDefault("ALSOFT_DRIVERS", "default"),
            "backgroundFps", fps(), "launchId", System.getProperty("flashback.agent.launchId", ""),
            "pid", ProcessHandle.current().pid());
    }
}
