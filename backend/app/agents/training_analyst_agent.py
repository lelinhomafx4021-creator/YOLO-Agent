"""
训练分析智能体 (Training Analyst Agent)

本模块是 YOLOps 平台中的训练分析智能体，负责在 YOLO 模型训练流水线
完成后自动生成结构化的训练分析报告。它作为一个独立的分析模块被上层
编排逻辑调用，不直接对外暴露 API 接口。

主要功能与职责：
  1. 读取数据库中的训练运行记录、模型版本、数据集版本和标注审计报告
  2. 从本地文件系统读取数据集清单 (dataset_manifest.json)、评估指标
     (metrics.json)、逐轮训练结果 (results.csv) 和审计报告 JSON
  3. 分析数据集质量：检查类别分布均衡性、标注异常情况（无效边界框、
     缺失标签文件等）
  4. 分析训练指标：对比 Precision 与 Recall 的关系，检查 mAP 提升趋势，
     评估模型生产就绪度
  5. 综合以上分析生成关键发现 (findings) 和下一轮改进建议 (suggestions)
  6. 将报告内容组装为 Markdown 格式并写入 ai_training_report.md 文件
  7. 将报告路径和摘要文本持久化到数据库的 training_runs 表中

设计理念：
  - 每个辅助函数职责单一，方便单元测试
  - 文件读取类函数自动处理文件缺失场景，避免调用方重复处理异常
  - 报告生成函数以 training_run_id 为唯一入口，通过数据库关联获取
    所有需要的信息，保持接口简洁

依赖模块：
  - app.core.database: 数据库连接与会话管理（db 上下文管理器、utc_now）
  - 标准库: csv（解析 results.csv）、json（解析 JSON 文件）、
    pathlib（路径操作）、typing（类型标注）
"""

import csv      # 用于解析 CSV 格式的逐轮训练结果文件
import json     # 用于读取和序列化 JSON 格式的数据文件
from pathlib import Path  # 跨平台路径操作，替代 os.path
from typing import Any    # 类型标注支持

from app.core.database import db, utc_now  # 数据库上下文管理器与 UTC 时间戳工具


def _read_json(path: Path) -> dict[str, Any]:
    """
    读取指定路径的 JSON 文件并解析为字典。

    该函数是模块内部的辅助方法（以下划线开头），用于统一处理 JSON 文件的
    读取逻辑。当文件不存在时返回空字典，使得调用方无需每次判断文件存在性，
    从而简化主流程的代码。

    参数:
        path (Path): JSON 文件的完整路径。

    返回:
        dict[str, Any]: 解析后的字典内容。若文件不存在、路径无效或
            文件内容不是合法 JSON，则返回空字典 {}。
    """
    # 文件不存在时直接返回空字典，避免 FileNotFoundError
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_results(path: Path) -> list[dict[str, str]]:
    """
    读取 CSV 格式的训练逐轮结果文件，返回字典列表。

    YOLO 训练过程中会输出每一轮的指标数据到 CSV 文件，该函数负责
    解析该文件。每一行记录对应一轮训练的结果，列名作为字典的键，
    单元格的字符串值作为字典的值。

    参数:
        path (Path): CSV 文件的完整路径。

    返回:
        list[dict[str, str]]: 一个列表，其中每个元素是代表一行记录的
            字典（列名 -> 单元格值）。若文件不存在则返回空列表 []。
    """
    # 文件不存在时直接返回空列表
    if not path.exists():
        return []
    # 以只读模式打开 CSV 文件，使用 csv.DictReader 自动将首行作为列名
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _metric(row: dict[str, str], names: list[str]) -> float | None:
    """
    从 CSV 行字典中按多个候选列名提取首个有效的数值指标。

    YOLO 不同版本输出的 CSV 列名可能存在差异（如 "metrics/mAP50-95(B)"
    与 "metrics/mAP50-95"），该函数通过按优先级顺序尝试多个列名来提高
    兼容性。提取到有效数值后立即返回，不再继续尝试后续列名。

    参数:
        row (dict[str, str]): CSV 中某一行的数据字典，键为列名，值为字符串。
        names (list[str]): 候选列名列表，按优先级从高到低排列。
            例如: ["metrics/mAP50-95(B)", "metrics/mAP50-95"]

    返回:
        float | None: 成功提取到的浮点数指标值。若所有候选列名对应的值
            均为空、不存在或无法转换为 float，则返回 None。
    """
    # 按优先级遍历所有候选列名
    for name in names:
        # 检查当前列名在行中是否存在且值非空
        if name in row and row[name] not in {"", None}:
            try:
                # 尝试将字符串值转换为浮点数
                return float(row[name])
            except ValueError:
                # 值无法转换为 float（如包含非数字字符）时静默跳过，
                # 继续尝试下一个候选列名
                pass
    # 所有候选列名均无效，返回 None
    return None


