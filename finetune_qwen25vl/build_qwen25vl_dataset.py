#!/usr/bin/env python3
"""Single-script Qwen2.5-VL fine-tuning dataset builder.

Pipeline:
1. Scan folder-labeled fire hydrant images.
2. Compute sha256 and merge same-image multi-label samples.
3. Skip conflicting samples where one image is both normal and defective.
4. Call local vLLM Qwen2.5-VL teacher to enrich each sample.
5. Export merged train/val/test jsonl plus reports.

Typical usage:
    python3 build_qwen25vl_dataset.py --run-name baseline_qwen25vl

Useful debug usage:
    python3 build_qwen25vl_dataset.py --skip-vllm --max-samples 100 --output-root /tmp/qwen25_debug
"""


'''
python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py --run-name baseline_qwen25vl

python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py \
    --run-name baseline_qwen25vl \
    --vllm-api-base http://127.0.0.1:你的端口/v1 \
    --model-name 你的模型名
'''

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT_ROOT = Path("/data/clj/data/XFData/室内消火栓")
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_SCENE_TYPES = {"室内消火栓箱", "室内消火栓", "非目标对象", "无法判断"}
ALLOWED_DOOR_STATES = {"开启", "关闭", "半开", "不可见", "不适用"}
ALLOWED_RISK_LEVELS = {"低", "中", "高", "待复核"}

FINAL_SYSTEM_PROMPT = (
    "你是室内消火栓图像审核助手。请根据图片内容识别室内消火栓或消火栓箱状态，"
    "只依据清晰可见证据判断，不要臆测内部不可见组件，并输出严格 JSON。"
)

FINAL_USER_PROMPT = """请检查这张图片中的室内消火栓或消火栓箱，并输出 JSON。

正常标签：
["外观合规", "组件合规"]

异常标签：
["无'消火栓'和'FIRE HYDRANT'字样","无操作说明标注","无耐久铭牌","破坏隔墙耐火性","箱体、箱门损坏","箱门可燃材料","箱门辨识度低","供水管网材质存在问题","供水阀门关闭","拆除消火栓","消防用水挪作他用","箱内堆放杂物","箱门锁闭","被圈占、遮挡、箱门被遮掩","手轮缺失","按钮传输或控制线路未穿管保护或保护不到位","栓体缺失","栓口方向错误","消防接口缺失","消防水带不足","消防水带损坏","消防水带缺失","消防水枪不足","消防水枪缺失","消防软管缺失","缺少消火栓箱","软管折弯严重、损坏"]

只输出这些字段：
target_present, scene_type, door_state, status, normal_labels, defect_labels, risk_level, needs_review, review_reason, evidence, short_conclusion
"""

TEACHER_SYSTEM_PROMPT = """你是一名室内消火栓图像审核教师模型。

你需要查看单张图片，并输出一个严格 JSON 对象。
规则：
1. 只依据图片中清晰可见的证据判断。
2. 若箱门关闭、内部不可见、视角不全、模糊或被遮挡，不要臆测内部组件缺失。
3. evidence 只写 1 到 3 条直接可见证据。
4. 只输出 JSON，不要输出解释、markdown、代码块。

允许的 scene_type:
["室内消火栓箱", "室内消火栓", "非目标对象", "无法判断"]

允许的 door_state:
["开启", "关闭", "半开", "不可见", "不适用"]

允许的 risk_level:
["低", "中", "高", "待复核"]
"""

TEACHER_USER_TEMPLATE = """请查看这张图片，并结合下面的目录标签提示，输出严格 JSON。

目录标签提示：
- status: {status}
- normal_labels: {normal_labels}
- defect_labels: {defect_labels}

输出字段固定为：
scene_type, door_state, risk_level, needs_review, review_reason, evidence, short_conclusion, predicted_status, predicted_normal_labels, predicted_defect_labels

要求：
1. predicted_status 只能是 "无隐患"、"有隐患"、"无法判断"、"非目标对象"。
2. predicted_normal_labels 和 predicted_defect_labels 必须是数组。
3. 如果证据不足，needs_review=true。
4. 只输出 JSON。
"""


