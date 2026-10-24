package dev.flashbackagent.background;

import java.lang.classfile.*;
import java.lang.constant.*;
import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;

/** Installed by -javaagent before Fabric, GLFW, or any mod can create a window. */
public final class BackgroundAgent {
    private static final ClassDesc GLFW = ClassDesc.of("org.lwjgl.glfw.GLFW");
    private static final Set<String> BLOCKED = Set.of("glfwShowWindow", "glfwFocusWindow",
        "glfwRequestWindowAttention", "glfwRestoreWindow", "glfwMaximizeWindow",
        "glfwSetWindowMonitor", "glfwSetCursorPos", "glfwSetInputMode");

    public static void premain(String args, Instrumentation instrumentation) {
        System.setProperty("flashback.agent.background", "true");
        System.setProperty("java.awt.headless", "true");
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override public byte[] transform(ClassLoader loader, String name, Class<?> type,
                    ProtectionDomain domain, byte[] bytes) {
                if (!name.equals("org/lwjgl/glfw/GLFW") && !name.equals("org/lwjgl/util/tinyfd/TinyFileDialogs")) return null;
                try {
                    byte[] result = protect(name, bytes);
                    System.setProperty("flashback.agent.guard." + (name.endsWith("/GLFW") ? "glfw" : "dialogs"), "active");
                    return result;
                } catch (Throwable failure) {
                    // Transformer exceptions are otherwise ignored by the JVM. Never fall back to an unguarded launch.
                    failure.printStackTrace(System.err);
                    Runtime.getRuntime().halt(78);
                    return null;
                }
            }
        });
    }

    static byte[] protect(String name, byte[] bytes) {
        ClassFile cf = ClassFile.of();
        ClassModel model = cf.parse(bytes);
        boolean glfw = name.endsWith("/GLFW");
        if (glfw) {
            Set<String> methods = new HashSet<>();
            for (var method : model.methods()) if (method.code().isPresent()) methods.add(method.methodName().stringValue());
            if (!methods.containsAll(BLOCKED) || !methods.contains("nglfwCreateWindow"))
                throw new IllegalStateException("Unsupported GLFW; refusing a potentially visible launch");
        }
        return cf.transformClass(model, (builder, element) -> {
            if (!(element instanceof MethodModel method) || method.code().isEmpty()) { builder.with(element); return; }
            String methodName = method.methodName().stringValue();
            if (glfw && BLOCKED.contains(methodName)) {
                builder.transformMethod(method, (mb, me) -> {
                    if (me instanceof CodeModel) mb.withCode(code -> code.return_()); else mb.with(me);
                });
            } else if (glfw && methodName.equals("nglfwCreateWindow")) {
                if (!method.methodType().stringValue().equals("(IIJJJ)J")) throw new IllegalStateException("Unknown GLFW creation signature");
                builder.transformMethod(method, MethodTransform.transformingCode(new CodeTransform() {
                    @Override public void atStart(CodeBuilder code) {
                        // GLFW_VISIBLE, FOCUSED, FOCUS_ON_SHOW, AUTO_ICONIFY. Enforce immediately before creation,
                        // even if a mod or saved fullscreen preference supplied different hints.
                        for (int hint : new int[]{0x00020004, 0x00020001, 0x0002000C, 0x00020006})
                            code.loadConstant(hint).iconst_0().invokestatic(GLFW, "glfwWindowHint", MethodTypeDesc.ofDescriptor("(II)V"));
                        code.lconst_0().lstore(4); // monitor=NULL: never switch the desktop display mode
                    }
                    @Override public void accept(CodeBuilder code, CodeElement e) { code.with(e); }
                }));
            } else if (!glfw && methodName.startsWith("tinyfd_") &&
                       (methodName.endsWith("Dialog") || methodName.endsWith("Box") || methodName.equals("tinyfd_notifyPopup"))) {
                builder.transformMethod(method, (mb, me) -> {
                    if (me instanceof CodeModel) mb.withCode(code -> code
                        .new_(ClassDesc.of("java.lang.IllegalStateException")).dup()
                        .ldc("Native dialog suppressed in background mode: " + methodName)
                        .invokespecial(ClassDesc.of("java.lang.IllegalStateException"), "<init>", MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)V")).athrow());
                    else mb.with(me);
                });
            } else builder.with(method);
        });
    }
}
