"""One requested HWND frame per native Windows Graphics Capture session.

No monitor source, desktop crop fallback, or idle/background capture session.
The OS capture indicator keeps its default. Secondary windows default off.
"""
from __future__ import annotations

import threading

from .windows import UnsupportedDesktop, WindowNotReady


def capture_window(hwnd, expected_size, timeout=2.0):
    if not hwnd:
        raise UnsupportedDesktop("Window capture requires an exact window handle")
    try:
        from windows_capture import WindowsCapture
    except ImportError as exc:
        raise UnsupportedDesktop("Windows window capture is unavailable; run the updated TeachDesk launcher") from exc

    ready = threading.Event()
    result = []
    errors = []
    control = None
    try:
        # Only HWND is supplied: the library otherwise defaults to a monitor.
        # Optional newer-OS settings stay at defaults for compatibility.
        capture = WindowsCapture(window_hwnd=int(hwnd), cursor_capture=False)

        @capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                if (frame.width, frame.height) != expected_size:
                    raise WindowNotReady(f"Window capture size {(frame.width, frame.height)} differs from physical bounds {expected_size}; frame discarded")
                from PIL import Image
                # Native frames are BGRA with possible row padding. Make an
                # owned RGB copy before the callback releases its GPU mapping.
                result.append(Image.frombytes("RGB", expected_size, frame.frame_buffer[:, :, [2, 1, 0]].tobytes()))
            except Exception as exc:
                errors.append(exc)
            finally:
                capture_control.stop()
                ready.set()

        @capture.event
        def on_closed():
            ready.set()

        control = capture.start_free_threaded()
        if not ready.wait(timeout):
            raise WindowNotReady("Window capture timed out; refocus the target and check Windows graphics capture support")
        if errors:
            raise errors[0]
        if not result:
            raise WindowNotReady("Target closed before a window image arrived")
        return result[0]
    except UnsupportedDesktop:
        raise
    except Exception as exc:
        raise UnsupportedDesktop("Windows Graphics Capture failed; this window or graphics configuration is unsupported") from exc
    finally:
        if control is not None:
            try:
                # stop() joins and propagates native failure; it does not need
                # another frame to arrive. Never leave the source capturing.
                control.stop()
            except Exception as exc:
                raise UnsupportedDesktop("Windows window capture did not shut down cleanly") from exc
