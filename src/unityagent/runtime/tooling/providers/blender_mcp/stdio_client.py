"""外部MCP Serverとの限定JSON-RPC stdio接続。依存導入と再送は行わない。"""
from __future__ import annotations
import json
import hashlib
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

    def __enter__(self):
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.identity = self.request('initialize', {'protocolVersion': '2024-11-05',
                'capabilities': {}, 'clientInfo': {'name': 'UnityAgent', 'version': '0.0.8'}})
            if self.identity.get('protocolVersion') not in {'2024-11-05', '2025-03-26'}:
                raise ValueError('Incompatible MCP protocol')
            self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            self.tools = {t['name'] for t in self.request('tools/list', {}).get('tools', [])}
            if 'get_scene_info' in self.tools:
                self.scene_observation = self.tool('get_scene_info', {})
                facts = self.scene_observation.get('structuredContent') or {}
                observed = facts.get('blender_session_identity')
                if isinstance(observed, str) and observed.strip():
                    self.blender_session_identity = observed
                    self.session_id = 'blender-' + hashlib.sha256(observed.encode('utf-8')).hexdigest()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

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
        if name not in {'get_scene_info', 'execute_blender_code'} or name not in self.tools:
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
