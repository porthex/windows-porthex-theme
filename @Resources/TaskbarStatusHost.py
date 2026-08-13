"""Keep the Porthex Rainmeter indicator taskbar-bound and fullscreen-aware.

Windows 11's XAML taskbar does not visually compose arbitrary cross-process
child windows. The indicator therefore remains a top-level Rainmeter window,
but this helper pins it to unused taskbar space and hides it whenever the
foreground application truly covers its monitor (for example browser F11).
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
MONITOR_DEFAULTTONEAREST = 2
HWND_TOPMOST = ctypes.c_void_p(-1).value

SKIN_TITLE_SUFFIX = r"\WindowsPorthexTheme\TaskbarStatus\TaskbarStatus.ini"
RAINMETER = r"C:\Program Files\Rainmeter\Rainmeter.exe"
STATE_PATH = Path(__file__).with_name("TaskbarStatusHost.state.json")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


USER32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
USER32.FindWindowW.restype = wintypes.HWND
USER32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
USER32.EnumWindows.restype = wintypes.BOOL
USER32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
USER32.EnumChildWindows.restype = wintypes.BOOL
USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
USER32.GetWindowTextLengthW.restype = ctypes.c_int
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetWindowTextW.restype = ctypes.c_int
USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetClassNameW.restype = ctypes.c_int
USER32.GetParent.argtypes = [wintypes.HWND]
USER32.GetParent.restype = wintypes.HWND
USER32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
USER32.SetParent.restype = wintypes.HWND
USER32.IsWindow.argtypes = [wintypes.HWND]
USER32.IsWindow.restype = wintypes.BOOL
USER32.IsWindowVisible.argtypes = [wintypes.HWND]
USER32.IsWindowVisible.restype = wintypes.BOOL
USER32.GetForegroundWindow.restype = wintypes.HWND
USER32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
USER32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
USER32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
USER32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
USER32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
USER32.SetWindowPos.restype = wintypes.BOOL
USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
USER32.ShowWindow.restype = wintypes.BOOL
USER32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
USER32.GetWindowRect.restype = wintypes.BOOL
USER32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
USER32.MonitorFromWindow.restype = wintypes.HANDLE
USER32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
USER32.GetMonitorInfoW.restype = wintypes.BOOL
KERNEL32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
KERNEL32.CreateMutexW.restype = wintypes.HANDLE


def window_text(hwnd: int) -> str:
    length = USER32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    USER32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def rect(hwnd: int) -> tuple[int, int, int, int]:
    value = wintypes.RECT()
    USER32.GetWindowRect(hwnd, ctypes.byref(value))
    return value.left, value.top, value.right, value.bottom


def find_status(tray: int) -> int:
    found: list[int] = []

    @WNDENUMPROC
    def visit(hwnd: int, _lparam: int) -> bool:
        if class_name(hwnd) == "RainmeterMeterWindow" and window_text(hwnd).endswith(SKIN_TITLE_SUFFIX):
            found.append(hwnd)
            return False
        return True

    USER32.EnumWindows(visit, 0)
    if not found and tray:
        USER32.EnumChildWindows(tray, visit, 0)
    return found[0] if found else 0


def foreground_is_fullscreen() -> bool:
    hwnd = USER32.GetForegroundWindow()
    if not hwnd or not USER32.IsWindowVisible(hwnd):
        return False
    if class_name(hwnd) in {
        "Shell_TrayWnd",
        "Progman",
        "WorkerW",
        "RainmeterMeterWindow",
        "Windows.UI.Core.CoreWindow",
    }:
        return False

    monitor = USER32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not monitor or not USER32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False

    left, top, right, bottom = rect(hwnd)
    bounds = info.rcMonitor
    # Borderless/fullscreen windows can be one or two physical pixels short due
    # compositor rounding. Treat that as fullscreen instead of oscillating at
    # the monitor boundary.
    tolerance = 2
    return (
        left <= bounds.left + tolerance
        and top <= bounds.top + tolerance
        and right >= bounds.right - tolerance
        and bottom >= bounds.bottom - tolerance
    )


def bind_to_taskbar(hwnd: int, tray: int, hide_for_fullscreen: bool) -> str:
    # Undo the abandoned cross-process child-host attempt; Windows 11's XAML
    # taskbar hit-tests such a child but does not visually compose it.
    if USER32.GetParent(hwnd):
        USER32.SetParent(hwnd, None)

    style = USER32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    wanted_style = (style | WS_POPUP) & ~WS_CHILD
    if style != wanted_style:
        USER32.SetWindowLongPtrW(hwnd, GWL_STYLE, wanted_style)

    exstyle = USER32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    wanted_exstyle = exstyle | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    if exstyle != wanted_exstyle:
        USER32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, wanted_exstyle)

    if hide_for_fullscreen:
        if USER32.IsWindowVisible(hwnd):
            USER32.ShowWindow(hwnd, SW_HIDE)
        return "hidden_fullscreen"

    tray_left, tray_top, _tray_right, _tray_bottom = rect(tray)
    target = (tray_left + 16, tray_top + 10, tray_left + 172, tray_top + 38)
    is_visible = bool(USER32.IsWindowVisible(hwnd))
    needs_position = rect(hwnd) != target
    is_topmost = bool(USER32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0x00000008)

    if not is_visible:
        USER32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    if not is_visible or needs_position or not is_topmost:
        if not USER32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            target[0],
            target[1],
            156,
            28,
            SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    return "visible_taskbar"


def refresh_skin() -> None:
    subprocess.Popen(
        [RAINMETER, "!Refresh", r"WindowsPorthexTheme\TaskbarStatus"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )


def write_state(hwnd: int, tray: int, status: str, error: str = "") -> None:
    payload = {
        "pid": os.getpid(),
        "status": status,
        "error": error,
        "taskbar_hwnd": int(tray),
        "status_hwnd": int(hwnd),
        "parent_hwnd": int(USER32.GetParent(hwnd) or 0) if hwnd and USER32.IsWindow(hwnd) else 0,
        "rect": list(rect(hwnd)) if hwnd and USER32.IsWindow(hwnd) else [0, 0, 0, 0],
        "visible": bool(USER32.IsWindowVisible(hwnd)) if hwnd and USER32.IsWindow(hwnd) else False,
        "style": hex(USER32.GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF) if hwnd and USER32.IsWindow(hwnd) else "0x0",
        "exstyle": hex(USER32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF) if hwnd and USER32.IsWindow(hwnd) else "0x0",
        "updated_unix": time.time(),
    }
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(STATE_PATH)


def main() -> None:
    mutex = KERNEL32.CreateMutexW(None, False, "Local\\PorthexTaskbarStatusHost")
    if not mutex or ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return

    hwnd = 0
    missing_cycles = 0
    last_state = ""
    last_state_write = 0.0
    fullscreen_latched = False
    nonfullscreen_since: float | None = None

    while True:
        try:
            tray = USER32.FindWindowW("Shell_TrayWnd", None)
            if not tray:
                hwnd = 0
                time.sleep(1.0)
                continue

            if not hwnd or not USER32.IsWindow(hwnd):
                hwnd = find_status(tray)

            if not hwnd:
                missing_cycles += 1
                if missing_cycles in (3, 10):
                    refresh_skin()
                write_state(0, tray, "waiting")
                time.sleep(1.0)
                continue

            missing_cycles = 0
            now = time.monotonic()
            raw_fullscreen = foreground_is_fullscreen()
            if raw_fullscreen:
                fullscreen_latched = True
                nonfullscreen_since = None
            elif fullscreen_latched:
                if nonfullscreen_since is None:
                    nonfullscreen_since = now
                elif now - nonfullscreen_since >= 1.25:
                    fullscreen_latched = False
                    nonfullscreen_since = None

            status = bind_to_taskbar(hwnd, tray, fullscreen_latched)
            if status != last_state or now - last_state_write >= 30.0:
                write_state(hwnd, tray, status)
                last_state = status
                last_state_write = now
        except Exception as exc:
            write_state(hwnd, 0, "error", repr(exc))

        time.sleep(0.25)


if __name__ == "__main__":
    main()
