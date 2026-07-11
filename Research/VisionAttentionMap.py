"""
Qwen3-VL 注意力热力图可视化脚本
使用模型推理图片，并将注意力分数高的区域以热力图形式展示
"""

import torch
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from transformers import AutoModelForVision2Seq, AutoProcessor
import cv2
import argparse
import os
import logging
# ----------------------------------------------
# 日志
# ----------------------------------------------
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True,
    )
logger = logging.getLogger(__name__)

def log_print(message):
    logger.info(message)


# ----------------------------------------------
# 启动命令
# ----------------------------------------------

'''
python attentionMap.py --image_path "/data/clj/data/imageNet/dataset/val/ILSVRC2012_val_00001590.JPEG" --output_dir ./attention_outputs --prompt "descirbe the background of the bus" --max_size 256 --aggregation mean
'''

def load_model(model_path: str, device: str = "cuda"):
    """加载 Qwen3-VL 模型和处理器"""
    print(f"Loading model: {model_path}")
    
    model = AutoModelForVision2Seq.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map=device,
        trust_remote_code=True,
        attn_implementation="eager",  # 使用 eager 模式以获取注意力权重
    )
    
    processor = AutoProcessor.from_pretrained(
        model_path,
        trust_remote_code=True
    )
    
    print("Model loaded!")
    return model, processor


class VisionAttentionCapture:
    """用于捕获视觉编码器注意力的类"""
    def __init__(self):
        self.attentions = []
        self.handles = []
    
    def hook_fn(self, module, input, output):
        # 捕获注意力权重
        if hasattr(output, 'attentions') and output.attentions is not None:
            self.attentions.append(output.attentions)
        elif isinstance(output, tuple) and len(output) > 1:
            # 有些模块直接返回 (hidden_states, attn_weights)
            if output[1] is not None and isinstance(output[1], torch.Tensor):
                self.attentions.append(output[1])
    
    def register(self, model):
        # 尝试在视觉编码器的注意力层注册 hook
        if hasattr(model, 'visual'):
            i = 0
            for name, module in model.visual.named_modules():
                log_print(f"视觉编码器注意力层名称{i+1}: {name}")
                i += 1
                if 'attn' in name.lower() and hasattr(module, 'forward'):
                    handle = module.register_forward_hook(self.hook_fn)
                    self.handles.append(handle)
        log_print(f"注册 hook 成功")
        return self
    
    def remove(self):
        for handle in self.handles:
            handle.remove()
        self.handles = []
    
    def get_attention_map(self, grid_h, grid_w):
        if not self.attentions:
            return None
        # 使用最后一层的注意力
        # 注意力通常是 CLS token 对所有 patch 的注意力
        last_attn = self.attentions[-1]
        if isinstance(last_attn, torch.Tensor):
            attn = last_attn.float().cpu()
            # 取平均 head
            if attn.dim() == 4:  # (batch, heads, q, k)
                attn = attn.mean(dim=1)[0]  # (q, k)
            if attn.dim() == 2:
                # 取 CLS token (第一个) 对其他所有 token 的注意力
                cls_attn = attn[0, 1:]  # 跳过 CLS 自己
                return cls_attn.numpy()
        return None


def inference_with_attention(model, processor, image_path: str, prompt: str = "描述这张图片", max_size: int = 512, max_new_tokens: int = 256):
    """推理图片并获取注意力权重"""
    
    # 加载图片
    image = Image.open(image_path).convert("RGB")
    log_print(f"Image 加载⭐⭐⭐: {image_path}")
    original_size = image.size  # (width, height)
    
    # 限制图片大小以节省显存
    if max(image.size) > max_size:
        ratio = max_size / max(image.size)
        new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
        image = image.resize(new_size, Image.LANCZOS)
        log_print(f"修改图片大小: {original_size} -> {image.size}")
    
    # 构建消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt}
            ]
        }
    ]
    
    # 处理输入
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(
        text=[text],
        images=[image],
        return_tensors="pt",
        padding=True
    )
    inputs = inputs.to(model.device)
    
    # 注册 hook 捕获视觉注意力
    vision_capture = VisionAttentionCapture().register(model)
    
    # 推理并获取注意力
    print("Running inference...")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            output_attentions=True,
            return_dict_in_generate=True,
        )
    
    # 移除 hook
    vision_capture.remove()
    
    # 解码生成的文本
    generated_ids = outputs.sequences[:, inputs.input_ids.shape[1]:]
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
    # 获取注意力权重
    attentions = outputs.attentions
    log_print(f"注意力权重: {len(attentions)}")
    vision_attentions = vision_capture.attentions
    log_print(f"视觉注意力权重: {len(vision_attentions)}")
    return image, attentions, inputs, generated_text, original_size, vision_attentions


