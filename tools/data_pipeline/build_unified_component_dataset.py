#!/usr/bin/env python3
"""Merge branch component datasets into one globally indexed YOLO dataset."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(
    "/data/clj/data/xfLLM/training_data/20261105_fire_facility_v2_clean/components_yolo"
)
SPLITS = ("train", "val", "test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--name", default="unified")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_names(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    names = payload["names"]
    if isinstance(names, dict):
        names = [names[index] for index in sorted(names)]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate local class names in {path}")
    return names


def link_image(source: Path, target: Path) -> None:
    target.symlink_to(source.resolve())


def main() -> None:
    args = parse_args()
    target = args.root / args.name
    branches = sorted(
        path for path in args.root.iterdir()
        if path.is_dir() and path.name != args.name and (path / "data.yaml").is_file()
    )
    if not branches:
        raise FileNotFoundError(f"No branch datasets found under {args.root}")

    local_names = {branch.name: load_names(branch / "data.yaml") for branch in branches}
    global_names = sorted({name for names in local_names.values() for name in names})
    if len(global_names) != sum(len(names) for names in local_names.values()):
        duplicates = Counter(name for names in local_names.values() for name in names)
        repeated = sorted(name for name, count in duplicates.items() if count > 1)
        raise ValueError(f"Classes overlap across branches; resolve aliases first: {repeated}")

    if target.exists():
        if not args.force:
            raise FileExistsError(f"Target already exists: {target}; pass --force to rebuild")
        shutil.rmtree(target)
    for split in SPLITS:
        (target / "images" / split).mkdir(parents=True)
        (target / "labels" / split).mkdir(parents=True)
    (target / "metadata").mkdir()

    global_index = {name: index for index, name in enumerate(global_names)}
    split_images = Counter()
    split_instances = Counter()
    class_images = Counter()
    class_instances = Counter()
    seen_source_files: dict[tuple[int, int], str] = {}
    manifest = []

    for branch in branches:
        remap = {
            local_id: global_index[name]
            for local_id, name in enumerate(local_names[branch.name])
        }
        for split in SPLITS:
            image_dir = branch / "images" / split
            for source_image in sorted(path for path in image_dir.iterdir() if path.is_file()):
                source_label = branch / "labels" / split / f"{source_image.stem}.txt"
                if not source_label.is_file():
                    raise FileNotFoundError(f"Missing label for {source_image}")
                target_image = target / "images" / split / source_image.name
                target_label = target / "labels" / split / f"{source_image.stem}.txt"
                if target_image.exists() or target_label.exists():
                    raise FileExistsError(f"Filename collision: {source_image.name}")

                stat = source_image.stat()
                source_key = (stat.st_dev, stat.st_ino)
                previous_split = seen_source_files.get(source_key)
                if previous_split and previous_split != split:
                    raise ValueError(
                        f"Image leakage across splits: {source_image} appears in "
                        f"{previous_split} and {split}"
                    )
                seen_source_files[source_key] = split

                output_lines = []
                image_classes = set()
                for line_number, line in enumerate(
                    source_label.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    fields = line.split()
                    if len(fields) != 5:
                        raise ValueError(f"Invalid YOLO row {source_label}:{line_number}: {line}")
                    local_id = int(fields[0])
                    if local_id not in remap:
                        raise ValueError(f"Unknown class {local_id} in {source_label}:{line_number}")
                    global_id = remap[local_id]
                    output_lines.append(" ".join([str(global_id), *fields[1:]]))
                    image_classes.add(global_id)
                    class_instances[global_id] += 1
                    split_instances[split] += 1
                if not output_lines:
                    raise ValueError(f"Empty component label: {source_label}")

                link_image(source_image, target_image)
                target_label.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
                split_images[split] += 1
                for class_id in image_classes:
                    class_images[class_id] += 1
                manifest.append(
                    {
                        "branch": branch.name,
                        "split": split,
                        "image": str(target_image),
                        "source_image": str(source_image.resolve()),
                        "instances": len(output_lines),
                        "classes": [global_names[index] for index in sorted(image_classes)],
                    }
                )

    yaml_payload = {
        "path": str(target),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {index: name for index, name in enumerate(global_names)},
    }
    (target / "data.yaml").write_text(
        yaml.safe_dump(yaml_payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (target / "metadata" / "manifest.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in manifest) + "\n",
        encoding="utf-8",
    )
    summary = {
        "dataset": args.name,
        "source_branches": [branch.name for branch in branches],
        "classes": len(global_names),
        "images": dict(split_images),
        "instances": dict(split_instances),
        "class_distribution": [
            {
                "id": index,
                "name": name,
                "images": class_images[index],
                "instances": class_instances[index],
            }
            for index, name in enumerate(global_names)
        ],
    }
    (target / "metadata" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
