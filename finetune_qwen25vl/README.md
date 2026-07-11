# Qwen2.5-VL 微调数据脚本说明

这个目录只有一个主脚本：

- `build_qwen25vl_dataset.py`

它的作用是把室内消火栓目录标签数据，整理成可直接用于 `Qwen2.5-VL` 微调的 `jsonl` 数据。

## 这个脚本生成什么模板

脚本最终生成的是多模态对话微调模板，每条样本结构如下：

```json
{
  "id": "fh_000001",
  "image": "/abs/path/to/image.jpg",
  "messages": [
    {
      "role": "system",
      "content": "你是室内消火栓图像审核助手。请根据图片内容识别室内消火栓或消火栓箱状态，只依据清晰可见证据判断，不要臆测内部不可见组件，并输出严格 JSON。"
    },
    {
      "role": "user",
      "content": "请检查这张图片中的室内消火栓或消火栓箱，并输出 JSON。..."
    },
    {
      "role": "assistant",
      "content": "{\"target_present\":true,\"scene_type\":\"室内消火栓\",\"door_state\":\"关闭\",\"status\":\"有隐患\",\"normal_labels\":[],\"defect_labels\":[\"箱门锁闭\"],\"risk_level\":\"中\",\"needs_review\":true,\"review_reason\":\"箱门关闭，内部不可见\",\"evidence\":[\"箱门处于关闭状态\"],\"short_conclusion\":\"箱门关闭，需进一步复核内部情况\"}"
    }
  ]
}
```

也就是：

- `image` 指向图片绝对路径
- `messages` 是标准对话格式
- `assistant.content` 是严格 JSON 字符串

## assistant 最终输出字段

脚本生成的最终监督字段为：

- `target_present`
- `scene_type`
- `door_state`
- `status`
- `normal_labels`
- `defect_labels`
- `risk_level`
- `needs_review`
- `review_reason`
- `evidence`
- `short_conclusion`

其中：

- `status`、`normal_labels`、`defect_labels` 主要来自目录标签
- `door_state`、`risk_level`、`needs_review`、`review_reason`、`evidence`、`short_conclusion` 主要由本地 vLLM 启动的 `Qwen2.5-VL-72B` 教师模型补充
- 如果教师模型不可用，脚本会自动回退到基础标签版本，不会中断整个流程

## 脚本做了哪些事情

单脚本会依次完成：

1. 扫描原始目录标签数据
2. 只处理图片文件
3. 计算 `sha256` 去重
4. 合并同图多标签
5. 过滤“同一张图既正常又异常”的冲突样本
6. 调用本地 vLLM 的 `Qwen2.5-VL-72B`
7. 生成 `train / val / test` 三个 `jsonl`
8. 输出统计表和报告

## 输出文件

运行后会在：

```text
output/<run_name>/
```

生成这些文件：

- `raw_manifest.csv`
  - 原始逐文件清单
- `canonical_samples.csv`
  - 去重和多标签合并后的主样本表
- `conflicts.csv`
  - 冲突样本表
- `train.jsonl`
- `val.jsonl`
- `test.jsonl`
- `split_statistics.csv`
- `label_statistics.csv`
- `time_statistics.csv`
- `dataset_report.md`

## 最常用命令

如果 vLLM 地址和模型名已经是默认值：

```bash
python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py \
  --run-name baseline_qwen25vl
```

如果你要手动指定 vLLM：

```bash
python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py \
  --run-name baseline_qwen25vl \
  --vllm-api-base http://127.0.0.1:9300/v1 \
  --model-name Qwen2.5-VL-72B-Instruct
```

如果只想先做数据整理，不调用教师模型：

```bash
python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py \
  --run-name debug_no_teacher \
  --skip-vllm
```

## 默认输入目录

```text
/data/clj/data/XFData/室内消火栓
```

## 适合当前项目的使用方式

建议先跑一次小样本：

```bash
python3 /data/clj/Project/XFDemo/finetune_qwen25vl/build_qwen25vl_dataset.py \
  --run-name smoke_test \
  --max-samples 20
```

确认：

- `teacher_ok` 是否成功
- `assistant` 的 JSON 是否符合预期
- `conflicts.csv` 是否有明显异常

确认没问题后，再跑全量。
