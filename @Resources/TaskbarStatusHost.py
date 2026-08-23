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
import sys
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
ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABE_TOP = 1
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
TOPBAR_TITLE_SUFFIX = r"\WindowsPorthexTheme\TopBar\TopBar.ini"
RAINMETER = r"C:\Program Files\Rainmeter\Rainmeter.exe"
STATE_PATH = Path(__file__).with_name("TaskbarStatusHost.state.json")
TASKBAR_SKIN = STATE_PATH.parent.parent / "TaskbarStatus" / "TaskbarStatus.ini"
TRAY_ICON_DIR = STATE_PATH.parent / "TrayIcons"
TOPBAR_HEIGHT = 36

WM_APP = 0x8000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
PM_REMOVE = 0x0001
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
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
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
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
SHELL32 = ctypes.WinDLL("shell32", use_last_error=True)
SHELL32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
SHELL32.SHAppBarMessage.restype = ctypes.c_size_t
USER32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
USER32.CreateWindowExW.restype = wintypes.HWND
USER32.DestroyWindow.argtypes = [wintypes.HWND]
USER32.DestroyWindow.restype = wintypes.BOOL
USER32.GetSystemMetrics.argtypes = [ctypes.c_int]
USER32.GetSystemMetrics.restype = ctypes.c_int
USER32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
USER32.RegisterClassW.restype = wintypes.ATOM
USER32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER32.DefWindowProcW.restype = ctypes.c_ssize_t
USER32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
USER32.LoadImageW.restype = wintypes.HANDLE
USER32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
USER32.PeekMessageW.restype = wintypes.BOOL
USER32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
USER32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
KERNEL32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
KERNEL32.GetModuleHandleW.restype = wintypes.HINSTANCE
SHELL32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
SHELL32.Shell_NotifyIconW.restype = wintypes.BOOL


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


@WNDPROC
def tray_wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_APP + 20 and (lparam & 0xFFFF) in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
        os.startfile("https://sv1.porthex.io/")
        return 0
    return USER32.DefWindowProcW(hwnd, message, wparam, lparam)


def create_tray_icon() -> tuple[int, dict[str, int]]:
    instance = KERNEL32.GetModuleHandleW(None)
    class_name_value = "PorthexStatusTrayWindow"
    window_class = WNDCLASSW(
        lpfnWndProc=tray_wndproc,
        hInstance=instance,
        lpszClassName=class_name_value,
    )
    if not USER32.RegisterClassW(ctypes.byref(window_class)) and ctypes.get_last_error() != 1410:
        raise ctypes.WinError(ctypes.get_last_error())
    hwnd = USER32.CreateWindowExW(
        WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        class_name_value,
        "Porthex status",
        WS_POPUP,
        0,
        0,
        0,
        0,
        None,
        None,
        instance,
        None,
    )
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    icons = {
        state: int(USER32.LoadImageW(None, str(TRAY_ICON_DIR / filename), IMAGE_ICON, 0, 0, LR_LOADFROMFILE))
        for state, filename in (("ONLINE", "PorthexOnline.ico"), ("OFFLINE", "PorthexOffline.ico"))
    }
    if not all(icons.values()):
        raise ctypes.WinError(ctypes.get_last_error())
    return hwnd, icons


def set_tray_icon(hwnd: int, icon: int, state: str, add: bool) -> None:
    data = NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    data.hWnd = hwnd
    data.uID = 1
    data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    data.uCallbackMessage = WM_APP + 20
    data.hIcon = icon
    data.szTip = f"Porthex server — {state}"
    if not SHELL32.Shell_NotifyIconW(NIM_ADD if add else NIM_MODIFY, ctypes.byref(data)):
        raise ctypes.WinError(ctypes.get_last_error())


def read_server_state() -> str:
    try:
        for line in TASKBAR_SKIN.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("ServerState="):
                return "ONLINE" if line.partition("=")[2].strip().upper() == "ONLINE" else "OFFLINE"
    except OSError:
        pass
    return "OFFLINE"


