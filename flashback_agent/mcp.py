"""Optional MCP stdio adapter. Skill users can call the same tools via the CLI."""
import json
import sys
from .tools import TOOLS, call_tool


def serve(game_dir=None, server_dir=None):
    def send(message):
        print(json.dumps(message, ensure_ascii=False, allow_nan=False), flush=True)

    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Expected JSON-RPC object')
            if request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str) or not isinstance(request.get('params', {}), dict):
                raise ValueError('Invalid JSON-RPC request')
            method = request.get('method')
            if 'id' not in request:  # initialized/cancellation notifications have no reply
                continue
            if method == 'initialize':
                requested = request.get('params', {}).get('protocolVersion')
                result = {'protocolVersion': requested if requested in ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25') else '2025-11-25',
                          'capabilities': {'tools': {}}, 'serverInfo': {'name': 'flashback-carpet-tools', 'version': '0.4.0'},
                          'instructions': 'Use tool descriptions and returned state. Inputs are not proof of scene outcomes. Ongoing bot actions expire in game ticks; a disconnected MCP caller does not cancel them.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = request.get('params', {})
                try:
                    value = call_tool(params['name'], params.get('arguments', {}), game_dir=game_dir, server_dir=server_dir)
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}],
                              'isError': value['state'] != 'completed'}
                except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as exc:
                    result = {'content': [{'type': 'text', 'text': str(exc)}], 'isError': True}
            else:
                send({'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32601, 'message': 'Method not found'}})
                continue
            send({'jsonrpc': '2.0', 'id': request['id'], 'result': result})
        except json.JSONDecodeError as exc:
            send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': str(exc)}})
        except (ValueError, KeyError, TypeError) as exc:
            send({'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                  'error': {'code': -32600, 'message': str(exc)}})