@dataclass(frozen=True)
class RawRecord:
    sha256: str
    absolute_path: str
    relative_path: str
    filename: str
    size_bytes: int
    level_1: str
    level_2: str
    level_3: str
    status: str
    normal_label: str
    defect_group: str
    defect_label: str
    effective_time: str
    time_source: str
    time_bucket: str


@dataclass(frozen=True)
class TeacherResult:
    ok: bool
    scene_type: str
    door_state: str
    risk_level: str
    needs_review: bool
    review_reason: str
    evidence: tuple[str, ...]
    short_conclusion: str
    predicted_status: str
    predicted_normal_labels: tuple[str, ...]
    predicted_defect_labels: tuple[str, ...]
    raw_response: str
    error: str


@dataclass(frozen=True)
class CanonicalSample:
    sample_id: str
    sha256: str
    image_path: str
    relative_path: str
    status: str
    normal_labels: tuple[str, ...]
    defect_groups: tuple[str, ...]
    defect_labels: tuple[str, ...]
    source_count: int
    effective_time: str
    time_source: str
    time_bucket: str
    split: str
    teacher: TeacherResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Qwen2.5-VL fine-tuning data with folder labels and local vLLM teacher."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"Dataset root. Default: {DEFAULT_INPUT_ROOT}",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Output root. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Output folder name. Defaults to current timestamp.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation ratio.")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Test ratio.")
    parser.add_argument(
        "--time-bucket",
        choices=("day", "month", "year"),
        default="month",
        help="Time bucket granularity for reports.",
    )
    parser.add_argument(
        "--skip-vllm",
        action="store_true",
        help="Skip teacher-model enrichment and build dataset from folder labels only.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Optional limit for canonical samples, mainly for debug.",
    )
    parser.add_argument(
        "--vllm-api-base",
        type=str,
        default=os.getenv("VLLM_API_BASE", "http://localhost:9300/v1"),
        help="OpenAI-compatible vLLM base URL.",
    )
    parser.add_argument(
        "--vllm-api-key",
        type=str,
        default=os.getenv("VLLM_API_KEY", "EMPTY"),
        help="vLLM API key. Default uses env or EMPTY.",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=os.getenv("MODEL_NAME", "Qwen2.5-VL-72B-Instruct"),
        help="Served model name for the teacher.",
    )
    parser.add_argument(
        "--teacher-max-tokens",
        type=int,
        default=1200,
        help="Max tokens for teacher responses.",
    )
    parser.add_argument(
        "--teacher-temperature",
        type=float,
        default=0.1,
        help="Temperature for teacher responses.",
    )
    parser.add_argument(
        "--teacher-retries",
        type=int,
        default=2,
        help="Retry count for teacher requests.",
    )
    parser.add_argument(
        "--teacher-timeout",
        type=int,
        default=180,
        help="HTTP timeout in seconds for teacher requests.",
    )
    return parser.parse_args()


def ensure_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    total = round(train_ratio + val_ratio + test_ratio, 6)
    if total != 1.0:
        raise SystemExit("train-ratio + val-ratio + test-ratio must equal 1.0")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_effective_time(name: str, mtime: float) -> tuple[datetime, str]:
    stem = Path(name).stem

    img_match = re.match(r"^(IMG|MVIMG)_(\d{8})_(\d{6})", stem, re.IGNORECASE)
    if img_match:
        return (
            datetime.strptime(
                f"{img_match.group(2)}{img_match.group(3)}",
                "%Y%m%d%H%M%S",
            ),
            f"filename:{img_match.group(1).upper()}",
        )

    wx_match = re.match(r"^微信图片_(\d{14})", stem)
    if wx_match:
        return datetime.strptime(wx_match.group(1), "%Y%m%d%H%M%S"), "filename:WECHAT"

    screenshot_match = re.match(r"^ScreenShot_(\d{4})-(\d{2})-(\d{2})_(\d{6})", stem)
    if screenshot_match:
        timestamp = "".join(screenshot_match.groups())
        return datetime.strptime(timestamp, "%Y%m%d%H%M%S"), "filename:SCREENSHOT"

    generic_match = re.search(r"(?<!\d)(20\d{6})[_-]?(\d{6})(?!\d)", stem)
    if generic_match:
        return (
            datetime.strptime(
                f"{generic_match.group(1)}{generic_match.group(2)}",
                "%Y%m%d%H%M%S",
            ),
            "filename:GENERIC",
        )

    return datetime.fromtimestamp(mtime), "mtime"