def extract_image_attention(model, processor, inputs, attentions, original_size, vision_attentions=None, aggregation='mean', layer_ratio=0.66):
    """
    提取图像区域的注意力分数
    
    对每个生成的 token，计算它对视觉 token 的注意力，然后聚合所有生成 token 的注意力
    得到整个生成句子对图像各区域的综合注意力热力图
    
    Args:
        aggregation: 聚合方式 - 'mean'(平均), 'max'(最大), 'sum'(求和)
    """
    from scipy import ndimage
    
    if hasattr(inputs, 'image_grid_thw') and inputs.image_grid_thw is not None:
        # 提取图像的物理维度 t (时间/帧数, 图片通常为1)、h (高)、w (宽)
        grid_thw = inputs.image_grid_thw[0]  # (t, h, w)
        t, h, w = grid_thw.tolist()
        log_print(f"Image token grid: t={t}, h={h}, w={w}")
        num_image_tokens = t * h * w
    else:
        num_image_tokens = 256
        t = 1
        h = w = 16
    
    print(f"Image token grid: t={t}, h={h}, w={w}, total={num_image_tokens}")
    
    # 获取输入 token 信息，找到视觉 token 的位置
    input_ids = inputs.input_ids[0].cpu().numpy()
    vision_token_id = 151655  # Qwen2.5-VL 的视觉 token ID
    vision_mask = (input_ids == vision_token_id)
    vision_indices = np.where(vision_mask)[0]
    num_vision_tokens = len(vision_indices)
    
    print(f"Found {num_vision_tokens} vision tokens in input sequence")
    
    if len(attentions) == 0 or attentions[0] is None:
        return None
    
    # 收集所有生成 token 对视觉 token 的注意力
    all_token_attentions = []
    num_generated_tokens = len(attentions)
    
    print(f"Processing attention from {num_generated_tokens} generated tokens...")
    
    for step_idx, step_attn in enumerate(attentions):
        if step_attn is None:
            continue
        
        # step_attn 是一个 tuple，每层一个 tensor
        # 使用指定层的注意力（中间层通常有更好的空间信息）
        num_layers = len(step_attn)
        target_layer = min(int(num_layers * layer_ratio), num_layers - 1)
        if step_idx == 0:  # 只打印一次
            print(f"Using layer {target_layer}/{num_layers} (ratio={layer_ratio})")
        last_layer_attn = step_attn[target_layer]  # (batch, num_heads, query_len, key_len)
        
        # 对于每个生成步骤，query_len 通常是 1（当前生成的 token）
        # key_len 是之前所有 token（包括输入和已生成的 token）
        
        # 平均所有注意力头
        avg_attn = last_layer_attn[0].mean(dim=0)  # (query_len, key_len)
        
        if avg_attn.dim() == 2:
            # 取最后一个 query（当前生成的 token）对所有 key 的注意力
            current_token_attn = avg_attn[-1]  # (key_len,)
        else:
            current_token_attn = avg_attn.squeeze()
        
        attn_values = current_token_attn.float().cpu().numpy()
        
        # 提取视觉 token 位置的注意力
        if num_vision_tokens > 0:
            # 只取在当前 key 范围内的视觉 token 索引
            valid_indices = vision_indices[vision_indices < len(attn_values)]
            if len(valid_indices) > 0:
                vision_attn = attn_values[valid_indices]
                all_token_attentions.append(vision_attn)
    
    if len(all_token_attentions) == 0:
        print("No valid attention extracted!")
        return None
    
    print(f"Collected attention from {len(all_token_attentions)} tokens")
    
    # 聚合所有生成 token 的注意力
    # 将所有 token 的注意力堆叠成 (num_tokens, num_vision_tokens)
    stacked_attn = np.stack(all_token_attentions, axis=0)
    
    # 分析不同 token 之间注意力分布的方差
    token_variance = stacked_attn.var(axis=0)  # 每个视觉位置在不同token间的方差
    mean_variance = token_variance.mean()
    print(f"Attention variance across tokens: mean={mean_variance:.8f}")
    
    # 找出注意力变化最大的 token（表示不同词关注不同区域）
    token_attn_std = stacked_attn.std(axis=1)  # 每个生成token的注意力分散度
    most_focused_tokens = np.argsort(token_attn_std)[-5:][::-1]
    least_focused_tokens = np.argsort(token_attn_std)[:5]
    print(f"Most focused tokens (attend specific regions): {most_focused_tokens}")
    print(f"Least focused tokens (spread attention): {least_focused_tokens}")
    
    if aggregation == 'mean':
        aggregated_attn = stacked_attn.mean(axis=0)
        print(f"Aggregation: mean over {stacked_attn.shape[0]} tokens")
    elif aggregation == 'max':
        aggregated_attn = stacked_attn.max(axis=0)
        print(f"Aggregation: max over {stacked_attn.shape[0]} tokens")
    elif aggregation == 'sum':
        aggregated_attn = stacked_attn.sum(axis=0)
        print(f"Aggregation: sum over {stacked_attn.shape[0]} tokens")
    else:
        aggregated_attn = stacked_attn.mean(axis=0)
    
    actual_num = len(aggregated_attn)
    print(f"Aggregated attention shape: {actual_num}")
    
    # 将注意力重塑为 2D 网格
    target_h, target_w = h, w
    
    # 找到能整除 actual_num 的最佳因子对
    def find_best_factors(n, target_ratio):
        best_h, best_w = 1, n
        best_diff = abs(target_ratio - n)
        for i in range(1, int(np.sqrt(n)) + 1):
            if n % i == 0:
                h_cand, w_cand = i, n // i
                diff = abs(target_ratio - w_cand / h_cand)
                if diff < best_diff:
                    best_diff = diff
                    best_h, best_w = h_cand, w_cand
        return best_h, best_w
    
    target_ratio = target_w / target_h
    src_h, src_w = find_best_factors(actual_num, target_ratio)
    
    print(f"Reshape: {actual_num} -> ({src_h}, {src_w}) -> ({target_h}, {target_w})")
    
    # 打印注意力分布统计，帮助诊断
    print(f"Attention stats: min={aggregated_attn.min():.4f}, max={aggregated_attn.max():.4f}, "
          f"mean={aggregated_attn.mean():.4f}, std={aggregated_attn.std():.4f}")
    
    # 找出 top-5 注意力位置并显示其在网格中的坐标
    top_indices = np.argsort(aggregated_attn)[-5:][::-1]
    print(f"Top-5 attention indices: {top_indices}")
    print(f"Top-5 attention values: {aggregated_attn[top_indices]}")
    for idx in top_indices:
        row, col = idx // src_w, idx % src_w
        print(f"  Index {idx} -> grid position: row={row}, col={col}")
    
    # reshape 并缩放到目标网格大小
    # Qwen-VL 的视觉 token 按行优先排列（从左到右，从上到下）
    temp_map = aggregated_attn[:src_h * src_w].reshape(src_h, src_w)
    
    # 对于 Qwen2.5-VL，token 压缩后的排列可能需要调整
    # 打印热力图的角落值来诊断方向
    print(f"Attention map corners: TL={temp_map[0,0]:.6f}, TR={temp_map[0,-1]:.6f}, "
          f"BL={temp_map[-1,0]:.6f}, BR={temp_map[-1,-1]:.6f}")
    
    attention_map = ndimage.zoom(temp_map, (target_h / src_h, target_w / src_w), order=1)
    
    return attention_map


