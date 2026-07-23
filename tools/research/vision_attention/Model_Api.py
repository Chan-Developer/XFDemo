import base64
from openai import OpenAI

def encode_image_to_base64(image_path):
    """将本地图片转换为 base64 字符串"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def call_sglang_with_image(image_path):
    # 1. 初始化客户端 (指向你启动的 9200 端口)
    client = OpenAI(api_key="", base_url="http://127.0.0.1:9200/v1")
    
    # 2. 图片转 Base64
    base64_image = encode_image_to_base64(image_path)
    
    # 3. 发起对话请求
    response = client.chat.completions.create(
        model="qwen-7b", # 注意：如果是视觉模型，请换成对应的 VL 模型名
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "消火栓"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=512,
    )
    
    return response.choices[0].message.content

# 测试运行
img_path = "/data/xyc/fire_hydrant/indoor-fire-hydrant/normal/完好室内消火栓2/室内消火栓箱粘贴使用方法标识符合规范/IMG_20250412_113959.jpg"
try:
    result = call_sglang_with_image(img_path)
    print("--- 模型回复 ---")
    print(result)
except Exception as e:
    print(f"调用失败: {e}")