/**
 * AI 报告 API 模块
 * 提供训练运行和评估运行的 AI 报告接口调用。
 */

import { get, post } from './client.js'

// ── 训练报告 ──

/** 获取指定训练运行的 AI 报告 */
export function getReport(trainingRunId) { return get(`/training-runs/${trainingRunId}/ai-report`) }

/** 重新生成指定训练运行的 AI 报告 */
export function regenerateReport(trainingRunId) { return post(`/training-runs/${trainingRunId}/ai-report`) }

// ── 评估报告 ──

/** 获取指定评估运行的 AI 报告 */
export function getEvaluationReport(evaluationId) { return get(`/evaluation-runs/${evaluationId}/ai-report`) }

/** 重新生成指定评估运行的 AI 报告 */
export function regenerateEvaluationReport(evaluationId) { return post(`/evaluation-runs/${evaluationId}/ai-report`) }