def visualize_attention_heatmap(image: Image.Image, attention_map: np.ndarray, 
                                 output_path: str, alpha: float = 0.6):
    """将注意力热力图叠加到原图上"""
    
    # 转换图像为 numpy 数组
    img_array = np.array(image)
    h, w = img_array.shape[:2]
    
    # 归一化注意力图
    attention_map = (attention_map - attention_map.min()) / (attention_map.max() - attention_map.min() + 1e-8)
    
    # 调整注意力图大小以匹配原图
    attention_resized = cv2.resize(attention_map.astype(np.float32), (w, h))
    
    # 应用高斯模糊使热力图更平滑
    attention_resized = cv2.GaussianBlur(attention_resized, (21, 21), 0)
    
    # 再次归一化
    attention_resized = (attention_resized - attention_resized.min()) / (attention_resized.max() - attention_resized.min() + 1e-8)
    
    # 创建热力图
    heatmap = plt.cm.jet(attention_resized)[:, :, :3]  # 去掉 alpha 通道
    heatmap = (heatmap * 255).astype(np.uint8)
    
    # 叠加热力图到原图
    overlay = cv2.addWeighted(img_array, 1 - alpha, heatmap, alpha, 0)
    
    # 创建可视化图
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # Original image
    axes[0].imshow(img_array)
    axes[0].set_title('Original Image', fontsize=14)
    axes[0].axis('off')
    
    # Attention heatmap
    im = axes[1].imshow(attention_resized, cmap='jet')
    axes[1].set_title('Attention Heatmap', fontsize=14)
    axes[1].axis('off')
    plt.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)
    
    # Overlay
    axes[2].imshow(overlay)
    axes[2].set_title('Attention Overlay', fontsize=14)
    axes[2].axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"Attention heatmap saved to: {output_path}")
    
    return overlay


