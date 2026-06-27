"""
评估分析智能体 (Evaluation Analyst Agent)

本模块在 YOLO 模型验证/评估完成后自动生成结构化的评估分析报告。
与 training_analyst_agent 互补：训练报告侧重训练过程和收敛性，
评估报告侧重模型在独立测试集上的泛化表现和部署就绪度。

主要功能与职责：
  1. 读取评估运行记录、关联的模型版本和数据集版本
  2. 读取逐图预测样本（evaluation_samples）
  3. 分析 Precision/Recall/mAP 等指标
  4. 分析逐图预测质量（高置信度误检、漏检模式）
  5. 生成 Markdown 报告并持久化

设计理念：
  - 与 training_analyst_agent 保持一致的代码风格和结构
  - 评估报告聚焦"这个模型能否部署"而非"如何改进训练"
  - 逐图分析提供具体的错误案例而非抽象指标
"""

import csv
import json
from pathlib import Path
from typing import Any

from app.core.database import db, fetch_all, utc_now


def _read_json(path: Path) -> dict[str, Any]:
    """读取 JSON 文件，文件不存在时返回空字典。"""
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_results(path: Path) -> list[dict[str, str]]:
    """读取 CSV 格式的评估结果文件。"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _analyze_samples(samples: list[dict]) -> dict:
    """分析逐图预测样本，提取错误模式。"""
    total = len(samples)
    if total == 0:
        return {"total": 0, "issues": []}

    issues = []
    low_conf_count = 0
    empty_pred_count = 0
    high_conf_count = 0

    for s in samples:
        conf_str = s.get("confidence_summary", "")
        if "0 个预测框" in conf_str:
            empty_pred_count += 1
        elif "预测框" in conf_str:
            try:
                count = int(conf_str.split("个")[0].strip())
                if count > 10:
                    high_conf_count += 1
            except (ValueError, IndexError):
                pass

    if empty_pred_count > 0:
        pct = round(empty_pred_count / total * 100, 1)
        issues.append(f"{empty_pred_count}/{total} 张图片 ({pct}%) 无任何预测框，可能存在漏检问题。")

    if high_conf_count > 0:
        pct = round(high_conf_count / total * 100, 1)
        issues.append(f"{high_conf_count}/{total} 张图片 ({pct}%) 预测框数量 > 10，可能存在误检或密集预测。")

    return {
        "total": total,
        "empty_predictions": empty_pred_count,
        "high_density_predictions": high_conf_count,
        "issues": issues,
    }


def generate_evaluation_report(evaluation_run_id: int) -> dict[str, str]:
    """
    生成评估分析报告，返回包含摘要文本和报告路径的字典。

    执行流程：
      1. 查询 evaluation_runs / model_versions / dataset_versions
      2. 读取本地评估产物文件
      3. 查询逐图预测样本并分析
      4. 组装 Markdown 报告
      5. 写入文件并持久化到数据库

    参数:
        evaluation_run_id: 评估运行记录的主键 ID

    返回:
        {"summary": str, "report_path": str}
    """
    # 步骤 1：查询关联记录
    with db() as cur:
        run = dict(cur.execute(
            "SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_run_id,)
        ).fetchone())

        model = dict(cur.execute(
            "SELECT * FROM model_versions WHERE id = %s",
            (run["model_version_id"],),
        ).fetchone()) if run.get("model_version_id") else {}

        version = dict(cur.execute(
            "SELECT * FROM dataset_versions WHERE id = %s",
            (run["dataset_version_id"],),
        ).fetchone()) if run.get("dataset_version_id") else {}

    # 步骤 2：读取本地文件
    run_path = Path(run["run_path"])
    metrics = _read_json(run_path / "val" / "metrics.json") if (run_path / "val").exists() else {}
    params = _read_json(run_path / "params.json")
    # 尝试读取 val/results.csv
    results_csv = None
    for candidate in [run_path / "val" / "results.csv", run_path / "results.csv"]:
        if candidate.exists():
            results_csv = candidate
            break

    # 步骤 3：查询逐图样本
    samples = fetch_all(
        "SELECT * FROM evaluation_samples WHERE evaluation_run_id = %s ORDER BY id ASC",
        (evaluation_run_id,),
    )
    sample_analysis = _analyze_samples(samples if samples else [])

    # 步骤 4：分析
    findings: list[str] = []
    suggestions: list[str] = []

    p = run.get("precision")
    r = run.get("recall")
    m50 = run.get("map50")
    m5095 = run.get("map50_95")

    # Precision vs Recall
    if p is not None and r is not None:
        if p - r > 0.15:
            findings.append(f"Precision ({p:.3f}) 明显高于 Recall ({r:.3f})，模型偏保守，漏检较多。")
            suggestions.append("考虑降低置信度阈值或补充当前漏检场景的训练数据。")
        elif r - p > 0.15:
            findings.append(f"Recall ({r:.3f}) 高于 Precision ({p:.3f})，模型误检较多。")
            suggestions.append("提高置信度阈值，补充易混淆负样本，检查标注边界一致性。")

    # mAP 就绪度
    if m5095 is not None:
        if m5095 < 0.3:
            findings.append(f"mAP50-95 ({m5095:.3f}) 偏低，当前模型不适合直接部署。")
            suggestions.append("优先提升训练数据质量和模型容量，暂不建议导出部署。")
        elif m5095 < 0.5:
            findings.append(f"mAP50-95 ({m5095:.3f}) 中等，可在特定场景试用但需人工复核。")
            suggestions.append("在目标部署场景采集一批真实图片做人工抽检，确认可接受后再上线。")
        else:
            findings.append(f"mAP50-95 ({m5095:.3f}) 表现良好，模型具备部署就绪条件。")
            suggestions.append("导出 ONNX/TensorRT 前，用独立真实场景测试集跑一次回归验证。")

    # 逐图分析
    for issue in sample_analysis.get("issues", []):
        findings.append(f"[逐图分析] {issue}")
    if sample_analysis.get("empty_predictions", 0) > 0:
        suggestions.append("对无预测框的图片进行人工复核，确认是负样本还是模型漏检。")

    # 兜底
    if not findings:
        findings.append("评估指标在可接受范围内，未发现明显问题。")
    if not suggestions:
        suggestions.append("建议将当前模型标记为候选，并在真实业务场景做 A/B 测试。")

    # 步骤 5：组装报告
    summary = (
        f"{version.get('dataset_name', 'unknown')}:{version.get('version', '')} "
        f"评估完成，mAP50={m50}，mAP50-95={m5095}。"
    )

    body = [
        "# AI Evaluation Report",
        "",
        "## 1. 评估概览",
        f"- 评估 Run: `{run.get('run_id', '')}`",
        f"- 模型: `{model.get('run_id', '')}` (训练 Run: `{model.get('training_run_id', '')}`)",
        f"- 评估数据: `{version.get('dataset_name', '')}:{version.get('version', '')}`",
        f"- 数据 Split: `{params.get('source_split', 'test')}`",
        f"- Precision: `{p}`",
        f"- Recall: `{r}`",
        f"- mAP50: `{m50}`",
        f"- mAP50-95: `{m5095}`",
        f"- 逐图样本数: `{sample_analysis.get('total', 0)}`",
        "",
        "## 2. 指标分析",
    ]

    if p is not None and r is not None:
        body.append(f"- Precision-Recall 平衡: P={p:.3f}, R={r:.3f}，" +
                    ("模型偏向保守（漏检>误检）" if p - r > 0.1 else
                     "模型偏向激进（误检>漏检）" if r - p > 0.1 else
                     "两者较为平衡"))

    if m5095 is not None:
        deploy_status = "✅ 可考虑部署" if m5095 >= 0.5 else "⚠️ 需改进后部署" if m5095 >= 0.3 else "❌ 不建议部署"
        body.append(f"- 部署就绪度: {deploy_status}")

    body.extend([
        "",
        "## 3. 逐图预测分析",
        f"- 总样本: {sample_analysis.get('total', 0)} 张",
        f"- 空预测: {sample_analysis.get('empty_predictions', 0)} 张",
        f"- 高密度预测 (>10框): {sample_analysis.get('high_density_predictions', 0)} 张",
        "",
        "## 4. 关键发现",
        *[f"- {item}" for item in findings],
        "",
        "## 5. 部署建议",
        *[f"- {item}" for item in suggestions],
    ])

    # 写入文件
    report_path = run_path / "ai_evaluation_report.md"
    report_path.write_text("\n".join(body) + "\n", encoding="utf-8")

    # 持久化
    with db() as cur:
        cur.execute(
            "UPDATE evaluation_runs SET report_path = %s, summary = %s WHERE id = %s",
            (str(report_path), summary, evaluation_run_id),
        )

    return {"summary": summary, "report_path": str(report_path)}
