package dev.flashbackagent;

import com.google.gson.*;
import java.util.*;

/** World-space keys supplied by the caller. No entity, framing rule or automatic motion. */
record CameraPlan(List<Key> camera, double speed, Map<String, Boolean> visuals, String name) {
    record Key(int tick, double[] position, double yaw, double pitch, double roll, double fov, String interpolation) {}
    private static final Set<String> INTERPOLATIONS = Set.of("linear", "smooth", "ease_in", "ease_out", "ease_in_out", "hold", "hermite");

    static CameraPlan parse(JsonObject json, int start, int end) {
        fields(json, Set.of("version", "camera", "speed", "visuals", "name"));
        if (number(json, "version", -1, 1, 1) != 1) throw new IllegalArgumentException("Unknown camera plan version");
        JsonArray array = json.getAsJsonArray("camera");
        if (array == null || array.isEmpty() || array.size() > 10000) throw new IllegalArgumentException("Camera plan requires 1..10000 keys");
        List<Key> keys = new ArrayList<>();
        int previous = -1;
        for (JsonElement element : array) {
            JsonObject k = element.getAsJsonObject();
            fields(k, Set.of("tick", "position", "yaw", "pitch", "roll", "fov", "interpolation"));
            double tick = number(k, "tick", -1, 0, 2147483646);
            if (tick != (int)tick || tick <= previous) throw new IllegalArgumentException("Camera ticks must be strictly increasing integers");
            previous = (int)tick;
            JsonArray pos = k.getAsJsonArray("position");
            if (pos == null || pos.size() != 3) throw new IllegalArgumentException("Camera position must have three coordinates");
            double[] xyz = new double[3];
            for (int i = 0; i < 3; i++) { xyz[i] = pos.get(i).getAsDouble(); bounded(xyz[i], -30000000, 30000000); }
            if (!k.has("yaw") || !k.has("pitch")) throw new IllegalArgumentException("Normalized camera keys require yaw/pitch");
            String interpolation = k.has("interpolation") ? k.get("interpolation").getAsString() : "linear";
            if (!INTERPOLATIONS.contains(interpolation)) throw new IllegalArgumentException("Unknown interpolation");
            keys.add(new Key((int)tick, xyz, number(k, "yaw", 0, -36000, 36000), number(k, "pitch", 0, -90, 90),
                number(k, "roll", 0, -36000, 36000), number(k, "fov", 70, 1, 170), interpolation));
        }
        if (keys.size() > 1 && (keys.getFirst().tick() > start || keys.getLast().tick() < end))
            throw new IllegalArgumentException("Camera keys must cover the source range");
        Map<String, Boolean> visuals = new HashMap<>();
        if (json.has("visuals")) {
            JsonObject options = json.getAsJsonObject("visuals");
            fields(options, Set.of("nametags", "chat", "hotbar"));
            for (var e : options.entrySet()) {
                if (!e.getValue().isJsonPrimitive() || !e.getValue().getAsJsonPrimitive().isBoolean())
                    throw new IllegalArgumentException("Visual options must be booleans");
                visuals.put(e.getKey(), e.getValue().getAsBoolean());
            }
        }
        return new CameraPlan(List.copyOf(keys), number(json, "speed", 1, .1, 8), Map.copyOf(visuals),
            json.has("name") ? json.get("name").getAsString() : "Camera plan");
    }
    private static void fields(JsonObject object, Set<String> allowed) {
        for (String key : object.keySet()) if (!allowed.contains(key)) throw new IllegalArgumentException("Unsupported plan field: " + key);
    }
    private static double number(JsonObject object, String key, double fallback, double low, double high) {
        double value = object.has(key) ? object.get(key).getAsDouble() : fallback;
        bounded(value, low, high); return value;
    }
    private static void bounded(double value, double low, double high) {
        if (!Double.isFinite(value) || value < low || value > high) throw new IllegalArgumentException("Invalid camera number");
    }
}
