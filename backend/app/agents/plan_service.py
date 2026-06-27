"""
迭代计划 CRUD 服务

本模块提供迭代计划（iteration plan）的增删改查（CRUD）功能。
迭代计划是由 AI 智能体生成的行动计划，可被保存、查询、执行（应用）
并更新其状态。计划的最终目的是用于填充前端表单或驱动后续的训练/标注流程。

函数概览:
    save_plan          — 创建并保存一条新计划
    list_plans         — 按状态筛选列出所有计划
    get_plan           — 根据 ID 获取单条计划
    apply_plan         — 执行计划（标记为已执行），并解析其结构化参数
    update_plan_status — 更新计划的当前状态
"""
import json

from app.core.database import db, fetch_all, fetch_one, utc_now


def save_plan(
    session_id: int | None,
    plan_type: str,
    title: str,
    content: dict | str,
    project_id: int | None = None,
    dataset_version_id: int | None = None,
    training_run_id: int | None = None,
) -> dict:
    """
    保存一条新的迭代计划到数据库。

    如果 content 为字典类型，会自动序列化为 JSON 字符串后再写入。
    返回包含完整记录（含自增 ID、默认状态 'draft' 及时间戳）的字典。

    参数:
        session_id: 关联的会话 ID，可为 None
        plan_type: 计划类型（如 'train', 'annotate', 'dataset' 等）
        title: 计划的标题
        content: 计划内容，可以是字典或 JSON 字符串
        dataset_version_id: 关联的数据集版本 ID，可选
        training_run_id: 关联的训练运行 ID，可选

    返回:
        包含完整计划记录的字典
    """
    # 如果 content 是字典，则序列化为 JSON 字符串，确保数据库可存储
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    # 获取当前 UTC 时间戳作为记录的创建时间
    now = utc_now()
    with db() as cur:
        # 插入新计划记录，状态默认为 'draft'
        cur.execute(
            """INSERT INTO iteration_plans(project_id, session_id, dataset_version_id, training_run_id, plan_type, title, content, status, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s) RETURNING *""",
            (project_id, session_id, dataset_version_id, training_run_id, plan_type, title, content, now),
        )
        return dict(cur.fetchone())


def list_plans(status: str = "") -> list[dict]:
    """
    查询迭代计划列表。

    如果指定了 status 参数，则只返回状态匹配的计划；
    否则返回所有计划，并按 ID 降序排列（最新的在前）。

    参数:
        status: 状态筛选条件（如 'draft', 'executed' 等），为空字符串时不筛选

    返回:
        计划字典对象的列表
    """
    if status:
        # 按指定状态筛选，并按 ID 降序排列（最新的在前）
        return fetch_all("SELECT * FROM iteration_plans WHERE status = %s ORDER BY id DESC", (status,))
    # 无状态筛选时，返回所有计划，按 ID 降序排列
    return fetch_all("SELECT * FROM iteration_plans ORDER BY id DESC")


def get_plan(plan_id: int) -> dict | None:
    """
    根据主键 ID 获取单条迭代计划。

    参数:
        plan_id: 计划的 ID

    返回:
        计划字典，如果不存在则返回 None
    """
    return fetch_one("SELECT * FROM iteration_plans WHERE id = %s", (plan_id,))


def apply_plan(plan_id: int) -> dict:
    """
    执行（应用）一条迭代计划。

    该函数将计划状态更新为 'executed'，同时解析 content 字段中的
    结构化参数，返回 {plan, params} 格式的数据供前端表单预填充使用。
    如果 content 不是合法的 JSON，则将原始字符串包裹在 {'raw': ...} 中返回。

    参数:
        plan_id: 要执行的计划 ID

    返回:
        包含 'plan'（完整计划记录）和 'params'（解析后的参数字典）的字典

    抛出:
        ValueError: 当 plan_id 对应的计划不存在时
    """
    # 先查询计划是否存在，不存在则直接抛异常
    plan = fetch_one("SELECT * FROM iteration_plans WHERE id = %s", (plan_id,))
    if not plan:
        raise ValueError(f"plan not found: {plan_id}")

    # 解析 content 字段为结构化的参数字典，用于前端表单回填
    parsed = {}
    try:
        parsed = json.loads(plan["content"])
    except (json.JSONDecodeError, TypeError):
        # 如果 content 不是合法 JSON，则以原始字符串形式包裹在 raw 键下返回
        parsed = {"raw": plan["content"]}

    # 将计划状态更新为 'executed'（已执行）
    with db() as cur:
        cur.execute(
            "UPDATE iteration_plans SET status = 'executed' WHERE id = %s", (plan_id,)
        )

    # 返回计划记录及解析后的参数，供前端使用
    return {"plan": dict(plan), "params": parsed}


def update_plan_status(plan_id: int, status: str) -> dict:
    """
    更新一条迭代计划的状态。

    状态包括 'draft'（草稿）、'executed'（已执行）、'archived'（已归档）、'deleted'（已删除）。

    参数:
        plan_id: 要更新状态的计划 ID
        status: 新的状态值

    返回:
        更新后的完整计划记录字典

    抛出:
        ValueError: 当 plan_id 对应的计划不存在时
    """
    with db() as cur:
        cur.execute("UPDATE iteration_plans SET status = %s WHERE id = %s", (status, plan_id))
        row = cur.execute("SELECT * FROM iteration_plans WHERE id = %s", (plan_id,)).fetchone()
        if not row:
            raise ValueError(f"plan not found: {plan_id}")
        return dict(row)


def mark_plan_read(plan_id: int) -> dict:
    """标记计划为已读"""
    with db() as cur:
        cur.execute("UPDATE iteration_plans SET is_read = 1 WHERE id = %s", (plan_id,))
        row = cur.execute("SELECT * FROM iteration_plans WHERE id = %s", (plan_id,)).fetchone()
        if not row:
            raise ValueError(f"plan not found: {plan_id}")
        return dict(row)
