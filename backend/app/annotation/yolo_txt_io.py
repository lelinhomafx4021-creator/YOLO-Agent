"""
YOLO 格式标注文件的读写工具模块
===================================

本模块提供对 YOLO 格式（TXT）标注文件的读写操作。
YOLO 格式每行表示一个目标边界框，格式为：
    class_id x_center y_center width height

其中坐标值均为归一化后的浮点数（相对于图像宽度和高度的比例）。

YOLO TXT 文件以纯文本形式存储，每行对应一个目标检测框。
该格式广泛用于目标检测任务（如 YOLO 系列模型）的训练和推理。

函数列表：
    - read_yolo_txt  : 读取 YOLO TXT 文件，返回标注框列表
    - write_yolo_txt : 将标注框列表写入 YOLO TXT 文件
"""

from pathlib import Path  # 使用 pathlib 进行跨平台路径操作，比 os.path 更现代和便捷


def read_yolo_txt(path: Path) -> list[dict]:
    """
    读取 YOLO 格式的 TXT 标注文件。

    逐行解析文本文件，每行期望包含 5 个字段：
    class_id（类别索引）、x_center、y_center、width、height，
    所有坐标值为归一化浮点数。

    处理逻辑：
        1. 检查文件是否存在，不存在则返回空列表
        2. 读取全部文本内容，去除首尾空白
        3. 逐行解析，过滤格式不正确的行（非 5 字段的行）
        4. 将每行字段转为对应类型（int/float），组装为字典

    参数:
        path (Path): YOLO TXT 文件的路径。

    返回:
        list[dict]: 标注框字典列表，每个字典包含以下键：
            - class_id (int)  : 目标类别索引
            - x_center (float): 边界框中心点 X 坐标（归一化）
            - y_center (float): 边界框中心点 Y 坐标（归一化）
            - width (float)   : 边界框宽度（归一化）
            - height (float)  : 边界框高度（归一化）
        如果文件不存在、为空或没有有效行，则返回空列表。

    异常:
        不会引发异常。文件不存在、损坏或包含无效数据时均返回空列表。
    """
    # 检查文件是否存在，不存在则直接返回空列表（避免 FileNotFoundError）
    if not path.exists():
        return []

    boxes: list[dict] = []

    # 读取文件全部文本并去除首尾空白字符，避免空行干扰解析
    text = path.read_text(encoding="utf-8").strip()

    # 如果文件内容为空，返回空列表
    if not text:
        return boxes

    # 逐行解析标注数据
    for line in text.splitlines():
        # 按空格（或连续空白）分割每行字段
        parts = line.split()
        # 跳过格式不正确的行（YOLO 格式每行必须恰好 5 个字段：class_id, x, y, w, h）
        if len(parts) != 5:
            continue

        # 将各字段转换为对应类型并存入字典
        boxes.append({
            "class_id": int(parts[0]),      # 类别索引（整数）
            "x_center": float(parts[1]),    # 中心点 X 坐标（归一化浮点数）
            "y_center": float(parts[2]),    # 中心点 Y 坐标（归一化浮点数）
            "width": float(parts[3]),       # 边界框宽度（归一化浮点数）
            "height": float(parts[4]),      # 边界框高度（归一化浮点数）
        })

    return boxes


def write_yolo_txt(path: Path, boxes: list[dict]) -> None:
    """
    将标注框列表写入 YOLO 格式的 TXT 文件。

    每个标注框按 YOLO 格式输出一行：
        class_id x_center y_center width height

    坐标值保留 6 位小数以保证精度。
    如果输入列表为空，仍会创建空文件（而非省略文件）。

    参数:
        path (Path): 输出 TXT 文件的路径（目录不存在时会自动创建）。
        boxes (list[dict]): 标注框字典列表，每个字典需包含以下键：
            - class_id (int)  : 目标类别索引
            - x_center (float): 边界框中心点 X 坐标（归一化）
            - y_center (float): 边界框中心点 Y 坐标（归一化）
            - width (float)   : 边界框宽度（归一化）
            - height (float)  : 边界框高度（归一化）

    返回:
        None

    异常:
        如果 boxes 列表中的字典缺少必要键，会在格式化时引发 KeyError。
    """
    # 确保输出目录存在，如果不存在则递归创建（mkdir -p 语义）
    path.parent.mkdir(parents=True, exist_ok=True)

    # 将每个标注框格式化为 YOLO 格式字符串（坐标保留 6 位小数）
    lines = []
    for box in boxes:
        lines.append(
            f"{int(box['class_id'])} "                 # 类别索引，强转为 int 确保安全
            f"{float(box['x_center']):.6f} "            # 中心点 X，保留 6 位小数
            f"{float(box['y_center']):.6f} "            # 中心点 Y，保留 6 位小数
            f"{float(box['width']):.6f} "               # 边界框宽度，保留 6 位小数
            f"{float(box['height']):.6f}"               # 边界框高度，保留 6 位小数（注意末尾无空格）
        )

    # 一次性写入文件，写入后追加换行符（如果列表非空）
    # 使用 UTF-8 编码保证跨平台兼容性
    # "\n".join(lines) 将各行用换行符连接；lines 非空时末尾追加一个换行符使文件以换行结尾
    # 这样处理符合 POSIX 规范要求文本文件以换行符结尾
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
