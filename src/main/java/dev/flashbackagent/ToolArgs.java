package dev.flashbackagent;

import com.google.gson.*;
import java.util.*;

/** Validation also runs at the bridge, independently of the Python caller. */
final class ToolArgs {
    final JsonObject value;
    ToolArgs(JsonObject value, String... allowed) {
        this.value = value;
        Set<String> keys = Set.of(allowed);
        for (String key : value.keySet()) if (!keys.contains(key))
            throw new IllegalArgumentException("Unknown argument: " + key);
    }
    boolean has(String key) { return value.has(key); }
    String text(String key) {
        JsonElement e = value.get(key);
        if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString())
            throw new IllegalArgumentException(key + " must be a string");
        return e.getAsString();
    }
    String choice(String key, String... choices) {
        String v = text(key);
        if (!Set.of(choices).contains(v)) throw new IllegalArgumentException("Invalid " + key);
        return v;
    }
    String name() {
        String v = text("name");
        if (!v.matches("[A-Za-z0-9_]{1,16}")) throw new IllegalArgumentException("Bot name must be 1..16 letters, digits or underscores");
        return v;
    }
    double number(String key, double min, double max) {
        JsonElement e = value.get(key);
        if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isNumber())
            throw new IllegalArgumentException(key + " must be a number");
        double n = e.getAsDouble();
        if (!Double.isFinite(n) || n < min || n > max) throw new IllegalArgumentException(key + " out of range");
        return n;
    }
    int integer(String key, int min, int max) {
        double n = number(key, min, max);
        if (n != Math.rint(n)) throw new IllegalArgumentException(key + " must be an integer");
        return (int)n;
    }
    boolean bool(String key) {
        JsonElement e = value.get(key);
        if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException(key + " must be a boolean");
        return e.getAsBoolean();
    }
    double[] vector(String key) {
        JsonElement e = value.get(key);
        if (e == null || !e.isJsonArray() || e.getAsJsonArray().size() != 3)
            throw new IllegalArgumentException(key + " must contain x,y,z");
        double[] out = new double[3];
        for (int i=0; i<3; i++) {
            JsonElement n = e.getAsJsonArray().get(i);
            if (!n.isJsonPrimitive() || !n.getAsJsonPrimitive().isNumber()) throw new IllegalArgumentException("Invalid coordinate");
            out[i] = n.getAsDouble();
            if (!Double.isFinite(out[i]) || Math.abs(out[i]) > 29999984) throw new IllegalArgumentException("Coordinate out of range");
        }
        return out;
    }
}
