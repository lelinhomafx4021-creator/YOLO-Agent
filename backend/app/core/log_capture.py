"""实时捕获 stdout/stderr 并写入日志文件，同时保留原始输出。"""

import re
import sys
from pathlib import Path
from threading import Lock

# 全局锁保护所有日志文件写入
_log_lock = Lock()

# 过滤 ANSI 转义码和 tqdm 进度条控制字符
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\[[0-9;]*[Kmsu]|\r\x1b\[K?|\r')


class LogCapture:
    """替代 sys.stdout / sys.stderr，将输出同时写入日志文件和原始流。

    用法：
        capture = LogCapture(log_path, sys.stdout)
        old = sys.stdout
        sys.stdout = capture
        try:
            some_noisy_function()
        finally:
            sys.stdout = old
    """

    def __init__(self, log_path: Path, original):
        self.log_path = log_path
        self.original = original
        self._buffer = ""

    def write(self, text: str) -> int:
        if text:
            with _log_lock:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    self._write_line_locked(line)
        self.original.write(text)
        return len(text)

    def flush(self):
        with _log_lock:
            if self._buffer.strip():
                self._write_line_locked(self._buffer)
                self._buffer = ""
        self.original.flush()

    def _write_line_locked(self, line: str) -> None:
        """调用者必须持有 _log_lock。"""
        clean = _ANSI_RE.sub('', line).rstrip()
        if not clean:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(clean + "\n")

    def __getattr__(self, name):
        return getattr(self.original, name)


def append_log(path: Path, line: str) -> None:
    """直接追加一行到日志文件（线程安全）。"""
    clean = _ANSI_RE.sub('', line).rstrip()
    if not clean:
        return
    with _log_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(clean + "\n")