def time_bucket_of(dt: datetime, mode: str) -> str:
    if mode == "year":
        return dt.strftime("%Y")
    if mode == "day":
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m")


def extract_labels(rel_path: Path) -> tuple[str, str, str, str, str, str]:
    parts = rel_path.parts[:-1]
    level_1 = parts[0] if len(parts) > 0 else ""
    level_2 = parts[1] if len(parts) > 1 else ""
    level_3 = parts[2] if len(parts) > 2 else ""

    status = level_1 or "未归类"
    normal_label = level_2 if level_1 == "无隐患" else ""
    defect_group = level_2 if level_1 == "有隐患" else ""
    defect_label = level_3 if level_1 == "有隐患" else ""
    return level_1, level_2, level_3, status, normal_label, defect_group, defect_label


def collect_raw_records(input_root: Path, bucket_mode: str) -> list[RawRecord]:
    records: list[RawRecord] = []

    for path in sorted(input_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("00_"):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue

        stat = path.stat()
        rel_path = path.relative_to(input_root)
        (
            level_1,
            level_2,
            level_3,
            status,
            normal_label,
            defect_group,
            defect_label,
        ) = extract_labels(rel_path)
        dt, source = parse_effective_time(path.name, stat.st_mtime)

        records.append(
            RawRecord(
                sha256=file_sha256(path),
                absolute_path=str(path),
                relative_path=str(rel_path),
                filename=path.name,
                size_bytes=stat.st_size,
                level_1=level_1,
                level_2=level_2,
                level_3=level_3,
                status=status,
                normal_label=normal_label,
                defect_group=defect_group,
                defect_label=defect_label,
                effective_time=dt.isoformat(sep=" ", timespec="seconds"),
                time_source=source,
                time_bucket=time_bucket_of(dt, bucket_mode),
            )
        )

    return records


def merge_records(
    records: list[RawRecord],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, list[RawRecord]] = defaultdict(list)
    for record in records:
        grouped[record.sha256].append(record)

    canonical_rows: list[dict[str, object]] = []
    conflict_rows: list[dict[str, object]] = []

    for sha256, items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: item.relative_path)
        statuses = {item.status for item in items}
        normal_labels = sorted({item.normal_label for item in items if item.normal_label})
        defect_groups = sorted({item.defect_group for item in items if item.defect_group})
        defect_labels = sorted({item.defect_label for item in items if item.defect_label})
        conflict_reasons: list[str] = []

        if "有隐患" in statuses and "无隐患" in statuses:
            conflict_reasons.append("same_image_has_normal_and_defect_labels")
        if not statuses:
            conflict_reasons.append("missing_status")

        representative = items[0]
        earliest_time = min(item.effective_time for item in items)

        if conflict_reasons:
            conflict_rows.append(
                {
                    "sha256": sha256,
                    "representative_path": representative.absolute_path,
                    "source_count": len(items),
                    "statuses": "|".join(sorted(statuses)),
                    "normal_labels": "|".join(normal_labels),
                    "defect_groups": "|".join(defect_groups),
                    "defect_labels": "|".join(defect_labels),
                    "reason": "|".join(conflict_reasons),
                    "source_paths": "||".join(item.absolute_path for item in items),
                }
            )
            continue

        status = "有隐患" if "有隐患" in statuses else "无隐患"
        canonical_rows.append(
            {
                "sha256": sha256,
                "image_path": representative.absolute_path,
                "relative_path": representative.relative_path,
                "status": status,
                "normal_labels": tuple(normal_labels),
                "defect_groups": tuple(defect_groups),
                "defect_labels": tuple(defect_labels),
                "source_count": len(items),
                "effective_time": earliest_time,
                "time_source": representative.time_source,
                "time_bucket": representative.time_bucket,
            }
        )

    return canonical_rows, conflict_rows


