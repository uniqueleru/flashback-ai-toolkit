from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required')
class AssemblyTest(unittest.TestCase):
    def test_review_extracts_bounded_frames_for_inspection(self):
        from flashback_agent.media import review
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=128x72:r=24',
                            '-t','1','-c:v','libx264',str(clip)],check=True)
            result = review(clip, root/'frames', every=.25, max_frames=3)
            self.assertEqual(len(result['frames']), 3)
            self.assertTrue(all(Path(f).read_bytes().startswith(b'\x89PNG') for f in result['frames']))
            with self.assertRaises(FileExistsError):
                review(clip, root/'frames')

    def test_ordered_cuts_preserve_frames_and_refuse_overwrite(self):
        from flashback_agent.media import assemble, probe
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = []
            for color in ('red', 'blue'):
                clip = root / f'{color}.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color={color}:s=64x64:r=24',
                                '-t', '0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True)
                clips.append(clip)
            output = root / 'edit.mp4'
            result = assemble(clips, output)
            info = probe(output)
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(int(info['video']['nb_frames']), 24)
            pixels = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output), '-vf', 'scale=1:1',
                                              '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
            self.assertGreater(pixels[0], pixels[2] + 100)
            self.assertGreater(pixels[-1], pixels[-3] + 100)
            original = output.read_bytes()
            with self.assertRaises(FileExistsError):
                assemble(list(reversed(clips)), output)
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
