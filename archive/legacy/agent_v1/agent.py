import json
import os
import re
from flask import Flask, Response, request, jsonify, stream_with_context
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from prompt import system_prompt


app = Flask(__name__)

# ================= 配置区域 =================
# 1. vLLM 的地址
VLLM_API_BASE = os.getenv("VLLM_API_BASE", "http://localhost:9300/v1")

# 2. 你的 API Key (vLLM 默认是 "EMPTY")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")

# 3. 模型名称 (必须与 vLLM 启动时加载的名称完全一致)
# 你可以用 curl http://<vllm-host>:<port>/v1/models 查看
MODEL_NAME = os.getenv("MODEL_NAME", "/data/clj/Model/Qwen3-VL-32B-Instruct")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
TOP_P = float(os.getenv("TOP_P", "0.8"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "768"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "1200"))
MAX_IDENTICAL_DELTAS = int(os.getenv("MAX_IDENTICAL_DELTAS", "3"))
# ===========================================

# 初始化 LangChain 的 ChatOpenAI
llm = ChatOpenAI(
    model=MODEL_NAME,
    openai_api_base=VLLM_API_BASE,
    openai_api_key=VLLM_API_KEY,
    streaming=True,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    model_kwargs={
        "top_p": TOP_P,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.1,
    },
)


WHITESPACE_RE = re.compile(r"\s+")


def build_messages(data):
    query = (data or {}).get('query', '').strip()
    image_url = (data or {}).get('image')

    if not query:
        raise ValueError("Query is required")

    content_parts = [{"type": "text", "text": query}]
    print("human query:", content_parts)

    if image_url:
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": image_url
            }
        })

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=content_parts)
    ]


def extract_text(content):
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue

            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type == "text":
                text_parts.append(item.get("text", ""))
            elif item_type == "output_text":
                text_parts.append(item.get("text", ""))

        return "".join(text_parts)

    return str(content or "")


def extract_usage(metadata):
    if not isinstance(metadata, dict):
        return {}

    token_usage = metadata.get("token_usage")
    return token_usage if isinstance(token_usage, dict) else {}


def ndjson(payload):
    return json.dumps(payload, ensure_ascii=False) + "\n"


def normalize_text(text):
    return WHITESPACE_RE.sub("", text or "")


def has_repeated_tail(text):
    compact = normalize_text(text)
    if len(compact) < 72:
        return False

    max_unit = min(80, len(compact) // 3)
    for unit_len in range(max_unit, 15, -1):
        unit = compact[-unit_len:]
        if unit and compact.endswith(unit * 3):
            return True
    return False


def trim_repeated_tail(text):
    candidate = (text or "").strip()
    if not candidate:
        return candidate

    changed = True
    while changed:
        changed = False
        max_unit = min(80, len(candidate) // 3)
        for unit_len in range(max_unit, 15, -1):
            unit = candidate[-unit_len:]
            if unit and candidate.endswith(unit * 3):
                candidate = candidate[: -(2 * unit_len)].rstrip()
                changed = True
                break

    if len(candidate) > MAX_OUTPUT_CHARS:
        candidate = candidate[:MAX_OUTPUT_CHARS].rstrip()

    return candidate


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "vllm_api_base": VLLM_API_BASE,
        "model_name": MODEL_NAME
    }), 200

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        messages = build_messages(data)

        # 调用本地vLLM
        response = llm.invoke(messages)
        response_text = trim_repeated_tail(extract_text(response.content))
        print("大模型响应:", response_text)

        return jsonify({
            "response": response_text,
            "usage": extract_usage(getattr(response, "response_metadata", None))
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    try:
        data = request.get_json(silent=True) or {}
        messages = build_messages(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

    @stream_with_context
    def generate():
        full_response = []
        usage = {}
        finish_reason = "stop"
        last_delta_signature = ""
        identical_delta_hits = 0

        try:
            for chunk in llm.stream(messages):
                delta = extract_text(chunk.content)
                if delta:
                    delta_signature = normalize_text(delta)
                    if delta_signature and delta_signature == last_delta_signature:
                        identical_delta_hits += 1
                    elif delta_signature:
                        identical_delta_hits = 1
                        last_delta_signature = delta_signature

                    next_response = "".join(full_response) + delta
                    if identical_delta_hits >= MAX_IDENTICAL_DELTAS:
                        finish_reason = "repeat_guard"
                        break
                    if has_repeated_tail(next_response):
                        finish_reason = "repeat_guard"
                        break
                    if len(next_response) > MAX_OUTPUT_CHARS:
                        finish_reason = "length_guard"
                        break

                    full_response.append(delta)
                    yield ndjson({
                        "type": "delta",
                        "delta": delta
                    })

                chunk_usage = extract_usage(getattr(chunk, "response_metadata", None))
                if chunk_usage:
                    usage = chunk_usage

            yield ndjson({
                "type": "done",
                "response": trim_repeated_tail("".join(full_response)),
                "usage": usage,
                "finish_reason": finish_reason,
            })
        except Exception as e:
            print(f"Stream error: {str(e)}")
            yield ndjson({
                "type": "error",
                "error": str(e)
            })

    response = Response(generate(), mimetype='application/x-ndjson')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

if __name__ == '__main__':
    # 启动 Flask，监听 5000 端口
    app.run(host='0.0.0.0', port=5000, debug=False)