"""Compatibility facade for the inspection pipeline.

The implementation is split under backend.inspection_modules so existing imports
like `from backend.inspection import get_agent` keep working.
"""

from .inspection_modules.client import QwenClient, extract_usage
from .inspection_modules.labels import ALLOWED_LABELS, APPEARANCE_LABELS, INTERNAL_LABELS
from .inspection_modules.messages import (
    apply_missing_equipment_visibility_review,
    build_judge_messages,
    build_messages,
    build_missing_equipment_verify_messages,
    parse_missing_equipment_verify,
)
from .inspection_modules.parser import (
    detect_task,
    extract_json_object,
    extract_structured_report_sections,
    has_structured_report,
    labels_from_report,
    normalize_label_list,
    pick_primary_structured_report,
    report_fields_for_trace,
    sanitize_final_report,
)
from .inspection_modules.output_formatter import format_public_report
from .inspection_modules.pipeline import (
    InspectionAgent,
    create_inspection_graph,
    create_prepare_graph,
    get_agent,
    merge_usage,
    prepare_input,
)
from .inspection_modules.postprocess import (
    evidence_says_component_visible,
    format_judge_json,
    guarded_format_judge_json,
    remove_contradictory_missing_labels,
)
from .inspection_modules.prompts import (
    AUTO_PROMPT,
    MISSING_EQUIPMENT_VERIFY_PROMPT,
    STRICT_JUDGE_PROMPT_TEMPLATE,
)
from .inspection_modules.settings import env_bool, env_float, env_int, first_env, get_settings, load_env
from .inspection_modules.trace import build_trace_summary, trace_stage
from .inspection_modules.types import InspectionState, ModelDelta, ModelResult, Settings
from .inspection_modules.utils import (
    file_to_data_url,
    has_repeated_tail,
    ndjson,
    normalize_image,
    normalize_text,
    strip_reasoning,
    trim_output,
)
from .inspection_modules.yolo_context import (
    MISSING_EQUIPMENT_LABELS,
    apply_yolo_backstop,
    build_missing_equipment_fallback_prompt,
    missing_equipment_fallback_labels,
    yolo_component_labels,
    yolo_detected_components_text,
    yolo_has_component_for_defect,
    yolo_labels_for_trace,
)