def pump_tray_messages() -> None:
    message = MSG()
    while USER32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
        USER32.TranslateMessage(ctypes.byref(message))
        USER32.DispatchMessageW(ctypes.byref(message))


def find_skin(title_suffix: str, tray: int = 0) -> int:
    found: list[int] = []

    @WNDENUMPROC
    def visit(hwnd: int, _lparam: int) -> bool:
        if class_name(hwnd) == "RainmeterMeterWindow" and window_text(hwnd).endswith(title_suffix):
            found.append(hwnd)
            return False
        return True

    USER32.EnumWindows(visit, 0)
    if not found and tray:
        USER32.EnumChildWindows(tray, visit, 0)
    return found[0] if found else 0


def create_appbar() -> int:
    hwnd = USER32.CreateWindowExW(
        WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        "Static",
        "PorthexTopAppBar",
        WS_POPUP,
        0,
        0,
        USER32.GetSystemMetrics(0),
        TOPBAR_HEIGHT,
        None,
        None,
        None,
        None,
    )
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    return hwnd


def reserve_top(hwnd: int, register: bool = False) -> None:
    width = USER32.GetSystemMetrics(0)
    data = APPBARDATA(
        cbSize=ctypes.sizeof(APPBARDATA),
        hWnd=hwnd,
        uCallbackMessage=0x8001,
        uEdge=ABE_TOP,
        rc=wintypes.RECT(0, 0, width, TOPBAR_HEIGHT),
    )
    if register and not SHELL32.SHAppBarMessage(ABM_NEW, ctypes.byref(data)):
        raise ctypes.WinError(ctypes.get_last_error())
    SHELL32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(data))
    data.rc.bottom = data.rc.top + TOPBAR_HEIGHT
    SHELL32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(data))
    USER32.SetWindowPos(hwnd, None, data.rc.left, data.rc.top, data.rc.right - data.rc.left, TOPBAR_HEIGHT, SWP_NOACTIVATE)


def release_appbar(hwnd: int) -> None:
    data = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA), hWnd=hwnd)
    SHELL32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(data))
    USER32.DestroyWindow(hwnd)


def window_process_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_covers_monitor(hwnd: int) -> bool:
    if not hwnd or not USER32.IsWindowVisible(hwnd):
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


def foreground_is_fullscreen() -> bool:
    hwnd = USER32.GetForegroundWindow()
    return bool(
        hwnd
        and class_name(hwnd)
        not in {
            "Shell_TrayWnd",
            "Progman",
            "WorkerW",
            "RainmeterMeterWindow",
            "Windows.UI.Core.CoreWindow",
        }
        and window_covers_monitor(hwnd)
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


def bind_topbar(hwnd: int, hide_for_fullscreen: bool) -> None:
    if hide_for_fullscreen:
        return

    width = USER32.GetSystemMetrics(0)
    target = (0, 0, width, TOPBAR_HEIGHT)
    if not USER32.IsWindowVisible(hwnd):
        USER32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    if rect(hwnd) != target or not (USER32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0x00000008):
        if not USER32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, width, TOPBAR_HEIGHT, SWP_NOACTIVATE | SWP_SHOWWINDOW):
            raise ctypes.WinError(ctypes.get_last_error())