def create_attention_highlight(image: Image.Image, attention_map: np.ndarray, 
                                threshold: float = 0.7, output_path: str = None):
    """高亮显示注意力分数高的区域"""
    
    img_array = np.array(image)
    h, w = img_array.shape[:2]
    
    # 归一化注意力图
    attention_map = (attention_map - attention_map.min()) / (attention_map.max() - attention_map.min() + 1e-8)
    
    # 调整大小
    attention_resized = cv2.resize(attention_map.astype(np.float32), (w, h))
    attention_resized = cv2.GaussianBlur(attention_resized, (21, 21), 0)
    attention_resized = (attention_resized - attention_resized.min()) / (attention_resized.max() - attention_resized.min() + 1e-8)
    
    # 创建掩码（高注意力区域）
    mask = attention_resized > threshold
    
    # 找到轮廓
    mask_uint8 = (mask * 255).astype(np.uint8)
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 在图像上绘制轮廓
    result = img_array.copy()
    cv2.drawContours(result, contours, -1, (255, 0, 0), 3)  # 红色轮廓
    
    if output_path:
        plt.figure(figsize=(10, 10))
        plt.imshow(result)
        plt.title(f'High Attention Regions (threshold={threshold})', fontsize=14)
        plt.axis('off')
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"High attention regions saved to: {output_path}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Qwen3-VL 注意力热力图可视化')
    parser.add_argument('--model_path', type=str, default='/data/xyc/fire_hydrant/output_model',
                        help='模型路径')
    parser.add_argument('--image_path', type=str, required=True,
                        help='输入图片路径')
    parser.add_argument('--prompt', type=str, default='请详细描述这张图片中的内容',
                        help='提示词')
    parser.add_argument('--output_dir', type=str, default='./attention_outputs',
                        help='输出目录')
    parser.add_argument('--device', type=str, default='cuda:1',
                        help='设备 (cuda/cpu)')
    parser.add_argument('--max_size', type=int, default=384,
                        help='Max image size (to save GPU memory)')
    parser.add_argument('--aggregation', type=str, default='mean', choices=['mean', 'max', 'sum'],
                        help='How to aggregate attention across generated tokens (mean/max/sum)')
    parser.add_argument('--layer_ratio', type=float, default=0.66,
                        help='Which layer to extract attention from (0.0=first, 1.0=last, 0.66=recommended) 提前注意力的位置,中间层通常有更好的空间信息')
    parser.add_argument('--max_new_tokens', type=int, default=256,
                        help='Maximum number of tokens to generate') 
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 加载模型
    model, processor = load_model(args.model_path, args.device)
    
    # 推理并获取注意力
    image, attentions, inputs, generated_text, original_size, vision_attentions = inference_with_attention(
        model, processor, args.image_path, args.prompt, args.max_size
    )
    
    # 提取图像注意力（聚合所有生成 token 的注意力）
    attention_map = extract_image_attention(
        model, processor, inputs, attentions, original_size, 
        vision_attentions, aggregation=args.aggregation, layer_ratio=args.layer_ratio
    )
    
    if attention_map is not None:
        # 获取文件名
        base_name = os.path.splitext(os.path.basename(args.image_path))[0]
        
        # 可视化热力图
        heatmap_path = os.path.join(args.output_dir, f'{base_name}_heatmap.png')
        visualize_attention_heatmap(image, attention_map, heatmap_path)
        
        # 高亮高注意力区域
        highlight_path = os.path.join(args.output_dir, f'{base_name}_highlight.png')
        create_attention_highlight(image, attention_map, threshold=0.6, output_path=highlight_path)
        
        print(f"\nProcessing complete!")
        print(f"Model response: {generated_text}")
    else:
        print("Failed to extract attention map, please check model output")


if __name__ == '__main__':
    main()
