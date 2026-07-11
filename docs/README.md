# XFDemo 项目说明

这份文档只保留项目管理需要的核心信息：当前部署、后端结构、Prompt 链路和后续维护建议。

## 1. 当前部署

当前线上链路是：

```text
浏览器
  -> 阿里云 8.137.175.63:80
  -> xf-frontend Docker / nginx
  -> /api 代理到 L40 http://100.84.194.18:5000
  -> L40 Flask 后端
  -> L40 微调大模型 http://127.0.0.1:9300/v1
  -> L40 本地 YOLO 组件检测
```

L40 当前服务：

```text
项目路径: /data/clj/Project/XFDemo
前端: 100.84.194.18:3000
后端: 100.84.194.18:5000
模型: 100.84.194.18:9300
本机访问: http://127.0.0.1:13000
```

阿里云当前服务：

```text
项目路径: /root/workspace/XFDeploy
公网入口: http://8.137.175.63/
运行容器: xf-frontend
停止容器: xf-backend
```

说明：现在后续先按这个部署方式维护，即阿里云只做公网前端和代理，后端、VLM、YOLO 都在 L40。

## 2. 后端结构

核心检测链路已经从原来的单个大文件拆开：

```text
backend/
├── app.py                         # Flask 路由、历史记录、数据集接口
├── inspection.py                  # 兼容入口，只做导出
├── yolo_detector.py               # YOLO 调用适配器
└── inspection_modules/
    ├── paths.py                   # 项目路径、参考图路径
    ├── labels.py                  # 内部/外观标签体系
    ├── prompts.py                 # 所有 Prompt
    ├── types.py                   # 类型定义
    ├── settings.py                # 环境变量和模型配置
    ├── client.py                  # OpenAI-compatible 客户端
    ├── utils.py                   # 图片、文本、NDJSON 工具
    ├── parser.py                  # 结构化报告解析
    ├── messages.py                # 多模态 message 构造
    ├── yolo_context.py            # YOLO 结果解释
    ├── postprocess.py             # 后处理规则
    ├── trace.py                   # trace 记录
    └── pipeline.py                # InspectionAgent 主流程
```

`backend/inspection.py` 保留是为了兼容现有导入：

```python
from backend.inspection import get_agent, get_settings
```

## 3. Prompt 链路

当前不是单 Prompt，而是多阶段：

```text
用户上传单图
  -> 首轮自动判断 Prompt
  -> 判断范围: 内部组件 / 箱体外观
  -> 内部组件时调用 YOLO
  -> 将 YOLO 结果注入 Judge Prompt
  -> 二次复核 Judge Prompt
  -> 必要时水枪/水带专项复核 Prompt
  -> 后处理规则清洗
  -> 最终报告格式化输出
```

Prompt 代码统一在：

```text
backend/inspection_modules/prompts.py
```

### 首轮自动判断

变量：`AUTO_PROMPT`

作用：

- 自动判断图片是内部组件还是箱体外观。
- 输出检查范围、结论、可见依据、隐患标签。
- 不输出思维链。
- 外观重点判断玻璃门。

### 二次复核

变量：`STRICT_JUDGE_PROMPT_TEMPLATE`

作用：

- 输入用户图、合规参考图、首轮输出、YOLO 结果。
- 判断首轮是否误报或漏报。
- 只输出 JSON。
- 证据不足时设置 `needs_manual_review=true`。

参考图：

```text
agent_reference/内部合规.png
agent_reference/外观合规.jpg
```

### YOLO 注入文本

函数：`format_yolo_for_prompt()`

位置：

```text
backend/yolo_detector.py
```

当前 YOLO 是内部组件存在检测，不是隐患检测。

类别：

```text
手轮、接口、控制器、栓体、水带、水枪、软管、阀门
```

当前权重：

```text
/data/clj/output/yolo/fire_hydrant_v3_20260707/fire_hydrant_v3.pt
```

作用：辅助排除“组件缺失”类误报，不能直接作为最终结论。

### 水枪/水带专项复核

变量：`MISSING_EQUIPMENT_VERIFY_PROMPT`

触发条件：最终报告仍包含：

```text
室内消火栓无消防水枪
室内消火栓无消防水带
```

作用：只判断水枪/水带是否可见，用于排除误报。

## 4. 当前注意点

最终用户输出格式由代码固定生成：

```text
一、检测结论：合格/不合格
...

二、涉及法律法规
该功能建设中

三、整改建议
该功能建设中
```

格式化位置：

```text
backend/inspection_modules/output_formatter.py
```

说明：模型内部仍使用结构化格式 `检查范围/结论/可见依据/隐患标签` 做判断和 trace，最终展示给用户时才转换成报告格式。

1. `app.py` 还比较大，后续可以继续拆成 `routes/` 和 `services/`，但这一步会涉及路由和 IO，建议单独做。
2. `build_missing_equipment_fallback_prompt()` 生成了强约束文本，但当前没有拼进 Judge Prompt，需要后续修复。
3. YOLO 只在内部组件图上运行；如果首轮把图判成箱体外观，YOLO 会跳过。
4. 当前部署方式依赖 L40 后端和 L40 本地 YOLO 环境，阿里云后端容器不要直接启动混用。

## 5. 常用检查命令

检查 L40：

```bash
cd /data/clj/Project/XFDemo
ss -lntp | egrep ':3000|:5000|:9300'
curl -s http://127.0.0.1:5000/health
```

检查阿里云：

```bash
cd /root/workspace/XFDeploy
docker compose ps
docker exec xf-frontend sh -c 'grep -n "proxy_pass" /etc/nginx/conf.d/default.conf'
curl -s http://127.0.0.1/api/health
```
