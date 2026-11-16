"""Adapt model-owned class names to legacy report vocabulary, never numeric IDs."""

TASKS = {
    "internal_components": ("室内消火栓/", "内部组件", "component_presence"),
    "appearance": ("室内消火栓/", "箱体外观", "appearance_presence"),
    "outdoor_hydrant": ("室外消火栓/", "室外消火栓", "outdoor_hydrant_presence"),
    "fire_extinguisher": ("灭火器/", "灭火器", "fire_extinguisher_presence"),
}
INDOOR = {
    "室内消火栓": "栓体", "消火栓栓头（阀体）": "栓体", "消火栓手轮": "手轮",
    "消防接口": "接口", "消防水带": "水带", "消防水枪": "水枪",
    "消防软管卷盘": "软管", "消防软管卷盘/软管": "软管",
    "消火栓箱体": "消火栓", "消火栓箱门": "箱门",
    "消火栓文字标志": "中文标识", "消火栓箱门标注字样": "中文标识",
    "室内消火栓使用说明": "操作说明",
}
APPEARANCE = {"消火栓", "箱门", "中文标识", "操作说明", "铭牌", "把手", "英文标识"}


def canonical_name(name):
    if name.startswith("室内消火栓/"):
        suffix = name[len("室内消火栓/"):]
        return INDOOR.get(suffix, suffix)
    return {"fire_extinguisher": "灭火器", "outdoor_hydrant": "室外消火栓",
            "fire_extinguisher_pressure_indicator": "灭火器压力指示器"}.get(name, name)


def project_result(raw, task):
    """A scope change projects cached boxes; it never launches inference again."""
    prefix, scope, kind = TASKS[task]
    boxes = []
    for item in raw.get("detections", []):
        name = item.get("className", "")
        if not name.startswith(prefix):
            continue
        label = canonical_name(name)
        if task == "appearance" and label not in APPEARANCE:
            continue
        if task == "internal_components" and label in APPEARANCE:
            continue
        if task == "fire_extinguisher":
            label = {"灭火器/瓶体": "灭火器", "灭火器/压力指示器": "灭火器压力指示器"}.get(name, name)
        boxes.append({**item, "label": label, "component": label, "modelScope": scope, "modelType": kind})
    return {**raw, "detections": boxes, "modelScope": scope, "modelType": kind,
            "classes": sorted({x["label"] for x in boxes}), "detectorMode": "unified"}
