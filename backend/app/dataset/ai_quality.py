"""
AI 辅助数据集质量分析模块。

提供三个核心能力：
  1. 图片质量筛查 — 模糊、过曝、过暗检测（纯 OpenCV，无需 GPU）
  2. 重复图片检测 — 感知哈希 (pHash) 找近似重复
  3. 标注一致性对比 — 用已有模型推理，计算人工标注与 AI 预测的 IoU

全部本地运行，不依赖外部 API。
"""

import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core.config import DATASETS_DIR, MODEL_REGISTRY_DIR
from app.core.database import fetch_all, fetch_one


# ═══════════════════════════════════════════════════════════════════════════
# 1. 图片质量筛查
# ═══════════════════════════════════════════════════════════════════════════

def _pil_ensure():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise RuntimeError("Pillow is required: pip install Pillow")


def check_image_quality(image_path: Path) -> dict:
    """
    检测单张图片的质量问题。

    返回:
      { "is_ok": bool, "blur_score": float, "exposure": str, "issues": [...] }

    模糊阈值: Laplacian variance < 100 → 模糊, < 50 → 严重模糊
    曝光判断: 均值 < 40 → 过暗, > 220 → 过曝
    """
    import numpy as np

    try:
        import cv2
    except ImportError:
        # 纯 PIL 回退：只做曝光检测
        return _check_quality_pil_fallback(image_path)

    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"is_ok": False, "blur_score": 0, "exposure": "unknown", "issues": ["无法读取图片"]}

    issues = []
    h, w = img.shape

    # 分辨率检查
    if w < 200 or h < 200:
        issues.append(f"分辨率过低 ({w}×{h})")

    # 模糊检测: Laplacian 方差
    laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
    blur_score = round(laplacian_var, 1)
    if laplacian_var < 50:
        issues.append("严重模糊")
    elif laplacian_var < 100:
        issues.append("轻度模糊")

    # 曝光检测: 像素均值
    mean_brightness = float(img.mean())
    if mean_brightness < 40:
        exposure = "过暗"
        issues.append("曝光不足")
    elif mean_brightness > 220:
        exposure = "过曝"
        issues.append("过度曝光")
    elif mean_brightness < 60:
        exposure = "偏暗"
    elif mean_brightness > 200:
        exposure = "偏亮"
    else:
        exposure = "正常"

    return {
        "is_ok": len(issues) == 0,
        "blur_score": blur_score,
        "exposure": exposure,
        "mean_brightness": round(mean_brightness, 1),
        "dimensions": f"{w}×{h}",
        "issues": issues,
    }


