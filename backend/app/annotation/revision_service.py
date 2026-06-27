"""
修订历史记录服务 —— 每次保存标注时自动创建快照。

该模块提供标注修订版本的管理功能，包括：
- 保存修订版本：将当前标签文件快照到 .yolops/history/ 目录，并在数据库中记录修订信息
- 查询修订列表：获取指定图片的所有历史修订记录
- 获取修订快照内容：读取指定修订版本对应的标签文件快照内容
- 恢复修订版本：将指定修订版本的快照文件恢复到当前标签路径

依赖:
    - shutil: 用于文件和目录的复制操作
    - pathlib.Path: 用于路径的跨平台规范化处理
    - app.core.database: 提供数据库连接和查询工具函数
"""

import shutil  # 用于文件的复制操作（copy2 保留元数据）
from pathlib import Path  # 用于路径的跨平台处理

from app.core.database import db, fetch_all, fetch_one, utc_now


def save_revision(
    image_item_id: int,
    source: str,
    label_path: str | Path,
    box_count: int,
    changed_by: str = "user",
    note: str = "",
) -> dict:
    """保存当前标注的修订版本（创建快照并写入数据库记录）。

    执行流程：
        1. 校验 image_item_id 在 image_items 表中是否存在
        2. 构建快照存储路径：<label父目录>/.yolops/history/<文件名主干>/
        3. 将当前标签文件（.txt）复制到上述快照目录中，以 UTC 时间戳命名
        4. 向 annotation_revisions 表插入一条修订记录
        5. 同步更新 image_items 表的 updated_at 时间戳
        6. 返回刚插入的完整修订记录

    Args:
        image_item_id: 图片项的唯一标识 ID（对应 image_items 表的主键）
        source: 修订来源标识（如 "manual" 表示手动保存，"restore" 表示恢复操作）
        label_path: 当前标签文件的路径（支持字符串或 Path 对象）
        box_count: 当前标注框的数量（用于记录快照时的标注状态）
        changed_by: 修改者标识，默认为 "user"
        note: 修订备注说明，默认为空字符串

    Returns:
        包含新插入修订记录的字典（包含 id, image_item_id, source,
        label_snapshot_path, box_count, changed_by, note, created_at 等字段）

    Raises:
        ValueError: 如果指定的 image_item_id 在数据库中不存在
    """
    # 将传入的路径统一转换为 Path 对象，确保跨平台兼容性
    label_path = Path(label_path)

    # ========== 第一步：校验图片项是否存在 ==========
    # 从 image_items 表中查询指定 ID 的记录
    image = fetch_one("SELECT * FROM image_items WHERE id = %s", (image_item_id,))
    if not image:
        # 如果数据库中没有该图片项，则抛出异常阻止后续操作
        raise ValueError(f"image_item not found: {image_item_id}")

    # ========== 第二步：构建快照存储目录 ==========
    # 快照目录结构：<label_dir>/.yolops/history/<label_stem>/
    # 例如：labels/train/abc.txt -> labels/train/.yolops/history/abc/
    # 其中 label_path.parent 是 labels/train，label_path.stem 是 abc
    history_dir = label_path.parent.parent / ".yolops" / "history" / label_path.stem
    # 递归创建目录，如果已存在则不报错
    history_dir.mkdir(parents=True, exist_ok=True)

    # ========== 第三步：复制标签文件作为快照 ==========
    # 生成快照文件名：以当前 UTC 时间戳命名，去除冒号、短横线和 Z 后缀
    # 例如：2026-06-23T12:34:56Z -> 20260623T123456
    timestamp = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    snapshot_path = history_dir / f"{timestamp}.txt"
    if snapshot_path.exists():
        counter = 1
        while True:
            candidate = history_dir / f"{timestamp}_{counter}.txt"
            if not candidate.exists():
                snapshot_path = candidate
                break
            counter += 1

    # 检查源标签文件是否存在，若存在则执行复制
    # 使用 copy2 以保留文件的元数据（如修改时间等）
    if label_path.exists():
        shutil.copy2(label_path, snapshot_path)
    # 如果标签文件不存在，则跳过复制（快照目录中就不会有该文件）

    # ========== 第四步：写入数据库记录 ==========
    now = utc_now()  # 获取当前 UTC 时间，作为修订记录和图片更新的统一时间戳
    with db() as cur:
        # 4a. 向 annotation_revisions 表插入一条修订记录
        #     包含图片 ID、来源、快照路径、标注框数量、修改者、备注和创建时间
        cur.execute(
            """INSERT INTO annotation_revisions(image_item_id, source, label_snapshot_path, box_count, changed_by, note, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (image_item_id, source, str(snapshot_path), box_count, changed_by, note, now),
        )
        # 4b. 同步更新 image_items 表中对应记录的 updated_at 时间戳
        #     确保图片的"最近修改时间"与修订记录的创建时间一致
        cur.execute(
            "UPDATE image_items SET updated_at = %s WHERE id = %s",
            (now, image_item_id),
        )
        # 4c. 查询并返回刚插入的最新修订记录
        #     按 id 降序排列取第一条，确保获取到刚刚插入的记录
        row = cur.execute(
            "SELECT * FROM annotation_revisions WHERE image_item_id = %s ORDER BY id DESC LIMIT 1",
            (image_item_id,),
        ).fetchone()
        return dict(row)


def get_revisions(image_item_id: int) -> list[dict]:
    """获取指定图片的所有历史修订记录列表。

    按修订 ID 降序排列（最新的记录排在最前面），便于前端展示最近操作。

    Args:
        image_item_id: 图片项的唯一标识 ID

    Returns:
        修订记录字典列表，每项包含 id, image_item_id, source,
        label_snapshot_path, box_count, changed_by, note, created_at 等字段。
        如果没有修订记录，则返回空列表。
    """
    # 从 annotation_revisions 表中查询该图片的所有修订记录
    # 使用 ORDER BY id DESC 使最新的记录排在最前
    return fetch_all(
        "SELECT * FROM annotation_revisions WHERE image_item_id = %s ORDER BY id DESC",
        (image_item_id,),
    )


def get_revision_snapshot(revision_id: int) -> dict:
    """获取指定修订版本的快照文件内容。

    根据修订记录 ID 从数据库中查询对应的元数据，然后读取磁盘上
    对应的快照标签文件（.txt）的全部文本内容。

    Args:
        revision_id: 修订记录的唯一标识 ID

    Returns:
        包含两个键的字典：
            - "revision": 修订记录的字典（元数据）
            - "content":  快照文件的文本内容（如果文件不存在则为空字符串）

    Raises:
        ValueError: 如果指定的 revision_id 在数据库中不存在
    """
    # 第一步：从数据库中查询修订记录
    rev = fetch_one("SELECT * FROM annotation_revisions WHERE id = %s", (revision_id,))
    if not rev:
        # 如果查询结果为空，说明该修订记录 ID 无效
        raise ValueError(f"revision not found: {revision_id}")

    # 第二步：从修订记录中提取快照文件路径
    # 数据库中存储的是字符串路径，需要转为 Path 对象以便后续操作
    path = Path(rev["label_snapshot_path"])
    # 第三步：读取快照文件的文本内容
    # 如果文件在磁盘上已不存在（如被手动删除），则返回空字符串
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    # 返回修订元数据和文件内容
    return {"revision": rev, "content": content}


def restore_revision(image_item_id: int, revision_id: int) -> dict:
    """将指定修订版本的快照恢复到当前标签文件。

    该操作会执行以下步骤：
        1. 校验修订记录和图片项是否存在
        2. 检查快照文件是否仍然存在于磁盘上
        3. 将快照文件复制覆盖到当前标签路径
        4. 自动生成一条来源为 "restore" 的新修订记录（通过 save_revision）

    Args:
        image_item_id: 图片项的唯一标识 ID
        revision_id:   要恢复的修订记录 ID

    Returns:
        save_revision() 返回的新修订记录字典（恢复操作本身也会被记录为一条修订）

    Raises:
        ValueError:       如果 revision_id 或 image_item_id 在数据库中不存在
        FileNotFoundError: 如果快照文件在磁盘上已丢失
    """
    # ========== 第一步：校验修订记录是否存在 ==========
    # 根据 revision_id 从 annotation_revisions 表查询目标修订记录
    rev = fetch_one("SELECT * FROM annotation_revisions WHERE id = %s", (revision_id,))
    if not rev:
        raise ValueError(f"revision not found: {revision_id}")

    # ========== 第二步：校验图片项是否存在 ==========
    # 根据 image_item_id 从 image_items 表查询目标图片
    image = fetch_one("SELECT * FROM image_items WHERE id = %s", (image_item_id,))
    if not image:
        raise ValueError(f"image_item not found: {image_item_id}")

    # ========== 第三步：检查快照文件是否存在 ==========
    # 从修订记录中提取快照文件的磁盘路径
    snapshot = Path(rev["label_snapshot_path"])
    if not snapshot.exists():
        # 如果快照文件已被删除，则无法恢复，抛出文件不存在的异常
        raise FileNotFoundError(f"snapshot file missing: {snapshot}")

    # ========== 第四步：将快照文件恢复到当前标签路径 ==========
    # 从图片记录中获取当前标签文件的路径，并用快照文件覆盖它
    label_path = Path(image["label_path"])
    shutil.copy2(snapshot, label_path)

    # ========== 第五步：记录恢复操作 ==========
    # 恢复操作本身也是一次修改，因此自动创建一条新的修订记录
    # 来源标记为 "restore"，以便与手动保存区分
    return save_revision(
        image_item_id,
        source="restore",
        label_path=label_path,
        box_count=rev["box_count"],
        note=f"restored from revision {revision_id}",
    )
