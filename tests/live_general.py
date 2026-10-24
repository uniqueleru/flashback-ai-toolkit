"""Opt-in live proof of scene queries, target-free cameras, retiming and ordered edits."""
import argparse
import json
from pathlib import Path

from flashback_agent import bridge_health, submit_job, wait_job
from flashback_agent.media import probe, review
from flashback_agent.sequence import render_sequence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=False)
    bridge_health(args.game_dir)
    job = submit_job(args.game_dir, args.replay, '1-3', operation='sample', sample_interval_ticks=10)
    result = wait_job(job, timeout=180)
    assert result['state'] == 'completed', result
    samples_file = result['samplesFile']
    samples = json.loads(Path(samples_file).read_text(encoding='utf-8'))['samples']
    assert [s['tick'] for s in samples] == [20,30,40,50,60]
    assert samples[0]['entities'], samples
    player = next(e for e in samples[0]['entities'] if e['player'])
    x,y,z = player['position']
    focus = [x,y+1.5,z+8]
    # World-space camera; no target is passed and no tracking generator runs.
    fixed = {'version':1,'name':'Fixed landscape','camera':[
        {'tick':20,'position':[x+8,y+6,z-10],'lookAt':focus,'fov':60}]}
    travel = {'version':1,'name':'Authored dolly at 2x','speed':2,'camera':[
        {'tick':100,'position':[x+12,y+8,z-3],'lookAt':focus,'fov':65,'roll':-4,'interpolation':'ease_in_out'},
        {'tick':140,'position':[x+6,y+8,z+3],'lookAt':focus,'fov':60,'roll':0,'interpolation':'ease_in_out'},
        {'tick':180,'position':[x,y+8,z+8],'lookAt':focus,'fov':55,'roll':4,'interpolation':'ease_in_out'}]}
    for name, plan in [('fixed',fixed),('travel',travel)]:
        (args.work_dir/f'{name}.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    edit = {'version':1,'replay':str(args.replay.resolve()),
            'render':{'width':640,'height':360,'fps':24,'audio':False},
            'shots':[{'range':'1-3','plan':'fixed.json'}, {'range':'5-9','plan':'travel.json'}]}
    edit_path = args.work_dir/'edit.json'
    edit_path.write_text(json.dumps(edit,indent=2,ensure_ascii=False),encoding='utf-8')
    state = render_sequence(edit_path,args.game_dir,args.output,work_dir=args.work_dir/'render',
                            on_progress=lambda s: print(json.dumps(s),flush=True))
    assert state['state'] == 'completed' and state['frames'] == 96, state
    for job_path in state['jobs']:
        job = Path(job_path)
        request = json.loads((job/'request.json').read_text(encoding='utf-8'))
        result = json.loads((job/'result.json').read_text(encoding='utf-8'))
        assert request['target'] is None and request['plan']['camera']
        assert result['frames'] == 48 and result['targetUuid'] == '', result
        assert json.loads((job/'camera-plan.json').read_text(encoding='utf-8')) == request['plan']
    info = probe(args.output)
    assert int(info['video']['nb_frames']) == 96 and abs(float(info['format']['duration'])-4) < .05
    reviewed = review(args.output,args.work_dir/'review',every=.5,max_frames=8)
    proof = {'state':'verified','query':samples_file, 'sampleCount':len(samples),
             'sequence':state,'media':info,'reviewFrames':reviewed['frames']}
    (args.work_dir/'verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    print(json.dumps({'verified':True,'output':str(args.output),'frames':96}),flush=True)


if __name__ == '__main__':
    main()