def _check_quality_pil_fallback(image_path: Path) -> dict:
    """PIL only fallback — basic brightness/exposure check."""
    Image = _pil_ensure()
    import numpy as np
    img = Image.open(image_path).convert("L")
    arr = np.array(img, dtype=np.float64)
    mean = float(arr.mean())
    exposure = "正常"
    issues = []
    if mean < 40:
        exposure = "过暗"; issues.append("曝光不足")
    elif mean > 220:
        exposure = "过曝"; issues.append("过度曝光")
    elif mean < 60:
        exposure = "偏暗"
    elif mean > 200:
        exposure = "偏亮"
    return {
        "is_ok": len(issues) == 0,
        "blur_score": 0,
        "exposure": exposure,
        "mean_brightness": round(mean, 1),
        "dimensions": f"{img.width}×{img.height}",
        "issues": issues,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 重复图片检测 (pHash)
# ═══════════════════════════════════════════════════════════════════════════

def compute_phash(image_path: Path) -> str:
    """计算图片的 64-bit 感知哈希 (pHash)。"""
    Image = _pil_ensure()
    img = Image.open(image_path).convert("L").resize((8, 8), Image.LANCZOS)
    import numpy as np
    arr = np.array(img, dtype=np.float64)
    dct = _dct_2d(arr)
    # 取左上 8x8 低频
    dct_low = dct[:8, :8]
    median = float(np.median(dct_low))
    bits = (dct_low > median).flatten()
    # 转 hex
    hash_int = 0
    for i, b in enumerate(bits):
        if b:
            hash_int |= 1 << i
    return f"{hash_int:016x}"


def _dct_2d(arr):
    """2D DCT (离散余弦变换) — 简化实现。"""
    import numpy as np
    n = arr.shape[0]
    result = np.zeros((n, n), dtype=np.float64)
    for u in range(n):
        for v in range(n):
            total = 0.0
            for x in range(n):
                for y in range(n):
                    total += arr[x, y] * np.cos((2*x+1)*u*np.pi/(2*n)) * np.cos((2*y+1)*v*np.pi/(2*n))
            cu = 1/np.sqrt(2) if u == 0 else 1.0
            cv = 1/np.sqrt(2) if v == 0 else 1.0
            result[u, v] = cu * cv * total / 4.0
    return result


def hamming_distance(h1: str, h2: str) -> int:
    """计算两个十六进制哈希的汉明距离。"""
    if len(h1) != len(h2):
        return 64
    dist = 0
    for c1, c2 in zip(h1, h2):
        xor = int(c1, 16) ^ int(c2, 16)
        dist += bin(xor).count("1")
    return dist


def find_duplicates(image_paths: list[Path], threshold: int = 12) -> list[dict]:
    """
    在一组图片中找出近似重复的图片对。

    threshold: 汉明距离阈值，≤ 此值视为重复（默认 12，允许轻微差异）

    返回: [{ "pair": [path1, path2], "distance": int }, ...]
    """
    hashes = {}
    duplicates = []

    for p in image_paths:
        try:
            h = compute_phash(p)
            hashes[str(p)] = h
        except Exception:
            continue

    seen = [None] * len(image_paths)
    paths = list(hashes.keys())
    for i in range(len(paths)):
        if seen[i]:
            continue
        for j in range(i + 1, len(paths)):
            if seen[j]:
                continue
            dist = hamming_distance(hashes[paths[i]], hashes[paths[j]])
            if dist <= threshold:
                duplicates.append({
                    "pair": [paths[i], paths[j]],
                    "distance": dist,
                })
                seen[i] = seen[j] = True
                break  # 每张只算一组

    return duplicates


# ═══════════════════════════════════════════════════════════════════════════
# 3. 标注 vs AI 预测一致性
# ═══════════════════════════════════════════════════════════════════════════

def _iou(box1: list[float], box2: list[float]) -> float:
    """
    计算两个 YOLO 归一化 bbox 的 IoU。
    box: [cx, cy, w, h] 归一化坐标
    """
    def to_xyxy(box):
        cx, cy, w, h = box
        return [cx - w/2, cy - h/2, cx + w/2, cy + h/2]

    a = to_xyxy(box1)
    b = to_xyxy(box2)

    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def check_annotation_consistency(
    image_path: Path,
    label_path: Path,
    model_path: str,
    conf: float = 0.25,
    iou_threshold: float = 0.5,
) -> dict:
    """
    用已有模型推理一张图，对比人工标注和 AI 预测。

    返回:
      {
        "image": str,
        "human_boxes": int,       # 人工标注框数
        "ai_boxes": int,          # AI 预测框数
        "matched": int,           # IoU ≥ threshold 的匹配对数
        "missed_by_ai": int,     # 人工有、AI 没检出的
        "extra_by_ai": int,      # AI 检出、人工没标的
        "avg_iou": float,         # 匹配对的平均 IoU
        "status": "ok" | "review" | "mismatch",
      }
    """
    from ultralytics import YOLO

    if not Path(model_path).exists():
        return {"error": f"模型文件不存在: {model_path}"}

    model = YOLO(model_path)
    results = model(str(image_path), conf=conf, verbose=False)

    ai_boxes = []
    if results and results[0].boxes:
        for box in results[0].boxes:
            xywh = box.xywhn[0].tolist()  # 归一化 [cx, cy, w, h]
            cls_id = int(box.cls[0])
            ai_boxes.append({"bbox": xywh, "class": cls_id})

    # 读取人工标注
    human_boxes = []
    if label_path.exists():
        with open(label_path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    cls_id = int(parts[0])
                    bbox = [float(x) for x in parts[1:5]]
                    human_boxes.append({"bbox": bbox, "class": cls_id})

    # 匹配计算
    matched = 0
    total_iou = 0.0
    human_matched = [False] * len(human_boxes)
    ai_matched = [False] * len(ai_boxes)

    for hi, hb in enumerate(human_boxes):
        best_iou = 0.0
        best_ai = -1
        for ai_idx, ab in enumerate(ai_boxes):
            if ai_matched[ai_idx]:
                continue
            if hb["class"] != ab["class"]:
                continue
            iou_val = _iou(hb["bbox"], ab["bbox"])
            if iou_val > best_iou:
                best_iou = iou_val
                best_ai = ai_idx
        if best_iou >= iou_threshold:
            human_matched[hi] = True
            ai_matched[best_ai] = True
            matched += 1
            total_iou += best_iou

    missed_by_ai = human_matched.count(False)
    extra_by_ai = ai_matched.count(False)

    # 状态判断
    if len(human_boxes) == 0 and len(ai_boxes) == 0:
        status = "ok"
    elif missed_by_ai > 0 and len(human_boxes) > 0 and missed_by_ai == len(human_boxes):
        status = "mismatch"  # AI 完全没检出人工标注
    elif extra_by_ai > 0 and len(human_boxes) == 0:
        status = "review"    # 只有 AI 检出，可能漏标
    elif missed_by_ai > 0 or extra_by_ai > 0:
        status = "review"
    else:
        status = "ok"

    return {
        "image": str(image_path),
        "human_boxes": len(human_boxes),
        "ai_boxes": len(ai_boxes),
        "matched": matched,
        "missed_by_ai": missed_by_ai,
        "extra_by_ai": extra_by_ai,
        "avg_iou": round(total_iou / matched, 3) if matched > 0 else 0.0,
        "status": status,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 批量分析 API（给前端用的入口）
# ═══════════════════════════════════════════════════════════════════════════

def analyze_dataset_images(dataset_version_id: int, checks: list[str] | None = None) -> dict:
    """
    对数据集版本中的所有图片运行质量分析和重复检测。

    checks: 可选 ["quality", "duplicates", "consistency"]，默认全部
    """
    if checks is None:
        checks = ["quality", "duplicates"]

    version = fetch_one(
        "SELECT dv.*, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id = dv.dataset_id WHERE dv.id = %s",
        (dataset_version_id,),
    )
    if not version:
        return {"error": f"Dataset version {dataset_version_id} not found"}

    images = fetch_all(
        "SELECT * FROM image_items WHERE dataset_version_id = %s ORDER BY id ASC",
        (dataset_version_id,),
    )

    result = {
        "dataset_version_id": dataset_version_id,
        "dataset_name": version.get("dataset_name", ""),
        "version": version.get("version", ""),
        "total_images": len(images),
        "quality": None,
        "duplicates": None,
        "consistency": None,
        "summary": {},
    }

    # ── 质量筛查 ──
    if "quality" in checks and images:
        qr = []
        blurry = 0
        exposure_issues = 0
        low_res = 0
        for img in images:
            path = Path(img["image_path"])
            if not path.exists():
                continue
            q = check_image_quality(path)
            q["image_id"] = img["id"]
            q["image_name"] = path.name
            qr.append(q)
            if any("模糊" in i for i in q.get("issues", [])):
                blurry += 1
            if any("曝" in i for i in q.get("issues", [])):
                exposure_issues += 1
            if any("分辨率" in i for i in q.get("issues", [])):
                low_res += 1
        result["quality"] = qr
        result["summary"]["quality"] = {
            "total": len(qr),
            "ok": sum(1 for q in qr if q["is_ok"]),
            "blurry": blurry,
            "exposure_issues": exposure_issues,
            "low_resolution": low_res,
        }

    # ── 重复检测 ──
    if "duplicates" in checks and images and len(images) > 1:
        paths = [Path(img["image_path"]) for img in images if Path(img["image_path"]).exists()]
        dups = find_duplicates(paths)
        result["duplicates"] = dups
        result["summary"]["duplicates"] = {
            "scanned": len(paths),
            "duplicate_pairs": len(dups),
        }

    # ── 标注一致性 ──
    if "consistency" in checks and images:
        # 找最新的 best.pt
        model = fetch_one(
            "SELECT registry_path, best_pt_path FROM model_versions WHERE is_production = 1 ORDER BY id DESC LIMIT 1"
        )
        if not model:
            model = fetch_one(
                "SELECT registry_path, best_pt_path FROM model_versions ORDER BY id DESC LIMIT 1"
            )

        if model:
            model_path = model.get("best_pt_path") or ""
            if not model_path and model.get("registry_path"):
                bp = Path(model["registry_path"]) / "weights" / "best.pt"
                if bp.exists():
                    model_path = str(bp)

            if model_path:
                cs = []
                mismatch_count = 0
                review_count = 0
                # 只检查有标注的图片
                for img in images:
                    lp = Path(img["label_path"]) if img.get("label_path") else None
                    if not lp or not lp.exists():
                        continue
                    ip = Path(img["image_path"])
                    if not ip.exists():
                        continue
                    c = check_annotation_consistency(ip, lp, model_path)
                    c["image_id"] = img["id"]
                    c["image_name"] = ip.name
                    cs.append(c)
                    if c.get("status") == "mismatch":
                        mismatch_count += 1
                    elif c.get("status") == "review":
                        review_count += 1

                result["consistency"] = cs
                result["summary"]["consistency"] = {
                    "checked": len(cs),
                    "ok": sum(1 for c in cs if c.get("status") == "ok"),
                    "needs_review": review_count,
                    "mismatch": mismatch_count,
                    "model_used": str(Path(model_path).name) if model_path else "",
                }
            else:
                result["summary"]["consistency"] = {"error": "未找到可用模型权重 (best.pt)"}
        else:
            result["summary"]["consistency"] = {"error": "没有已训练的模型，请先完成一次训练"}

    return result
