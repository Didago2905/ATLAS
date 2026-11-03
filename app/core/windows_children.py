"""Owned Windows children: suspended creation, Job assignment, targeted shutdown."""
import ctypes
from ctypes import wintypes as w
import os
import subprocess
import time


class StartupFailure(RuntimeError):
    pass


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", w.DWORD),
                ("min_working_set", ctypes.c_size_t), ("max_working_set", ctypes.c_size_t),
                ("active_processes", w.DWORD), ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD), ("scheduling", w.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ["read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes"]]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ["user_time", "kernel_time", "period_user", "period_kernel"]] + [
        (name, w.DWORD) for name in ["page_faults", "total_processes", "active_processes", "terminated_processes"]]


class StartupInfo(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR), ("title", w.LPWSTR)] + [
        (name, w.DWORD) for name in ["x", "y", "width", "height", "chars_x", "chars_y", "fill", "flags"]] + [
        ("show", w.WORD), ("reserved_bytes", w.WORD), ("reserved_data", ctypes.c_void_p),
        ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


def _kernel():
    if os.name != "nt":
        raise StartupFailure("Development supervisor requires Windows")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
        "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                            ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)], w.BOOL),
        "ResumeThread": ([w.HANDLE], w.DWORD), "CloseHandle": ([w.HANDLE], w.BOOL),
        "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
        "GenerateConsoleCtrlEvent": ([w.DWORD, w.DWORD], w.BOOL),
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "IsProcessInJob": ([w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(k, name)
        function.argtypes, function.restype = arguments, result
    return k


class Child:
    def __init__(self, kernel, handle, pid, job):
        self.kernel, self.handle, self.pid, self.job = kernel, handle, pid, job

    def poll(self):
        if self.kernel.WaitForSingleObject(self.handle, 0) == 258:
            return None
        result = w.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(result)):
            raise StartupFailure("Owned child status unavailable")
        return int(result.value)

    def interrupt(self):
        if self.active_processes():
            self.kernel.GenerateConsoleCtrlEvent(1, self.pid)  # CTRL_BREAK for this group only.

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while self.active_processes():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        return True

    def active_processes(self):
        if not self.job:
            return int(self.poll() is None)
        info = Accounting()
        if not self.kernel.QueryInformationJobObject(self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise StartupFailure("Owned subtree status unavailable")
        return info.active_processes

    def close(self):
        self.finish_tree()
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def finish_tree(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None


class WindowsChildren:
    def __init__(self):
        self.kernel = _kernel()
        self.children = []
        self.job = self.new_job()

    def new_job(self):
        job = self.kernel.CreateJobObjectW(None, None)
        if not job:
            raise StartupFailure("Cannot create owned process job")
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        if not self.kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.kernel.CloseHandle(job)
            raise StartupFailure("Cannot configure owned process job")
        return job

    def spawn(self, command, environment, cwd):
        info = StartupInfo(cb=ctypes.sizeof(StartupInfo))
        process = ProcessInfo()
        child_job = self.new_job()
        arguments = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
        block = ctypes.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in
                                                       sorted(environment.items(), key=lambda item: item[0].upper())) + "\0\0")
        # SUSPENDED + NEW_PROCESS_GROUP + UNICODE_ENVIRONMENT; share this console
        # for targeted Ctrl+Break, but inherit NO handles (especially job handle).
        flags = 0x4 | 0x200 | 0x400
        try:
            if not self.kernel.CreateProcessW(command[0], arguments, None, None, False, flags,
                                              block, str(cwd), ctypes.byref(info), ctypes.byref(process)):
                self.kernel.CloseHandle(child_job)
                raise StartupFailure("Owned child creation failed")
        finally:
            ctypes.memset(block, 0, ctypes.sizeof(block))
        try:
            if not self.kernel.AssignProcessToJobObject(self.job, process.process):
                raise StartupFailure("Owned child could not join cleanup job")
            if not self.kernel.AssignProcessToJobObject(child_job, process.process):
                raise StartupFailure("Owned child could not join isolated subtree job")
            if self.kernel.ResumeThread(process.thread) == 0xFFFFFFFF:
                raise StartupFailure("Owned child could not start")
        except BaseException:
            self.kernel.CloseHandle(child_job)
            self.kernel.TerminateProcess(process.process, 1)
            self.kernel.CloseHandle(process.process)
            raise
        finally:
            self.kernel.CloseHandle(process.thread)
        child = Child(self.kernel, process.process, int(process.pid), child_job)
        self.children.append(child)
        return child

    def owns_listener(self, port):
        output = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5).stdout
        pids = {int(parts[4]) for line in output.splitlines() if len(parts := line.split()) == 5
                and parts[1].endswith(":" + str(port)) and parts[3] == "LISTENING"}
        if not pids:
            return False
        for pid in pids:
            process = self.kernel.OpenProcess(0x1000, False, pid)
            if not process:
                return False
            try:
                belongs = w.BOOL()
                if not self.kernel.IsProcessInJob(process, self.job, ctypes.byref(belongs)) or not belongs.value:
                    return False
            finally:
                self.kernel.CloseHandle(process)
        return True

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        for child in self.children:
            child.wait(5)
            child.close()
        self.children.clear()
