"""Lưu nguyên văn phản hồi từ nguồn ngoài ra data/raw/<ngày>/run-<id>/<nguồn>.jsonl.gz.

Chỉ ghi thêm, không bao giờ ghi đè. record() không raise để không bị các khối
fail-soft nuốt mất: lỗi ghi được giữ trong .error và run_daily đọc lại.
"""
import contextlib
import gzip
import hashlib
import json
import logging
import zlib
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

log = logging.getLogger("pipeline.raw")

_active: ContextVar["RawArchive | None"] = ContextVar("raw_archive", default=None)


@dataclass
class ArchiveFile:
    source: str
    path: str
    line_count: int
    byte_size: int
    sha256: str


class RawArchive:
    def __init__(self, root: Path, run_id: int, day: date) -> None:
        self.root = Path(root)
        self.relative_dir = Path(day.isoformat()) / f"run-{run_id}"
        self.error: str | None = None
        self._files: dict[str, tuple[BinaryIO, gzip.GzipFile]] = {}
        self._counts: dict[str, int] = {}

    def _open(self, source: str) -> gzip.GzipFile:
        if source not in self._files:
            path = self.root / self.relative_dir / f"{source}.jsonl.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = open(path, "xb")  # "x": file đã tồn tại thì lỗi, không ghi đè
            self._files[source] = (raw, gzip.GzipFile(fileobj=raw, mode="wb"))
            self._counts[source] = 0
        return self._files[source][1]

    def record(self, source: str, request: dict, status: int | None, body: str) -> None:
        try:
            line = json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "source": source,
                    "request": request,
                    "status": status,
                    "body": body,
                },
                ensure_ascii=False,
            )
            stream = self._open(source)
            stream.write(line.encode() + b"\n")
            stream.flush()  # sync flush để file dở vẫn đọc được nếu tiến trình bị kill
            self._files[source][0].flush()
            self._counts[source] += 1
        except Exception as e:
            log.error("không ghi được dữ liệu thô (%s): %s", source, e)
            self.error = self.error or f"{source}: {e}"

    def close(self) -> list[ArchiveFile]:
        out: list[ArchiveFile] = []
        for source, (raw, stream) in self._files.items():
            try:
                stream.close()
                raw.close()
                relative = self.relative_dir / f"{source}.jsonl.gz"
                data = (self.root / relative).read_bytes()
                out.append(ArchiveFile(
                    source, relative.as_posix(), self._counts[source],
                    len(data), hashlib.sha256(data).hexdigest(),
                ))
            except Exception as e:
                log.error("không đóng được file thô (%s): %s", source, e)
                self.error = self.error or f"{source}: {e}"
        self._files.clear()
        return out


@contextlib.contextmanager
def use_archive(archive: RawArchive) -> Iterator[None]:
    token = _active.set(archive)
    try:
        yield
    finally:
        _active.reset(token)


def record_raw(source: str, request: dict, status: int | None, body: str) -> None:
    archive = _active.get()
    if archive is not None:
        archive.record(source, request, status, body)


def read_records_tolerant(path: Path) -> list[dict]:
    """Đọc file thô, kể cả file dở do tiến trình bị kill giữa chừng."""
    decoder = zlib.decompressobj(zlib.MAX_WBITS | 16)
    text = decoder.decompress(Path(path).read_bytes())
    complete = text[: text.rfind(b"\n") + 1]  # bỏ dòng cuối bị cắt dở
    return [json.loads(line) for line in complete.splitlines()]
