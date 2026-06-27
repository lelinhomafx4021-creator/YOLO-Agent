"""
模型注册模块

该模块负责模型版本的生命周期管理，主要提供模型提升（promote）功能：
将指定模型版本从候选状态提升为生产状态，或仅标记为候选版本。
所有操作均通过数据库事务完成，确保数据一致性。

依赖:
    - app.core.database: 数据库连接管理模块，提供数据库会话上下文管理器
"""

from app.core.database import db


def promote_model(model_id: int, production: bool = False) -> dict:
    """
    提升指定模型版本的状态。

    将模型版本标记为候选（candidate）版本，并可选择同时标记为生产（production）版本。
    当提升为生产版本时，会自动将同一数据集（dataset_name）下的其他生产版本取消标记，
    确保每个数据集在同一时刻有且只有一个生产版本。这是一种"最多一个"的互斥策略。

    函数执行流程：
        1. 通过上下文管理器获取数据库连接，自动处理事务提交和回滚
        2. 如果 production=True，先查询目标模型是否存在，不存在则抛出异常
        3. 将同一数据集下所有现有生产版本标记为 is_production=0
        4. 将目标模型标记为 is_candidate=1 和/或 is_production=1
        5. 查询并返回更新后的完整行数据

    Args:
        model_id (int): 模型版本在数据库 model_versions 表中的唯一标识 ID。
        production (bool): 是否同时提升为生产版本。
                           - True: 同时标记为候选版本和生产版本
                           - False (默认): 仅标记为候选版本，不修改生产状态

    Returns:
        dict: 更新后模型版本的完整行数据，以字典形式返回，键名与 model_versions
              表列名一一对应（如 id, dataset_name, version, is_candidate, is_production 等）。

    Raises:
        ValueError: 当 model_id 对应的模型版本在数据库中不存在时抛出。
                    异常信息格式为 "model not found: {model_id}"。

    示例:
        # 仅标记为候选版本
        result = promote_model(42)

        # 标记为候选版本并同时提升为生产版本
        result = promote_model(42, production=True)
    """
    # 使用上下文管理器 'with db() as conn' 获取数据库连接
    # db() 返回的上下文管理器自动在成功时提交事务，在异常时回滚事务，
    # 确保数据一致性；无需手动调用 conn.commit() 或 conn.rollback()
    with db() as cur:
        if production:
            # --- 生产提升分支 ---
            # 第一步：验证目标模型版本存在
            # 使用参数化查询 (? 占位符) 防止 SQL 注入攻击
            model = cur.execute(
                "SELECT * FROM model_versions WHERE id = %s", (model_id,)
            ).fetchone()
            if not model:
                # 模型不存在时抛出 ValueError，由上层调用方决定如何处理
                raise ValueError(f"model not found: {model_id}")

            # 第二步：取消同一数据集下所有现有生产版本的标记
            # 策略说明：一个数据集（dataset_name）下只能有一个生产版本，
            # 因此在设置新的生产版本之前，需要先清除该数据集下所有旧的生产标记。
            # 这是通过 UPDATE 语句将 is_production 统一置为 0 来实现的，
            # 无论之前有多少个生产版本都会被清除。
            cur.execute(
                "UPDATE model_versions SET is_production = 0 WHERE project_id = %s",
                (model["project_id"],),
            )

            # 第三步：将目标模型同时标记为候选版本和生产版本
            # 使用 SET is_candidate = 1, is_production = 1 同时更新两个状态位
            cur.execute(
                "UPDATE model_versions SET is_candidate = 1, is_production = 1 WHERE id = %s",
                (model_id,),
            )
        else:
            # --- 非生产提升分支（仅候选）---
            # 仅将模型标记为候选版本，不涉及任何生产版本的修改
            # 这不会影响同一数据集下现有的生产版本
            cur.execute(
                "UPDATE model_versions SET is_candidate = 1 WHERE id = %s", (model_id,)
            )

        # --- 通用收尾：返回更新后的数据 ---
        # 重新查询数据库，获取 update 操作后该行的最新完整数据
        # 使用 dict() 将 sqlite3.Row 对象转换为普通字典，方便调用方使用
        row = cur.execute(
            "SELECT * FROM model_versions WHERE id = %s", (model_id,)
        ).fetchone()
        return dict(row)
