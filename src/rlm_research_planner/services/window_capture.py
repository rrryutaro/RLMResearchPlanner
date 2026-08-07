from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterator

from PySide6.QtGui import QImage


@dataclass(frozen=True)
class CapturableWindow:
    window_id: int
    title: str
    left: int
    top: int
    width: int
    height: int
    is_fullscreen: bool = False
    is_minimized: bool = False


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", wintypes.DWORD * 3),
    ]


@contextmanager
def _per_monitor_dpi_context() -> Iterator[None]:
    """Use physical screen coordinates without changing process-wide DPI state."""

    if os.name != "nt":
        yield
        return
    user32 = ctypes.windll.user32
    setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if setter is None:
        yield
        return
    setter.argtypes = [wintypes.HANDLE]
    setter.restype = wintypes.HANDLE
    previous = setter(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    try:
        yield
    finally:
        if previous:
            setter(previous)


def _client_window_rectangle(hwnd: int) -> wintypes.RECT | None:
    """Return the top-level window's client area in physical screen pixels."""

    user32 = ctypes.windll.user32
    client = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None
    origin = wintypes.POINT(client.left, client.top)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    width = client.right - client.left
    height = client.bottom - client.top
    if width <= 0 or height <= 0:
        return None
    return wintypes.RECT(
        origin.x,
        origin.y,
        origin.x + width,
        origin.y + height,
    )


def _visible_window_rectangle(hwnd: int) -> wintypes.RECT | None:
    rectangle = wintypes.RECT()
    try:
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            9,  # DWMWA_EXTENDED_FRAME_BOUNDS
            ctypes.byref(rectangle),
            ctypes.sizeof(rectangle),
        )
    except (AttributeError, OSError):
        result = -1
    if result != 0:
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rectangle)):
            return None
    if rectangle.right <= rectangle.left or rectangle.bottom <= rectangle.top:
        return None
    return rectangle


def _monitor_rectangle(hwnd: int) -> wintypes.RECT | None:
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor:
        return None
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    return info.rcMonitor


def rectangles_match(
    first: wintypes.RECT,
    second: wintypes.RECT,
    *,
    tolerance: int = 2,
) -> bool:
    """Return whether two screen rectangles represent the same pixel area."""

    return all(
        abs(left - right) <= max(0, tolerance)
        for left, right in (
            (first.left, second.left),
            (first.top, second.top),
            (first.right, second.right),
            (first.bottom, second.bottom),
        )
    )


def list_capturable_windows() -> list[CapturableWindow]:
    if os.name != "nt":
        return []
    with _per_monitor_dpi_context():
        return _list_capturable_windows_physical()


def _list_capturable_windows_physical() -> list[CapturableWindow]:
    user32 = ctypes.windll.user32
    windows: list[CapturableWindow] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        is_minimized = bool(user32.IsIconic(hwnd))
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True
        rectangle = _client_window_rectangle(hwnd)
        if rectangle is None:
            rectangle = _visible_window_rectangle(hwnd)
        if rectangle is None:
            return True
        width = rectangle.right - rectangle.left
        height = rectangle.bottom - rectangle.top
        if width < 100 or height < 100:
            return True
        windows.append(
            CapturableWindow(
                window_id=int(hwnd),
                title=title,
                left=int(rectangle.left),
                top=int(rectangle.top),
                width=int(width),
                height=int(height),
                is_fullscreen=(
                    not is_minimized
                    and (monitor_rectangle := _monitor_rectangle(hwnd)) is not None
                    and rectangles_match(rectangle, monitor_rectangle)
                ),
                is_minimized=is_minimized,
            )
        )
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return sorted(windows, key=lambda item: item.title.casefold())


def capture_visible_window(window: CapturableWindow) -> QImage:
    """Capture the pixels currently visible inside a top-level window rectangle."""

    if os.name != "nt" or window.width <= 0 or window.height <= 0:
        return QImage()
    with _per_monitor_dpi_context():
        return _capture_visible_window_physical(window)


def reveal_window_for_capture(window: CapturableWindow) -> None:
    """Bring an obscured game window forward and wait for desktop composition."""

    if os.name != "nt":
        return
    with _per_monitor_dpi_context():
        try:
            if window.is_minimized:
                ctypes.windll.user32.ShowWindow(window.window_id, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(window.window_id)
            ctypes.windll.dwmapi.DwmFlush()
            ctypes.windll.dwmapi.DwmFlush()
        except (AttributeError, OSError):
            return


def _capture_visible_window_physical(window: CapturableWindow) -> QImage:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
    ]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        ctypes.POINTER(_BitmapInfo),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

    desktop_dc = user32.GetDC(None)
    if not desktop_dc:
        return QImage()
    memory_dc = gdi32.CreateCompatibleDC(desktop_dc)
    bitmap = gdi32.CreateCompatibleBitmap(
        desktop_dc, window.width, window.height
    )
    previous_bitmap = None
    try:
        if not memory_dc or not bitmap:
            return QImage()
        previous_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        copied = gdi32.BitBlt(
            memory_dc,
            0,
            0,
            window.width,
            window.height,
            desktop_dc,
            window.left,
            window.top,
            0x00CC0020 | 0x40000000,  # SRCCOPY | CAPTUREBLT
        )
        if not copied:
            return QImage()
        byte_count = window.width * window.height * 4
        pixels = ctypes.create_string_buffer(byte_count)
        bitmap_info = _BitmapInfo()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        bitmap_info.bmiHeader.biWidth = window.width
        bitmap_info.bmiHeader.biHeight = -window.height  # top-down image
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0  # BI_RGB
        scan_lines = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            window.height,
            pixels,
            ctypes.byref(bitmap_info),
            0,
        )
        if scan_lines != window.height:
            return QImage()
        return QImage(
            pixels.raw,
            window.width,
            window.height,
            window.width * 4,
            QImage.Format_ARGB32,
        ).copy()
    finally:
        if previous_bitmap and memory_dc:
            gdi32.SelectObject(memory_dc, previous_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, desktop_dc)


def preferred_window_index(
    windows: list[CapturableWindow], preferred_title: str
) -> int:
    expected = preferred_title.strip().casefold()
    if not expected:
        return -1
    for index, window in enumerate(windows):
        if window.title.strip().casefold() == expected:
            return index
    return -1


def should_refresh_window_before_ocr(image_source: str) -> bool:
    return image_source != "file"
