"""
PyInstaller runtime hook — add bundled NVIDIA CUDA DLL directories to the
DLL search path so ctranslate2 / faster-whisper can find cublas64_12.dll
and friends at runtime.
"""

import os
import sys

def _add_cuda_dll_dirs():
    base = sys._MEIPASS  # PyInstaller's temporary extraction directory
    cuda_subdirs = [
        os.path.join(base, "nvidia", "cublas", "bin"),
        os.path.join(base, "nvidia", "cudnn", "bin"),
        os.path.join(base, "nvidia", "cuda_nvrtc", "bin"),
        os.path.join(base, "ctranslate2"),
    ]
    for d in cuda_subdirs:
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass  # os.add_dll_directory requires Python 3.8+ / Windows

_add_cuda_dll_dirs()