def stratify_key(row: dict[str, object]) -> str:
    if row["status"] == "有隐患" and row["defect_labels"]:
        labels = tuple(row["defect_labels"])
        return f"defect:{labels[0]}"
    if row["status"] == "无隐患" and row["normal_labels"]:
        labels = tuple(row["normal_labels"])
        return f"normal:{labels[0]}"
    return f"status:{row['status']}"


def assign_splits(
    rows: list[dict[str, object]],
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
    max_samples: int,
) -> list[CanonicalSample]:
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        buckets[stratify_key(row)].append(row)

    assigned: list[CanonicalSample] = []

    for _, bucket_rows in sorted(buckets.items()):
        rng.shuffle(bucket_rows)
        total = len(bucket_rows)

        if total == 1:
            split_counts = {"train": 1, "val": 0, "test": 0}
        elif total == 2:
            split_counts = {"train": 1, "val": 1, "test": 0}
        else:
            train_count = max(1, int(round(total * train_ratio)))
            val_count = int(round(total * val_ratio))
            test_count = total - train_count - val_count

            if test_count < 1 and total >= 3:
                test_count = 1
                train_count = max(1, train_count - 1)
            if val_count < 1 and total >= 4:
                val_count = 1
                train_count = max(1, train_count - 1)

            while train_count + val_count + test_count > total:
                if train_count >= val_count and train_count >= test_count and train_count > 1:
                    train_count -= 1
                elif val_count >= test_count and val_count > 0:
                    val_count -= 1
                else:
                    test_count = max(0, test_count - 1)

            split_counts = {"train": train_count, "val": val_count, "test": test_count}

        split_sequence = (
            ["train"] * split_counts["train"]
            + ["val"] * split_counts["val"]
            + ["test"] * split_counts["test"]
        )
        if len(split_sequence) < total:
            split_sequence.extend(["train"] * (total - len(split_sequence)))

        for index, row in enumerate(bucket_rows):
            if max_samples and len(assigned) >= max_samples:
                return assigned
            assigned.append(
                CanonicalSample(
                    sample_id=f"fh_{len(assigned) + 1:06d}",
                    sha256=str(row["sha256"]),
                    image_path=str(row["image_path"]),
                    relative_path=str(row["relative_path"]),
                    status=str(row["status"]),
                    normal_labels=tuple(row["normal_labels"]),
                    defect_groups=tuple(row["defect_groups"]),
                    defect_labels=tuple(row["defect_labels"]),
                    source_count=int(row["source_count"]),
                    effective_time=str(row["effective_time"]),
                    time_source=str(row["time_source"]),
                    time_bucket=str(row["time_bucket"]),
                    split=split_sequence[index],
                    teacher=TeacherResult(
                        ok=False,
                        scene_type="室内消火栓",
                        door_state="不可见",
                        risk_level=derive_risk_level(str(row["status"]), tuple(row["defect_labels"])),
                        needs_review=False,
                        review_reason="",
                        evidence=(),
                        short_conclusion="",
                        predicted_status="",
                        predicted_normal_labels=(),
                        predicted_defect_labels=(),
                        raw_response="",
                        error="teacher_skipped",
                    ),
                )
            )

    return assigned


def encode_image_to_data_uri(image_path: str) -> str:
    path = Path(image_path)
    mime = "image/jpeg"
    if path.suffix.lower() == ".png":
        mime = "image/png"
    elif path.suffix.lower() == ".webp":
        mime = "image/webp"
    elif path.suffix.lower() == ".bmp":
        mime = "image/bmp"

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def extract_json_object(raw_text: str) -> dict[str, object]:
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def normalize_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            item = item.strip()
            if item:
                items.append(item)
    return tuple(items)


