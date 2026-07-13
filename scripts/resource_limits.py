#!/usr/bin/env python3
"""Conservative resource limits for HTTP, files, Excel, PDF, OCR, and subprocesses.

Limits are enforced *before* unbounded reads where possible. Violations raise
``ResourceLimitError`` (structured blocker), never silently truncate as complete.

CLI / env overrides (optional):
  D_RESEARCH_HTTP_MAX_BYTES
  D_RESEARCH_HTTP_TIMEOUT_SEC
  D_RESEARCH_DOWNLOAD_MAX_BYTES
  D_RESEARCH_EXCEL_MAX_COL          (0-based; XFD = 16383)
  D_RESEARCH_EXCEL_MAX_CELLS
  D_RESEARCH_XLSX_MAX_UNCOMPRESSED
  D_RESEARCH_XLSX_MAX_COMPRESSION_RATIO
  D_RESEARCH_PDF_MAX_PAGES
  D_RESEARCH_PDF_MAX_BYTES
  D_RESEARCH_OCR_MAX_PAGES
  D_RESEARCH_OCR_MAX_PIXELS
  D_RESEARCH_OCR_MAX_IMAGE_BYTES
  D_RESEARCH_SUBPROCESS_TIMEOUT_SEC
  D_RESEARCH_SUBPROCESS_MAX_OUTPUT_BYTES
  D_RESEARCH_TABLE_MAX_ROWS
  D_RESEARCH_TABLE_MAX_CELLS
  D_RESEARCH_WAYBACK_MAX_BYTES
  D_RESEARCH_SOCIAL_MAX_BYTES
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Optional, Sequence


# Excel column XFD is column index 16383 (0-based).
EXCEL_XFD_COL_INDEX = 16383


@dataclass(frozen=True)
class ResourceLimits:
    http_max_bytes: int = 20 * 1024 * 1024
    http_timeout_sec: int = 30
    download_max_bytes: int = 50 * 1024 * 1024
    excel_max_col: int = EXCEL_XFD_COL_INDEX
    excel_max_cells: int = 2_000_000
    xlsx_max_uncompressed: int = 200 * 1024 * 1024
    xlsx_max_compression_ratio: float = 100.0
    pdf_max_pages: int = 500
    pdf_max_bytes: int = 100 * 1024 * 1024
    ocr_max_pages: int = 50
    ocr_max_pixels: int = 40_000_000  # ~6300x6300
    ocr_max_image_bytes: int = 25 * 1024 * 1024
    subprocess_timeout_sec: int = 120
    subprocess_max_output_bytes: int = 20 * 1024 * 1024
    table_max_rows: int = 100_000
    table_max_cells: int = 2_000_000
    wayback_max_bytes: int = 20 * 1024 * 1024
    social_max_bytes: int = 2 * 1024 * 1024

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResourceLimitError(Exception):
    """Structured resource-limit violation (never silent truncate)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        limit: Any = None,
        observed: Any = None,
        incomplete: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.limit = limit
        self.observed = observed
        self.incomplete = incomplete

    def to_blocker(self) -> dict[str, Any]:
        return {
            "error": "resource_limit",
            "code": self.code,
            "message": self.message,
            "limit": self.limit,
            "observed": self.observed,
            "incomplete": True,
            "complete": False,
        }

    def exit_code(self) -> int:
        return 3


@dataclass(frozen=True)
class BoundedCompletedProcess:
    """Small ``CompletedProcess`` equivalent with byte output."""

    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


