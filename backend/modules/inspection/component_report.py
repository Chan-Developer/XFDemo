"""Image-grounded descriptions for facilities without compliance rules yet."""
from typing import Any

from backend.infrastructure.vision.yolo_detector import format_yolo_for_prompt
from backend.modules.inspection.utils import strip_reasoning


def describe_components(model: Any, image: str, facility: str, detections: dict) -> tuple[str, dict]:
    # Boxes are candidate evidence, never an assertion of presence or compliance.
    prompt = (
        f"当前图片主体类型为{facility}。请结合原始图片核对以下组件候选信息，"
        "只描述原图中能确认的组件名称、位置和可见状态。候选可能存在误检，"
        "与原图不符的名称不要照抄，未定位到不等于缺失。不要讨论其他设施的检查标准。"
        "只输出一段面向用户的自然中文观察描述，不输出标题，不做合格、不合格、隐患或法规判断。"
        "看不清的部位简短说明，不猜测。禁止提及YOLO、模型、置信度、辅助检测、路由等内部过程。\n"
        + format_yolo_for_prompt(detections)
    )
    response = model.invoke([{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": prompt},
    ]}])
    description = strip_reasoning(response.content or "").strip()
    if not description:
        raise ValueError("组件观察描述为空，请重试")
    report = (
        "一、检测结论：未开展合规判定\n" + description
        + "\n本次仅提供组件识别描述，不据此判定合格或不合格。"
        + "\n\n二、涉及法律法规\n该功能建设中\n\n三、整改建议\n该功能建设中"
    )
    return report, response.usage
