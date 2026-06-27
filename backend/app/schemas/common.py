"""
=============================================================================
公共数据模型 / 通用请求与响应 Schema 定义

文件用途:
    本文件定义了 YOLOps 系统中各 API 端点共享的 Pydantic 数据模型（Schema），
    涵盖数据集管理、标注操作、预标注以及训练任务等通用请求/响应结构。
    所有模型均继承自 pydantic.BaseModel，利用 Field 约束实现自动校验。

设计说明:
    - 所有 Schema 均为不可变的 data class，通过 Pydantic 的解析器在入口处
      完成类型校验与转换，无需在业务代码中重复做参数校验。
    - 所有可选字段均以 Python 类型注解中的 Optional / | None 标记，或提供了默认值。
    - 数值约束（如 ge/le）在 Field 中声明，确保非法值在请求入口即被拒绝。
=============================================================================
"""

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="项目名称")
    description: str = Field(default="", description="项目说明")
    task_type: str = Field(default="detect", description="任务类型，默认 detect")
    workspace_name: str = Field(default="", description="绑定的工作台名称")


class ProjectDatasetBind(BaseModel):
    dataset_version_id: int = Field(..., description="要绑定的数据集版本 ID")
    role: str = Field(default="", description="数据用途：train/val/test/supplement/unlabeled，为空则自动推断")
    source_split: str = Field(default="", description="物理 split，例如 train/val/test；为空则使用全部可用图片")
    note: str = Field(default="", description="绑定说明")


class EvaluationCreate(BaseModel):
    model_version_id: int = Field(..., description="用于评测的模型版本 ID")
    dataset_version_id: int = Field(..., description="用于评测的数据集版本 ID")
    binding_id: int | None = Field(default=None, description="项目数据绑定 ID")
    source_split: str = Field(default="test", description="评测使用的物理 split")
    imgsz: int = Field(default=640, ge=64, le=4096, description="评测图片尺寸")
    batch: int = Field(default=8, ge=1, le=512, description="评测 batch")
    device: str = Field(default="", description="评测设备")



class DatasetCreate(BaseModel):
    """创建数据集请求模型

    用于接收前端创建新数据集的请求参数，包含数据集的基本元信息。

    属性:
        name:        数据集名称，长度限制 1~80 字符，必填。
                     建议使用有业务含义的名称，如 "coco-person-2026"。
        description: 数据集描述，可选字段，默认为空字符串。
                     可用于记录数据集来源、标注规范等补充信息。
    """
    name: str = Field(
        min_length=1,
        max_length=80,
        description="数据集名称，1~80 个字符"
    )
    description: str = Field(
        default="",
        description="数据集描述，可选"
    )


class DatasetImportRequest(BaseModel):
    """数据集导入请求模型

    用于从本地文件系统路径导入已有的 YOLO 格式数据集。
    系统会扫描 source_path 下的目录结构，自动识别图片与标注文件。

    属性:
        source_path: 源数据集在服务器文件系统上的绝对路径或相对路径。
                     路径指向的目录应包含 images/ 和 labels/ 等子目录。
    """
    source_path: str = Field(
        ...,
        description="源数据集的本地文件系统路径"
    )


class AnnotationBox(BaseModel):
    """标注边界框模型

    表示单个目标检测标注框，采用 YOLO 格式的归一化坐标。
    坐标值均为相对于图片宽高的浮点数，取值范围 [0, 1]。

    属性:
        class_id:   目标类别 ID（整数），与数据集的类别配置文件（data.yaml）中的
                    类别索引一一对应。
        x_center:   边界框中心点的归一化 X 坐标，取值范围 [0, 1]。
                    相对于图片宽度：x_center = 中心点像素X / 图片宽度。
        y_center:   边界框中心点的归一化 Y 坐标，取值范围 [0, 1]。
                    相对于图片高度：y_center = 中心点像素Y / 图片高度。
        width:      边界框宽度的归一化值，取值范围 [0, 1]。
                    相对于图片宽度：width = 框像素宽度 / 图片宽度。
        height:     边界框高度的归一化值，取值范围 [0, 1]。
                    相对于图片高度：height = 框像素高度 / 图片高度。
        confidence: 检测置信度，取值范围 [0, 1]。
                    手动标注时通常不传此字段；预标注（模型推理）结果会携带置信度，
                    用于后续的人工复审或自动过滤低质量预测。
    """
    class_id: int = Field(
        ...,
        description="目标类别 ID，对应 data.yaml 中的类别索引"
    )
    x_center: float = Field(
        ...,
        description="归一化中心点 X 坐标，介于 0~1"
    )
    y_center: float = Field(
        ...,
        description="归一化中心点 Y 坐标，介于 0~1"
    )
    width: float = Field(
        ...,
        description="归一化边界框宽度，介于 0~1"
    )
    height: float = Field(
        ...,
        description="归一化边界框高度，介于 0~1"
    )
    confidence: float | None = Field(
        default=None,
        description="检测置信度（0~1），仅预标注结果携带，手动标注为 None"
    )


