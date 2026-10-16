"""外部MCP Serverとの限定JSON-RPC stdio接続。依存導入と再送は行わない。"""
from __future__ import annotations
import json
import hashlib
import os
import queue
import subprocess
import threading
import uuid


class McpStdioClient:
    def __init__(self, command, *, timeout_seconds=30):
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError('Explicit MCP server command is required')
        self.command = command
        self.timeout = timeout_seconds
        self.session_id = uuid.uuid4().hex
        self.process = None
        self.messages = queue.Queue()
        self.counter = 0
        self.identity = None
        self.blender_session_identity = None
        self.scene_observation = None
        self.tools = set()
        self.addon_version = 'unmeasured'
        self.blender_version = 'unmeasured'
        self._session_attestation = None

    def __enter__(self):
        # AST Safe Mode is required; this is not an OS sandbox.
        child_env = dict(os.environ)
        child_env['BLENDER_MCP_SAFE_MODE'] = '1'
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                        bufsize=1, env=child_env)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.identity = self.request('initialize', {'protocolVersion': '2024-11-05',
                'capabilities': {}, 'clientInfo': {'name': 'UnityAgent', 'version': '0.0.8'}})
            if self.identity.get('protocolVersion') not in {'2024-11-05', '2025-03-26'}:
                raise ValueError('Incompatible MCP protocol')
            self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            self.tools = {t['name'] for t in self.request('tools/list', {}).get('tools', [])}
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise


    @staticmethod
    def _text_result(result):
        if not isinstance(result, dict) or result.get('isError'):
            raise ValueError('Blender MCP observation failed')
        parts = [p.get('text') for p in result.get('content', [])
                 if isinstance(p, dict) and p.get('type') == 'text' and isinstance(p.get('text'), str)]
        if len(parts) != 1:
            raise ValueError('Blender MCP response lacks one text observation')
        return parts[0]

    def _observe_session(self):
        """Upstream text-only MCP status + live bpy runtime observation."""
        required = {'get_scene_info', 'get_addon_status', 'execute_blender_code'}
        if not required.issubset(self.tools):
            raise ValueError('MCP addon/status/session observation tools unavailable')
        status_text = self._text_result(self.tool('get_addon_status', {}))
        status, _ = json.JSONDecoder().raw_decode(status_text.lstrip())
        if (not isinstance(status, dict) or status.get('up_to_date') is not True
                or status.get('protocol_version') != status.get('expected_protocol_version')
                or not status.get('addon_version') or not status.get('blender_version')):
            raise ValueError('Blender MCP addon/protocol compatibility not verified')
        scene_text = self._text_result(self.tool('get_scene_info', {}))
        if not scene_text.strip() or scene_text.lstrip().startswith(('Error', 'Could not')):
            raise ValueError('Blender live scene observation unavailable')
        # Upstream get_scene_info returns text, not structuredContent.blender_session_identity.
        # Fixed read-only bpy script. Pointer is a process-bound hint, NOT OS attestation.
        probe = (
            'import bpy, json\n'
            'print("UNITYAGENT_SESSION_V1:" + json.dumps({"wm_pointer": '
            'bpy.context.window_manager.as_pointer(), '
            '"blender_version": bpy.app.version_string}))'
        )
        observed_text = self._text_result(self.tool('execute_blender_code', {'code': probe}))
        marker = 'UNITYAGENT_SESSION_V1:'
        if observed_text.count(marker) != 1:
            raise ValueError('Blender live runtime identity missing')
        document = observed_text.split(marker, 1)[1].lstrip()
        observation, position = json.JSONDecoder().raw_decode(document)
        if document[position:].strip():
            raise ValueError('Blender runtime identity has trailing content')
        if (not isinstance(observation, dict) or isinstance(observation.get('wm_pointer'), bool)
                or not isinstance(observation.get('wm_pointer'), int) or observation['wm_pointer'] <= 0
                or observation.get('blender_version') != status['blender_version']):
            raise ValueError('Blender runtime identity and addon status disagree')
        return {'wm_pointer': observation['wm_pointer'], 'blender_version': status['blender_version'],
                'addon_version': status['addon_version'], 'protocol_version': status['protocol_version'],
                'server': self.identity.get('serverInfo')}

    def bind_session(self):
        """Called only after approved Plan verification; never from Doctor."""
        observation = self._observe_session()
        self._session_attestation = observation
        token = hashlib.sha256(json.dumps(observation, sort_keys=True).encode('utf-8')).hexdigest()
        self.blender_session_identity = token
        self.session_id = 'blender-' + token
        self.blender_version = observation['blender_version']
        self.addon_version = observation['addon_version']
        return self.session_id

    def recheck_session(self):
        if self._session_attestation is None or self._observe_session() != self._session_attestation:
            raise ValueError('Blender session changed; manual reconciliation required')

    def _read(self):
        for line in self.process.stdout:
            try: self.messages.put(json.loads(line))
            except ValueError: self.messages.put({'error': 'Malformed MCP server output'})
        self.messages.put({'error': 'MCP server closed'})

    def _send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        identifier = self.counter
        self._send({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params})
        import time
        deadline = time.monotonic() + self.timeout
        while True:
            try: message = self.messages.get(timeout=max(0, deadline-time.monotonic()))
            except queue.Empty as exc: raise TimeoutError('MCP result not observed; do not resubmit mutation') from exc
            if 'id' not in message and 'error' not in message:
                continue
            if 'error' in message:
                raise ValueError(str(message['error']))
            if message.get('id') == identifier:
                return message['result']

    def tool(self, name, arguments):
        if name not in {'get_scene_info', 'get_addon_status', 'execute_blender_code'} or name not in self.tools:
            raise ValueError('Required reviewed Blender MCP tool is unavailable')
        result = self.request('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise ValueError('Blender MCP tool failed: ' + json.dumps(result.get('content')))
        return result

    def __exit__(self, *_):
        if self.process is not None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