def normalize_teacher_result(data: dict[str, object], raw_response: str) -> TeacherResult:
    scene_type = str(data.get("scene_type", "室内消火栓")).strip()
    if scene_type not in ALLOWED_SCENE_TYPES:
        scene_type = "室内消火栓"

    door_state = str(data.get("door_state", "不可见")).strip()
    if door_state not in ALLOWED_DOOR_STATES:
        door_state = "不可见"

    risk_level = str(data.get("risk_level", "待复核")).strip()
    if risk_level not in ALLOWED_RISK_LEVELS:
        risk_level = "待复核"

    needs_review = bool(data.get("needs_review", False))
    review_reason = str(data.get("review_reason", "")).strip()
    evidence = normalize_string_list(data.get("evidence"))[:3]
    short_conclusion = str(data.get("short_conclusion", "")).strip()
    predicted_status = str(data.get("predicted_status", "")).strip()
    predicted_normal_labels = normalize_string_list(data.get("predicted_normal_labels"))
    predicted_defect_labels = normalize_string_list(data.get("predicted_defect_labels"))

    return TeacherResult(
        ok=True,
        scene_type=scene_type,
        door_state=door_state,
        risk_level=risk_level,
        needs_review=needs_review,
        review_reason=review_reason,
        evidence=evidence,
        short_conclusion=short_conclusion,
        predicted_status=predicted_status,
        predicted_normal_labels=predicted_normal_labels,
        predicted_defect_labels=predicted_defect_labels,
        raw_response=raw_response,
        error="",
    )


def call_vllm_teacher(
    sample: CanonicalSample,
    api_base: str,
    api_key: str,
    model_name: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
    retries: int,
) -> TeacherResult:
    api_base = api_base.rstrip("/")
    url = f"{api_base}/chat/completions"
    data_uri = encode_image_to_data_uri(sample.image_path)
    user_prompt = TEACHER_USER_TEMPLATE.format(
        status=sample.status,
        normal_labels=list(sample.normal_labels),
        defect_labels=list(sample.defect_labels),
    )
    payload = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    last_error = ""
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            raw_content = response_data["choices"][0]["message"]["content"]
            if isinstance(raw_content, list):
                raw_content = "".join(
                    item.get("text", "") for item in raw_content if isinstance(item, dict)
                )
            parsed = extract_json_object(str(raw_content))
            return normalize_teacher_result(parsed, str(raw_content))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))

    return TeacherResult(
        ok=False,
        scene_type="室内消火栓",
        door_state="不可见",
        risk_level=derive_risk_level(sample.status, sample.defect_labels),
        needs_review=False,
        review_reason="",
        evidence=(),
        short_conclusion="",
        predicted_status="",
        predicted_normal_labels=(),
        predicted_defect_labels=(),
        raw_response="",
        error=last_error or "teacher_request_failed",
    )


def derive_risk_level(status: str, defect_labels: tuple[str, ...]) -> str:
    if status != "有隐患":
        return "低"
    high_risk_labels = {
        "消防水带缺失",
        "消防水枪缺失",
        "栓体缺失",
        "缺少消火栓箱",
        "供水阀门关闭",
        "拆除消火栓",
    }
    if any(label in high_risk_labels for label in defect_labels):
        return "高"
    return "中"


def fallback_conclusion(status: str, normal_labels: tuple[str, ...], defect_labels: tuple[str, ...]) -> str:
    if status == "有隐患" and defect_labels:
        return f"存在缺陷：{','.join(defect_labels[:3])}"
    if status == "无隐患" and normal_labels:
        return f"目录标签显示为{','.join(normal_labels)}"
    return "需要进一步人工复核"


def merged_target(sample: CanonicalSample) -> dict[str, object]:
    teacher = sample.teacher
    risk_level = teacher.risk_level if teacher.ok else derive_risk_level(sample.status, sample.defect_labels)
    short_conclusion = teacher.short_conclusion if teacher.ok and teacher.short_conclusion else fallback_conclusion(
        sample.status, sample.normal_labels, sample.defect_labels
    )

    return {
        "target_present": True,
        "scene_type": teacher.scene_type if teacher.ok else "室内消火栓",
        "door_state": teacher.door_state if teacher.ok else "不可见",
        "status": sample.status,
        "normal_labels": list(sample.normal_labels),
        "defect_labels": list(sample.defect_labels),
        "risk_level": risk_level,
        "needs_review": teacher.needs_review if teacher.ok else False,
        "review_reason": teacher.review_reason if teacher.ok else "",
        "evidence": list(teacher.evidence) if teacher.ok else [],
        "short_conclusion": short_conclusion,
    }


