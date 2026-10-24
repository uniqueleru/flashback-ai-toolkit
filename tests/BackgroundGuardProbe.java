import org.lwjgl.glfw.GLFW;
import org.lwjgl.util.tinyfd.TinyFileDialogs;

/** A real native adversarial startup probe, always launched with the premain guard. */
public class BackgroundGuardProbe {
    public static void main(String[] args) throws Exception {
        Class.forName("org.lwjgl.glfw.GLFW");
        if (!"active".equals(System.getProperty("flashback.agent.guard.glfw"))) throw new AssertionError("No guard");
        if (!GLFW.glfwInit()) throw new AssertionError("GLFW init failed");
        GLFW.glfwWindowHint(GLFW.GLFW_VISIBLE, GLFW.GLFW_TRUE);
        GLFW.glfwWindowHint(GLFW.GLFW_FOCUSED, GLFW.GLFW_TRUE);
        GLFW.glfwWindowHint(GLFW.GLFW_FOCUS_ON_SHOW, GLFW.GLFW_TRUE);
        long window = GLFW.glfwCreateWindow(640, 360, "Guard validation", GLFW.glfwGetPrimaryMonitor(), 0);
        if (window == 0) throw new AssertionError("No context");
        GLFW.glfwShowWindow(window);
        GLFW.glfwFocusWindow(window);
        GLFW.glfwRequestWindowAttention(window);
        GLFW.glfwRestoreWindow(window);
        GLFW.glfwMaximizeWindow(window);
        GLFW.glfwSetWindowMonitor(window, GLFW.glfwGetPrimaryMonitor(), 0, 0, 800, 600, 60);
        GLFW.glfwSetInputMode(window, GLFW.GLFW_CURSOR, GLFW.GLFW_CURSOR_DISABLED);
        GLFW.glfwSetCursorPos(window, 0, 0);
        GLFW.glfwPollEvents();
        if (GLFW.glfwGetWindowAttrib(window, GLFW.GLFW_VISIBLE) != 0 ||
            GLFW.glfwGetWindowAttrib(window, GLFW.GLFW_FOCUSED) != 0 ||
            GLFW.glfwGetWindowMonitor(window) != 0 ||
            GLFW.glfwGetInputMode(window, GLFW.GLFW_CURSOR) != GLFW.GLFW_CURSOR_NORMAL)
            throw new AssertionError("Desktop isolation failed");
        Class.forName("org.lwjgl.util.tinyfd.TinyFileDialogs");
        if (!"active".equals(System.getProperty("flashback.agent.guard.dialogs"))) throw new AssertionError("No dialog guard");
        boolean blocked = false;
        try { TinyFileDialogs.tinyfd_messageBox("Guard validation", "Must never appear", "ok", "info", 1); }
        catch (IllegalStateException expected) { blocked = true; }
        if (!blocked) throw new AssertionError("Native dialog allowed");
        GLFW.glfwDestroyWindow(window);
        GLFW.glfwTerminate();
        System.out.println("{\"state\":\"verified\",\"showFocusFullscreenCursorDialogBlocked\":true}");
    }
}
