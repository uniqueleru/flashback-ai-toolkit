"""Probe real GLFW: forced-visible/fullscreen creation and show/focus/cursor calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flashback_agent.runtime import java_argfile
from window_audit import WindowAudit

root = Path(__file__).resolve().parents[1]
instance = root/'runtime/background-client'
manifest = json.loads((instance/'.background/instance.json').read_text(encoding='utf-8'))
work = root/'work/background-guard-proof'
work.mkdir(exist_ok=True)
classpath = os.pathsep.join(Path(p).as_posix() for p in manifest['classpath'])
args = ['-cp', classpath, '-d', str(work), str(root/'tests/BackgroundGuardProbe.java')]
(work/'compile.args').write_text(java_argfile(args), encoding='utf-8')
compiled = subprocess.run([str(Path(manifest['java']).with_name('javac.exe')), '@'+str(work/'compile.args')],
                          capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
assert compiled.returncode == 0, compiled.stderr
args = [f'-javaagent:{manifest["guard"]}', '--enable-native-access=ALL-UNNAMED', '-cp',
        str(work)+os.pathsep+classpath, 'BackgroundGuardProbe']
(work/'probe.args').write_text(java_argfile(args), encoding='utf-8')
with WindowAudit() as audit, (work/'probe.log').open('wb') as log:
    process = subprocess.Popen([manifest['java'], '@'+str(work/'probe.args')], stdout=log,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    code = process.wait(timeout=40)
    events = audit.for_pid(process.pid)
report = {'pid': process.pid, 'exitCode': code, 'windowEvents': events,
          'log': (work/'probe.log').read_text(encoding='utf-8', errors='replace')}
(work/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
assert code == 0 and not events, report
