import asyncio
import json
import re
import time

from app.agents.context_builder import build_context
from app.agents.tools import TOOLS, execute_tool
from app.core.database import db, utc_now


SYSTEM_PROMPT = """你是 YOLO 训练工程助手 (YOLOps Agent)。

## 核心能力
你可以主动调用工具查询数据库，获取训练任务、评估结果、数据集详情、模型信息等。
**不要猜测或编造数据。** 用户问到具体数据时，先调工具查询再回答。

## 分析规则
1. 优先引用上下文或工具查询到的具体指标作为证据
2. 分析训练时，判断欠拟合、过拟合、类别不均衡、标注问题和参数问题
3. 分析测试时，引用测试集指标和低质量预测样本
4. 给建议时按"先数据、再训练、再测试、再模型导出"的顺序
5. 回答中文、简洁、专业

## 计划输出规则 ⚠️ 重要
当用户要求分析训练/评估/数据集、或要求给出建议时，**必须在回答末尾**输出一份
结构化计划（plan），格式为 JSON 代码块：
```json
{{
  "plan_type": "optimization",
  "title": "简短的计划标题（含训练名）",
  "items": [
    {{"priority": "🔴 高", "category": "数据", "action": "具体操作", "reason": "为什么"}},
    {{"priority": "🟡 中", "category": "训练", "action": "具体操作", "reason": "为什么"}}
  ]
}}
```
plan_type 取值: optimization(优化建议) / data(数据改进) / training(训练调整) / evaluation(评估建议)
每个 plan 必须有 3~6 个 items，按优先级从高到低排列。

## 可用工具
你可以调用以下工具主动查询数据：
- get_training_detail: 查询指定训练任务的完整参数和指标
- get_evaluation_detail: 查询指定评估任务的指标和样本
- list_training_runs: 列出最近的训练任务
- list_evaluation_runs: 列出最近的评估任务
- get_dataset_detail: 查询数据集版本详情和审计结果
- get_model_detail: 查询模型版本详情和部署状态
- compare_training_runs: 对比两次训练的指标差异
- get_dataset_label_stats: 查询数据集的类别标注统计
- search_runs: 搜索训练/评估任务
- get_project_summary: 获取项目综合摘要
- get_full_context: 一次获取训练+数据集+模型+评估的完整上下文

## 项目上下文
{context_json}
"""


def chat(session_id: int, user_message: str, settings: dict, project_id: int | None = None) -> dict:
    ctx = build_context(project_id)
    context_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    with db() as cur:
        cur.execute(
            "INSERT INTO agent_messages(session_id, role, content, context_json, created_at) VALUES (%s, 'user', %s, %s, %s)",
            (session_id, user_message, context_json, utc_now()),
        )

    tool_calls_log = []

    if settings.get("agent_mode") == "llm" and settings.get("llm_endpoint") and settings.get("llm_api_key"):
        try:
            from app.core.database import fetch_all
            history = fetch_all(
                "SELECT role, content FROM agent_messages WHERE session_id = %s AND id < (SELECT MAX(id) FROM agent_messages WHERE session_id = %s) ORDER BY id ASC",
                (session_id, session_id),
            ) or []
            response, tool_calls_log = _call_llm_with_tools(settings, context_json, user_message, history[-20:])
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print(f"[Agent] LLM 调用失败，回退规则模式: {e}")
            print(f"[Agent] 详细: {err_detail[:500]}")
            response = _rule_response(ctx, user_message)
            response = f"⚠️ LLM 调用失败（{str(e)[:100]}），以下为本地规则分析：\n\n{response}"
    else:
        response = _rule_response(ctx, user_message)

    plan = _extract_plan(response)

    with db() as cur:
        cur.execute(
            "INSERT INTO agent_messages(session_id, role, content, context_json, created_at) VALUES (%s, 'agent', %s, %s, %s)",
            (session_id, response, context_json, utc_now()),
        )

    result = {"role": "agent", "content": response}
    if plan:
        result["plan"] = plan
    if tool_calls_log:
        result["tool_calls"] = tool_calls_log

    # 自动生成标题
    session = fetch_one("SELECT title FROM agent_sessions WHERE id = %s", (session_id,))
    title = (session or {}).get("title", "")
    if not title or title.startswith("新会话") or title.startswith("会话 "):
        generated = _generate_title(user_message, settings)
        if generated:
            with db() as cur:
                cur.execute("UPDATE agent_sessions SET title = %s WHERE id = %s", (generated, session_id))
            result["title"] = generated

    return result


