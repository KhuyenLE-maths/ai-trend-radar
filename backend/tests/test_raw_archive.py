import gzip
import hashlib
import json
from datetime import date

from app.pipeline.raw_archive import RawArchive, read_records_tolerant, record_raw, use_archive


def test_writes_jsonl_gz_per_source(raw_dir):
    a = RawArchive(raw_dir, 7, date(2026, 10, 30))
    a.record("github_rest", {"url": "/x"}, 200, '{"a":1}')
    a.record("github_rest", {"url": "/y"}, 500, "boom")
    [f] = a.close()
    assert f.path == "2026-10-30/run-7/github_rest.jsonl.gz"
    lines = [json.loads(line) for line in gzip.open(raw_dir / f.path, "rt")]
    assert [line["status"] for line in lines] == [200, 500]
    assert lines[1]["body"] == "boom" and "ts" in lines[0]
    assert f.line_count == 2
    assert f.byte_size == (raw_dir / f.path).stat().st_size
    assert f.sha256 == hashlib.sha256((raw_dir / f.path).read_bytes()).hexdigest()


def test_never_overwrites_existing_file(raw_dir):
    p = raw_dir / "2026-10-30/run-7"
    p.mkdir(parents=True)
    (p / "hackernews.jsonl.gz").write_bytes(b"old")
    a = RawArchive(raw_dir, 7, date(2026, 10, 30))
    a.record("hackernews", {}, 200, "x")
    assert a.error is not None
    assert (p / "hackernews.jsonl.gz").read_bytes() == b"old"


def test_unwritable_root_sets_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    a = RawArchive(blocker, 1, date(2026, 10, 30))
    a.record("github_rest", {}, 200, "x")
    assert a.error is not None


def test_truncated_file_readable_up_to_last_record(raw_dir):
    a = RawArchive(raw_dir, 8, date(2026, 10, 30))
    a.record("hackernews", {}, 200, "one")
    a.record("hackernews", {}, 200, "two")
    path = raw_dir / "2026-10-30/run-8/hackernews.jsonl.gz"  # không close: mô phỏng bị kill
    assert read_records_tolerant(path)[-1]["body"] == "two"


def test_reader_drops_torn_last_line(raw_dir):
    path = raw_dir / "x.jsonl.gz"
    path.write_bytes(gzip.compress(b'{"body": "one"}\n{"body": "tw'))
    assert read_records_tolerant(path) == [{"body": "one"}]


def test_record_raw_without_archive_is_noop():
    record_raw("hackernews", {}, 200, "x")


def test_record_raw_goes_to_active_archive(raw_dir):
    a = RawArchive(raw_dir, 9, date(2026, 10, 30))
    with use_archive(a):
        record_raw("hackernews", {}, 200, "x")
    assert a.close()[0].line_count == 1
