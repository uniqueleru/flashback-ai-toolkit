package dev.flashbackagent;

import java.util.Arrays;

final class EncoderSelection {
    static String h264(String[] workingEncoders) {
        // Flashback already probes these encoders. Its bundled FFmpeg may omit GPL libx264.
        for (String preferred : new String[]{"h264_nvenc", "h264_amf", "h264_qsv", "libx264", "libopenh264"})
            if (Arrays.asList(workingEncoders).contains(preferred)) return preferred;
        if (workingEncoders.length > 0) return workingEncoders[0];
        throw new IllegalStateException("Flashback found no working H.264 encoder");
    }
}