class AnnotationUpdate(BaseModel):
    """标注更新请求模型

    用于提交或更新某张图片的全部标注框及其审核状态。
    前端在标注界面操作完成后，将整张图片的所有标注框一次性提交。

    属性:
        boxes:  边界框列表，每个元素为 AnnotationBox 类型。
                前端传入的列表会整体替换该图片的所有现有标注。
        status: 标注状态，用于标记当前图片在审核流程中的阶段。
                可选值: "reviewed"（已审核）、"pending"（待审核）等。
                默认值为 "reviewed"，即提交即通过审核。
    """
    boxes: list[AnnotationBox] = Field(
        ...,
        description="该图片的全部边界框列表，整体替换现有标注"
    )
    status: str = Field(
        default="reviewed",
        description="标注审核状态，例如 'reviewed' 或 'pending'"
    )


class PrelabelRequest(BaseModel):
    """预标注请求模型

    使用指定的 YOLO 模型权重对数据集进行自动预标注。
    系统会加载模型对数据集中的每个图片进行推理，并将推理结果转为标注框。

    典型用法:
        1. 用户选择一个已训练好的模型权重文件（.pt）
        2. 设置合适的置信度阈值（conf），低于该阈值的预测将被过滤
        3. 系统自动对目标数据集进行批量推理
        4. 预标注结果写入标注文件，供人工复核修正

    属性:
        model_path: 模型权重文件路径（.pt 格式）。
                    默认使用 "yolo11n.pt"（YOLO11 Nano 轻量版），
                    也可以在系统配置目录下放置自定义权重。
        conf:       检测置信度阈值，取值范围 [0, 1]。
                    仅保留置信度大于等于此值的检测框，默认 0.25。
                    调高阈值可减少误报但可能漏检；调低则反之。
    """
    model_path: str = Field(
        default="yolo11n.pt",
        description="预标注模型权重路径，默认使用 YOLO11 Nano 轻量版"
    )
    conf: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="检测置信度阈值，仅保留高于该值的预测框"
    )


class TrainingCreate(BaseModel):
    """创建训练任务请求模型

    用于启动一次 YOLO 模型训练任务，包含所有训练超参数。
    系统收到该请求后会创建一个异步训练任务，在后台执行训练流程。

    训练流程:
        1. 根据 dataset_version_id 获取训练数据集
        2. 加载 base_model 指定的预训练权重作为初始参数
        3. 按 epochs、imgsz、batch 等超参数执行训练
        4. 训练结束后自动保存最佳权重，并记录训练指标

    属性:
        dataset_version_id: 数据集版本 ID，指定使用哪个版本的数据进行训练。
                            数据集管理模块会为每次数据集变更生成一个新版本。
        base_model:         基础模型权重路径（预训练权重）。
                            默认使用 "yolo11n.pt"（YOLO11 Nano），
                            也可以指定之前训练好的输出权重做增量训练。
        epochs:             训练轮数，范围 1~1000。
                            训练过程中的每次 epoch 会遍历一次完整数据集。
                            默认 3 轮用于功能测试，生产环境通常设为 50~300。
        imgsz:              输入图片尺寸（像素），范围 64~4096。
                            训练时会将图片缩放到此尺寸再送入网络。
                            默认 640 是 YOLO 系列的经典输入尺寸。
        batch:              批次大小（batch size），范围 1~512。
                            每步训练同时处理的图片数量，受 GPU 显存限制。
                            默认 8 适合大部分消费级 GPU。
        device:             训练设备标识，如 "cpu"、"cuda:0"、"cuda:1" 等。
                            空字符串表示由系统自动选择可用设备（优先 GPU）。
        run_name:           本次训练的运行名称，用于区分不同的训练实验。
                            在日志、权重保存目录和可视化面板中使用。
                            不传时系统会自动生成一个时间戳名称。
    """
    project_id: int | None = Field(
        default=None,
        description="所属项目 ID；旧接口可不传"
    )
    dataset_version_id: int = Field(
        ...,
        description="训练集版本 ID"
    )
    val_dataset_version_id: int | None = Field(
        default=None,
        description="验证集版本 ID（可选），用于评估时自动关联验证数据"
    )
    base_model: str = Field(
        default="yolo11n.pt",
        description="基础模型权重路径，默认 yolo11n.pt"
    )
    epochs: int = Field(
        default=3,
        ge=1,
        le=1000,
        description="训练轮数，1~1000，默认 3（测试用短轮次）"
    )
    imgsz: int = Field(
        default=640,
        ge=64,
        le=4096,
        description="输入图片尺寸（像素），64~4096，默认 640"
    )
    batch: int = Field(
        default=8,
        ge=1,
        le=512,
        description="批大小（batch size），1~512，默认 8"
    )
    device: str = Field(
        default="",
        description="训练设备，空字符串表示自动选择"
    )
    run_name: str | None = Field(
        default=None,
        description="训练运行名称，可选；不传则自动生成"
    )
    optimizer: str = Field(
        default="auto",
        description="优化器：auto / SGD / Adam / AdamW"
    )
    lr0: str = Field(
        default="",
        description="初始学习率，空字符串使用 YOLO 默认值"
    )
