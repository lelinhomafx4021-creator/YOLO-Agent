"""
YOLOps-Agent 核心基础设施包

本包提供整个后端应用所依赖的公共基础设施层，作为应用的核心初始化入口，
集中导出配置管理与数据库访问两大基础模块的公开 API。

所包含的模块：

  - 配置模块（config）：
      定义全局路径常量（项目根目录、数据目录、数据集目录、运行输出目录、
      模型注册表目录、数据库连接配置等）及支持的图片文件扩展名集合。
      所有路径均基于代码位置自动解析，无需手动配置。

  - 数据库访问层（database）：
      基于 PostgreSQL 实现的数据持久化层，提供：
        * 完整的业务表结构 DDL（数据集、版本、标注审核、训练运行、模型等）
        * 线程安全的数据库连接上下文管理器（db()）
        * 常用查询封装（fetch_one / fetch_all）
        * 数据库迁移支持（_migrate）
        * 工具函数（utc_now、dict_from_row、as_path）

典型用法：
    from app.core import (
        BASE_DIR, DATA_DIR, DATASETS_DIR,    # 路径常量
        ensure_data_dirs,                      # 初始化数据目录
        init_db, db, fetch_one, fetch_all      # 数据库操作
    )

    # 应用启动时调用
    ensure_data_dirs()
    init_db()

    # 后续在业务代码中使用数据库连接
    with db() as cur:
        cur.execute("SELECT ...")

所属项目：YOLOps-Agent —— 工业级 YOLO 数据集管理、训练归档与 AI 复盘平台
"""

# ──────────────────────────────────────────────────────────────
# 从 config 模块导出路径常量与初始化函数
# ──────────────────────────────────────────────────────────────
# config 模块定义了所有与文件系统相关的路径和全局默认值。
# 以下导出让上层代码可以通过 `from app.core import xxx` 直接访问，
# 而不需要关心具体子模块路径。

# 项目根目录（backend/），用于定位其他资源
from app.core.config import BASE_DIR

# 数据根目录，所有运行时数据（数据集、运行输出、模型等）均存放于此
from app.core.config import DATA_DIR

# 数据集存放目录，每个数据集在此目录下有自己的子目录
from app.core.config import DATASETS_DIR

# 训练/推理运行输出目录（日志、权重、结果等）
from app.core.config import RUNS_DIR

# 模型注册表目录（已注册的模型归档）
from app.core.config import MODEL_REGISTRY_DIR

# 允许上传/处理的图片文件扩展名集合，用于校验用户上传的文件类型
from app.core.config import IMAGE_EXTENSIONS

# 确保所有必需数据目录存在的初始化函数（应用启动时调用）
from app.core.config import ensure_data_dirs


# ──────────────────────────────────────────────────────────────
# 从 database 模块导出数据库初始化、连接管理、查询工具
# ──────────────────────────────────────────────────────────────
# database 模块封装了数据库的全部操作，包括连接管理、
# 表结构初始化、数据迁移、常用查询模式和辅助工具函数。

# 初始化数据库表结构并执行迁移（应用启动时调用）
from app.core.database import init_db

# 线程安全的数据库连接上下文管理器（with db() as cur:），
# 确保每个线程/协程使用独立的数据库连接
from app.core.database import db

# 查询单行记录，返回字典或 None，简化单条数据的读取
from app.core.database import fetch_one

# 查询多行记录，返回字典列表，简化批量数据的读取
from app.core.database import fetch_all

# 获取当前 UTC 时间字符串（ISO 8601 格式），用于记录创建/更新时间
from app.core.database import utc_now

# 将数据库行对象转换为字典（内部使用）
from app.core.database import dict_from_row

# 规范化路径：展开 ~ 用户目录并解析为绝对路径
from app.core.database import as_path


# ── 本包公开发布的 API 列表 ──────────────────────────────────
# 以下 __all__ 变量显式声明了本包的公开接口，一方面方便 IDE 自动补全，
# 另一方面也明确了哪些符号是稳定的对外 API，供上层业务代码导入使用。
# 通过 `from app.core import xxx` 可直接访问上述全部符号。
__all__ = [
    # ── config 模块导出的路径常量和工具函数 ────────────────
    "BASE_DIR",              # 项目根目录路径
    "DATA_DIR",              # 数据根目录路径
    "DATASETS_DIR",          # 数据集存放目录路径
    "RUNS_DIR",              # 训练/推理运行输出目录路径
    "MODEL_REGISTRY_DIR",    # 模型注册表目录路径
    "IMAGE_EXTENSIONS",      # 支持的图片文件扩展名集合
    "ensure_data_dirs",      # 创建/确保数据目录存在的初始化函数

    # ── database 模块导出的数据库操作工具 ──────────────────
    "init_db",               # 数据库表结构初始化与迁移函数
    "db",                    # 线程安全的数据库连接上下文管理器
    "fetch_one",             # 单行查询函数，返回字典或 None
    "fetch_all",             # 多行查询函数，返回字典列表
    "utc_now",               # 获取当前 UTC 时间字符串
    "dict_from_row",         # 数据库行对象转字典的内部工具
    "as_path",               # 规范化路径字符串
]