def refresh_skin() -> None:
    subprocess.Popen(
        [RAINMETER, "!Refresh", r"WindowsPorthexTheme\TaskbarStatus"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )


def set_skins_hidden(hidden: bool) -> None:
    bang = "!Hide" if hidden else "!Show"
    for config in (r"WindowsPorthexTheme\TopBar", r"WindowsPorthexTheme\TaskbarStatus"):
        subprocess.run(
            [RAINMETER, bang, config],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
            timeout=2,
            check=False,
        )


def write_state(hwnd: int, tray: int, status: str, error: str = "", topbar: int = 0) -> None:
    payload = {
        "pid": os.getpid(),
        "status": status,
        "error": error,
        "taskbar_hwnd": int(tray),
        "status_hwnd": int(hwnd),
        "parent_hwnd": int(USER32.GetParent(hwnd) or 0) if hwnd and USER32.IsWindow(hwnd) else 0,
        "rect": list(rect(hwnd)) if hwnd and USER32.IsWindow(hwnd) else [0, 0, 0, 0],
        "visible": bool(USER32.IsWindowVisible(hwnd)) if hwnd and USER32.IsWindow(hwnd) else False,
        "topbar_hwnd": int(topbar),
        "topbar_rect": list(rect(topbar)) if topbar and USER32.IsWindow(topbar) else [0, 0, 0, 0],
        "topbar_visible": bool(USER32.IsWindowVisible(topbar)) if topbar and USER32.IsWindow(topbar) else False,
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
    topbar = 0
    appbar = create_appbar()
    tray_icon_hwnd, tray_icons = create_tray_icon()
    tray_icon_state = ""
    tray_icon_added = False
    next_tray_icon_check = 0.0
    last_tray = 0
    missing_cycles = 0
    last_state = ""
    last_state_write = 0.0
    fullscreen_latched = False
    fullscreen_hwnd = 0
    nonfullscreen_since: float | None = None
    applied_fullscreen: bool | None = None

    while True:
        try:
            tray = USER32.FindWindowW("Shell_TrayWnd", None)
            if not tray:
                hwnd = 0
                time.sleep(1.0)
                continue

            if tray != last_tray:
                reserve_top(appbar, register=True)
                tray_icon_added = False
                last_tray = tray

            if not hwnd or not USER32.IsWindow(hwnd):
                hwnd = find_skin(SKIN_TITLE_SUFFIX, tray)
            if not topbar or not USER32.IsWindow(topbar):
                topbar = find_skin(TOPBAR_TITLE_SUFFIX)

            if not hwnd:
                missing_cycles += 1
                if missing_cycles in (3, 10):
                    refresh_skin()
            else:
                missing_cycles = 0

            now = time.monotonic()
            if now >= next_tray_icon_check:
                state = read_server_state()
                if not tray_icon_added or state != tray_icon_state:
                    set_tray_icon(tray_icon_hwnd, tray_icons[state], state, add=not tray_icon_added)
                    tray_icon_added = True
                    tray_icon_state = state
                next_tray_icon_check = now + 1.0
            pump_tray_messages()
            raw_fullscreen = foreground_is_fullscreen()
            if raw_fullscreen:
                fullscreen_latched = True
                fullscreen_hwnd = USER32.GetForegroundWindow()
                nonfullscreen_since = None
            elif fullscreen_latched:
                foreground = USER32.GetForegroundWindow()
                same_app_overlay = (
                    fullscreen_hwnd
                    and window_covers_monitor(fullscreen_hwnd)
                    and window_process_id(foreground) == window_process_id(fullscreen_hwnd)
                )
                if same_app_overlay:
                    nonfullscreen_since = None
                elif nonfullscreen_since is None:
                    nonfullscreen_since = now
                elif now - nonfullscreen_since >= 1.25:
                    fullscreen_latched = False
                    fullscreen_hwnd = 0
                    nonfullscreen_since = None

            if fullscreen_latched != applied_fullscreen:
                # Keep Rainmeter's internal state in sync; direct ShowWindow
                # calls make active skins reappear and flash every update.
                set_skins_hidden(fullscreen_latched)
                applied_fullscreen = fullscreen_latched

            status = bind_to_taskbar(hwnd, tray, fullscreen_latched) if hwnd else "waiting"
            if topbar:
                bind_topbar(topbar, fullscreen_latched)
            if status != last_state or now - last_state_write >= 30.0:
                reserve_top(appbar)
                write_state(hwnd, tray, status, topbar=topbar)
                last_state = status
                last_state_write = now
        except Exception as exc:
            write_state(hwnd, 0, "error", repr(exc), topbar=topbar)

        time.sleep(0.25)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert ctypes.sizeof(APPBARDATA) in (36, 48)
        assert TOPBAR_HEIGHT > 0
        assert all((TRAY_ICON_DIR / name).is_file() for name in ("PorthexOnline.ico", "PorthexOffline.ico"))
        assert read_server_state() in {"ONLINE", "OFFLINE"}
        print("ok")
    else:
        main()
