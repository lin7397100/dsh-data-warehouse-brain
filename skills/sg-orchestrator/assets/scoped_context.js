/**
 * scoped_context.js · 范围上下文构造（≈5KB，非全量历史）
 *
 * 改造项：P1-4（落地范围上下文 handoff）
 *
 * 目标：sub-agent 只收「C0 宪章 + 本阶段契约」+ 边界/词汇/禁项，不再灌入完整对话历史。
 * 经验值：全量历史 ≈200KB，范围上下文 ≈5KB → 单次 handoff 上下文 ≈ 1/40。
 *
 * 设计：构造纯对象，附带 _estSizeKB 供调用方断言上下文未膨胀。不依赖外部模块。
 */

const VOCAB = ['C-GOV-3', 'C-GOV-4', 'C-GOV-6', 'C-G11', 'C28', 'C29', 'D1~D5', 'G0~G5'];

const FORBIDDEN = [
  '禁止使用「定稿 / final / 最终交付」措辞（仅 P5 总监可发最终）',
  '禁止静默覆盖已冻结契约（回溯须走 reopen 申请）',
  '禁止回改上游只读契约（C1 只读于 P2，C2 只读于 P3 …）',
  '禁止跨专家直接互相调用（一律经编排器中转）'
];

/**
 * 构造范围上下文。
 * @param {object} charter  C0 宪章（至少含 scope/caliber/deliverable_type）
 * @param {object} phaseContract 本阶段契约（C1~C5 之一，含 hash）
 * @param {object} [opts]
 * @param {string} [opts.phase]   当前阶段名（如 'P2'）
 * @param {string} [opts.writer]  当前写者专家
 * @param {string[]} [opts.readOnlyContracts] 允许只读的下游契约 phase 列表
 */
function buildScopedContext(charter, phaseContract, opts = {}) {
  if (!charter) throw new Error('buildScopedContext: 缺少 C0 宪章');
  const ctx = {
    charter,                                   // C0（共享宪章，所有 agent 同读一份）
    phaseContract: phaseContract || null,       // 本阶段契约（带 hash）
    phase: opts.phase || (phaseContract && phaseContract.phase) || null,
    writer: opts.writer || null,                // 活跃写者（写者独占）
    boundaries: '只读上游契约，禁止回改上游；本阶段唯一写者',
    readOnlyContracts: opts.readOnlyContracts || [],
    vocab: VOCAB,
    forbidden: FORBIDDEN
  };
  const sizeKB = (Buffer.byteLength(JSON.stringify(ctx), 'utf8') / 1024).toFixed(1);
  ctx._estSizeKB = Number(sizeKB);
  return ctx;
}

module.exports = { buildScopedContext, VOCAB, FORBIDDEN };
