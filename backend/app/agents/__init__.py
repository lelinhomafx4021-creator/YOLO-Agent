"""
==============================================================================
agents 包 — YOLOps-Agent 智能体模块

本包提供了 AI 驱动的智能体（Agent）功能，用于与用户进行交互对话、
分析训练结果、生成迭代计划等。所有智能体均基于项目上下文
（数据库中的数据集、版本、训练记录等）进行推理和响应。

包含的子模块：
    chat_agent.py              — 聊天智能体：LLM 驱动的对话代理，
                                 支持基于关键词匹配的规则引擎回落（fallback）
    context_builder.py         — 上下文构建器：从数据库提取项目状态信息，
                                 组装为结构化的 JSON 上下文快照
    plan_service.py            — 计划服务：迭代计划的增删改查（CRUD）操作，
                                 包括保存、查询、执行和状态更新
    training_analyst_agent.py  — 训练分析智能体：在训练完成后自动生成
                                 包含关键发现和改进建议的 Markdown 分析报告

典型工作流程：
    1. context_builder.build_context()    从数据库获取项目全景数据
    2. chat_agent.chat()                  接收用户消息，结合上下文生成回复
    3. plan_service.save_plan()           若回复包含计划，将其持久化
    4. training_analyst_agent.generate_training_report()  训练完成后自动复盘

所属项目：YOLOps-Agent —— 工业级 YOLO 数据集管理、训练归档与 AI 复盘平台
==============================================================================
"""

# ---- 从 chat_agent 导出主要接口 ----
# chat() 是聊天智能体的主入口，接收用户消息并返回智能体回复
from app.agents.chat_agent import chat

# ---- 从 context_builder 导出上下文构建接口 ----
# build_context() 从数据库提取所有项目状态信息，组装为结构化的 JSON 快照
from app.agents.context_builder import build_context

# ---- 从 plan_service 导出计划 CRUD 接口 ----
# 提供迭代计划的创建、查询、执行和状态更新功能
from app.agents.plan_service import (
    save_plan,          # 创建并保存一条新计划
    list_plans,         # 按状态筛选列出所有计划
    get_plan,           # 根据 ID 获取单条计划
    apply_plan,         # 执行计划并解析其结构化参数
    update_plan_status, # 更新计划的当前状态
)

# ---- 从 training_analyst_agent 导出报告生成接口 ----
# generate_training_report() 在训练完成后自动生成分析报告
from app.agents.training_analyst_agent import generate_training_report

# 定义包级别的公开 API，被 from app.agents import * 时导入的符号列表
__all__ = [
    "chat",                     # 聊天智能体主入口
    "build_context",            # 构建项目上下文
    "save_plan",                # 保存迭代计划
    "list_plans",               # 列出迭代计划
    "get_plan",                 # 获取单条计划
    "apply_plan",               # 执行计划
    "update_plan_status",       # 更新计划状态
    "generate_training_report", # 生成训练分析报告
]
