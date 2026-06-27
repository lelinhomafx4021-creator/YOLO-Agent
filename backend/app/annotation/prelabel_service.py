"""
预标注服务模块

本模块提供了基于 YOLO 模型对图像进行自动预标注的核心功能。
通过加载预训练的 YOLO 模型，对输入图像进行推理检测，
并将检测到的目标边界框坐标从像素空间归一化到 [0, 1] 区间，
最终以 YOLO 格式写入对应的 .txt 标签文件中。

主要功能：
    - prelabel_image: 对单张图像执行 YOLO 推理并生成标注文件

依赖：
    - ultralytics: YOLO 模型加载与推理（延迟导入）
    - app.annotation.yolo_txt_io.write_yolo_txt: YOLO 格式标签写入
"""

from pathlib import Path  # 用于处理文件系统路径

from app.annotation.yolo_txt_io import write_yolo_txt  # YOLO 格式标注数据写入工具


def prelabel_image(image_path: Path, label_path: Path, model_path: str, conf: float = 0.25) -> list[dict]:
    """
    对指定图像进行 YOLO 模型预标注，并将结果写入标签文件。

    该函数加载 YOLO 模型并对图像执行目标检测，将检测到的每个目标
    的边界框坐标从像素坐标归一化后，以 YOLO 格式返回，同时将结果
    写入指定的 .txt 标签文件。

    工作流程：
        1. 延迟导入 ultralytics.YOLO（仅在首次调用时加载）
        2. 加载指定路径的 YOLO 模型权重
        3. 对输入图像进行推理，获取检测结果
        4. 遍历每个检测到的目标，将像素坐标转换为 YOLO 归一化坐标
        5. 将转换后的结果写入标签文件并返回

    参数:
        image_path (Path): 输入图像的文件路径。
        label_path (Path): 输出标签文件（.txt）的保存路径。
                           函数会将检测结果以 YOLO 格式写入该文件。
        model_path (str): YOLO 模型权重文件路径，支持 .pt 格式。
        conf (float): 检测置信度阈值，范围为 [0.0, 1.0]。
                      低于此阈值的检测结果将被过滤。默认值为 0.25。

    返回:
        list[dict]: 检测结果列表，每个元素为一个字典，包含以下字段：
            - class_id (int): 目标类别 ID（从 0 开始）
            - x_center (float): 归一化后的边界框中心点 x 坐标（范围 [0, 1]）
            - y_center (float): 归一化后的边界框中心点 y 坐标（范围 [0, 1]）
            - width (float): 归一化后的边界框宽度（范围 [0, 1]）
            - height (float): 归一化后的边界框高度（范围 [0, 1]）
            - confidence (float): 检测置信度（范围 [0, 1]）

    抛出:
        RuntimeError: 当 ultralytics 库未安装时抛出，提示用户安装。

    示例:
        >>> results = prelabel_image(
        ...     image_path=Path("image.jpg"),
        ...     label_path=Path("image.txt"),
        ...     model_path="yolov8n.pt",
        ...     conf=0.5
        ... )
        >>> print(len(results))
        3
    """
    # ----------------------------------------------------------------
    # 第一步：延迟导入 ultralytics 库
    # 仅在调用此函数时才加载，避免模块导入时的额外开销
    # ----------------------------------------------------------------
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is not installed") from exc

    # ----------------------------------------------------------------
    # 第二步：加载 YOLO 模型
    # 从指定路径加载预训练权重，支持 YOLOv8/v9/v10/v11 等模型
    # ----------------------------------------------------------------
    model = YOLO(model_path)

    # ----------------------------------------------------------------
    # 第三步：对输入图像执行推理
    # - source: 输入图像路径
    # - conf: 置信度阈值，低于该值的目标将被忽略
    # - verbose: 关闭冗长输出，减少控制台日志
    # ----------------------------------------------------------------
    results = model.predict(source=str(image_path), conf=conf, verbose=False)

    # ----------------------------------------------------------------
    # 第四步：解析检测结果，转换为 YOLO 格式的归一化坐标
    # YOLO 格式要求：class_id x_center y_center width height
    # 所有坐标值均需归一化到 [0, 1] 区间
    # ----------------------------------------------------------------
    boxes: list[dict] = []
    if results:
        # 取第一个（也是唯一一个）图像的检测结果
        # results 是一个列表，每个元素对应一张图像的检测结果
        result = results[0]
        # 获取原始图像的尺寸（高, 宽），用于后续坐标归一化计算
        image_h, image_w = result.orig_shape

        # 遍历每个检测到的目标边界框
        for item in result.boxes:
            # 提取目标类别 ID（整数）
            cls_id = int(item.cls[0].item())

            # 获取边界框的左上角和右下角像素坐标 [x1, y1, x2, y2]
            xyxy = item.xyxy[0].tolist()
            x1, y1, x2, y2 = xyxy

            # 将像素坐标转换为 YOLO 格式的归一化坐标：
            #   - x_center = (x1 + x2) / 2 / image_w   (中心点横坐标 / 图像宽度)
            #   - y_center = (y1 + y2) / 2 / image_h   (中心点纵坐标 / 图像高度)
            #   - width    = (x2 - x1) / image_w        (框宽度 / 图像宽度)
            #   - height   = (y2 - y1) / image_h        (框高度 / 图像高度)
            boxes.append({
                "class_id": cls_id,
                "x_center": ((x1 + x2) / 2) / image_w,
                "y_center": ((y1 + y2) / 2) / image_h,
                "width": (x2 - x1) / image_w,
                "height": (y2 - y1) / image_h,
                "confidence": float(item.conf[0].item()),
            })

    # ----------------------------------------------------------------
    # 第五步：将检测结果写入 YOLO 格式的标签文件
    # 每行格式为：class_id x_center y_center width height
    # ----------------------------------------------------------------
    write_yolo_txt(label_path, boxes)

    # 返回检测结果列表，供调用方进一步使用
    return boxes
