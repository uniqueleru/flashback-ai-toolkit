"""Opt-in integration proof. Run ONLY in the disposable carpet-agent-test save.

Creates a small stage and directs two test bots, records, verifies the replay,
and exports a fixed validation camera. This is a test, never a scene preset.
"""
import json
import argparse
import math
from pathlib import Path
import time
from flashback_agent import submit_job, wait_job, inspect_replay
from flashback_agent.tools import call_tool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work-dir', type=Path, default=Path('work/carpet-proof'))
    parser.add_argument('--game-dir', type=Path, default=Path('run'))
    parser.add_argument('--audio', action='store_true')
    args = parser.parse_args()
    root = args.game_dir.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    proof = []

    def call(name, args=None, success=True):
        result = call_tool(name, args or {}, game_dir=root, timeout=150)
        proof.append({'tool': name, 'arguments': args or {}, 'response': result})
        (work/'calls.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        assert (result['state'] == 'completed') == success, result
        print(json.dumps({'tool': name, 'state': result['state'], 'id': result['id']}), flush=True)
        return result.get('result', result)

    status = call('record_status')
    assert status['inWorld'] and not status['inReplay'] and not status['recording']
    observer = status['observer']['name']
    assert Path(call('carpet_list')['worldDirectory']).name == 'carpet-agent-test', 'Refusing to modify a non-test world'
    call('carpet_command', {'command': 'fill -5 110 -5 30 110 8 minecraft:stone'})
    call('carpet_command', {'command': 'fill -5 110 -5 30 110 8 minecraft:smooth_sandstone'})
    call('carpet_command', {'command': f'gamemode spectator {observer}'})
    call('carpet_command', {'command': f'tp {observer} 10 117 -8 0 25'})
    call('carpet_command', {'command': 'time set day'})
    listed = call('carpet_list')
    for name, position in [('ClipActor', [0, 111, 0]), ('ClipActorB', [12, 111, 5])]:
        if any(p['name'] == name for p in listed['players']):
            call('carpet_teleport', {'name': name, 'position': position})
        else:
            call('carpet_spawn', {'name': name, 'position': position, 'yaw': -90, 'gameMode': 'creative'})
    call('carpet_move', {'name': observer, 'forward': 1, 'ticks': 20}, success=False)
    call('carpet_spawn', {'name': 'ClipActor', 'position': [0, 111, 0]}, success=False)
    call('carpet_look', {'name': 'ClipActor', 'yaw': -90, 'pitch': 0})
    call('carpet_look', {'name': 'ClipActorB', 'at': [0, 112, 0]})
    observations = call('carpet_observe', {'name': 'ClipActor', 'radius': 2})
    assert any(b['block'] == 'minecraft:smooth_sandstone' for b in observations['blocks'])
    call('carpet_command', {'command': 'give ClipActor minecraft:stone 16'})
    inventory = call('carpet_inventory', {'name': 'ClipActor'})
    assert any(item['item'] == 'minecraft:stone' for item in inventory['items'])
    call('carpet_hotbar', {'name': 'ClipActor', 'slot': 1})
    visible = call('record_status')['visiblePlayers']
    assert {'ClipActor', 'ClipActorB'} <= {p['name'] for p in visible}, visible
    actors = [p for p in visible if p['name'] in ('ClipActor', 'ClipActorB')]
    assert all(p['gameMode'] == 'creative' and not p['invisible'] for p in actors), actors
    rid = call('record_start')['recordingId']
    call('record_start', success=False)
    call('record_stop', {'recordingId': 'wrong-session', 'output': str(work/'wrong-id.zip')}, success=False)
    assert not (work/'wrong-id.zip').exists()
    # No retries after partial execution: the job ledger and recording ID remain on disk.
    (work/'recording-id.txt').write_text(rid)
    begin = call('carpet_state', {'name': 'ClipActor'})
    call('carpet_action', {'name': 'ClipActor', 'action': 'jump', 'mode': 'interval', 'interval': 18, 'ticks': 60})
    call('carpet_move', {'name': 'ClipActor', 'forward': 1, 'sprint': True, 'ticks': 60})
    call('carpet_action', {'name': 'ClipActorB', 'action': 'jump', 'mode': 'once'})
    if args.audio:
        time.sleep(1)
        call('carpet_command', {'command': 'playsound minecraft:block.note_block.pling master @a 10 114 -6 2 1 1'})
        time.sleep(2.8)
    else:
        time.sleep(3.8)
    end = call('carpet_state', {'name': 'ClipActor'})
    assert math.dist(begin['position'], end['position']) > 5, (begin, end)
    assert not end['controlsRemainingTicks'], end
    time.sleep(.5)
    later = call('carpet_state', {'name': 'ClipActor'})
    assert math.dist(end['position'], later['position']) < .15, (end, later)
    recording = call('record_stop', {'recordingId': rid, 'output': str(work/'actors.zip')})
    assert recording['totalTicks'] >= 80
    call('carpet_stop', {'name': 'ClipActor'})
    call('carpet_remove', {'name': 'ClipActor'})
    call('carpet_remove', {'name': 'ClipActorB'})
    call('world_close')
    metadata = inspect_replay(work/'actors.zip')
    job = submit_job(root, work/'actors.zip', '0.5-4', operation='sample', sample_interval_ticks=10)
    sample_result = wait_job(job, timeout=180)
    assert sample_result['state'] == 'completed', sample_result
    samples = json.loads(Path(sample_result['samplesFile']).read_text(encoding='utf-8'))['samples']
    names = [(s['tick'], [e['name'] for e in s['entities'] if e['player']]) for s in samples]
    assert all({'ClipActor', 'ClipActorB'} <= set(players) for tick, players in names), names
    tracks = [next(e for e in s['entities'] if e['name'] == 'ClipActor')['position'] for s in samples]
    assert max(p[0] for p in tracks)-min(p[0] for p in tracks) > 5, tracks
    playback = call('record_status')['visiblePlayers']
    playback_actors = [p for p in playback if p['name'] in ('ClipActor', 'ClipActorB')]
    assert len(playback_actors) == 2 and all(not p['invisible'] and not p['spectator'] for p in playback_actors), playback_actors
    camera = {'version': 1, 'name': 'Integration validation view', 'visuals': {'chat': False, 'hotbar': False, 'nametags': False}, 'camera': [
        {'tick': 10, 'position': [10, 119, -15], 'lookAt': [10, 112, 2], 'fov': 65}]}
    (work/'camera.json').write_text(json.dumps(camera, indent=2))
    render = submit_job(root, work/'actors.zip', '0.5-4', output=work/'carpet-recording-proof.mp4',
                        plan=camera, width=960, height=540, fps=30, audio=args.audio)
    result = wait_job(render, timeout=240)
    assert result['state'] == 'completed' and result['frames'] == 105, result
    report = {'state': 'verified', 'calls': len(proof), 'recording': recording, 'metadata': metadata,
              'actorStart': begin, 'actorEnd': end, 'sampleJob': str(job), 'renderJob': str(render), 'render': result,
              'scope': 'Integrated Fabric server in disposable copied save; dedicated server not live-tested'}
    (work/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'state': 'verified', 'proof': str(work/'verification.json')}), flush=True)


if __name__ == '__main__':
    main()
