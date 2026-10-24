package dev.flashbackagent;

final class ReplayIds {
    static boolean isRecordedPlayer(int entityId, int firstViewerId) {
        return entityId > firstViewerId;
    }
}
