package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReplayIdsTest {
    @Test void recordedPlayersAreAboveTheDescendingNegativeViewerIdRange() {
        int first = -981723987;
        assertTrue(ReplayIds.isRecordedPlayer(42, first));
        assertTrue(ReplayIds.isRecordedPlayer(-1, first));
        assertFalse(ReplayIds.isRecordedPlayer(first, first));
        assertFalse(ReplayIds.isRecordedPlayer(first - 1, first));
    }
}
