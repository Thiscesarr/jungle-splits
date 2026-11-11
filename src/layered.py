"""Shows an RGBA image as a window's whole content, with per-pixel alpha (UpdateLayeredWindow).

Windows then composites the overlay itself: nothing is painted on WM_PAINT and the image stays on
screen until the next one, so the overlay only costs anything when its content actually changes.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image

# Own DLL handles, so these argtypes never clash with ctypes.windll used elsewhere.
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

ULW_ALPHA = 0x2
AC_SRC_OVER, AC_SRC_ALPHA = 0x0, 0x1
BI_RGB, DIB_RGB_COLORS = 0, 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.GdiFlush.restype = wintypes.BOOL


class LayeredSurface:
    """A 32-bit bitmap kept between frames (re-created only when the size changes)."""

    def __init__(self):
        self.dc = gdi32.CreateCompatibleDC(None)
        self.bitmap = None
        self.previous = None
        self.bits = ctypes.c_void_p()
        self.size: tuple[int, int] | None = None

    def _resize(self, width: int, height: int) -> None:
        info = BITMAPINFO()
        header = info.bmiHeader
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth, header.biHeight = width, -height  # negative: rows top to bottom, like Pillow's
        header.biPlanes, header.biBitCount, header.biCompression = 1, 32, BI_RGB
        bitmap = gdi32.CreateDIBSection(self.dc, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(self.bits),
                                        None, 0)
        if not bitmap:
            raise OSError(ctypes.get_last_error(), "CreateDIBSection failed")
        old = gdi32.SelectObject(self.dc, bitmap)
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        else:
            self.previous = old
        self.bitmap, self.size = bitmap, (width, height)

    def present(self, hwnd: int, image: Image.Image) -> bool:
        """Puts image (RGBA, straight alpha) on the window; the window keeps its position."""
        width, height = image.size
        if self.size != (width, height):
            self._resize(width, height)
        data = image.convert("RGBa").tobytes("raw", "BGRa")  # premultiplied BGRA, as Windows expects
        gdi32.GdiFlush()
        ctypes.memmove(self.bits, data, len(data))
        screen = user32.GetDC(None)
        try:
            return bool(user32.UpdateLayeredWindow(
                hwnd, screen, None, ctypes.byref(wintypes.SIZE(width, height)), self.dc,
                ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)),
                ULW_ALPHA))
        finally:
            user32.ReleaseDC(None, screen)

    def close(self) -> None:
        if self.dc:
            if self.previous:
                gdi32.SelectObject(self.dc, self.previous)
            if self.bitmap:
                gdi32.DeleteObject(self.bitmap)
            gdi32.DeleteDC(self.dc)
            self.dc = self.bitmap = None
