from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtGui import QImage


@dataclass(frozen=True)
class CapturableWindow:
    window_id: int
    title: str
    left: int
    top: int
    width: int
    height: int


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


def list_capturable_windows() -> list[CapturableWindow]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    windows: list[CapturableWindow] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True
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
            )
        )
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return sorted(windows, key=lambda item: item.title.casefold())


def capture_visible_window(window: CapturableWindow) -> QImage:
    """Capture the pixels currently visible inside a top-level window rectangle."""

    if os.name != "nt" or window.width <= 0 or window.height <= 0:
        return QImage()
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
