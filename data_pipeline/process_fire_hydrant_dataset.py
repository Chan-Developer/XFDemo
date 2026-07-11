#!/usr/bin/env python3
"""Build a structured manifest and time-based statistics for fire hydrant data."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT_ROOT = Path("/data/clj/data/XFData/室内消火栓")
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".txt",
}


@dataclass(frozen=True)
class FileRecord:
    absolute_path: str
    relative_path: str
    filename: str
    suffix: str
    size_bytes: int
    level_1: str
    level_2: str
    level_3: str
    status: str
    normal_label: str
    defect_group: str
    defect_label: str
    category_path: str
    effective_timestamp: str
    timestamp_source: str
    year: str
    month: str
    day: str


def should_skip_file(relative_path: Path) -> bool:
    """Skip derived helper files that are not raw dataset samples."""
    return relative_path.name.startswith("00_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process fire hydrant dataset and generate time-based statistics."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"Dataset root directory. Default: {DEFAULT_INPUT_ROOT}",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Directory for generated reports. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Optional output folder name. Defaults to current timestamp.",
    )
    parser.add_argument(
        "--group-by",
        choices=("day", "month", "year"),
        default="day",
        help="Time bucket granularity for statistics.",
    )
    parser.add_argument(
        "--disable-mtime-fallback",
        action="store_true",
        help="Do not fall back to filesystem modification time when filename has no timestamp.",
    )
    return parser.parse_args()


def parse_timestamp_from_name(name: str) -> tuple[datetime | None, str]:
    stem = Path(name).stem

    img_match = re.match(r"^(IMG|MVIMG)_(\d{8})_(\d{6})", stem, re.IGNORECASE)
    if img_match:
        return (
            datetime.strptime(
                f"{img_match.group(2)}{img_match.group(3)}", "%Y%m%d%H%M%S"
            ),
            f"filename:{img_match.group(1).upper()}",
        )

    wx_match = re.match(r"^微信图片_(\d{14})", stem)
    if wx_match:
        return (
            datetime.strptime(wx_match.group(1), "%Y%m%d%H%M%S"),
            "filename:WECHAT",
        )

    screenshot_match = re.match(r"^ScreenShot_(\d{4})-(\d{2})-(\d{2})_(\d{6})", stem)
    if screenshot_match:
        composed = "".join(screenshot_match.groups())
        return (
            datetime.strptime(composed, "%Y%m%d%H%M%S"),
            "filename:SCREENSHOT",
        )

    generic_match = re.search(r"(?<!\d)(20\d{6})[_-]?(\d{6})(?!\d)", stem)
    if generic_match:
        return (
            datetime.strptime(
                f"{generic_match.group(1)}{generic_match.group(2)}",
                "%Y%m%d%H%M%S",
            ),
            "filename:GENERIC",
        )

    return None, "unknown"


def bucket_for(dt: datetime | None, group_by: str) -> str:
    if dt is None:
        return "UNKNOWN"
    if group_by == "year":
        return dt.strftime("%Y")
    if group_by == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


def split_labels(
    relative_path: Path,
) -> tuple[str, str, str, str, str, str, str, str]:
    parts = relative_path.parts[:-1]
    level_1 = parts[0] if len(parts) > 0 else ""
    level_2 = parts[1] if len(parts) > 1 else ""
    level_3 = parts[2] if len(parts) > 2 else ""

    status = level_1 or "未归类"
    normal_label = ""
    defect_group = ""
    defect_label = ""

    if level_1 == "无隐患":
        normal_label = level_2
    elif level_1 == "有隐患":
        defect_group = level_2
        defect_label = level_3

    category_path = "/".join(parts)
    return (
        level_1,
        level_2,
        level_3,
        status,
        normal_label,
        defect_group,
        defect_label,
        category_path,
    )


def collect_records(input_root: Path, allow_mtime_fallback: bool) -> list[FileRecord]:
    records: list[FileRecord] = []

    for path in sorted(input_root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(input_root)
        if should_skip_file(rel_path):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        (
            level_1,
            level_2,
            level_3,
            status,
            normal_label,
            defect_group,
            defect_label,
            category_path,
        ) = split_labels(rel_path)

        parsed_dt, source = parse_timestamp_from_name(path.name)
        stat = path.stat()
        if parsed_dt is None and allow_mtime_fallback:
            parsed_dt = datetime.fromtimestamp(stat.st_mtime)
            source = "mtime"

        effective_timestamp = (
            parsed_dt.isoformat(sep=" ", timespec="seconds") if parsed_dt else ""
        )
        year = parsed_dt.strftime("%Y") if parsed_dt else ""
        month = parsed_dt.strftime("%Y-%m") if parsed_dt else ""
        day = parsed_dt.strftime("%Y-%m-%d") if parsed_dt else ""

        records.append(
            FileRecord(
                absolute_path=str(path),
                relative_path=str(rel_path),
                filename=path.name,
                suffix=path.suffix.lower(),
                size_bytes=stat.st_size,
                level_1=level_1,
                level_2=level_2,
                level_3=level_3,
                status=status,
                normal_label=normal_label,
                defect_group=defect_group,
                defect_label=defect_label,
                category_path=category_path,
                effective_timestamp=effective_timestamp,
                timestamp_source=source,
                year=year,
                month=month,
                day=day,
            )
        )

    records.sort(
        key=lambda item: (
            item.effective_timestamp == "",
            item.effective_timestamp,
            item.relative_path,
        )
    )
    return records


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_time_rows(records: list[FileRecord], group_by: str) -> list[dict[str, object]]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        dt = (
            datetime.fromisoformat(record.effective_timestamp)
            if record.effective_timestamp
            else None
        )
        bucket = bucket_for(dt, group_by)
        counter = buckets[bucket]
        counter["total_files"] += 1

        if record.status:
            counter[f"status:{record.status}"] += 1
        if record.defect_group:
            counter[f"group:{record.defect_group}"] += 1
        if record.normal_label:
            counter[f"normal:{record.normal_label}"] += 1
        if record.timestamp_source.startswith("filename:"):
            counter["timestamp:filename"] += 1
        elif record.timestamp_source == "mtime":
            counter["timestamp:mtime"] += 1
        else:
            counter["timestamp:unknown"] += 1

    rows: list[dict[str, object]] = []
    ordered_buckets = sorted(buckets, key=lambda item: (item == "UNKNOWN", item))
    for bucket in ordered_buckets:
        counter = buckets[bucket]
        rows.append(
            {
                "time_bucket": bucket,
                "total_files": counter["total_files"],
                "有隐患": counter["status:有隐患"],
                "无隐患": counter["status:无隐患"],
                "未归类": counter["status:未归类"],
                "外观问题": counter["group:外观问题"],
                "常见违法行为": counter["group:常见违法行为"],
                "组件问题": counter["group:组件问题"],
                "外观合规": counter["normal:外观合规"],
                "组件合规": counter["normal:组件合规"],
                "filename_time_files": counter["timestamp:filename"],
                "mtime_time_files": counter["timestamp:mtime"],
                "unknown_time_files": counter["timestamp:unknown"],
            }
        )
    return rows


def build_label_rows(records: list[FileRecord]) -> list[dict[str, object]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        if record.status == "无隐患":
            counter[(record.status, record.normal_label, "")] += 1
        elif record.status == "有隐患":
            counter[(record.status, record.defect_group, record.defect_label)] += 1
        else:
            counter[(record.status, "", "")] += 1

    rows: list[dict[str, object]] = []
    for (status, group_name, label_name), count in sorted(counter.items()):
        rows.append(
            {
                "status": status,
                "group_or_normal_label": group_name,
                "defect_label": label_name,
                "file_count": count,
            }
        )
    return rows


def write_markdown_summary(
    path: Path,
    input_root: Path,
    output_dir: Path,
    group_by: str,
    records: list[FileRecord],
    time_rows: list[dict[str, object]],
) -> None:
    status_counter = Counter(record.status for record in records)
    source_counter = Counter(record.timestamp_source for record in records)

    valid_times = [
        datetime.fromisoformat(record.effective_timestamp)
        for record in records
        if record.effective_timestamp
    ]
    time_min = min(valid_times).strftime("%Y-%m-%d %H:%M:%S") if valid_times else "N/A"
    time_max = max(valid_times).strftime("%Y-%m-%d %H:%M:%S") if valid_times else "N/A"

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# 室内消火栓数据处理统计\n\n")
        handle.write(f"- 数据目录: `{input_root}`\n")
        handle.write(f"- 输出目录: `{output_dir}`\n")
        handle.write(f"- 统计粒度: `{group_by}`\n")
        handle.write(f"- 文件总数: **{len(records)}**\n")
        handle.write(f"- 最早有效时间: `{time_min}`\n")
        handle.write(f"- 最晚有效时间: `{time_max}`\n\n")

        handle.write("## 状态分布\n\n")
        for status, count in sorted(status_counter.items()):
            handle.write(f"- {status}: {count}\n")

        handle.write("\n## 时间来源分布\n\n")
        for source, count in sorted(source_counter.items()):
            handle.write(f"- {source}: {count}\n")

        handle.write("\n## 时间统计表\n\n")
        handle.write(
            "| 时间桶 | 总文件数 | 有隐患 | 无隐患 | 外观问题 | 常见违法行为 | 组件问题 | 文件名时间 | mtime补全 |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in time_rows:
            handle.write(
                f"| {row['time_bucket']} | {row['total_files']} | {row['有隐患']} | "
                f"{row['无隐患']} | {row['外观问题']} | {row['常见违法行为']} | "
                f"{row['组件问题']} | {row['filename_time_files']} | "
                f"{row['mtime_time_files']} |\n"
            )


def main() -> None:
    args = parse_args()
    input_root = args.input_root.resolve()
    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")

    run_name = args.run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root.resolve() / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    records = collect_records(
        input_root=input_root,
        allow_mtime_fallback=not args.disable_mtime_fallback,
    )
    if not records:
        raise SystemExit(f"No supported files found under: {input_root}")

    manifest_path = output_dir / "dataset_manifest.csv"
    label_stats_path = output_dir / "label_statistics.csv"
    time_stats_csv_path = output_dir / f"time_statistics_{args.group_by}.csv"
    time_stats_md_path = output_dir / f"time_statistics_{args.group_by}.md"

    write_csv(
        manifest_path,
        [
            "absolute_path",
            "relative_path",
            "filename",
            "suffix",
            "size_bytes",
            "level_1",
            "level_2",
            "level_3",
            "status",
            "normal_label",
            "defect_group",
            "defect_label",
            "category_path",
            "effective_timestamp",
            "timestamp_source",
            "year",
            "month",
            "day",
        ],
        [record.__dict__ for record in records],
    )

    label_rows = build_label_rows(records)
    write_csv(
        label_stats_path,
        ["status", "group_or_normal_label", "defect_label", "file_count"],
        label_rows,
    )

    time_rows = build_time_rows(records, args.group_by)
    write_csv(
        time_stats_csv_path,
        [
            "time_bucket",
            "total_files",
            "有隐患",
            "无隐患",
            "未归类",
            "外观问题",
            "常见违法行为",
            "组件问题",
            "外观合规",
            "组件合规",
            "filename_time_files",
            "mtime_time_files",
            "unknown_time_files",
        ],
        time_rows,
    )

    write_markdown_summary(
        time_stats_md_path,
        input_root=input_root,
        output_dir=output_dir,
        group_by=args.group_by,
        records=records,
        time_rows=time_rows,
    )

    print(f"Processed files: {len(records)}")
    print(f"Manifest: {manifest_path}")
    print(f"Label stats: {label_stats_path}")
    print(f"Time stats CSV: {time_stats_csv_path}")
    print(f"Time stats Markdown: {time_stats_md_path}")


if __name__ == "__main__":
    main()
