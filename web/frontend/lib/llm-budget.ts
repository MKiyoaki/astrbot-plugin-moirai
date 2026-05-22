/**
 * LLM 用量估算 — 按「功能权重」粗略估计当前配置下的 LLM 负载。
 *
 * 这不是真实 token 用量（真实用量见 /stats 页 TokenStats），而是一个
 * 配置层面的指标：所有 LLM 消耗型功能全开 = 100%。权重按调用频率分配。
 *
 * 关于 distillation：extraction_strategy = "semantic" 时，事件抽取改为
 * 「DBSCAN 分簇 + 每个分区各发一次 LLM 调用」（task_name="distillation"），
 * 一个窗口会产生 N 次调用，明显重于 "llm" 模式的单次批量调用。因此语义
 * 模式视为「事件抽取」之上的额外负载，单列一项计入估算。
 *
 * 纯函数，输入 /api/config 的 `values`，无副作用。
 */

export type LlmFeatureKey = 'extraction' | 'summary' | 'synthesis' | 'relation' | 'distillation'

interface LlmFeatureDef {
  key: LlmFeatureKey
  weight: number
  /** true 表示该功能无开关、始终计入（事件抽取是核心功能）。 */
  always?: boolean
}

/** 权重表，合计 100。顺序即清单展示顺序。 */
export const LLM_FEATURES: readonly LlmFeatureDef[] = [
  { key: 'extraction',   weight: 40, always: true },
  { key: 'summary',      weight: 20 },
  { key: 'synthesis',    weight: 15 },
  { key: 'relation',     weight: 15 },
  { key: 'distillation', weight: 10 },
] as const

export interface LlmFeatureState {
  key: LlmFeatureKey
  enabled: boolean
  always: boolean
}

/**
 * 功能 → 插件配置页对应字段 key 的映射，用于点击徽标清单跳转到配置项。
 * `extraction` 无开关（核心功能常驻），故为 null，不可跳转。
 */
export const LLM_FEATURE_CONFIG_KEY: Record<LlmFeatureKey, string | null> = {
  extraction: null,
  summary: 'summary_enabled',
  synthesis: 'persona_synthesis_enabled',
  relation: 'relation_enabled',
  distillation: 'extraction_strategy',
}

export interface LlmBudget {
  /** 0–100 的整数百分比；抽取无法关闭，故实际范围 40–100。 */
  percent: number
  features: LlmFeatureState[]
}

/** 判断单个功能在给定配置下是否启用。 */
function isFeatureEnabled(key: LlmFeatureKey, values: Record<string, unknown>): boolean {
  switch (key) {
    case 'extraction':
      return true // 核心功能，始终运行
    case 'summary':
      return values.summary_enabled !== false // 默认 true
    case 'synthesis':
      // 调度需 persona_synthesis_enabled 与 relation_enabled 同时开启
      // （plugin_initializer.py: `if cfg.persona_synthesis_enabled and cfg.relation_enabled`）
      return values.persona_synthesis_enabled !== false && values.relation_enabled !== false
    case 'relation':
      return values.relation_enabled !== false // 默认 true
    case 'distillation':
      // 无独立开关：extraction_strategy 选 "semantic" 时启用（默认 "llm"）。
      // 语义模式按分区多次调用 LLM，比单次批量抽取更重。
      return values.extraction_strategy === 'semantic'
  }
}

/** 从 /api/config 的 values 计算 LLM 用量估算。 */
export function computeLlmBudget(values: Record<string, unknown>): LlmBudget {
  const features: LlmFeatureState[] = LLM_FEATURES.map(f => ({
    key: f.key,
    enabled: isFeatureEnabled(f.key, values),
    always: f.always ?? false,
  }))
  const percent = LLM_FEATURES.reduce(
    (sum, f, i) => sum + (features[i].enabled ? f.weight : 0),
    0,
  )
  return { percent, features }
}
