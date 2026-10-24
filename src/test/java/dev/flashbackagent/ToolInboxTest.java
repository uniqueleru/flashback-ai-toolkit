package dev.flashbackagent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class ToolInboxTest {
    @TempDir Path root;
    @Test void rejectsOldWorldAndExpiredJobsBeforeExecuting() throws Exception {
        AtomicInteger calls=new AtomicInteger();
        ToolInbox inbox=new ToolInbox(root,"test",(tool,args)->{ calls.incrementAndGet(); return CompletableFuture.completedFuture(Map.of("ok",true)); });
        try {
            await(root.resolve("bridge.json"));
            String session=JobFiles.read(root.resolve("bridge.json")).get("session").getAsString();
            for(int i=0;i<3;i++) {
                Path job=root.resolve("jobs").resolve(UUID.randomUUID().toString().replace("-","")); Files.createDirectories(job);
                JobFiles.write(job.resolve("request.json"),Map.of("session",i==0?"old-world":session,"expiresAt",i==1?0:System.currentTimeMillis()+10000,
                    "tool","test","arguments",Map.of()));
                await(job.resolve("result.json"));
                assertEquals(i==2?"completed":"failed",JobFiles.read(job.resolve("result.json")).get("state").getAsString());
            }
            assertEquals(1,calls.get());
        } finally { inbox.close(); }
    }
    private static void await(Path file) throws Exception {
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
        while(!Files.isRegularFile(file)) { if(System.nanoTime()>until) fail("Timed out: "+file); Thread.sleep(25); }
    }
}
