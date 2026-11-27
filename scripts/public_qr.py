"""Render public text with Fedora's libqrencode. No image files are involved."""
import ctypes

from privacy.errors import PipelineError


class QRcode(ctypes.Structure):
    _fields_ = [("version", ctypes.c_int), ("width", ctypes.c_int),
                ("data", ctypes.POINTER(ctypes.c_ubyte))]


def matrix(public_text):
    try:
        lib = ctypes.CDLL("libqrencode.so.4")
    except OSError:
        raise PipelineError("Install Fedora qrencode-libs to display the public QR.") from None
    lib.QRcode_encodeString8bit.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.QRcode_encodeString8bit.restype = ctypes.POINTER(QRcode)
    lib.QRcode_free.argtypes = [ctypes.POINTER(QRcode)]
    lib.QRcode_free.restype = None
    code = lib.QRcode_encodeString8bit(public_text, 0, 1)
    if not code:
        raise PipelineError("QR capacity exceeded. Export the public register instead.")
    try:
        width = code.contents.width
        data = code.contents.data[:width*width]
        return ["".join("1" if item & 1 else "0" for item in data[i:i+width])
                for i in range(0, len(data), width)]
    finally:
        lib.QRcode_free(code)
