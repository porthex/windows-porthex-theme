"""Create, name, switch, and inspect the three Porthex Windows desktops."""
from __future__ import annotations

import argparse
import ctypes
import json
import time
from ctypes import wintypes
from pathlib import Path

DLL_PATH = Path(__file__).resolve().parent / "VirtualDesktopAccessor.dll"
NAMES = ("Quiet", "Work", "Deep Focus")
RAINMETER_CLASS = "RainmeterMeterWindow"


def load_dll():
    if not DLL_PATH.is_file():
        raise RuntimeError(f"Missing {DLL_PATH.name}; reinstall the Porthex theme")
    dll = ctypes.WinDLL(str(DLL_PATH))
    for name in (
        "GetDesktopCount", "GetCurrentDesktopNumber", "CreateDesktop",
        "GoToDesktopNumber", "PinWindow", "PinApp", "IsPinnedWindow",
    ):
        getattr(dll, name).restype = ctypes.c_int
    dll.SetDesktopName.argtypes = [ctypes.c_int, ctypes.c_char_p]
    dll.SetDesktopName.restype = ctypes.c_int
    return dll


def rainmeter_windows():
    """Find Rainmeter windows without third-party Python dependencies."""
    user32 = ctypes.windll.user32
    handles: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, len(name))
            if name.value == RAINMETER_CLASS:
                handles.append(int(hwnd))
        return True

    user32.EnumWindows(enum, 0)
    return handles


def pin_rainmeter(dll):
    results = []
    for index, hwnd in enumerate(rainmeter_windows()):
        results.append({
            "hwnd": hwnd,
            "window": dll.PinWindow(hwnd),
            "app": dll.PinApp(hwnd) if index == 0 else 0,
        })
    return results


def ensure_three(dll):
    count = dll.GetDesktopCount()
    if count < 1:
        raise RuntimeError("Virtual desktop API unavailable")
    while count < 3:
        if dll.CreateDesktop() < 0:
            raise RuntimeError("Could not create the required Windows virtual desktops")
        count = dll.GetDesktopCount()
    names = [dll.SetDesktopName(index, name.encode("utf-8")) for index, name in enumerate(NAMES)]
    return count, names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "switch", "status"))
    parser.add_argument("desktop", nargs="?", type=int)
    args = parser.parse_args()
    dll = load_dll()
    output: dict[str, object] = {}
    if args.action == "setup":
        count, names = ensure_three(dll)
        output.update({"count": count, "names": names, "pinned": pin_rainmeter(dll)})
    elif args.action == "switch":
        if args.desktop not in (1, 2, 3):
            raise SystemExit("desktop must be 1, 2, or 3")
        if dll.GetDesktopCount() < 3:
            ensure_three(dll)
        pin_rainmeter(dll)
        result = dll.GoToDesktopNumber(args.desktop - 1)
        if result != 1:
            raise RuntimeError(f"Desktop switch failed: {result}")
        time.sleep(0.35)
        output.update({"requested": args.desktop - 1, "current": dll.GetCurrentDesktopNumber(), "result": result})
    else:
        output.update({"count": dll.GetDesktopCount(), "current": dll.GetCurrentDesktopNumber(), "pinned": pin_rainmeter(dll)})
    print(json.dumps(output))


if __name__ == "__main__":
    main()
