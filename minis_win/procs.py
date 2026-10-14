"""Process facts through ctypes only (no psutil, no WMI, no PowerShell): list processes, image path, CPU time, command line.

Used for two things: detecting known AI programs (sources.py) and proving a pid is ours before `stop` kills it.
Command lines are only pattern-matched or compared, never stored, logged or printed.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as wt

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
ntdll = ctypes.WinDLL('ntdll')
shell32 = ctypes.WinDLL('shell32', use_last_error=True)

TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD), ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', wt.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [('Length', wt.USHORT), ('MaximumLength', wt.USHORT), ('Buffer', ctypes.c_void_p)]


kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
ntdll.NtQueryInformationProcess.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.ULONG, ctypes.POINTER(wt.ULONG)]
ntdll.NtQueryInformationProcess.restype = ctypes.c_long
shell32.CommandLineToArgvW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
shell32.CommandLineToArgvW.restype = ctypes.POINTER(wt.LPWSTR)


def list_processes():
    """-> [(pid, ppid, exe name lower-case)]"""
    out = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((int(e.th32ProcessID), int(e.th32ParentProcessID), e.szExeFile.lower()))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


class _Handle:
    def __init__(self, pid):
        self.h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)) if int(pid) > 0 else None

    def __enter__(self):
        return self.h

    def __exit__(self, *a):
        if self.h:
            kernel32.CloseHandle(self.h)


def alive(pid):
    with _Handle(pid) as h:
        if not h:
            return False
        code = wt.DWORD()
        if not kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE


def image_path(pid):
    with _Handle(pid) as h:
        if not h:
            return None
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return None
        return buf.value


def _ft(f):
    return (f.dwHighDateTime << 32) | f.dwLowDateTime


def times(pid):
    """-> (creation time as an opaque int, CPU seconds kernel+user) or None if the process cannot be queried."""
    with _Handle(pid) as h:
        if not h:
            return None
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return _ft(c), (_ft(k) + _ft(u)) / 1e7


def cmdline(pid):
    """The process's command line (ProcessCommandLineInformation, Windows 8.1+), or None when it cannot be read."""
    with _Handle(pid) as h:
        if not h:
            return None
        need = wt.ULONG(0)
        ntdll.NtQueryInformationProcess(h, 60, None, 0, ctypes.byref(need))
        if need.value < ctypes.sizeof(UNICODE_STRING) or need.value > 1 << 20:
            return None
        buf = ctypes.create_string_buffer(need.value)
        st = ntdll.NtQueryInformationProcess(h, 60, buf, need.value, ctypes.byref(need))
        if st != 0:
            return None
        us = UNICODE_STRING.from_buffer(buf)
        if not us.Buffer or not us.Length:
            return ''
        return ctypes.wstring_at(us.Buffer, us.Length // 2)


def split_cmdline(s):
    """Windows argv rules (CommandLineToArgvW)."""
    if not s:
        return []
    n = ctypes.c_int(0)
    arr = shell32.CommandLineToArgvW(s, ctypes.byref(n))
    if not arr:
        return []
    try:
        return [arr[i] for i in range(n.value)]
    finally:
        kernel32.LocalFree(ctypes.cast(arr, ctypes.c_void_p))


def argv(pid):
    s = cmdline(pid)
    return None if s is None else split_cmdline(s)


class Info:
    """The real process facts, in the shape sources.ProcessScanner expects (tests inject a fake with the same methods)."""
    list = staticmethod(list_processes)
    path = staticmethod(image_path)
    times = staticmethod(times)
    argv = staticmethod(argv)
