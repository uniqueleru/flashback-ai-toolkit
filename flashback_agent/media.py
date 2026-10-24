"""Local media inspection and explicit ordered cuts using FFmpeg, without a shell."""
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile


def _run(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr[-3000:]}')
    return result.stdout


def probe(path):
    path = Path(path).resolve(strict=True)
    info = json.loads(_run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    videos = [s for s in info['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        raise ValueError('Expected exactly one video stream')
    return {'path': str(path), 'video': videos[0], 'audio': [s for s in info['streams'] if s['codec_type'] == 'audio'],
            'format': info['format']}


def review(video, output_dir, *, every=1.0, max_frames=24):
    """Extract a bounded chronological frame sequence; this does not score cinematic quality."""
    if not math.isfinite(every) or every <= 0 or type(max_frames) is not int or not 1 <= max_frames <= 240:
        raise ValueError('Review requires a positive interval and 1..240 frames')
    info = probe(video)
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    _run(['ffmpeg','-v','error','-n','-i',info['path'],'-vf',f'fps=1/{every},scale=640:-2',
          '-frames:v',str(max_frames),str(directory/'frame-%04d.png')])
    frames = [str(p) for p in sorted(directory.glob('frame-*.png'))]
    if not frames:
        raise RuntimeError('No review frames extracted; use a shorter sampling interval')
    result = {'media':info, 'frames':frames, 'intervalSeconds':every,
              'note':'Frames support visual inspection; sparse stills do not prove stable motion. Inspect a dense short preview for temporal issues.'}
    (directory/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def assemble(clips, output):
    """Join clips in caller order with hard cuts. Reject incompatible media instead of silently reframing."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Output already exists: {output}')
    if output.suffix.lower() != '.mp4' or not clips:
        raise ValueError('Assembly requires input clips and an MP4 output')
    media = [probe(p) for p in clips]
    def signature(m):
        v = m['video']
        return (v['width'], v['height'], Fraction(v['avg_frame_rate']),
                tuple((a['sample_rate'], a['channels']) for a in m['audio']))
    if any(signature(m) != signature(media[0]) for m in media):
        raise ValueError('Clips must have matching dimensions, frame rates and audio layout; choose explicit render settings')
    fps = signature(media[0])[2]
    if fps <= 0:
        raise ValueError('Invalid input frame rate')
    frames = [int(m['video']['nb_frames']) for m in media]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.flashback-cut-', dir=output.parent) as directory:
        temp = Path(directory)
        entries = []
        for m, count in zip(media, frames):
            path = Path(m['path']).as_posix()
            if any(c in path for c in '\r\n\0'):
                raise ValueError('Unsupported newline in media path')
            escaped = path.replace("'", "'\\''")
            entries.append(f"file '{escaped}'\nduration {float(count / fps):.12f}\n")
        manifest = temp / 'concat.txt'
        manifest.write_text(''.join(entries), encoding='utf-8')
        partial = temp / 'assembled.mp4'
        args = ['ffmpeg', '-v', 'error', '-n', '-f', 'concat', '-safe', '0', '-i', str(manifest),
                '-map', '0:v:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                '-r', str(fps), '-fps_mode', 'cfr']
        args += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '192k'] if media[0]['audio'] else ['-an']
        args += ['-movflags', '+faststart', str(partial)]
        _run(args)
        result = probe(partial)
        if int(result['video']['nb_frames']) != sum(frames):
            raise RuntimeError('Assembled frame count does not match the ordered inputs')
        # Same-filesystem link publishes only a complete file and never replaces a destination.
        os.link(partial, output)
    return {'state': 'completed', 'output': str(output), 'clips': [m['path'] for m in media],
            'frames': sum(frames), 'durationSeconds': float(sum(frames)/fps)}