def _call_llm_with_tools(settings: dict, context_json: str, user_message: str, history: list[dict]) -> tuple[str, list]:
    """带工具调用的 LLM 循环。最多 5 轮。返回 (最终回复, 工具调用日志)。"""
    import urllib.request

    endpoint = settings["llm_endpoint"].rstrip("/") + "/chat/completions"
    model = settings.get("llm_model", "deepseek-chat")

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context_json=context_json)}]
    for msg in history:
        role = "assistant" if msg["role"] == "agent" else "user"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    tool_calls_log = []

    for _round in range(5):
        body = json.dumps({
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "temperature": 0.4,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {settings['llm_api_key']}")

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        choice = data["choices"][0]
        msg = choice["message"]

        # 有 tool_calls → 执行并继续循环
        if msg.get("tool_calls"):
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg["tool_calls"]})

            for tc in msg["tool_calls"]:
                func = tc["function"]
                tool_name = func["name"]
                try:
                    tool_args = json.loads(func["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                result = execute_tool(tool_name, tool_args)
                tool_calls_log.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result_preview": result[:300],
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            continue  # 继续下一轮

        # 没有 tool_calls → 最终回复
        return msg.get("content", ""), tool_calls_log

    return "分析超时，请重试。", tool_calls_log


def _call_llm(settings: dict, context_json: str, user_message: str, history: list[dict] | None = None) -> str:
    import urllib.request

    endpoint = settings["llm_endpoint"].rstrip("/") + "/chat/completions"
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context_json=context_json)}]
    if history:
        for msg in history:
            messages.append({"role": "assistant" if msg["role"] == "agent" else "user", "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    body = json.dumps(
        {
            "model": settings.get("llm_model", "deepseek-chat"),
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 2000,
        }
    ).encode("utf-8")

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {settings['llm_api_key']}")

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════════════════
# 规则分析引擎 — 对项目上下文做实际计算，而非关键词匹配
# ═══════════════════════════════════════════════════════════════════════════

def _rule_response(ctx: dict, user_message: str) -> str:
    """基于项目上下文的实际数据做计算分析。"""
    latest_run = ctx.get("latest_run")
    latest_eval = ctx.get("latest_evaluation")
    latest_model = ctx.get("latest_model")
    versions = ctx.get("versions", [])
    runs = ctx.get("runs", [])
    evals = ctx.get("evaluations", [])
    models = ctx.get("models", [])
    msg = user_message.lower()

    # ── 过拟合分析 ──
    if any(w in msg for w in ["过拟合", "overfit", "泛化"]):
        return _analyze_overfitting(latest_run, latest_eval, runs)

    # ── 训练参数/指标 ──
    if any(w in msg for w in ["训练", "参数", "调参", "超参"]):
        return _analyze_training(latest_run, runs)

    # ── 评估/测试 ──
    if any(w in msg for w in ["测试", "评估", "test", "预测"]):
        return _analyze_evaluation(latest_eval, latest_run, evals)

    # ── 数据集/标注质量 ──
    if any(w in msg for w in ["数据", "标注", "数据集", "质量", "分布", "均衡"]):
        return _analyze_dataset_quality(versions)

    # ── 模型导出/部署 ──
    if any(w in msg for w in ["导出", "模型", "部署", "best.pt", "上线"]):
        return _analyze_deployment(latest_model, latest_eval, models, evals)

    # ── 对比 ──
    if any(w in msg for w in ["对比", "比较", "diff", "变化", "趋势"]):
        return _compare_runs(runs, evals)

    # ── 改进建议 ──
    if any(w in msg for w in ["改进", "建议", "优化", "下一步", "提升", "推荐"]):
        return _suggest_next_steps(latest_run, latest_eval, versions)

    # ── 兜底：综合摘要 ──
    return _summary(ctx)


# ═══════════════════════════════════════════════════════════════════════════
# 专项分析函数
# ═══════════════════════════════════════════════════════════════════════════

def _analyze_overfitting(latest_run, latest_eval, runs) -> str:
    """诊断过拟合：对比训练 vs 评估指标、检查 mAP 收敛性。"""
    if not latest_run:
        return "当前项目还没有训练记录，先完成一次正式训练。"

    lines = [f"## 过拟合分析\n"]
    lines.append(f"**训练** `{latest_run['run_id']}`: P={_fmt(latest_run.get('precision'))}, R={_fmt(latest_run.get('recall'))}, mAP50={_fmt(latest_run.get('map50'))}, mAP50-95={_fmt(latest_run.get('map50_95'))}")

    p = latest_run.get("precision")
    r = latest_run.get("recall")
    m = latest_run.get("map50_95")

    # 1. P-R 差异分析
    if p is not None and r is not None:
        diff = p - r
        if diff > 0.15:
            lines.append(f"\n⚠️ **Precision ({p:.3f}) 比 Recall ({r:.3f}) 高 {diff:.2f}**")
            lines.append("模型预测保守，漏检多。可能原因：少数类样本不足、标注漏标、conf 阈值偏高。")
            lines.append("- 建议：补充少数类样本 20-50 张 → 降低 conf 到 0.25 → 重新评估")
        elif diff < -0.15:
            lines.append(f"\n⚠️ **Recall ({r:.3f}) 比 Precision ({p:.3f}) 高 {-diff:.2f}**")
            lines.append("模型误检多。可能原因：负样本不足、类别边界模糊、conf 阈值偏低。")
            lines.append("- 建议：补充易混淆负样本 → 提高 conf 到 0.5 → 检查类别标注一致性")
        else:
            lines.append(f"\n✅ P-R 差距 {abs(diff):.2f}，在合理范围内 (±0.15)")

    # 2. mAP 绝对值判断
    if m is not None:
        if m < 0.2:
            lines.append(f"\n❌ mAP50-95={m:.3f} 极低，模型几乎没有有效学习。")
            lines.append("根本原因通常是：数据量 < 100 张、标注大量错误、或类别定义不合理。")
        elif m < 0.4:
            lines.append(f"\n⚠️ mAP50-95={m:.3f} 偏低，可能欠拟合或数据质量差。")
            lines.append("建议检查：标注审计报告 → 补数据至 200+ 张 → epochs 提升到 150+")
        elif m < 0.6:
            lines.append(f"\n📈 mAP50-95={m:.3f} 中等，数据或模型容量可能饱和。")
        else:
            lines.append(f"\n✅ mAP50-95={m:.3f} 良好。")

    # 3. 训练 vs 评估对比（核心过拟合判断）
    if latest_eval and latest_eval.get("map50_95") is not None:
        eval_m = latest_eval.get("map50_95")
        eval_p = latest_eval.get("precision")
        eval_r = latest_eval.get("recall")
        if m is not None:
            gap = m - eval_m
            lines.append(f"\n### 训练 vs 评估对比")
            lines.append(f"训练 mAP50-95: {m:.3f}  →  评估 mAP50-95: {eval_m:.3f}  (差距 {gap:+.3f})")
            if gap > 0.05:
                lines.append(f"⚠️ **存在过拟合** — 训练指标显著高于评估指标 ({gap:.3f})")
                lines.append("建议：增加数据增强强度 → 补充验证集多样性 → 考虑减小模型或加 dropout")
            elif gap > 0.02:
                lines.append(f"⚡ 轻微过拟合迹象 ({gap:.3f})，可接受但需关注。")
            else:
                lines.append(f"✅ 泛化良好，训练和评估指标一致。")
    else:
        lines.append(f"\n💡 当前没有独立评估记录，无法判断过拟合。建议用 test 集跑一次评估。")

    # 4. 多轮训练趋势
    if len(runs) >= 2:
        first, last = runs[-1], runs[0]
        fm = first.get("map50_95")
        lm = last.get("map50_95")
        if fm is not None and lm is not None:
            delta = lm - fm
            lines.append(f"\n### 训练趋势（{len(runs)} 轮）")
            lines.append(f"最早 mAP50-95: {fm:.3f} → 最新: {lm:.3f}  ({delta:+.3f})")
            if delta < 0.01 and len(runs) >= 3:
                lines.append("⚠️ 多轮训练无明显提升，数据或方法已到瓶颈。建议换模型架构或重构数据集。")
            elif delta > 0:
                lines.append(f"📈 持续改进中，每轮平均提升约 {delta/len(runs):.3f}。")

    return "\n".join(lines)


def _analyze_training(latest_run, runs) -> str:
    """分析训练参数和指标。"""
    if not latest_run:
        return "当前项目还没有训练记录。"

    run = latest_run
    lines = [f"## 训练分析: `{run['run_id']}`\n"]
    lines.append(f"| 参数 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 基础模型 | `{run.get('base_model', '-')}` |")
    lines.append(f"| Epochs | {run.get('epochs', '-')} |")
    lines.append(f"| Image Size | {run.get('imgsz', '-')} |")
    lines.append(f"| Batch | {run.get('batch', '-')} |")
    lines.append(f"| 状态 | {run.get('status', '-')} |")
    lines.append(f"| Precision | {_fmt(run.get('precision'))} |")
    lines.append(f"| Recall | {_fmt(run.get('recall'))} |")
    lines.append(f"| mAP50 | {_fmt(run.get('map50'))} |")
    lines.append(f"| mAP50-95 | {_fmt(run.get('map50_95'))} |")

    p, r = run.get("precision"), run.get("recall")
    if p is not None and r is not None:
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
        lines.append(f"| F1 Score | {f1:.3f} |")

    lines.append(f"\n### 参数建议")
    m = run.get("map50_95")
    if m is not None and m < 0.3 and run.get("epochs", 100) < 200:
        lines.append(f"- 当前 epochs={run.get('epochs')}，mAP 偏低，建议增加到 200-300")
    if run.get("batch", 16) > 8:
        lines.append(f"- 当前 batch={run.get('batch')}，如果 OOM 可降到 8")
    lines.append(f"- 如果小目标检测差，考虑 imgsz 从 {run.get('imgsz', 640)} 提升到 960 或 1280")

    if len(runs) >= 2:
        prev = runs[1]
        pm = prev.get("map50_95")
        cm = run.get("map50_95")
        if pm is not None and cm is not None:
            lines.append(f"\n相比上一轮 `{prev.get('run_id', '-')}`: mAP50-95 {pm:.3f} → {cm:.3f} ({cm-pm:+.3f})")

    return "\n".join(lines)


def _analyze_evaluation(latest_eval, latest_run, evals) -> str:
    """分析评估/测试结果，重点是对比训练指标判断泛化。"""
    if not latest_eval:
        return "当前项目还没有评估记录。建议用 best.pt 对 test 集跑一次评估。"

    e = latest_eval
    lines = [f"## 评估分析: `{e['run_id']}`\n"]
    lines.append(f"| 指标 | 评估值 | 训练值 | 差距 |")
    lines.append(f"|------|--------|--------|------|")

    def _diff_row(label, eval_key, run_key=None):
        ev = e.get(eval_key)
        rv = latest_run.get(run_key or eval_key) if latest_run else None
        if ev is not None:
            diff = f"{ev - rv:+.3f}" if rv is not None else "-"
            rv_str = _fmt(rv)
            lines.append(f"| {label} | {ev:.3f} | {rv_str} | {diff} |")

    _diff_row("Precision", "precision")
    _diff_row("Recall", "recall")
    _diff_row("mAP50", "map50")
    _diff_row("mAP50-95", "map50_95")

    # 过拟合判断
    em = e.get("map50_95")
    tm = latest_run.get("map50_95") if latest_run else None
    if em is not None and tm is not None:
        gap = tm - em
        lines.append(f"\n### 泛化诊断")
        if gap > 0.05:
            lines.append(f"⚠️ 训练 mAP ({tm:.3f}) > 评估 mAP ({em:.3f})，差距 {gap:.3f} — **存在过拟合**")
        elif gap < -0.02:
            lines.append(f"🤔 评估 mAP ({em:.3f}) > 训练 mAP ({tm:.3f}) — 评估集可能比训练集简单，或训练未充分收敛")
        else:
            lines.append(f"✅ 泛化良好 (差距 {gap:+.3f})")

    # 逐图分析摘要
    samples = e.get("samples", [])
    if samples:
        empty_count = sum(1 for s in samples if "0 个" in str(s.get("confidence_summary", "")))
        lines.append(f"\n### 预测质量")
        lines.append(f"- 样本总数: {len(samples)}")
        if empty_count > 0:
            lines.append(f"- ⚠️ {empty_count}/{len(samples)} 张无预测框 ({empty_count/len(samples)*100:.0f}%) — 检查漏检模式")

    # 历史评估趋势
    if len(evals) >= 2:
        prev_e = evals[1]
        pem = prev_e.get("map50_95")
        if em is not None and pem is not None:
            lines.append(f"\n相比上次评估 `{prev_e.get('run_id', '-')}`: mAP50-95 {pem:.3f} → {em:.3f} ({em-pem:+.3f})")

    return "\n".join(lines)


def _analyze_dataset_quality(versions) -> str:
    """分析数据集标注质量和类别分布。"""
    if not versions:
        return "当前项目还没有导入数据集。"

    lines = ["## 数据集质量分析\n"]

    for v in versions[:5]:  # 最多分析 5 个版本
        lines.append(f"### {v.get('dataset_name', '')} / {v.get('version', '')}")
        lines.append(f"- 图片数: {v.get('image_count', 0)} | 类别数: {v.get('class_count', 0)}")

        # 标注进度
        pending = v.get("pending_count", 0)
        reviewed = v.get("reviewed_count", 0)
        total = pending + reviewed
        if total > 0:
            pct = reviewed / total * 100
            lines.append(f"- 标注进度: {reviewed}/{total} ({pct:.0f}%)")
            if pending > 0:
                lines.append(f"  ⚠️ 还有 {pending} 张未标注，建议完成标注后再训练")

        # 审计数据
        audit = v.get("audit", {})
        issues = []
        if audit.get("missing_labels", 0) > 0:
            issues.append(f"{audit['missing_labels']} 张缺标签")
        if audit.get("orphan_labels", 0) > 0:
            issues.append(f"{audit['orphan_labels']} 个孤儿标签")
        if audit.get("invalid_bboxes", 0) > 0:
            issues.append(f"{audit['invalid_bboxes']} 个异常 bbox")
        if audit.get("empty_labels", 0) > 0:
            issues.append(f"{audit['empty_labels']} 个空标签")

        if issues:
            lines.append(f"- ⚠️ 质量问题: {', '.join(issues)}")
        else:
            lines.append(f"- ✅ 未发现标注质量问题")

        # 类别均衡性
        if v.get("class_count", 0) < 3:
            lines.append(f"- 类别数较少 ({v.get('class_count')})，训练收敛通常较快")

    # 全局建议
    lines.append(f"\n### 数据策略建议")
    total_images = sum(v.get("image_count", 0) for v in versions)
    if total_images < 200:
        lines.append(f"- ⚠️ 总图片数 {total_images} < 200，建议补充到 300+ 以获得稳定收敛")
    elif total_images < 500:
        lines.append(f"- 总图片数 {total_images}，对于 {versions[0].get('class_count', 0)} 类目标检测基本够用")
    else:
        lines.append(f"- 总图片数 {total_images}，数据量充足")
    lines.append(f"- 确保有独立 test 集（不与 train 重叠）做最终评估")
    lines.append(f"- 建议定期运行标注审计（`POST /api/dataset-versions/{versions[0].get('id', '')}/audit`）")

    return "\n".join(lines)


def _analyze_deployment(latest_model, latest_eval, models, evals) -> str:
    """评估模型部署就绪度。"""
    if not latest_model:
        return "当前还没有模型记录。先完成一次训练，训练完成会自动注册模型。"

    m = latest_model
    lines = [f"## 模型部署分析: `{m.get('run_id', '-')}`\n"]

    m5095 = m.get("map50_95")
    p = m.get("precision")
    r = m.get("recall")

    lines.append(f"| 指标 | 值 | 状态 |")
    lines.append(f"|------|-----|------|")

    def _status(val, good, ok):
        if val is None: return "-", "-"
        if val >= good: return f"{val:.3f}", "✅"
        if val >= ok: return f"{val:.3f}", "⚠️"
        return f"{val:.3f}", "❌"

    for label, val, good, ok in [
        ("mAP50-95", m5095, 0.5, 0.3),
        ("Precision", p, 0.7, 0.5),
        ("Recall", r, 0.7, 0.5),
    ]:
        v, s = _status(val, good, ok)
        lines.append(f"| {label} | {v} | {s} |")

    # 部署评分
    score = 0
    if m5095 is not None:
        score += min(m5095 / 0.6 * 50, 50)  # mAP 占 50 分
    if p is not None and r is not None:
        balance = 1 - abs(p - r)  # P-R 平衡性
        score += balance * 20
    if latest_eval and latest_eval.get("status") == "completed":
        score += 15  # 已完成独立评估
    if m.get("is_production"):
        score += 10  # 已标记为生产

    lines.append(f"\n### 部署评分: {score:.0f}/100")
    if score >= 80:
        lines.append("✅ **建议部署** — 指标优秀，已完成独立评估")
        lines.append("下一步：导出 ONNX → 集成到推理服务 → 监控线上指标")
    elif score >= 50:
        lines.append("⚠️ **条件部署** — 可在特定场景试用，需人工复核")
        lines.append("建议：先用 test 集做一次独立评估 → 确认 P-R 平衡 → 导出 ONNX")
    else:
        lines.append("❌ **不建议部署** — 模型性能不满足生产要求")
        lines.append("建议：改进数据质量 → 增加训练轮数 → 换更大模型 → 重新评估")

    # 评估记录
    if latest_eval:
        lines.append(f"\n最近评估: `{latest_eval.get('run_id', '-')}` mAP50-95={_fmt(latest_eval.get('map50_95'))}")
    else:
        lines.append(f"\n⚠️ 还没有独立评估记录，部署前必须完成。")

    return "\n".join(lines)


def _compare_runs(runs, evals) -> str:
    """对比最近两次训练/评估。"""
    lines = ["## 训练对比\n"]
    if len(runs) < 2:
        lines.append("需要至少 2 次训练记录才能对比。")
    else:
        lines.append("| 指标 | 最新 | 上次 | 变化 |")
        lines.append("|------|------|------|------|")
        a, b = runs[0], runs[1]
        for key, label in [("precision", "Precision"), ("recall", "Recall"),
                           ("map50", "mAP50"), ("map50_95", "mAP50-95")]:
            av, bv = a.get(key), b.get(key)
            if av is not None and bv is not None:
                delta = av - bv
                arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                lines.append(f"| {label} | {av:.3f} | {bv:.3f} | {arrow} {delta:+.3f} |")

    # 评估对比
    if len(evals) >= 2:
        lines.append(f"\n## 评估对比\n")
        lines.append("| 指标 | 最新 | 上次 | 变化 |")
        lines.append("|------|------|------|------|")
        a, b = evals[0], evals[1]
        for key, label in [("precision", "Precision"), ("recall", "Recall"),
                           ("map50", "mAP50"), ("map50_95", "mAP50-95")]:
            av, bv = a.get(key), b.get(key)
            if av is not None and bv is not None:
                delta = av - bv
                arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                lines.append(f"| {label} | {av:.3f} | {bv:.3f} | {arrow} {delta:+.3f} |")

    lines.append(f"\n💡 详细对比可查看 `results.png` 和 `PR_curve.png`。")
    return "\n".join(lines)


def _suggest_next_steps(latest_run, latest_eval, versions) -> str:
    """综合所有信息给出改进建议。"""
    lines = ["## 改进建议\n"]
    items = []

    # 数据维度
    if versions:
        v = versions[0]
        if v.get("image_count", 0) < 200:
            items.append(("🔴 数据", f"图片仅 {v.get('image_count')} 张，优先补充到 300+。每类至少 50 张。"))
        audit = v.get("audit", {})
        if audit.get("missing_labels", 0) + audit.get("invalid_bboxes", 0) + audit.get("orphan_labels", 0) > 0:
            items.append(("🟡 标注", "存在标注质量问题，建议运行审计并修复异常标签。"))

    # 训练维度
    if latest_run:
        m = latest_run.get("map50_95")
        if m is not None and m < 0.3:
            items.append(("🔴 训练", f"mAP50-95={m:.3f} 偏低。尝试: epochs×2, 更大模型 (m/l), 强数据增强。"))
        elif m is not None and m < 0.5:
            items.append(("🟡 训练", f"mAP50-95={m:.3f} 中等。尝试特定类别数据增强或 mosaic/mixup。"))

    # 评估维度
    if latest_eval and latest_run:
        eg = latest_run.get("map50_95", 0) - latest_eval.get("map50_95", 0)
        if eg > 0.05:
            items.append(("🔴 泛化", "存在过拟合。增加数据增强、补充验证集多样性、考虑 early stopping。"))

    if not items:
        items.append(("✅ 综合", "当前状态良好。建议定期用新数据做回归测试，保持模型持续改进。"))

    for tag, text in items:
        lines.append(f"- **{tag}**: {text}")

    lines.append(f"\n### 执行顺序")
    lines.append(f"1. 先修数据 → 2. 再调训练 → 3. 独立评估 → 4. 模型部署")

    return "\n".join(lines)


def _summary(ctx) -> str:
    """项目综合摘要。"""
    lines = ["## 项目状态摘要\n"]

    # 数据集
    versions = ctx.get("versions", [])
    if versions:
        total_img = sum(v.get("image_count", 0) for v in versions)
        lines.append(f"**数据集**: {len(versions)} 个版本, 共 {total_img} 张图片")
        v0 = versions[0]
        lines.append(f"  最新: `{v0.get('dataset_name', '')}/{v0.get('version', '')}` — {v0.get('image_count', 0)} 张, {v0.get('class_count', 0)} 类")
    else:
        lines.append("**数据集**: 无")

    # 训练
    runs = ctx.get("runs", [])
    if runs:
        r0 = runs[0]
        lines.append(f"**训练**: {len(runs)} 次, 最新 `{r0.get('run_id', '-')}` — mAP50-95={_fmt(r0.get('map50_95'))} ({r0.get('status', '-')})")
    else:
        lines.append("**训练**: 无")

    # 评估
    evals = ctx.get("evaluations", [])
    if evals:
        e0 = evals[0]
        lines.append(f"**评估**: {len(evals)} 次, 最新 `{e0.get('run_id', '-')}` — mAP50-95={_fmt(e0.get('map50_95'))}")
    else:
        lines.append("**评估**: 无 — 建议用 test 集完成首次评估")

    # 模型
    models = ctx.get("models", [])
    if models:
        prod = [m for m in models if m.get("is_production")]
        lines.append(f"**模型**: {len(models)} 个, 生产标记: {len(prod)} 个")
    else:
        lines.append("**模型**: 无")

    lines.append(f"\n直接问我：过拟合判断 | 训练分析 | 评估分析 | 数据质量 | 部署建议 | 改进建议 | 对比分析")
    return "\n".join(lines)


def _extract_plan(text: str) -> dict | None:
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except Exception:
        return str(value)


# ═══════════════════════════════════════════════════════════════════════════
# 流式输出
# ═══════════════════════════════════════════════════════════════════════════

async def chat_stream(session_id: int, user_message: str, settings: dict, project_id: int | None = None):
    """
    流式生成 Agent 回复。

    Yields: {"chunk": str} | {"plan": dict} | {"title": str} | {"done": true}
    """
    ctx = build_context(project_id)
    context_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    with db() as cur:
        cur.execute(
            "INSERT INTO agent_messages(session_id, role, content, context_json, created_at) VALUES (%s, 'user', %s, %s, %s)",
            (session_id, user_message, context_json, utc_now()),
        )

    full_response = ""

    tool_calls_log = []

    if settings.get("agent_mode") == "llm" and settings.get("llm_endpoint") and settings.get("llm_api_key"):
        try:
            from app.core.database import fetch_all
            history = fetch_all(
                "SELECT role, content FROM agent_messages WHERE session_id = %s AND id < (SELECT MAX(id) FROM agent_messages WHERE session_id = %s) ORDER BY id ASC",
                (session_id, session_id),
            ) or []
            # 先用非流式 Tool Use 获取结果，再流式输出最终回复
            final_response, tool_calls_log = _call_llm_with_tools(settings, context_json, user_message, history[-20:])
            # Yield tool calls as events for frontend to show
            for tc in tool_calls_log:
                yield {"tool_call": tc}
            # Simulate streaming for final response
            for chunk in _chunk_text(final_response):
                full_response += chunk
                yield {"chunk": chunk}
        except Exception:
            pass

    # LLM 失败或无 LLM → 规则模式（模拟流式）
    if not full_response:
        full_response = _rule_response(ctx, user_message)
        # 按段落分块模拟流式
        paragraphs = full_response.split("\n\n")
        for i, para in enumerate(paragraphs):
            chunk = para + ("\n\n" if i < len(paragraphs) - 1 else "")
            yield {"chunk": chunk}
            await asyncio.sleep(0.05)

    # 保存完整回复
    plan = _extract_plan(full_response)
    with db() as cur:
        cur.execute(
            "INSERT INTO agent_messages(session_id, role, content, context_json, created_at) VALUES (%s, 'agent', %s, %s, %s)",
            (session_id, full_response, context_json, utc_now()),
        )

    if plan:
        yield {"plan": plan}

    # 如果会话还没有标题，自动生成
    session = None
    with db() as cur:
        cur.execute("SELECT title FROM agent_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
    if row:
        session = dict(row) if hasattr(row, 'keys') else None
        title = (session or {}).get("title", "")

    if not title or title.startswith("新会话") or title.startswith("会话 "):
        generated_title = _generate_title(user_message, settings)
        if generated_title:
            with db() as cur:
                cur.execute("UPDATE agent_sessions SET title = %s WHERE id = %s", (generated_title, session_id))
            yield {"title": generated_title}

    yield {"done": True}


async def _call_llm_stream(settings: dict, context_json: str, user_message: str, history: list[dict] | None = None):
    """流式调用 LLM API，yield 每个 token 片段。"""
    import urllib.request

    endpoint = settings["llm_endpoint"].rstrip("/") + "/chat/completions"
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context_json=context_json)}]
    if history:
        for msg in history:
            messages.append({"role": "assistant" if msg["role"] == "agent" else "user", "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    body = json.dumps({
        "model": settings.get("llm_model", "deepseek-chat"),
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 2000,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {settings['llm_api_key']}")

    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            line = line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue


def _chunk_text(text: str, size: int = 8):
    """将文本按字符块 yield（模拟流式）。"""
    for i in range(0, len(text), size):
        yield text[i:i+size]


TITLE_PROMPT = """根据用户的提问内容，生成一个简短的会话标题（不超过 15 个字）。
标题应该概括用户想了解的核心问题，不要包含"分析"、"请"等冗余词。
只返回标题文本，不要引号、不要解释。

用户提问: {user_message}
标题:"""


def _generate_title(user_message: str, settings: dict) -> str:
    """从用户消息生成会话标题。LLM 模式用 AI 总结，规则模式用智能截断。"""
    # LLM 模式：调 API 生成标题
    if settings.get("agent_mode") == "llm" and settings.get("llm_endpoint") and settings.get("llm_api_key"):
        try:
            import urllib.request
            endpoint = settings["llm_endpoint"].rstrip("/") + "/chat/completions"
            body = json.dumps({
                "model": settings.get("llm_model", "deepseek-chat"),
                "messages": [{"role": "user", "content": TITLE_PROMPT.format(user_message=user_message)}],
                "temperature": 0.3,
                "max_tokens": 30,
            }).encode("utf-8")
            req = urllib.request.Request(endpoint, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {settings['llm_api_key']}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                title = data["choices"][0]["message"]["content"].strip().strip('"').strip("'").strip("。")
                if title and len(title) <= 25:
                    return title
        except Exception:
            pass  # LLM 失败 → 回退规则

    # 规则模式：智能截断
    clean = user_message.strip()
    for prefix in ["请帮我", "请", "帮我", "能不能", "可以", "如何", "怎么"]:
        if clean.startswith(prefix) and len(clean) > len(prefix) + 3:
            clean = clean[len(prefix):]
            break

    if len(clean) > 25:
        for sep in ["？", "?", "，", ",", "。", ".", "！", "!", "的"]:
            idx = clean[:25].rfind(sep)
            if idx > 8:
                return clean[:idx].strip()
        return clean[:22] + "…"
    return clean.strip() or "新对话"
