# XFDemo

室内消火栓单图智能巡检系统。当前链路由微调 Qwen3-VL 初检、YOLO 内部组件存在检测、Qwen Judge 二次复核和规则后处理组成，前端使用 Vue 3 + Vite，后端使用 Flask。

## 目录

```text
backend/                    Flask API 与巡检编排
backend/inspection_modules/ Prompt、解析、复核、后处理与报告格式化
frontend/                   Vue 前端
agent_reference/            内部与外观合规参考图
scripts/yolo_infer.py       YOLO 推理入口
services/pipes_counting/    型材计数常驻推理服务
data_pipeline/              数据扫描与统计脚本
examples/                   示例图片
```

模型权重、训练数据、检测历史、环境变量、API Key、虚拟环境和 Docker 镜像不在仓库中。

## 当前运行链路

```text
浏览器
  -> 前端 /api
  -> Flask :5000
  -> SGLang 微调模型 :9300
  -> YOLO 内部组件检测
  -> qwen3-vl-plus Judge
  -> 后处理与中文检测报告
```

当前部署模型：

```text
qwen3vl8b_hydrant_v5_full_pos_balanced_3to1_checkpoint600_merged_20260701
```

当前 YOLO 类别：手轮、接口、控制器、栓体、水带、水枪、软管、阀门，默认置信度阈值为 `0.20`。

型材计数模型作为独立服务运行，类别为圆管、方管、角钢和槽钢。XFDemo 后端通过 `PIPE_COUNTING_BASE_URL` 调用该服务，浏览器不直接访问模型端口。

## 本地启动

准备环境变量：

```bash
cp .env.example .env
```

启动后端：

```bash
python -m backend.app
```

启动型材计数服务：

```bash
PIPES_DEVICE=2 gunicorn --bind 127.0.0.1:9400 --workers 1 --threads 2 \
  --timeout 180 services.pipes_counting.app:app
```

启动前端：

```bash
cd frontend
npm ci
npm run dev
```

默认地址：

- 前端：`http://127.0.0.1:3000`
- 后端健康检查：`http://127.0.0.1:5000/health`
- 模型 API：`http://127.0.0.1:9300/v1`

## 当前业务口径

1. 铭牌缺失或模糊暂不作为隐患。
2. 操作说明采用张贴、粘贴或印刷形式均认可，只判断是否存在且清晰可读。
3. 英文 `FIRE HYDRANT` 缺失不能单独判不合格，重点检查中文“消火栓”标识。
4. 不判断箱门材质，玻璃门或透明门不能作为隐患。
5. 透明门或开门图片如果同时可见外观和内部，必须同时检查两个范围。
6. 软管自然弧度、正常下垂、盘绕和普通转弯不能判为严重折弯。
7. 最终报告不得暴露 YOLO、Judge、置信度或其他内部处理过程。

## 当前待办

当前运行代码尚未完全实现上述最新口径：

- `labels.py` 仍保留铭牌、耐久印制和中英文绑定标签。
- 检测流程仍将外观和内部作为二选一范围。
- 软管严重折弯仍是活动标签，只做了严格后处理限制。
- YOLO 仅在内部范围运行，双可见图片可能跳过 YOLO。
- `output_formatter.py` 仍有部分硬编码合格描述。

后续应先统一标签、实现双范围检测，并使用固定的人工审核图片做回归测试，再决定是否训练下一版模型。

## 说明

历史 LangGraph 后端已经停用。本仓库仅保留当前运行所需源码；旧部署镜像、旧 Prompt、备份脚本和运行产物未提交。