def enrich_with_teacher(samples: list[CanonicalSample], args: argparse.Namespace) -> list[CanonicalSample]:
    if args.skip_vllm:
        return samples

    enriched: list[CanonicalSample] = []
    total = len(samples)

    for index, sample in enumerate(samples, start=1):
        print(f"[teacher] {index}/{total} {sample.relative_path}", flush=True)
        teacher = call_vllm_teacher(
            sample=sample,
            api_base=args.vllm_api_base,
            api_key=args.vllm_api_key,
            model_name=args.model_name,
            max_tokens=args.teacher_max_tokens,
            temperature=args.teacher_temperature,
            timeout=args.teacher_timeout,
            retries=args.teacher_retries,
        )
        enriched.append(
            CanonicalSample(
                sample_id=sample.sample_id,
                sha256=sample.sha256,
                image_path=sample.image_path,
                relative_path=sample.relative_path,
                status=sample.status,
                normal_labels=sample.normal_labels,
                defect_groups=sample.defect_groups,
                defect_labels=sample.defect_labels,
                source_count=sample.source_count,
                effective_time=sample.effective_time,
                time_source=sample.time_source,
                time_bucket=sample.time_bucket,
                split=sample.split,
                teacher=teacher,
            )
        )

    return enriched


def jsonl_record(sample: CanonicalSample) -> dict[str, object]:
    return {
        "id": sample.sample_id,
        "image": sample.image_path,
        "messages": [
            {"role": "system", "content": FINAL_SYSTEM_PROMPT},
            {"role": "user", "content": FINAL_USER_PROMPT},
            {
                "role": "assistant",
                "content": json.dumps(
                    merged_target(sample),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_time_statistics(samples: list[CanonicalSample]) -> list[dict[str, object]]:
    counter_map: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for sample in samples:
        key = (sample.time_bucket, sample.split)
        counter = counter_map[key]
        counter["total"] += 1
        counter[f"status:{sample.status}"] += 1
        if sample.defect_groups:
            for group in sample.defect_groups:
                counter[f"group:{group}"] += 1
        if sample.normal_labels:
            for label in sample.normal_labels:
                counter[f"normal:{label}"] += 1

    rows: list[dict[str, object]] = []
    for (time_bucket, split), counter in sorted(counter_map.items()):
        rows.append(
            {
                "time_bucket": time_bucket,
                "split": split,
                "total_samples": counter["total"],
                "有隐患": counter["status:有隐患"],
                "无隐患": counter["status:无隐患"],
                "外观问题": counter["group:外观问题"],
                "常见违法行为": counter["group:常见违法行为"],
                "组件问题": counter["group:组件问题"],
                "外观合规": counter["normal:外观合规"],
                "组件合规": counter["normal:组件合规"],
            }
        )
    return rows


def build_split_statistics(samples: list[CanonicalSample]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    split_counter: dict[str, Counter[str]] = defaultdict(Counter)

    for sample in samples:
        counter = split_counter[sample.split]
        counter["total"] += 1
        counter[f"status:{sample.status}"] += 1
        counter[f"teacher_ok:{sample.teacher.ok}"] += 1
        if sample.teacher.error == "teacher_skipped":
            counter["teacher_skipped"] += 1
        elif not sample.teacher.ok:
            counter["teacher_failed"] += 1

    for split, counter in sorted(split_counter.items()):
        rows.append(
            {
                "split": split,
                "total_samples": counter["total"],
                "有隐患": counter["status:有隐患"],
                "无隐患": counter["status:无隐患"],
                "teacher_ok": counter["teacher_ok:True"],
                "teacher_skipped": counter["teacher_skipped"],
                "teacher_failed": counter["teacher_failed"],
            }
        )
    return rows


def build_label_statistics(samples: list[CanonicalSample]) -> list[dict[str, object]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for sample in samples:
        if sample.status == "有隐患":
            for defect in sample.defect_labels:
                counter[(sample.split, "defect", defect)] += 1
        elif sample.status == "无隐患":
            for label in sample.normal_labels:
                counter[(sample.split, "normal", label)] += 1

    rows: list[dict[str, object]] = []
    for (split, label_type, label_name), count in sorted(counter.items()):
        rows.append(
            {
                "split": split,
                "label_type": label_type,
                "label_name": label_name,
                "sample_count": count,
            }
        )
    return rows


def write_report(
    path: Path,
    input_root: Path,
    output_dir: Path,
    raw_records: list[RawRecord],
    canonical_samples: list[CanonicalSample],
    conflict_rows: list[dict[str, object]],
    time_statistics: list[dict[str, object]],
) -> None:
    split_counter = Counter(sample.split for sample in canonical_samples)
    status_counter = Counter(sample.status for sample in canonical_samples)
    teacher_ok = sum(1 for sample in canonical_samples if sample.teacher.ok)
    teacher_skipped = sum(1 for sample in canonical_samples if sample.teacher.error == "teacher_skipped")
    teacher_failed = sum(
        1 for sample in canonical_samples if not sample.teacher.ok and sample.teacher.error != "teacher_skipped"
    )
    multilabel_count = sum(1 for sample in canonical_samples if len(sample.defect_labels) > 1)

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Qwen2.5-VL 微调数据报告\n\n")
        handle.write(f"- 输入目录: `{input_root}`\n")
        handle.write(f"- 输出目录: `{output_dir}`\n")
        handle.write(f"- 原始图像数: **{len(raw_records)}**\n")
        handle.write(f"- 去重后样本数: **{len(canonical_samples)}**\n")
        handle.write(f"- 冲突样本数: **{len(conflict_rows)}**\n")
        handle.write(f"- 多标签缺陷样本数: **{multilabel_count}**\n")
        handle.write(f"- 教师成功数: **{teacher_ok}**\n")
        handle.write(f"- 教师跳过数: **{teacher_skipped}**\n")
        handle.write(f"- 教师失败数: **{teacher_failed}**\n\n")

        handle.write("## Split 分布\n\n")
        for split, count in sorted(split_counter.items()):
            handle.write(f"- {split}: {count}\n")

        handle.write("\n## 状态分布\n\n")
        for status, count in sorted(status_counter.items()):
            handle.write(f"- {status}: {count}\n")

        handle.write("\n## 时间统计\n\n")
        handle.write("| 时间桶 | split | 总样本 | 有隐患 | 无隐患 | 外观问题 | 常见违法行为 | 组件问题 |\n")
        handle.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for row in time_statistics:
            handle.write(
                f"| {row['time_bucket']} | {row['split']} | {row['total_samples']} | "
                f"{row['有隐患']} | {row['无隐患']} | {row['外观问题']} | "
                f"{row['常见违法行为']} | {row['组件问题']} |\n"
            )


def main() -> None:
    args = parse_args()
    ensure_ratios(args.train_ratio, args.val_ratio, args.test_ratio)

    input_root = args.input_root.resolve()
    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")

    run_name = args.run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root.resolve() / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_records = collect_raw_records(input_root, args.time_bucket)
    if not raw_records:
        raise SystemExit(f"No image files found under: {input_root}")

    canonical_rows, conflict_rows = merge_records(raw_records)
    samples = assign_splits(
        rows=canonical_rows,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        max_samples=args.max_samples,
    )
    samples = enrich_with_teacher(samples, args)

    raw_manifest_path = output_dir / "raw_manifest.csv"
    canonical_path = output_dir / "canonical_samples.csv"
    conflicts_path = output_dir / "conflicts.csv"
    split_stats_path = output_dir / "split_statistics.csv"
    label_stats_path = output_dir / "label_statistics.csv"
    time_stats_path = output_dir / "time_statistics.csv"
    report_path = output_dir / "dataset_report.md"

    write_csv(
        raw_manifest_path,
        [
            "sha256",
            "absolute_path",
            "relative_path",
            "filename",
            "size_bytes",
            "level_1",
            "level_2",
            "level_3",
            "status",
            "normal_label",
            "defect_group",
            "defect_label",
            "effective_time",
            "time_source",
            "time_bucket",
        ],
        [record.__dict__ for record in raw_records],
    )

    write_csv(
        canonical_path,
        [
            "sample_id",
            "sha256",
            "image_path",
            "relative_path",
            "status",
            "normal_labels",
            "defect_groups",
            "defect_labels",
            "source_count",
            "effective_time",
            "time_source",
            "time_bucket",
            "split",
            "teacher_ok",
            "teacher_scene_type",
            "teacher_door_state",
            "teacher_risk_level",
            "teacher_needs_review",
            "teacher_review_reason",
            "teacher_evidence",
            "teacher_short_conclusion",
            "teacher_predicted_status",
            "teacher_predicted_normal_labels",
            "teacher_predicted_defect_labels",
            "teacher_error",
        ],
        [
            {
                "sample_id": sample.sample_id,
                "sha256": sample.sha256,
                "image_path": sample.image_path,
                "relative_path": sample.relative_path,
                "status": sample.status,
                "normal_labels": "|".join(sample.normal_labels),
                "defect_groups": "|".join(sample.defect_groups),
                "defect_labels": "|".join(sample.defect_labels),
                "source_count": sample.source_count,
                "effective_time": sample.effective_time,
                "time_source": sample.time_source,
                "time_bucket": sample.time_bucket,
                "split": sample.split,
                "teacher_ok": sample.teacher.ok,
                "teacher_scene_type": sample.teacher.scene_type,
                "teacher_door_state": sample.teacher.door_state,
                "teacher_risk_level": sample.teacher.risk_level,
                "teacher_needs_review": sample.teacher.needs_review,
                "teacher_review_reason": sample.teacher.review_reason,
                "teacher_evidence": "|".join(sample.teacher.evidence),
                "teacher_short_conclusion": sample.teacher.short_conclusion,
                "teacher_predicted_status": sample.teacher.predicted_status,
                "teacher_predicted_normal_labels": "|".join(sample.teacher.predicted_normal_labels),
                "teacher_predicted_defect_labels": "|".join(sample.teacher.predicted_defect_labels),
                "teacher_error": sample.teacher.error,
            }
            for sample in samples
        ],
    )

    write_csv(
        conflicts_path,
        [
            "sha256",
            "representative_path",
            "source_count",
            "statuses",
            "normal_labels",
            "defect_groups",
            "defect_labels",
            "reason",
            "source_paths",
        ],
        conflict_rows,
    )

    split_statistics = build_split_statistics(samples)
    write_csv(
        split_stats_path,
        ["split", "total_samples", "有隐患", "无隐患", "teacher_ok", "teacher_skipped", "teacher_failed"],
        split_statistics,
    )

    label_statistics = build_label_statistics(samples)
    write_csv(
        label_stats_path,
        ["split", "label_type", "label_name", "sample_count"],
        label_statistics,
    )

    time_statistics = build_time_statistics(samples)
    write_csv(
        time_stats_path,
        [
            "time_bucket",
            "split",
            "total_samples",
            "有隐患",
            "无隐患",
            "外观问题",
            "常见违法行为",
            "组件问题",
            "外观合规",
            "组件合规",
        ],
        time_statistics,
    )

    for split in ("train", "val", "test"):
        split_samples = [sample for sample in samples if sample.split == split]
        write_jsonl(output_dir / f"{split}.jsonl", [jsonl_record(sample) for sample in split_samples])

    write_report(
        report_path,
        input_root=input_root,
        output_dir=output_dir,
        raw_records=raw_records,
        canonical_samples=samples,
        conflict_rows=conflict_rows,
        time_statistics=time_statistics,
    )

    print(f"Raw records: {len(raw_records)}")
    print(f"Canonical samples: {len(samples)}")
    print(f"Conflicts: {len(conflict_rows)}")
    print(f"Teacher enabled: {not args.skip_vllm}")
    print(f"Output dir: {output_dir}")


if __name__ == "__main__":
    main()