_ENV_MAP = {
    "http_max_bytes": ("D_RESEARCH_HTTP_MAX_BYTES", int),
    "http_timeout_sec": ("D_RESEARCH_HTTP_TIMEOUT_SEC", int),
    "download_max_bytes": ("D_RESEARCH_DOWNLOAD_MAX_BYTES", int),
    "excel_max_col": ("D_RESEARCH_EXCEL_MAX_COL", int),
    "excel_max_cells": ("D_RESEARCH_EXCEL_MAX_CELLS", int),
    "xlsx_max_uncompressed": ("D_RESEARCH_XLSX_MAX_UNCOMPRESSED", int),
    "xlsx_max_compression_ratio": ("D_RESEARCH_XLSX_MAX_COMPRESSION_RATIO", float),
    "pdf_max_pages": ("D_RESEARCH_PDF_MAX_PAGES", int),
    "pdf_max_bytes": ("D_RESEARCH_PDF_MAX_BYTES", int),
    "ocr_max_pages": ("D_RESEARCH_OCR_MAX_PAGES", int),
    "ocr_max_pixels": ("D_RESEARCH_OCR_MAX_PIXELS", int),
    "ocr_max_image_bytes": ("D_RESEARCH_OCR_MAX_IMAGE_BYTES", int),
    "subprocess_timeout_sec": ("D_RESEARCH_SUBPROCESS_TIMEOUT_SEC", int),
    "subprocess_max_output_bytes": ("D_RESEARCH_SUBPROCESS_MAX_OUTPUT_BYTES", int),
    "table_max_rows": ("D_RESEARCH_TABLE_MAX_ROWS", int),
    "table_max_cells": ("D_RESEARCH_TABLE_MAX_CELLS", int),
    "wayback_max_bytes": ("D_RESEARCH_WAYBACK_MAX_BYTES", int),
    "social_max_bytes": ("D_RESEARCH_SOCIAL_MAX_BYTES", int),
}

_CLI_FLAGS = {
    "http_max_bytes": "--max-http-bytes",
    "http_timeout_sec": "--http-timeout-sec",
    "download_max_bytes": "--max-file-bytes",
    "excel_max_col": "--max-excel-column-index",
    "excel_max_cells": "--max-excel-cells",
    "xlsx_max_uncompressed": "--max-xlsx-uncompressed-bytes",
    "xlsx_max_compression_ratio": "--max-xlsx-compression-ratio",
    "pdf_max_pages": "--max-pdf-pages",
    "pdf_max_bytes": "--max-pdf-bytes",
    "ocr_max_pages": "--max-ocr-pages",
    "ocr_max_pixels": "--max-ocr-pixels",
    "ocr_max_image_bytes": "--max-ocr-image-bytes",
    "subprocess_timeout_sec": "--subprocess-timeout-sec",
    "subprocess_max_output_bytes": "--max-subprocess-output-bytes",
    "table_max_rows": "--max-table-rows",
    "table_max_cells": "--max-table-cells",
    "wayback_max_bytes": "--max-wayback-bytes",
    "social_max_bytes": "--max-social-bytes",
}


def add_resource_limit_arguments(parser: argparse.ArgumentParser, fields: Sequence[str]) -> None:
    """Expose selected resource limits as explicit per-command CLI overrides."""

    for field in fields:
        if field not in _CLI_FLAGS or field not in _ENV_MAP:
            raise ValueError(f"unknown resource-limit field: {field}")
        flag = _CLI_FLAGS[field]
        cast = _ENV_MAP[field][1]
        parser.add_argument(
            flag,
            dest=f"resource_limit_{field}",
            type=cast,
            default=None,
            metavar="N",
            help=(
                f"Override {_ENV_MAP[field][0]} for this command only "
                "(must be positive and finite)."
            ),
        )


def apply_cli_limit_overrides(args: argparse.Namespace) -> ResourceLimits:
    """Validate CLI limit values and expose them to existing helper calls."""

    overrides: dict[str, Any] = {}
    for field in _CLI_FLAGS:
        value = getattr(args, f"resource_limit_{field}", None)
        if value is not None:
            overrides[field] = value
    limits = load_limits(overrides)
    for field, value in overrides.items():
        os.environ[_ENV_MAP[field][0]] = str(value)
    return limits


