#!/usr/bin/env python3
"""Train the v2 facility router or a component detector."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DATA_ROOT = Path("/data/clj/data/xfLLM/training_data/20261105_fire_facility_v2_clean")
OUTPUT_ROOT = Path("/data/clj/output/yolo/fire_facility_v2_20261105")
DEFAULT_COMPONENT_INIT = Path(
    "/data/clj/data/xfLLM/training_runs/"
    "20261014_fire_facility_yolov8s_det_1280_expanded_v2/export/best.pt"
)
DEFAULT_ROUTER_INIT = Path("/data/clj/Model/yolo/yolov8m-cls.pt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=("router", "components"))
    parser.add_argument("--branch", help="Required for components; use a folder under components_yolo")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--device", default="1")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--name")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--test-after", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wandb-project", default="fire-facility-v2")
    parser.add_argument("--wandb-mode", choices=("online", "offline", "disabled"), default="online")
    return parser.parse_args()


def router_config(args: argparse.Namespace) -> dict:
    data = args.data_root / "router_cls"
    if not (data / "train").is_dir() or not (data / "val").is_dir():
        raise FileNotFoundError(f"Router dataset is incomplete: {data}")
    return {
        "data": data,
        "model": args.model or DEFAULT_ROUTER_INIT,
        "name": args.name or "router_11class_yolov8m_cls",
        "imgsz": args.imgsz or 768,
        "batch": args.batch or 48,
        "epochs": args.epochs or 120,
        "kind": "classify",
    }


def component_config(args: argparse.Namespace) -> dict:
    if not args.branch:
        raise ValueError("--branch is required for components")
    data = args.data_root / "components_yolo" / args.branch / "data.yaml"
    if not data.is_file():
        available = sorted(path.name for path in (args.data_root / "components_yolo").iterdir() if path.is_dir())
        raise FileNotFoundError(f"Unknown component branch {args.branch!r}; available={available}")
    return {
        "data": data,
        "model": args.model or DEFAULT_COMPONENT_INIT,
        "name": args.name or f"components_{args.branch}_yolov8m",
        "imgsz": args.imgsz or 1280,
        "batch": args.batch or 16,
        "epochs": args.epochs or 150,
        "kind": "detect",
    }


def main() -> None:
    args = parse_args()
    config = router_config(args) if args.task == "router" else component_config(args)
    if config["model"].is_absolute() and not config["model"].is_file():
        raise FileNotFoundError(f"Initial model not found: {config['model']}")

    run_config = {
        **{key: str(value) if isinstance(value, Path) else value for key, value in config.items()},
        "output_root": str(args.output_root),
        "device": args.device,
        "workers": args.workers,
        "patience": args.patience,
        "seed": args.seed,
        "wandb_project": args.wandb_project,
        "wandb_mode": args.wandb_mode,
    }
    print(json.dumps(run_config, ensure_ascii=False, indent=2))
    if args.dry_run:
        return

    os.environ.setdefault("WANDB_PROJECT", args.wandb_project)
    os.environ.setdefault("WANDB_RUN_GROUP", "router" if args.task == "router" else f"components-{args.branch}")
    os.environ["WANDB_MODE"] = args.wandb_mode
    if args.wandb_mode != "disabled":
        import wandb

        if args.wandb_mode == "online" and not wandb.api.api_key:
            raise SystemExit(
                "W&B is not logged in. Run /home/user/miniforge3/envs/yolov8/bin/wandb login, "
                "or pass --wandb-mode offline/disabled."
            )
        wandb.init(
            project=args.wandb_project,
            name=config["name"],
            group="router" if args.task == "router" else f"components-{args.branch}",
            mode=args.wandb_mode,
            config=run_config,
        )
    from ultralytics import YOLO

    model = YOLO(str(config["model"]))
    train_args = {
        "data": str(config["data"]),
        "project": str(args.output_root),
        "name": config["name"],
        "device": args.device,
        "imgsz": config["imgsz"],
        "batch": config["batch"],
        "epochs": config["epochs"],
        "workers": args.workers,
        "patience": args.patience,
        "seed": args.seed,
        "deterministic": True,
        "cos_lr": True,
        "plots": True,
        "resume": args.resume,
        "exist_ok": False,
    }
    if config["kind"] == "detect":
        train_args["close_mosaic"] = 15
    result = model.train(**train_args)
    print(result)

    if args.test_after:
        best = args.output_root / config["name"] / "weights" / "best.pt"
        test_model = YOLO(str(best))
        test_result = test_model.val(
            data=str(config["data"]),
            split="test",
            device=str(args.device).split(",")[0],
            imgsz=config["imgsz"],
            batch=config["batch"],
            workers=args.workers,
            project=str(args.output_root),
            name=f"{config['name']}_test",
            plots=True,
        )
        print(test_result)


if __name__ == "__main__":
    main()
