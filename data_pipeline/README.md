# Data Pipeline

这个目录用于处理室内消火栓数据集，并生成结构化清单和按时间统计的报表。

## 脚本

- `process_fire_hydrant_dataset.py`

## 功能

- 扫描数据集目录
- 提取标签层级
- 优先从文件名解析时间
- 文件名无时间时回退到文件修改时间
- 生成文件清单
- 生成标签统计
- 生成按天、按月或按年的时间统计表

## 默认输入目录

```text
/data/clj/data/XFData/室内消火栓
```

## 默认输出目录

```text
/data/clj/Project/XFDemo/data_pipeline/output/<运行时间>
```

## 用法

按天生成统计：

```bash
python3 /data/clj/Project/XFDemo/data_pipeline/process_fire_hydrant_dataset.py
```

按月生成统计：

```bash
python3 /data/clj/Project/XFDemo/data_pipeline/process_fire_hydrant_dataset.py --group-by month
```

指定输入目录和输出名：

```bash
python3 /data/clj/Project/XFDemo/data_pipeline/process_fire_hydrant_dataset.py \
  --input-root /data/clj/data/XFData/室内消火栓 \
  --run-name baseline_v1 \
  --group-by day
```

不使用 mtime 回退：

```bash
python3 /data/clj/Project/XFDemo/data_pipeline/process_fire_hydrant_dataset.py \
  --disable-mtime-fallback
```

## 输出文件

- `dataset_manifest.csv`
  - 每个文件一行
  - 包含路径、标签层级、状态、缺陷类型、解析时间、时间来源等字段
- `label_statistics.csv`
  - 标签计数表
- `time_statistics_<group>.csv`
  - 时间维度聚合统计
- `time_statistics_<group>.md`
  - Markdown 统计表，便于直接查看