def load_limits(
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> ResourceLimits:
    """Load defaults, then env, then explicit overrides."""
    env = env if env is not None else os.environ
    values = asdict(ResourceLimits())
    for field, (env_key, cast) in _ENV_MAP.items():
        raw = env.get(env_key)
        if raw is not None and str(raw).strip() != "":
            try:
                values[field] = cast(raw)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ResourceLimitError(
                    "invalid_resource_limit",
                    f"{env_key} must be a positive finite number",
                    observed=raw,
                ) from exc
    if overrides:
        for k, v in overrides.items():
            if k in values and v is not None:
                try:
                    values[k] = type(values[k])(v)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ResourceLimitError(
                        "invalid_resource_limit",
                        f"resource limit {k} must be a positive finite number",
                        observed=v,
                    ) from exc
    for field, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ResourceLimitError(
                "invalid_resource_limit",
                f"resource limit {field} must be numeric",
                observed=value,
            )
        if not math.isfinite(float(value)) or value <= 0:
            env_key = _ENV_MAP[field][0]
            raise ResourceLimitError(
                "invalid_resource_limit",
                f"{env_key} must be positive and finite",
                observed=value,
            )
    if values["excel_max_col"] > EXCEL_XFD_COL_INDEX:
        raise ResourceLimitError(
            "invalid_resource_limit",
            "D_RESEARCH_EXCEL_MAX_COL cannot exceed Excel XFD (16383, 0-based)",
            limit=EXCEL_XFD_COL_INDEX,
            observed=values["excel_max_col"],
        )
    return ResourceLimits(**values)


def check_http_content_length(content_length: Optional[int], limits: ResourceLimits) -> None:
    if content_length is None:
        return
    if content_length > limits.http_max_bytes:
        raise ResourceLimitError(
            "http_response_bytes",
            f"HTTP Content-Length {content_length} exceeds limit {limits.http_max_bytes}",
            limit=limits.http_max_bytes,
            observed=content_length,
        )


def read_bounded(stream: BinaryIO, max_bytes: int, *, code: str = "http_response_bytes") -> bytes:
    """Read up to max_bytes+1; raise if body exceeds max_bytes (no silent truncate)."""
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ResourceLimitError(
            "invalid_resource_limit",
            f"{code} byte limit must be a positive integer",
            observed=max_bytes,
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(65536, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ResourceLimitError(
                code,
                f"response/body exceeds limit {max_bytes} bytes",
                limit=max_bytes,
                observed=total,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def read_http_response_bounded(
    response: Any,
    limits: Optional[ResourceLimits] = None,
    *,
    max_bytes: Optional[int] = None,
    code: str = "http_response_bytes",
) -> bytes:
    """Read an urllib-style response with Content-Length and streaming caps."""
    active = limits or load_limits()
    limit = max_bytes if max_bytes is not None else active.http_max_bytes
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ResourceLimitError(
            "invalid_limit",
            "HTTP response byte limit must be a positive integer",
            limit=limit,
        )
    headers = getattr(response, "headers", None)
    raw_length = headers.get("Content-Length") if headers is not None else None
    if raw_length not in (None, ""):
        try:
            content_length = int(raw_length)
        except (TypeError, ValueError):
            content_length = None
        if content_length is not None:
            check_http_content_length(content_length, active)
            if content_length > limit:
                raise ResourceLimitError(
                    code,
                    f"HTTP response Content-Length {content_length} exceeds limit {limit}",
                    limit=limit,
                    observed=content_length,
                )
    return read_bounded(response, limit, code=code)


def check_file_size(path: str | os.PathLike[str], max_bytes: int, *, code: str = "download_file_bytes") -> None:
    if max_bytes <= 0:
        raise ResourceLimitError(
            "invalid_resource_limit",
            f"{code} byte limit must be positive",
            observed=max_bytes,
        )
    size = os.path.getsize(path)
    if size > max_bytes:
        raise ResourceLimitError(
            code,
            f"file {path} size {size} exceeds limit {max_bytes}",
            limit=max_bytes,
            observed=size,
        )


def check_excel_col(col_index: int, limits: ResourceLimits) -> None:
    if col_index > limits.excel_max_col:
        raise ResourceLimitError(
            "excel_max_col",
            f"Excel column index {col_index} exceeds limit {limits.excel_max_col} (XFD)",
            limit=limits.excel_max_col,
            observed=col_index,
        )


def check_excel_cells(cell_count: int, limits: ResourceLimits) -> None:
    if cell_count > limits.excel_max_cells:
        raise ResourceLimitError(
            "excel_max_cells",
            f"Excel cell count {cell_count} exceeds limit {limits.excel_max_cells}",
            limit=limits.excel_max_cells,
            observed=cell_count,
        )


def check_xlsx_zip(zf: Any, limits: ResourceLimits) -> None:
    """Inspect ZipFile members for uncompressed size and compression ratio bombs."""
    total_uncomp = 0
    total_comp = 0
    for info in zf.infolist():
        total_uncomp += info.file_size
        total_comp += info.compress_size
        if info.file_size > limits.xlsx_max_uncompressed:
            raise ResourceLimitError(
                "xlsx_uncompressed",
                f"XLSX member {info.filename} uncompressed {info.file_size} exceeds limit",
                limit=limits.xlsx_max_uncompressed,
                observed=info.file_size,
            )
        if info.compress_size > 0:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.xlsx_max_compression_ratio and info.file_size > 1024 * 1024:
                raise ResourceLimitError(
                    "xlsx_compression_ratio",
                    f"XLSX member {info.filename} compression ratio {ratio:.1f} exceeds limit",
                    limit=limits.xlsx_max_compression_ratio,
                    observed=ratio,
                )
    if total_uncomp > limits.xlsx_max_uncompressed:
        raise ResourceLimitError(
            "xlsx_uncompressed_total",
            f"XLSX total uncompressed {total_uncomp} exceeds limit",
            limit=limits.xlsx_max_uncompressed,
            observed=total_uncomp,
        )


def check_pdf_pages(page_count: int, limits: ResourceLimits) -> None:
    if page_count > limits.pdf_max_pages:
        raise ResourceLimitError(
            "pdf_max_pages",
            f"PDF pages {page_count} exceeds limit {limits.pdf_max_pages}",
            limit=limits.pdf_max_pages,
            observed=page_count,
        )


def check_pdf_bytes(size: int, limits: ResourceLimits) -> None:
    if size > limits.pdf_max_bytes:
        raise ResourceLimitError(
            "pdf_max_bytes",
            f"PDF size {size} exceeds limit {limits.pdf_max_bytes}",
            limit=limits.pdf_max_bytes,
            observed=size,
        )


def check_ocr_image(size_bytes: int, width: int = 0, height: int = 0, limits: Optional[ResourceLimits] = None) -> None:
    limits = limits or load_limits()
    if size_bytes > limits.ocr_max_image_bytes:
        raise ResourceLimitError(
            "ocr_max_image_bytes",
            f"OCR image bytes {size_bytes} exceeds limit",
            limit=limits.ocr_max_image_bytes,
            observed=size_bytes,
        )
    if width and height:
        pixels = width * height
        if pixels > limits.ocr_max_pixels:
            raise ResourceLimitError(
                "ocr_max_pixels",
                f"OCR pixels {pixels} exceeds limit",
                limit=limits.ocr_max_pixels,
                observed=pixels,
            )


def check_ocr_pages(page_count: int, limits: ResourceLimits) -> None:
    if page_count > limits.ocr_max_pages:
        raise ResourceLimitError(
            "ocr_max_pages",
            f"OCR pages {page_count} exceeds limit",
            limit=limits.ocr_max_pages,
            observed=page_count,
        )


def check_table_shape(rows: int, cols: int, limits: ResourceLimits) -> None:
    if rows > limits.table_max_rows:
        raise ResourceLimitError(
            "table_max_rows",
            f"table rows {rows} exceeds limit",
            limit=limits.table_max_rows,
            observed=rows,
        )
    cells = rows * max(cols, 0)
    if cells > limits.table_max_cells:
        raise ResourceLimitError(
            "table_max_cells",
            f"table cells {cells} exceeds limit",
            limit=limits.table_max_cells,
            observed=cells,
        )


def check_subprocess_output(size: int, limits: ResourceLimits) -> None:
    if size > limits.subprocess_max_output_bytes:
        raise ResourceLimitError(
            "subprocess_output_bytes",
            f"subprocess output {size} exceeds limit",
            limit=limits.subprocess_max_output_bytes,
            observed=size,
        )


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _stop_process(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def run_subprocess_bounded(
    command: Sequence[str | os.PathLike[str]],
    limits: ResourceLimits,
    *,
    timeout_sec: Optional[int] = None,
    max_output_bytes: Optional[int] = None,
    watch_dir: Optional[str | os.PathLike[str]] = None,
    max_generated_bytes: Optional[int] = None,
) -> BoundedCompletedProcess:
    """Run a process with bounded time, captured output, and optional generated files.

    Output is redirected to temporary files and polled so an untrusted helper cannot
    first exhaust parent-process memory via ``capture_output=True``.
    """

    timeout = timeout_sec if timeout_sec is not None else limits.subprocess_timeout_sec
    output_cap = (
        max_output_bytes
        if max_output_bytes is not None
        else limits.subprocess_max_output_bytes
    )
    if timeout <= 0 or output_cap <= 0:
        raise ResourceLimitError(
            "invalid_resource_limit",
            "subprocess timeout and output limits must be positive",
            observed={"timeout_sec": timeout, "max_output_bytes": output_cap},
        )
    if max_generated_bytes is not None and max_generated_bytes <= 0:
        raise ResourceLimitError(
            "invalid_resource_limit",
            "generated-file byte limit must be positive",
            observed=max_generated_bytes,
        )

    args = tuple(os.fspath(part) for part in command)
    # Windows can briefly retain redirected-file handles after a process exits.
    # Ignore only cleanup races; the resource-limit result must still propagate.
    with tempfile.TemporaryDirectory(
        prefix="d_research_proc_", ignore_cleanup_errors=True
    ) as tmp:
        stdout_path = Path(tmp) / "stdout.bin"
        stderr_path = Path(tmp) / "stderr.bin"
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            proc = subprocess.Popen(args, stdout=stdout_file, stderr=stderr_file)
            started = time.monotonic()
            try:
                while proc.poll() is None:
                    elapsed = time.monotonic() - started
                    if elapsed > timeout:
                        _stop_process(proc)
                        raise ResourceLimitError(
                            "subprocess_timeout",
                            f"subprocess exceeded timeout of {timeout} seconds",
                            limit=timeout,
                            observed=round(elapsed, 3),
                        )
                    captured = stdout_path.stat().st_size + stderr_path.stat().st_size
                    if captured > output_cap:
                        _stop_process(proc)
                        raise ResourceLimitError(
                            "subprocess_output_bytes",
                            f"subprocess output exceeds limit {output_cap}",
                            limit=output_cap,
                            observed=captured,
                        )
                    if watch_dir is not None and max_generated_bytes is not None:
                        generated = _directory_size(Path(watch_dir))
                        if generated > max_generated_bytes:
                            _stop_process(proc)
                            raise ResourceLimitError(
                                "subprocess_generated_bytes",
                                "subprocess generated files exceed limit",
                                limit=max_generated_bytes,
                                observed=generated,
                            )
                    time.sleep(0.02)
            except BaseException:
                _stop_process(proc)
                raise

        captured = stdout_path.stat().st_size + stderr_path.stat().st_size
        if captured > output_cap:
            raise ResourceLimitError(
                "subprocess_output_bytes",
                f"subprocess output exceeds limit {output_cap}",
                limit=output_cap,
                observed=captured,
            )
        if watch_dir is not None and max_generated_bytes is not None:
            generated = _directory_size(Path(watch_dir))
            if generated > max_generated_bytes:
                raise ResourceLimitError(
                    "subprocess_generated_bytes",
                    "subprocess generated files exceed limit",
                    limit=max_generated_bytes,
                    observed=generated,
                )
        return BoundedCompletedProcess(
            args=args,
            returncode=int(proc.returncode or 0),
            stdout=stdout_path.read_bytes(),
            stderr=stderr_path.read_bytes(),
        )


def write_incomplete_sidecar(path: str | os.PathLike[str], error: ResourceLimitError) -> None:
    """Mark an output sidecar as incomplete on limit violation."""
    payload = error.to_blocker()
    payload["status"] = "incomplete"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def incomplete_sidecar_path(
    output_path: str | os.PathLike[str], *, output_is_dir: bool = False
) -> Path:
    output = Path(output_path)
    if output_is_dir:
        return output / "_incomplete.meta.json"
    return Path(f"{output}.meta.json")


def emit_blocker(
    error: ResourceLimitError,
    output_path: Optional[str | os.PathLike[str]] = None,
    *,
    output_is_dir: bool = False,
) -> int:
    """Emit a structured blocker and, when possible, an incomplete sidecar."""

    if output_path:
        sidecar = incomplete_sidecar_path(output_path, output_is_dir=output_is_dir)
        try:
            write_incomplete_sidecar(sidecar, error)
        except OSError as exc:
            print(f"warning: could not write incomplete sidecar {sidecar}: {exc}", file=sys.stderr)
    print(json.dumps(error.to_blocker(), allow_nan=False), file=sys.stderr)
    return error.exit_code()


def emit_blocker_and_exit(error: ResourceLimitError, sidecar: Optional[str] = None) -> None:
    if sidecar:
        try:
            write_incomplete_sidecar(sidecar, error)
        except OSError as exc:
            print(f"warning: could not write incomplete sidecar {sidecar}: {exc}", file=sys.stderr)
    print(json.dumps(error.to_blocker(), allow_nan=False), file=sys.stderr)
    raise SystemExit(error.exit_code())


def run_self_test() -> int:
    errors: list[str] = []
    lim = load_limits({"http_max_bytes": 100})
    if lim.http_max_bytes != 100:
        errors.append("override http_max_bytes failed")

    try:
        check_http_content_length(200, lim)
        errors.append("expected http content-length raise")
    except ResourceLimitError as e:
        if e.code != "http_response_bytes" or not e.incomplete:
            errors.append("http blocker fields wrong")
        b = e.to_blocker()
        if b.get("complete") is not False or b.get("incomplete") is not True:
            errors.append("blocker must mark incomplete")

    import io

    try:
        read_bounded(io.BytesIO(b"x" * 50), 10)
        errors.append("read_bounded should raise")
    except ResourceLimitError as e:
        if e.code != "http_response_bytes":
            errors.append("read_bounded code wrong")

    ok = read_bounded(io.BytesIO(b"hello"), 10)
    if ok != b"hello":
        errors.append("read_bounded small body failed")

    class _Response(io.BytesIO):
        def __init__(self, body: bytes, content_length: str | None = None) -> None:
            super().__init__(body)
            self.headers = (
                {"Content-Length": content_length} if content_length is not None else {}
            )

    if read_http_response_bounded(_Response(b"hello"), max_bytes=10) != b"hello":
        errors.append("read_http_response_bounded small body failed")
    try:
        read_http_response_bounded(_Response(b"small", "999"), max_bytes=10)
        errors.append("read_http_response_bounded should reject large Content-Length")
    except ResourceLimitError:
        pass

    try:
        check_excel_col(EXCEL_XFD_COL_INDEX + 1, load_limits())
        errors.append("excel col should raise past XFD")
    except ResourceLimitError:
        pass

    try:
        check_excel_cells(10_000_000, load_limits({"excel_max_cells": 100}))
        errors.append("excel cells should raise")
    except ResourceLimitError as e:
        if e.code != "excel_max_cells":
            errors.append("excel cells code")

    try:
        check_pdf_pages(9999, load_limits({"pdf_max_pages": 5}))
        errors.append("pdf pages should raise")
    except ResourceLimitError:
        pass

    try:
        check_ocr_image(100, width=10000, height=10000, limits=load_limits({"ocr_max_pixels": 1000}))
        errors.append("ocr pixels should raise")
    except ResourceLimitError:
        pass

    try:
        check_table_shape(1_000_000, 10, load_limits({"table_max_rows": 100}))
        errors.append("table rows should raise")
    except ResourceLimitError:
        pass

    # Env override
    env_lim = load_limits(env={"D_RESEARCH_PDF_MAX_PAGES": "7"})
    if env_lim.pdf_max_pages != 7:
        errors.append("env override failed")

    cli_parser = argparse.ArgumentParser(add_help=False)
    add_resource_limit_arguments(
        cli_parser,
        ("download_max_bytes", "xlsx_max_compression_ratio"),
    )
    cli_args = cli_parser.parse_args(
        ["--max-file-bytes", "7", "--max-xlsx-compression-ratio", "2.5"]
    )
    if getattr(cli_args, "resource_limit_download_max_bytes", None) != 7:
        errors.append("CLI integer resource override parsing failed")
    if getattr(cli_args, "resource_limit_xlsx_max_compression_ratio", None) != 2.5:
        errors.append("CLI float resource override parsing failed")

    for bad_env in (
        {"D_RESEARCH_HTTP_MAX_BYTES": "0"},
        {"D_RESEARCH_HTTP_TIMEOUT_SEC": "0"},
        {"D_RESEARCH_HTTP_MAX_BYTES": "-1"},
        {"D_RESEARCH_XLSX_MAX_COMPRESSION_RATIO": "nan"},
        {"D_RESEARCH_XLSX_MAX_COMPRESSION_RATIO": "inf"},
        {"D_RESEARCH_EXCEL_MAX_COL": str(EXCEL_XFD_COL_INDEX + 1)},
    ):
        try:
            load_limits(env=bad_env)
            errors.append(f"invalid env limit should fail: {bad_env}")
        except ResourceLimitError as exc:
            if exc.code != "invalid_resource_limit":
                errors.append(f"invalid env wrong blocker: {bad_env}")

    try:
        read_bounded(io.BytesIO(b"must-not-silently-truncate"), -1)
        errors.append("negative direct read limit should fail")
    except ResourceLimitError:
        pass

    try:
        run_subprocess_bounded(
            [sys.executable, "-c", "print('x' * 1000)"],
            load_limits({"subprocess_max_output_bytes": 10}),
        )
        errors.append("bounded subprocess output cap should fail")
    except ResourceLimitError as exc:
        if exc.code != "subprocess_output_bytes":
            errors.append("bounded subprocess output wrong code")

    # Sidecar incomplete mark
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        side = Path(td) / "out.meta.json"
        err = ResourceLimitError("http_response_bytes", "too big", limit=1, observed=2)
        write_incomplete_sidecar(side, err)
        data = json.loads(side.read_text(encoding="utf-8"))
        if data.get("status") != "incomplete" or data.get("complete") is not False:
            errors.append("sidecar incomplete mark failed")

    if errors:
        print("resource_limits self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("resource_limits self-test ok")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Resource limit helpers")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    show = sub.add_parser("show")
    show.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return run_self_test()
        if args.cmd == "show":
            lim = load_limits()
            if args.json:
                print(json.dumps(lim.to_dict(), indent=2, allow_nan=False))
            else:
                for k, v in lim.to_dict().items():
                    print(f"{k}={v}")
            return 0
    except ResourceLimitError as error:
        return emit_blocker(error)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
