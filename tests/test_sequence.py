import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import fixtures


class EditTest(unittest.TestCase):
    def test_edit_resolves_relative_inputs_and_preserves_caller_shot_order(self):
        from flashback_agent.sequence import load_edit
        with tempfile.TemporaryDirectory() as directory, fixtures.fake_bridges(Path(directory)):
            root = Path(directory).resolve()  # CI temp folders can be 8.3 short names; edits resolve paths
            with zipfile.ZipFile(root/'world.zip', 'w') as archive:
                archive.writestr('metadata.json', json.dumps({'version_string': fixtures.MINECRAFT, 'total_ticks': 200}))
            (root/'camera.json').write_text(json.dumps({'version':1,'camera':[{'tick':0,'position':[0,80,0],'yaw':0,'pitch':20}]}))
            edit = {'version':1,'replay':'world.zip','render':{'width':640,'height':360,'fps':24,'audio':False},
                    'shots':[{'range':'6-8','plan':'camera.json'}, {'range':'1-2','plan':'camera.json'}]}
            path = root/'edit.json'
            path.write_text(json.dumps(edit))
            result = load_edit(path)
            self.assertEqual([s['range'] for s in result['shots']], ['6-8','1-2'])
            self.assertEqual(result['shots'][0]['replay'], str(root/'world.zip'))
            self.assertEqual(result['shots'][0]['plan']['camera'][0]['position'], [0,80,0])
            edit['shots'][1]['range'] = '9-11'
            path.write_text(json.dumps(edit))
            with self.assertRaises(ValueError):
                load_edit(path)
            with zipfile.ZipFile(root/'other.zip', 'w') as archive:
                archive.writestr('metadata.json', json.dumps({'version_string': '9.8', 'total_ticks': 200}))
            edit['shots'][1] = {'replay': 'other.zip', 'range': '1-2', 'plan': 'camera.json'}
            path.write_text(json.dumps(edit))
            with self.assertRaisesRegex(ValueError, 'bridge builds: 9.9'):
                load_edit(path)


if __name__ == '__main__':
    unittest.main()
