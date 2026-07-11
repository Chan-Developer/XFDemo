# LangGraph 阿里云兼容后端

这是新的后端入口，原有 `agent.py` 保持不变。

## 文件

- `langgraph_backend.py`: Flask 入口，保持 `/health`、`/chat`、`/chat/stream`
- `backend/graphs/inspection.py`: 业务 agent，包含配置读取、Qwen 兼容客户端、LangGraph 流程、标签体系和输出清洗
- `requirements-langgraph-backend.txt`: 新后端依赖
- `Dockerfile.langgraph-backend`: 新后端镜像构建文件

## .env 示例

```bash
DASHSCOPE_API_KEY=你的阿里云百炼 API Key
DASHSCOPE_BASE_URL=https://llm-s81wox1ib2cco1tz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen3.7-max
ENABLE_THINKING=true
THINKING_BUDGET=4096
```

后端会把 `ENABLE_THINKING=true` 转成：

```python
extra_body={"enable_thinking": True}
```

流式接口只返回 `delta.content`，不会把 `reasoning_content` 推给前端。

## 本地启动

```bash
cd /data/clj/Project/XFDemo
python3 -m pip install -r requirements-langgraph-backend.txt
python3 langgraph_backend.py
```

接口保持和旧后端一致：

- `GET /health`
- `POST /chat`
- `POST /chat/stream`

## Agent 设计

当前不是训练模型，而是用视觉大模型和规则化 agent 完成巡检判定。

数据集用于抽取业务标签体系和任务边界：

- 内部组件：手轮缺失、栓口方向错误、无消防水带、无消防水枪、消防接口缺失、软管卷盘供水管道折弯严重、无箱体、箱锈蚀、箱门缺失
- 箱体外观：无操作说明、未标注“消火栓”和英文“FIRE HYDRANT”、无铭牌、箱门标识模糊、铭牌模糊、玻璃门、遮挡

推荐线上流程：

1. 如果前端明确传 `task`，就直接走 `internal_components` 或 `appearance`
2. 如果任务不明确，就走 `auto`，让模型根据图片里箱门开关状态和主要可见区域判断当前是“内部组件”还是“箱体外观”
3. 按检查范围注入对应标签白名单和判定规则
4. 调用 Qwen 视觉模型，只要求三行输出：结论、可见依据、隐患标签
5. 过滤思考内容、重复内容和过长输出
6. 后续可加一个轻量校验节点：隐患标签必须来自白名单，格式不对时要求模型修正一次

规则取舍：

- 标签必须白名单
- 遮挡、反光、画面外、看不清，可以明确说明“无法判断”或“当前画面未见”
- 但不能把不可见内容直接判成异常
