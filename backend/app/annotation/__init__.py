"""
标注（Annotation）模块的初始化入口
====================================

本模块是整个标注子包的初始化文件，将子包内各模块的核心功能统一导出，
使得上层代码可以通过 `from app.annotation import xxx` 的方式便捷调用。

子包功能概览：
    - prelabel_service : 基于 YOLO 模型的自动预标注服务
    - revision_service : 标注修订历史版本的管理（快照、恢复、查询）
    - yolo_txt_io      : YOLO 格式（TXT）标注文件的读写工具

导出的公共函数：
    - prelabel_image       : 对单张图像执行 YOLO 推理并生成标注文件
    - save_revision        : 保存当前标注的修订版本快照
    - get_revisions        : 获取指定图片的所有修订历史记录
    - restore_revision     : 将指定修订版本的快照恢复到当前标签文件
    - get_revision_snapshot: 获取指定修订版本的快照文件内容
    - read_yolo_txt        : 读取 YOLO 格式的 TXT 标注文件
    - write_yolo_txt       : 将标注框列表写入 YOLO 格式的 TXT 文件
"""

# 导入预标注服务：基于 YOLO 模型对图像进行自动标注
from app.annotation.prelabel_service import prelabel_image

# 导入修订历史服务：提供标注版本管理的快照、恢复与查询功能
from app.annotation.revision_service import (
    get_revision_snapshot,  # 获取指定修订版本的快照文件内容
    get_revisions,          # 获取指定图片的所有历史修订记录
    restore_revision,       # 将指定修订版本恢复到当前标签文件
    save_revision,          # 保存当前标注为新的修订版本
)

# 导入 YOLO 格式文件读写工具：实现 .txt 标注文件的解析与写入
from app.annotation.yolo_txt_io import (
    read_yolo_txt,   # 读取 YOLO TXT 文件，返回标注框列表
    write_yolo_txt,  # 将标注框列表写入 YOLO TXT 文件
)

# 定义公开 API 列表，限制 from module import * 时的导出范围
__all__ = [
    "prelabel_image",         # 预标注（YOLO 推理）
    "save_revision",          # 保存修订版本
    "get_revisions",          # 查询修订历史
    "restore_revision",       # 恢复修订版本
    "get_revision_snapshot",  # 获取修订快照内容
    "read_yolo_txt",          # 读取 YOLO 标注文件
    "write_yolo_txt",         # 写入 YOLO 标注文件
]
