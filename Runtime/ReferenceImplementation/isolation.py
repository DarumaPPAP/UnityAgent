"""Bounded profile-selected specialist process and authenticated Windows IPC."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import multiprocessing.connection as mp_connection
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from typing import Any, Mapping

from .contracts import ContractValidationError, SurfaceGrant, TaskContract
from .profiles import ProfileValidationError, SubAgentProfile, CATALOG, profile_for_task_object


class IsolationError(RuntimeError):
    """The specialist cannot prove the required process/IPC boundary."""


class IsolationViolation(ContractValidationError):
    """A specialist requested a capability outside its SurfaceGrant."""


class SpecialistCapabilitySurface:
    """Allowlist exposed to a specialist process; it contains no executable API."""

    ALLOWED_MESSAGES = frozenset({"hello", "grant", "inspect", "propose_action", "capture", "evaluate", "complete"})
    FORBIDDEN_TOKENS = ("shell", "subprocess", "unity_cli", "installer", "install", "project_write", "filesystem_write", "exec")

    @classmethod
    def validate_message(cls, message: Mapping[str, Any]) -> None:
        if set(message) != {"session_id", "sequence", "message_type", "payload", "grant_id", "grant_digest"}:
            raise IsolationViolation("IPC message schema is not exact")
        if message["message_type"] not in cls.ALLOWED_MESSAGES:
            raise IsolationViolation("IPC message type is not exposed to the specialist")
        payload = message["payload"]
        if not isinstance(payload, Mapping):
            raise IsolationViolation("IPC payload must be an object")
        serialized = repr(message).casefold()
        if any(token in serialized for token in cls.FORBIDDEN_TOKENS):
            raise IsolationViolation("specialist IPC payload contains a forbidden capability token")
        sequence = message["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise IsolationViolation("IPC sequence must be a non-negative integer")


@dataclass(frozen=True)
class SpecialistSession:
    session_id: str
    subagent_instance_id: str
    nonce: str
    pipe_name: str
    task_id: str
    run_id: str
    grant_id: str
    grant_digest: str
    created_at: str
    expires_at: str
    profile_id: str = ""


class RuntimeIPCProtocol:
    def __init__(self, session: SpecialistSession, *, revocation_check: Any | None = None) -> None:
        self.session = session
        self._next_outbound = 0
        self._next_inbound = 0
        self._revoked = False
        self._revocation_check = revocation_check

    def revoke(self) -> None:
        self._revoked = True

    def _assert_session_active(self) -> None:
        if self._revoked:
            raise IsolationViolation("IPC session has been revoked")
        if self._revocation_check is not None:
            try:
                if self._revocation_check() is not True:
                    self._revoked = True
                    raise IsolationViolation("IPC session approval has been revoked")
            except IsolationViolation:
                raise
            except Exception as exc:
                self._revoked = True
                raise IsolationViolation(f"IPC session authority could not be revalidated: {exc}") from exc
        if self.session.expires_at:
            try:
                expires_at = datetime.fromisoformat(self.session.expires_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise IsolationViolation("IPC session expiry is invalid") from exc
            if expires_at <= datetime.now(timezone.utc):
                raise IsolationViolation("IPC session grant has expired")

    def make(self, message_type: str, payload: Mapping[str, Any], *, sequence: int | None = None) -> dict[str, Any]:
        self._assert_session_active()
        value = {
            "session_id": self.session.session_id,
            "sequence": self._next_outbound if sequence is None else sequence,
            "message_type": message_type,
            "payload": dict(payload),
            "grant_id": self.session.grant_id,
            "grant_digest": self.session.grant_digest,
        }
        SpecialistCapabilitySurface.validate_message(value)
        self._next_outbound = value["sequence"] + 1
        return value

    def accept(self, value: Mapping[str, Any]) -> dict[str, Any]:
        self._assert_session_active()
        SpecialistCapabilitySurface.validate_message(value)
        if value["session_id"] != self.session.session_id or value["grant_id"] != self.session.grant_id or value["grant_digest"] != self.session.grant_digest:
            raise IsolationViolation("IPC message is bound to a different session or grant")
        if value["sequence"] != self._next_inbound:
            raise IsolationViolation("IPC message was stale, replayed, or out of order")
        self._next_inbound += 1
        return dict(value)


class WindowsJobObject:
    """Small kill-on-close wrapper used when Windows exposes Job Objects."""

    def __init__(self) -> None:
        self.handle = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self._ctypes = ctypes
            self._wintypes = wintypes
            self.handle = ctypes.windll.kernel32.CreateJobObjectW(None, None)
            if self.handle not in (None, 0):
                self._configure_kill_on_close()

    @property
    def available(self) -> bool:
        return self.handle not in (None, 0)

    def assign(self, process: "SuspendedWindowsProcess") -> None:
        if not self.available:
            raise IsolationError("Windows Job Object is unavailable")
        kernel32 = self._ctypes.windll.kernel32
        kernel32.AssignProcessToJobObject.argtypes = [self._wintypes.HANDLE, self._wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = self._wintypes.BOOL
        if not kernel32.AssignProcessToJobObject(self.handle, process.process_handle):
            raise IsolationError("could not assign specialist process to Windows Job Object")

    def resume(self, process: "SuspendedWindowsProcess") -> None:
        if not self.available:
            raise IsolationError("Windows Job Object is unavailable")
        kernel32 = self._ctypes.windll.kernel32
        kernel32.ResumeThread.argtypes = [self._wintypes.HANDLE]
        kernel32.ResumeThread.restype = self._wintypes.DWORD
        result = kernel32.ResumeThread(process.thread_handle)
        if result == 0xFFFFFFFF:
            raise IsolationError("could not resume specialist process after Job Object assignment")

    def _configure_kill_on_close(self) -> None:
        ctypes = self._ctypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_ulonglong), ("WriteOperationCount", ctypes.c_ulonglong), ("OtherOperationCount", ctypes.c_ulonglong), ("ReadTransferCount", ctypes.c_ulonglong), ("WriteTransferCount", ctypes.c_ulonglong), ("OtherTransferCount", ctypes.c_ulonglong)]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimitInformation), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not ctypes.windll.kernel32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
            raise IsolationError("could not configure JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE")

    def close(self) -> None:
        if self.handle not in (None, 0):
            self._ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


class SuspendedWindowsProcess:
    """Native CreateProcess wrapper that remains suspended until Job assignment."""

    CREATE_SUSPENDED = 0x00000004
    CREATE_NO_WINDOW = 0x08000000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    INFINITE = 0xFFFFFFFF

    def __init__(self, args: list[str], *, cwd: str, env: Mapping[str, str]) -> None:
        if os.name != "nt":
            raise IsolationError("suspended Windows process launch is unavailable on this host")
        import ctypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32

        class StartupInfo(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", wintypes.LPBYTE),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class ProcessInformation(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        kernel32.CreateProcessW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID, wintypes.LPVOID,
            wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
            ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInformation),
        ]
        kernel32.CreateProcessW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL

        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
        environment_block = "\0".join(f"{key}={value}" for key, value in env.items()) + "\0\0"
        environment_buffer = ctypes.create_unicode_buffer(environment_block)
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(StartupInfo)
        startup.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process_info = ProcessInformation()
        created = kernel32.CreateProcessW(
            str(args[0]), command_line, None, None, False,
            self.CREATE_SUSPENDED | self.CREATE_NO_WINDOW | self.CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(environment_buffer, wintypes.LPVOID), cwd,
            ctypes.byref(startup), ctypes.byref(process_info),
        )
        if not created:
            raise ctypes.WinError(ctypes.get_last_error())
        self.process_handle = process_info.hProcess
        self.thread_handle = process_info.hThread
        self.pid = int(process_info.dwProcessId)
        self.returncode: int | None = None

    def _read_exit_code(self) -> int:
        code = self._wintypes.DWORD()
        if not self._kernel32.GetExitCodeProcess(self.process_handle, self._ctypes.byref(code)):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return int(code.value)

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if self._kernel32.WaitForSingleObject(self.process_handle, 0) == self.WAIT_OBJECT_0:
            self.returncode = self._read_exit_code()
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        milliseconds = self.INFINITE if timeout is None else max(0, int(timeout * 1000))
        result = self._kernel32.WaitForSingleObject(self.process_handle, milliseconds)
        if result == self.WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired("specialist process", timeout)
        if result != self.WAIT_OBJECT_0:
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        self.returncode = self._read_exit_code()
        return self.returncode

    def kill(self) -> None:
        if self.poll() is None and not self._kernel32.TerminateProcess(self.process_handle, 1):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self) -> None:
        if self.thread_handle not in (None, 0):
            self._kernel32.CloseHandle(self.thread_handle)
            self.thread_handle = None
        if self.process_handle not in (None, 0):
            self._kernel32.CloseHandle(self.process_handle)
            self.process_handle = None


class WindowsNamedPipeServer:
    def __init__(self, session: SpecialistSession) -> None:
        if os.name != "nt":
            raise IsolationError("Windows Named Pipe capability is unavailable on this host")
        self.session = session
        self._listener_handle = None
        self._security_descriptor = None
        self._kernel32 = None
        self._closed = False
        try:
            self._create_session_pipe()
        except Exception:
            self.close()
            raise

    def _create_session_pipe(self) -> None:
        """Create one session-owned pipe without mutating multiprocessing globals."""
        ctypes = __import__("ctypes")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._kernel32 = kernel32
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.ULONG)
        ]
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
        advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        advapi32.LocalFree.argtypes = [wintypes.HLOCAL]
        advapi32.LocalFree.restype = wintypes.HLOCAL
        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", wintypes.LPVOID),
                ("bInheritHandle", wintypes.BOOL),
            ]

        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise IsolationError("could not open the current Windows process token for pipe ACL binding")
        sid_buffer = None
        sid_text = wintypes.LPWSTR()
        try:
            required_size = wintypes.DWORD()
            advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required_size))
            if not required_size.value:
                raise IsolationError("current Windows user SID size was not observed")
            sid_buffer = ctypes.create_string_buffer(required_size.value)
            if not advapi32.GetTokenInformation(token, 1, sid_buffer, required_size, ctypes.byref(required_size)):
                raise IsolationError("could not observe the current Windows user SID")

            class SidAndAttributes(ctypes.Structure):
                _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

            class TokenUser(ctypes.Structure):
                _fields_ = [("User", SidAndAttributes)]

            user = ctypes.cast(sid_buffer, ctypes.POINTER(TokenUser)).contents
            if not user.User.Sid or not advapi32.ConvertSidToStringSidW(user.User.Sid, ctypes.byref(sid_text)):
                raise IsolationError("could not convert the current Windows user SID")
            current_user_sid = sid_text.value
        finally:
            if sid_text:
                advapi32.LocalFree(sid_text)
            kernel32.CloseHandle(token)

        security_descriptor = ctypes.c_void_p()
        security_descriptor_size = ctypes.c_ulong()
        # Explicitly authorize only the current user.  There is deliberately no
        # broad principal ACE and no process-wide CreateNamedPipe replacement.
        sddl = f"D:(A;;GRGW;;;{current_user_sid})"
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl,
            1,  # SDDL_REVISION_1
            ctypes.byref(security_descriptor),
            ctypes.byref(security_descriptor_size),
            ):
            raise IsolationError("could not create Named Pipe security descriptor")
        self._security_descriptor = (advapi32, security_descriptor)
        security_attributes = SecurityAttributes(
            ctypes.sizeof(SecurityAttributes), security_descriptor, False
        )
        flags = 0x00000003 | 0x40000000 | 0x00080000  # DUPLEX | OVERLAPPED | FIRST_PIPE_INSTANCE
        pipe_mode = 0x00000004 | 0x00000002 | 0x00000000 | 0x00000008  # MESSAGE | READMODE_MESSAGE | WAIT | REJECT_REMOTE_CLIENTS
        handle = kernel32.CreateNamedPipeW(
            session.pipe_name,
            flags,
            pipe_mode,
            1,
            0x1000,
            0x1000,
            0xFFFFFFFF,
            ctypes.byref(security_attributes),
        )
        if handle in (None, 0, wintypes.HANDLE(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        self._listener_handle = handle

    def _accept_once(self):
        if self._listener_handle in (None, 0):
            raise IsolationError("Named Pipe listener is closed")
        winapi = mp_connection._winapi
        handle = self._listener_handle
        try:
            overlapped = winapi.ConnectNamedPipe(handle, overlapped=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) != winapi.ERROR_NO_DATA:
                raise
        else:
            wait_result = winapi.WaitForMultipleObjects([overlapped.event], False, winapi.INFINITE)
            try:
                if wait_result != winapi.WAIT_OBJECT_0:
                    raise IsolationError("Named Pipe connection wait failed")
                _, error = overlapped.GetOverlappedResult(True)
                if error:
                    raise OSError(error, "ConnectNamedPipe failed")
            except BaseException:
                overlapped.cancel()
                raise
        self._listener_handle = None
        connection = mp_connection.PipeConnection(handle)
        try:
            authkey = bytes.fromhex(self.session.nonce)
            # This side is the Named Pipe server.  ``Client`` in the bounded
            # specialist performs the matching answer_challenge call; calling
            # it here as well would make the server wait for a second client
            # challenge and break the authenticated handshake.
            mp_connection.deliver_challenge(connection, authkey)
        except BaseException:
            connection.close()
            raise
        return connection

    def accept(self, timeout_seconds: float = 15.0):
        result: queue.Queue[Any] = queue.Queue(maxsize=1)

        def accept_worker() -> None:
            try:
                result.put(self._accept_once())
            except BaseException as exc:  # pragma: no cover - transport-specific
                result.put(exc)

        thread = threading.Thread(target=accept_worker, name="unityagent-ipc-accept", daemon=True)
        thread.start()
        try:
            value = result.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise IsolationError("specialist IPC connection timed out") from exc
        if isinstance(value, BaseException):
            raise IsolationError(f"specialist IPC accept failed: {value}") from value
        return value

    def close(self) -> None:
        self._closed = True
        if self._listener_handle not in (None, 0) and self._kernel32 is not None:
            self._kernel32.CloseHandle(self._listener_handle)
            self._listener_handle = None
        if self._security_descriptor is not None:
            advapi32, descriptor = self._security_descriptor
            advapi32.LocalFree(descriptor)
            self._security_descriptor = None


class SubAgentSessionManager:
    """Starts one bounded specialist and keeps all execution on Runtime IPC."""

    def create_session(self, *, task: TaskContract, grant: SurfaceGrant, profile: SubAgentProfile | None = None) -> SpecialistSession:
        selected = profile or profile_for_task_object(task)
        if os.name != "nt":
            raise IsolationError("specialist requires Windows Named Pipe isolation")
        if grant.task_id != task.task_id or grant.run_id != task.run_id:
            raise IsolationViolation("grant does not bind to session task")
        now = datetime.now(timezone.utc)
        return SpecialistSession(
            session_id=f"session-{uuid.uuid4().hex}",
            subagent_instance_id=grant.subagent_instance_id,
            nonce=uuid.uuid4().hex,
            pipe_name=rf"\\.\pipe\UnityAgent-{uuid.uuid4().hex}",
            task_id=task.task_id,
            run_id=task.run_id,
            grant_id=grant.grant_id,
            grant_digest=grant.grant_digest,
            created_at=now.isoformat(),
            expires_at=grant.expires_at,
            profile_id=selected.profile_id,
        )

    def run(
        self,
        *,
        task: TaskContract,
        grant: SurfaceGrant,
        context: Mapping[str, Any],
        approval_resolver: Any | None = None,
        profile: SubAgentProfile | None = None,
        timeout_seconds: float = 15.0,
    ) -> list[dict[str, Any]]:
        return self._run(task=task, grant=grant, context=context, approval_resolver=approval_resolver, profile=profile, timeout_seconds=timeout_seconds)

    def _run(
        self,
        *,
        task: TaskContract,
        grant: SurfaceGrant,
        context: Mapping[str, Any],
        approval_resolver: Any | None,
        profile: SubAgentProfile | None,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        selected = profile or profile_for_task_object(task)
        if timeout_seconds <= 0:
            raise IsolationError("specialist IPC deadline must be positive")
        session = self.create_session(task=task, grant=grant, profile=selected)
        server = WindowsNamedPipeServer(session)
        job = WindowsJobObject()
        if not job.available:
            server.close()
            raise IsolationError("Windows Job Object is unavailable; specialist launch is fail-closed")
        child_env = self._child_environment(session)
        process: SuspendedWindowsProcess | None = None
        connection: Any | None = None
        deadline = time.monotonic() + float(timeout_seconds)

        def receive() -> Any:
            if connection is None:
                raise IsolationError("specialist IPC connection is not established")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not connection.poll(remaining):
                raise IsolationError("specialist IPC response exceeded its deadline")
            return connection.recv()

        try:
            # CreateProcess starts the child suspended.  The primary process
            # handle is assigned to the configured Job Object before the
            # primary thread can execute any specialist code.
            process = SuspendedWindowsProcess(
                [sys.executable, "-m", CATALOG.definition(selected.profile_id).session_entrypoint],
                cwd=str(Path(__file__).resolve().parents[2]),
                env=child_env,
            )
            job.assign(process)
            job.resume(process)
            connection = server.accept(timeout_seconds=max(0.1, deadline - time.monotonic()))
            def authority_check() -> bool:
                if approval_resolver is None:
                    return True
                approval_resolver.resolve(grant.approval_decision_id, task=task)
                return True

            protocol = RuntimeIPCProtocol(session, revocation_check=authority_check)
            hello = protocol.accept(receive())
            if hello["message_type"] != "hello":
                raise IsolationViolation("specialist did not establish the expected identity handshake")
            if hello["payload"].get("subagent_instance_id") != session.subagent_instance_id:
                raise IsolationViolation("specialist instance identity does not bind to SurfaceGrant")
            if hello["payload"].get("audience") != selected.audience:
                raise IsolationViolation("specialist audience does not bind to the selected SubAgent profile")
            payload = {"task_envelope": task.to_envelope(), "grant_envelope": grant.to_envelope(), "context": dict(context)}
            if isinstance(context.get("approval"), Mapping):
                payload["approval_envelope"] = {"contract_type": "ApprovalDecision", "value": dict(context["approval"])}
            connection.send(protocol.make("grant", payload))
            events: list[dict[str, Any]] = []
            while True:
                message = protocol.accept(receive())
                events.append(message)
                if message["message_type"] == "complete":
                    break
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            return events
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            job.close()
            server.close()
            if process is not None:
                process.close()

    @staticmethod
    def _child_environment(session: SpecialistSession) -> dict[str, str]:
        python_dir = str(Path(sys.executable).parent)
        repo_root = str(Path(__file__).resolve().parents[2])
        env: dict[str, str] = {
            "PATH": python_dir,
            "PYTHONPATH": repo_root,
            "PYTHONUTF8": "1",
            "UNITY_AGENT_IPC_ADDRESS": session.pipe_name,
            "UNITY_AGENT_IPC_NONCE": session.nonce,
            "UNITY_AGENT_SESSION_ID": session.session_id,
            "UNITY_AGENT_SUBAGENT_INSTANCE_ID": session.subagent_instance_id,
            "UNITY_AGENT_GRANT_ID": session.grant_id,
            "UNITY_AGENT_GRANT_DIGEST": session.grant_digest,
            "UNITY_AGENT_PROFILE_ID": session.profile_id,
        }
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                env[name] = os.environ[name]
        # Some packaged Windows hosts expose SystemRoot as the expandable
        # string ``%SystemDrive%\\Windows``.  The child receives a deliberately
        # small environment, so include the expansion anchor explicitly; this
        # prevents native runtime caches from being written under the project
        # working directory as a literal ``%SystemDrive%`` path.
        system_drive = os.environ.get("SystemDrive") or Path(sys.executable).drive
        if system_drive:
            env["SystemDrive"] = system_drive
        return env


def assert_specialist_boundary(message: Mapping[str, Any]) -> None:
    """Public negative-test hook: forbidden direct surfaces must be rejected."""
    SpecialistCapabilitySurface.validate_message(message)
