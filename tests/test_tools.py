import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from flashback_agent.tools import submit_tool, validate_call


class ToolsTest(unittest.TestCase):
    def test_unbounded_actions_and_ambiguous_controls_rejected(self):
        for name, arguments in [
            ('carpet_move', {'name': 'Actor', 'forward': 1}),
            ('carpet_move', {'name': 'Actor', 'forward': 1, 'ticks': True}),
            ('carpet_action', {'name': 'Actor', 'action': 'attack', 'mode': 'continuous'}),
            ('carpet_action', {'name': 'Actor', 'action': 'jump', 'mode': 'once', 'ticks': 20}),
            ('carpet_look', {'name': 'Actor', 'at': [0, 0, 0], 'yaw': 90}),
            ('carpet_spawn', {'name': 'Actor\nstop', 'position': [0, 0, 0]}),
            ('carpet_spawn', {'name': 'Actor', 'position': [0, float('nan'), 0]}),
            ('carpet_command', {'command': 'time set day\nstop'}),
        ]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                validate_call(name, arguments)

    def test_queue_pins_server_session_and_refuses_stale_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'carpet-agent'
            root.mkdir()
            health = {'protocolVersion': 1, 'minecraft': '26.2', 'session': 'world-A',
                      'updatedAt': time.time()*1000, 'state': 'ready'}
            (root/'bridge.json').write_text(json.dumps(health))
            job = submit_tool('carpet_move', {'name': 'Actor', 'forward': 1, 'ticks': 20}, server_dir=tmp)
            request = json.loads((job/'request.json').read_text())
            self.assertEqual(request['session'], 'world-A')
            self.assertGreater(request['expiresAt'], time.time()*1000)
            health['updatedAt'] = 0
            (root/'bridge.json').write_text(json.dumps(health))
            with self.assertRaises(RuntimeError):
                submit_tool('carpet_list', {}, server_dir=tmp)
            self.assertEqual(len(list((root/'jobs').iterdir())), 1)

    def test_stdio_mcp_discovery_and_failure_are_protocol_messages(self):
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'carpet_move', 'arguments': {'name': 'Actor'}}},
        ]
        proc = subprocess.run([sys.executable, '-m', 'flashback_agent', 'mcp'],
                              input=''.join(json.dumps(m)+'\n' for m in messages), text=True, capture_output=True, check=True)
        replies = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([r['id'] for r in replies], [1, 2, 3])
        self.assertEqual(replies[0]['result']['protocolVersion'], '2025-11-25')
        schemas = {t['name']: t['inputSchema'] for t in replies[1]['result']['tools']}
        self.assertIn('ticks', schemas['carpet_move']['required'])
        self.assertIn('record_stop', schemas)
        self.assertTrue(replies[2]['result']['isError'])


if __name__ == '__main__':
    unittest.main()