def generate_training_report(training_run_id: int) -> dict[str, str]:
    """
    生成训练分析报告，返回包含摘要文本和报告路径的字典。

    这是本模块的对外主入口函数，上层编排逻辑以 training_run_id 为唯一
    参数调用该函数。函数内部依次执行数据库查询、本地文件读取、数据质量
    分析、指标趋势分析、报告组装与写入、结果持久化等步骤，最终返回摘要
    信息供调用方使用。

    执行流程（共 6 步）：
      1. 数据库查询：获取 training_runs / model_versions /
         dataset_versions / label_audit_reports 四张表的关联记录
      2. 本地文件读取：加载 dataset_manifest.json（数据集清单）、
         metrics.json（评估指标）、results.csv（逐轮结果）和审计报告
      3. 数据分析：检查类别分布均衡性、标注异常、Precision-Recall 关系、
         mAP 提升趋势、生产就绪度评估
      4. 报告组装：将分析结果格式化为 Markdown 文本，包含概览、数据质量、
         关键发现和下一轮建议四个章节
      5. 文件写入：将 Markdown 报告保存到模型 registry 目录下的
         ai_training_report.md 文件中
      6. 数据库持久化：将报告路径和摘要写入 training_runs 表

    参数:
        training_run_id (int): 训练运行记录的唯一主键 ID，用于关联查询
            所有相关数据。

    返回:
        dict[str, str]: 包含以下两个键的字典：
            - "summary": 报告摘要文本，简要描述本次训练结果
            - "report_path": 生成的 Markdown 报告文件的绝对路径字符串

    异常:
        KeyError: 当传入的 training_run_id 在数据库中不存在，或关联的
            model_versions / dataset_versions 记录缺失时，访问 run、
            model 或 version 字典的键会抛出 KeyError。
    """
    # ================================================================
    # 步骤 1：从数据库查询所有关联记录
    # 使用 db() 上下文管理器获取数据库连接，自动处理事务提交和回滚
    # ================================================================
    with db() as cur:
        run = dict(cur.execute(
            "SELECT * FROM training_runs WHERE id = %s", (training_run_id,)
        ).fetchone())

        model = dict(cur.execute(
            "SELECT * FROM model_versions WHERE training_run_id = %s",
            (training_run_id,),
        ).fetchone())

        version = dict(cur.execute(
            "SELECT * FROM dataset_versions WHERE id = %s",
            (run["dataset_version_id"],),
        ).fetchone())

        audit = dict(cur.execute(
            "SELECT missing_labels, orphan_labels, invalid_bboxes, empty_labels, class_distribution_json, suggestions_json, audit_report_path AS report_path FROM dataset_versions WHERE id = %s",
            (version["id"],),
        ).fetchone())

    # ================================================================
    # 步骤 2：从本地文件系统读取训练相关的数据文件
    # registry_path 是模型版本记录中存储的模型注册表路径
    # ================================================================
    registry_path = Path(model["registry_path"])
    # 读取数据集清单 JSON，包含数据集名称、版本、图片数、标注数等信息
    manifest = _read_json(registry_path / "dataset_manifest.json")
    # 读取训练评估指标 JSON，包含 precision、recall、mAP 等最终指标
    metrics = _read_json(registry_path / "metrics.json")
    # 读取逐轮训练结果 CSV，包含每轮的各类指标变化数据
    results = _read_results(registry_path / "results.csv")
    # 读取标注审计报告 JSON（如果存在审计记录）
    report_path_str = audit.get("report_path", "") if audit else ""
    audit_report = _read_json(Path(report_path_str)) if report_path_str and report_path_str != "." else {}

    # ================================================================
    # 步骤 3：对数据集质量和训练指标进行多维度分析
    # findings 列表存储关键发现，suggestions 列表存储改进建议
    # ================================================================
    findings: list[str] = []      # 关键发现列表
    suggestions: list[str] = []   # 下一轮改进建议列表

    # ---- 3a. 检查类别分布是否均衡 ----
    # 从审计报告中获取类别分布字典（类别名 -> 样本数）
    class_dist = audit_report.get("class_distribution", {})
    if class_dist:
        values = list(class_dist.values())
        # 均衡性判断标准：
        #   1) 存在样本数为 0 的类别（某些类别完全没有样本）
        #   2) 最大类样本数 / 最小类样本数 >= 5（极不均衡）
        # 满足任一条件即认为类别分布存在问题
        if min(values) == 0 or max(values) / max(min(values), 1) >= 5:
            findings.append("类别分布明显不均衡，少数类可能成为召回率瓶颈。")
            suggestions.append("下一轮优先补充少数类、遮挡、小目标和复杂背景样本。")

    # ---- 3b. 检查标注异常情况 ----
    # 检查是否存在无效边界框（坐标格式错误、超出图像边界等）
    if audit_report.get("invalid_bboxes", 0) > 0:
        findings.append(f"存在 {audit_report['invalid_bboxes']} 个异常标注行，训练前应修复。")
        suggestions.append("将异常 txt 加入人工复核清单，避免脏标签影响收敛。")
    # 检查是否存在缺失标签文件的图片
    if audit_report.get("missing_labels", 0) > 0:
        findings.append(f"有 {audit_report['missing_labels']} 张图片缺失标签文件。")
        suggestions.append("确认缺失标签图片是负样本还是漏标图片，并统一标注策略。")

    # ---- 3c. 分析 Precision 与 Recall 的关系 ----
    # 通过对比最终的 Precision 和 Recall 值判断模型的预测倾向
    if results:
        # 只取首轮和末轮的结果用于趋势判断（当前主要用于提取首轮 mAP）
        first, last = results[0], results[-1]
        # 从 metrics.json 中读取最终评估指标
        p = metrics.get("precision")   # 精确率
        r = metrics.get("recall")      # 召回率
        m = metrics.get("map50_95")    # mAP@50:95（综合精度指标）

        # 情况 1：Precision 明显高于 Recall（差值 > 0.15）
        # 含义：模型预测偏向保守，漏检（False Negative）较多
        if p is not None and r is not None and p - r > 0.15:
            findings.append("precision 明显高于 recall，模型偏保守，存在漏检风险。")
            suggestions.append(
                "提高少数类样本覆盖，检查漏标，并尝试更强增强或更大模型。"
            )

        # 情况 2：Recall 明显高于 Precision（差值 > 0.15）
        # 含义：模型预测偏向激进，误检（False Positive）较多
        if r is not None and p is not None and r - p > 0.15:
            findings.append("recall 高于 precision，模型可能存在较多误检。")
            suggestions.append(
                "补充易混淆负样本，检查类别边界，并适当提高置信度阈值。"
            )

        # ---- 3d. 检查 mAP 提升趋势（首轮 vs 末轮） ----
        # 从逐轮结果 CSV 中提取首轮和末轮的 mAP50-95 值
        # 使用 _metric 函数兼容不同 YOLO 版本的列名差异
        first_map = _metric(first, ["metrics/mAP50-95(B)", "metrics/mAP50-95"])
        last_map = _metric(last, ["metrics/mAP50-95(B)", "metrics/mAP50-95"])
        # 如果末轮 mAP 相比首轮提升不足 0.02，说明训练可能未收敛或数据有问题
        if first_map is not None and last_map is not None and last_map - first_map < 0.02:
            findings.append("mAP 提升幅度很小，可能是数据过少、标注质量差或训练轮数不足。")

        # ---- 3e. 根据 mAP 绝对值给出生产就绪度评估 ----
        # mAP50-95 < 0.35：性能较差，不建议用于生产环境
        if m is not None and m < 0.35:
            findings.append("mAP50-95 偏低，当前模型不建议作为生产候选。")
            suggestions.append("先修复数据质量并做 smoke training，再扩大训练轮数。")
        # mAP50-95 >= 0.5：性能较好，可作为候选模型，但仍需业务验证
        elif m is not None and m >= 0.5:
            suggestions.append("当前模型可作为候选模型，但仍建议通过真实业务样本做回归测试。")

    # ---- 3f. 兜底处理：没有任何发现或建议时给出中性提示 ----
    # 确保报告不会出现空的 findings 或 suggestions 章节
    if not findings:
        findings.append("未发现明显数据或训练异常，建议继续扩大验证集并做真实场景回归。")
    if not suggestions:
        suggestions.append("下一轮重点补充边界样本，保持数据集版本和 best.pt 可追溯。")

    # ================================================================
    # 步骤 4：组装报告内容
    # 生成摘要文本（简洁的一行描述）和完整 Markdown 报告正文
    # ================================================================
    # 摘要文本：包含数据集名称、版本号和 mAP50-95 指标
    summary = (
        f"{manifest.get('dataset_name', 'dataset')}:{manifest.get('version', '')} "
        f"训练完成，mAP50-95={metrics.get('map50_95')}。"
    )

    # Markdown 格式报告正文，按章节组织
    body = [
        "# AI Training Review",  # 报告标题
        "",
        "## 1. 本次训练概览",  # 章节 1：训练基本信息
        f"- Run ID: `{run['run_id']}`",
        f"- 数据集: `{manifest.get('dataset_name', '')}:{manifest.get('version', '')}`",
        f"- 基础模型: `{run['base_model']}`",
        f"- epochs/imgsz/batch: `{run['epochs']}/{run['imgsz']}/{run['batch']}`",
        f"- Precision: `{metrics.get('precision')}`",
        f"- Recall: `{metrics.get('recall')}`",
        f"- mAP50: `{metrics.get('map50')}`",
        f"- mAP50-95: `{metrics.get('map50_95')}`",
        "",
        "## 2. 数据集质量",  # 章节 2：数据集质量评估
        f"- 图片数: `{manifest.get('image_count')}`",
        f"- 标注文件数: `{manifest.get('label_file_count')}`",
        f"- 实例数: `{manifest.get('instance_count')}`",
        f"- 类别分布: `{json.dumps(class_dist, ensure_ascii=False)}`",
        "",
        "## 3. 关键发现",  # 章节 3：自动分析出的关键问题
        *[f"- {item}" for item in findings],
        "",
        "## 4. 下一轮建议",  # 章节 4：针对发现的改进建议
        *[f"- {item}" for item in suggestions],
    ]

    # ================================================================
    # 步骤 5：将报告写入本地 Markdown 文件
    # 文件保存在模型 registry 目录下，与数据集清单等文件同级
    # ================================================================
    report_path = registry_path / "ai_training_report.md"
    # 将 body 列表按行拼接，每个元素之间用换行符分隔，末尾追加一个换行
    report_path.write_text("\n".join(body) + "\n", encoding="utf-8")

    # ================================================================
    # 步骤 6：将报告记录持久化到数据库
    with db() as cur:
        cur.execute(
            "UPDATE training_runs SET report_path = %s, summary = %s WHERE id = %s",
            (str(report_path), summary, training_run_id),
        )

    # 返回摘要文本和报告路径供调用方使用
    return {"summary": summary, "report_path": str(report_path)}
