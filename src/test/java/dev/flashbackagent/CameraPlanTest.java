package dev.flashbackagent;

import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CameraPlanTest {
    @Test void acceptsWorldSpaceCameraWithoutAnyEntity() {
        var json = JsonParser.parseString("""
            {"version":1,"camera":[{"tick":20,"position":[1,80,3],"yaw":90,"pitch":15,"roll":7,"fov":50,"interpolation":"linear"}]}
            """).getAsJsonObject();
        var plan = CameraPlan.parse(json, 20, 60);
        assertEquals(1, plan.camera().size());
        assertEquals(7, plan.camera().getFirst().roll());
        assertEquals(80, plan.camera().getFirst().position()[1]);
        assertEquals(1, plan.speed());
    }
}
