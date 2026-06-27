"""SQLModel table definitions — used for DDL creation. Runtime queries still use raw SQL."""
from typing import Optional
from sqlmodel import SQLModel, Field


class Dataset(SQLModel, table=True):
    __tablename__ = "datasets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    description: str = ""
    collection_name: str = ""
    created_at: str

class DatasetVersion(SQLModel, table=True):
    __tablename__ = "dataset_versions"
    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int
    version: str
    root_path: str
    data_yaml_path: str
    image_count: int
    label_file_count: int
    instance_count: int
    class_count: int
    fingerprint: str
    status: str = "imported"
    dtype: str = ""
    created_at: str
    # 原 label_audit_reports 表字段（1:1 合并）
    missing_labels: int = 0
    orphan_labels: int = 0
    invalid_bboxes: int = 0
    empty_labels: int = 0
    class_distribution_json: str = "{}"
    suggestions_json: str = "[]"
    audit_report_path: str = ""

class DatasetExport(SQLModel, table=True):
    __tablename__ = "dataset_exports"
    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_version_id: int
    export_name: str
    export_path: str
    train_count: int = 0
    val_count: int = 0
    test_count: int = 0
    train_ratio: float = 0.7
    val_ratio: float = 0.2
    test_ratio: float = 0.1
    created_at: str

class Project(SQLModel, table=True):
    __tablename__ = "projects"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    description: str = ""
    task_type: str = "detect"
    workspace_name: str = ""
    status: str = "active"
    created_at: str
    updated_at: str

class ProjectDatasetBinding(SQLModel, table=True):
    __tablename__ = "project_dataset_bindings"
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int
    dataset_version_id: int
    role: str
    source_split: str = ""
    note: str = ""
    is_active: int = 1
    created_at: str


class ImageItem(SQLModel, table=True):
    __tablename__ = "image_items"
    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_version_id: int
    split: str
    image_path: str
    label_path: str
    annotation_status: str = "unlabeled"
    width: int = 0
    height: int = 0
    updated_at: str = ""

class TrainingRun(SQLModel, table=True):
    __tablename__ = "training_runs"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True)
    project_id: Optional[int] = None
    dataset_version_id: int
    val_dataset_version_id: Optional[int] = None
    dataset_name: str = ""
    base_model: str
    epochs: int
    imgsz: int
    batch: int
    device: str = ""
    optimizer: str = "auto"
    lr0: str = ""
    status: str
    run_path: str
    log_path: str
    error: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str
    # 原 ai_reports 表字段（1:1 合并）
    report_path: str = ""
    summary: str = ""
    notes: str = ""

class ModelVersion(SQLModel, table=True):
    __tablename__ = "model_versions"
    id: Optional[int] = Field(default=None, primary_key=True)
    training_run_id: int = Field(unique=True)
    project_id: Optional[int] = None
    run_id: str
    dataset_name: str
    dataset_version: str
    base_model: str
    epochs: int
    imgsz: int
    batch: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    best_epoch: Optional[int] = None
    best_pt_path: str
    last_pt_path: str
    registry_path: str
    model_name: str = ""
    notes: str = ""
    model_format: str = ""
    is_candidate: int = 0
    is_production: int = 0
    created_at: str

class AnnotationRevision(SQLModel, table=True):
    __tablename__ = "annotation_revisions"
    id: Optional[int] = Field(default=None, primary_key=True)
    image_item_id: int
    source: str = "manual"
    label_snapshot_path: str
    box_count: int = 0
    changed_by: str = "user"
    note: str = ""
    created_at: str


class AgentSession(SQLModel, table=True):
    __tablename__ = "agent_sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = None
    title: str
    mode: str = "rule"
    created_at: str

class AgentMessage(SQLModel, table=True):
    __tablename__ = "agent_messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int
    role: str
    content: str
    context_json: str = "{}"
    created_at: str

class IterationPlan(SQLModel, table=True):
    __tablename__ = "iteration_plans"
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = None
    session_id: Optional[int] = None
    dataset_version_id: Optional[int] = None
    training_run_id: Optional[int] = None
    plan_type: str
    title: str
    content: str
    status: str = "draft"
    is_read: int = 0
    created_at: str

class TrainingMetric(SQLModel, table=True):
    __tablename__ = "training_metrics"
    id: Optional[int] = Field(default=None, primary_key=True)
    training_run_id: int
    epoch: int
    train_box_loss: Optional[float] = None
    train_cls_loss: Optional[float] = None
    train_dfl_loss: Optional[float] = None
    val_box_loss: Optional[float] = None
    val_cls_loss: Optional[float] = None
    val_dfl_loss: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    created_at: str

class EvaluationRun(SQLModel, table=True):
    __tablename__ = "evaluation_runs"
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int
    model_version_id: int
    dataset_version_id: int
    binding_id: Optional[int] = None
    run_id: str = Field(unique=True)
    status: str
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    run_path: str
    log_path: str
    report_path: str = ""
    summary: str = ""
    error: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str

class EvaluationSample(SQLModel, table=True):
    __tablename__ = "evaluation_samples"
    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_run_id: int
    image_item_id: Optional[int] = None
    image_path: str
    label_path: str = ""
    prediction_label_path: str = ""
    prediction_image_path: str = ""
    confidence_summary: str = ""
    match_summary: str = ""
    created_at: str
