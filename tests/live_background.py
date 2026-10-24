"""Full copied-modpack hidden startup -> bots -> replay -> audiovisual MP4 -> stop."""
import json
from pathlib import Path
import runpy
import shutil
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from flashback_agent import runtime
from flashback_agent.tools import call_tool
from window_audit import WindowAudit

instance = root/'runtime/background-client'
work = root/'work/background-proof'
work.mkdir(exist_ok=True)
save = instance/'saves/carpet-agent-test'
if not save.exists():
    save.parent.mkdir(exist_ok=True)
    runtime.copy_tree(root/'run/saves/carpet-agent-test', save)
report = {'startedAt': time.time()}
pid = None
with WindowAudit() as audit:
    try:
        ready = runtime.start(instance, timeout=180)
        pid = ready['pid']
        report['startup'] = ready
        print(json.dumps({'state': 'ready', 'pid': pid, 'background': ready['background']}), flush=True)
        duplicate_refused = False
        try:
            runtime.start(instance)
        except RuntimeError as exc:
            duplicate_refused = 'already running' in str(exc)
        assert duplicate_refused
        report['duplicateStartRefused'] = True
        opened = call_tool('world_open', {'save': 'carpet-agent-test'}, game_dir=instance, timeout=150)
        assert opened['state'] == 'completed', opened
        sys.argv = ['live_carpet.py', '--work-dir', str(work/'carpet'), '--game-dir', str(instance), '--audio']
        runpy.run_path(str(root/'tests/live_carpet.py'), run_name='__main__')
        report['beforeStop'] = call_tool('record_status', {}, game_dir=instance)
        report['stop'] = runtime.stop(instance)
        assert report['stop']['state'] == 'stopped'
        report['state'] = 'verified'
    except BaseException as exc:
        report['state'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        if pid is None and (instance/'.background/process.json').exists():
            pid = json.loads((instance/'.background/process.json').read_text())['pid']
        report['windowEvents'] = audit.for_pid(pid) if pid else []
        report['finishedAt'] = time.time()
        (work/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'state': report['state'], 'windowEvents': report['windowEvents'], 'proof': str(work)}), flush=True)
assert not report['windowEvents'], report
