package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EncoderSelectionTest {
    @Test void usesAvailableH264WhenBundledFfmpegHasNoGplX264() {
        assertEquals("libopenh264", EncoderSelection.h264(new String[]{"libopenh264"}));
        assertEquals("h264_nvenc", EncoderSelection.h264(new String[]{"h264_nvenc", "libopenh264"}));
        assertThrows(IllegalStateException.class, () -> EncoderSelection.h264(new String[0]));
    }
}
