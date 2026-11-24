"""Replay recorded images without creating users or production history records."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib
from pathlib import Path
import subprocess
import time

from backend.config.settings import get_settings, load_env

# Detector paths and device defaults are evaluated at import time.
load_env()

from backend.infrastructure.vision.yolo_detector import run_yolo_detection
from backend.modules.inspection.intent import resolve_intent
from backend.modules.inspection.pipeline import InspectionAgent


GROUPS = dict(zip(
    ("室内消火栓", "室外消火栓", "灭火器", "防火门", "洒水喷头", "疏散通道", "消防水泵接合器",
     "消防供水设施", "湿式报警阀组", "火灾探测器", "火灾报警控制器"),
    ("indoor_hydrant", "outdoor_hydrant", "fire_extinguisher", "fire_door", "sprinkler", "evacuation_passage",
     "water_pump_connector", "water_supply", "wet_alarm_valve", "fire_detector", "fire_alarm_controller"),
))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ids", default="2,8,9,19,20,21,23,24,29,30")
    parser.add_argument("--mode", choices=("route", "full"), default="full")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    ids = {int(value) for value in args.ids.split(",")}
    samples = [row for row in json.loads(Path(args.source).read_text()) if row["id"] in ids]
    if {row["id"] for row in samples} != ids:
        raise ValueError("Requested sample IDs are missing")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    (output / "metadata.json").write_text(json.dumps({
        "source": args.source, "mode": args.mode, "ids": sorted(ids), "cwdCommit": commit,
        "codeRoot": str(Path(__file__).resolve().parents[2]),
        "sourceHashes": {name: hashlib.sha256((Path(__file__).resolve().parents[2] /
                          "backend/modules/inspection" / name).read_bytes()).hexdigest()
                         for name in ("intent.py", "pipeline.py", "evidence_gate.py", "image_evidence.py")},
        "model": settings.model, "judgeModel": settings.judge_model,
        "method": "InspectionAgent replay; no production history writes; route/contract checks are not human accuracy",
    }, ensure_ascii=False, indent=2))

    def run(sample):
        started = time.monotonic()
        row = {"id": sample["id"], "source": sample["source"], "expected": GROUPS[sample["group"]],
               "baselineBranch": sample["actual_branch"]}
        try:
            agent = InspectionAgent(settings)
            for model in (agent.model, agent.judge_model, agent.direction_model, agent.evidence_model):
                model.client = model.client.with_options(timeout=240, max_retries=0)
            image = "data:image/jpeg;base64," + base64.b64encode(Path(sample["source"]).read_bytes()).decode()
            if args.mode == "route":
                detections = run_yolo_detection(image, task="unified")
                if not detections.get("enabled") or detections.get("reason"):
                    raise RuntimeError("Detector unavailable")
                intent, meta = resolve_intent(agent.evidence_model, "", image, detections=detections)
                row.update(actual=intent.inspection_type, evidence=intent.evidence, routeMeta=meta)
            else:
                state = agent.invoke({"image": image}, progress_callback=lambda event: print(json.dumps({
                    "id": sample["id"], "stage": event.get("stage"), "status": event.get("status")}), flush=True))
                row.update(actual=state["inspection_type"], report=state["report"],
                           structuredReport=state["structured_report"], trace=state["trace"], usage=state["usage"])
                reviews = [stage["evidenceReview"] for stage in state["trace"]["stages"] if "evidenceReview" in stage]
                row["evidenceContractPassed"] = bool(reviews and reviews[-1]["observations"] and not reviews[-1]["error"])
            row["routeMatchesExpected"] = row["actual"] == row["expected"]
        except Exception as exc:
            row["error"] = type(exc).__name__
        row["seconds"] = round(time.monotonic() - started, 2)
        (output / f"{sample['id']:02d}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2))
        print(json.dumps({k: row.get(k) for k in ("id", "actual", "routeMatchesExpected", "evidenceContractPassed", "seconds", "error")}, ensure_ascii=False), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        rows = [future.result() for future in as_completed([executor.submit(run, sample) for sample in samples])]
    rows.sort(key=lambda row: row["id"])
    (output / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    summary = {"count": len(rows), "routeMatches": sum(row.get("routeMatchesExpected", False) for row in rows),
               "errors": sum("error" in row for row in rows),
               "evidenceContracts": sum(row.get("evidenceContractPassed", False) for row in rows)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    if summary["errors"] or summary["routeMatches"] != len(rows) or (
        args.mode == "full" and summary["evidenceContracts"] != len(rows)
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
