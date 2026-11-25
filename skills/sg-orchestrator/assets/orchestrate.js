/**
 * orchestrate.js · 六阶段(P0~P5)调度驱动器 —— sg-orchestrator 的"实际调度"引擎
 *
 * 改造项：接入实际调度（用户指令：把 sg-orchestrator 接入真实任务流）
 *
 * 把分散的运行时（contract_ledger / gates / fast_lane / scoped_context）收束为一个
 * 可实例化的 Orchestrator，供 team-lead（编排器）与 sg-supervisor（签发节点）在真实任务中直接调用：
 *
 *   const { Orchestrator } = require('sg-orchestrator/assets/orchestrate');
 *   const o = new Orchestrator({ reopenBudget: 2, ledgerPath: 'observed/ledgers/<trace>.json' });
 *   o.start(charter);                 // P0：建宪章 + 拿写者令牌
 *   o.enterPhase('P1','sg-development');
 *   const r = o.exitPhase('P1', { dataSourceExists:true, rowCountClosed:true, contractPayload:{rows:21} });
 *   const scoped = o.handoff(c1, 'sg-development');   // 给 sub-agent 范围上下文（≈5KB）
 *   o.signOff({ allGreen:true, stableMd5:true, userConfirmed:true, fingerprint, artifactPath });  // P5
 *
 * 零依赖（仅 require 同目录运行时），Node ≥ 12 可直接运行。
 */
const ContractLedger = require('./contract_ledger');
const { runAll, summarize } = require('./gates');
const { route } = require('./fast_lane');
const { buildScopedContext } = require('./scoped_context');

/** 各阶段退出闸门（复用既有门禁词汇，不另造） */
const PHASE_EXIT_GATES = {
  P0: ['G0'],
  P1: ['G1', 'C-GOV-3'],
  P2: ['G2', 'C28', 'C29'],
  P3: ['G3', 'D1'],
  P4: ['G4', 'C-GOV-4', 'C-G11'],
  P5: ['G5', 'C-GOV-6']
};

/** 各阶段唯一写者（RACI 主责，与 SOP 名册一致） */
const PHASE_WRITER = {
  P0: 'sg-semantic',
  P1: 'sg-development',
  P2: 'sg-quality',
  P3: 'sg-insight',
  P4: 'sg-governance',
  P5: 'sg-supervisor'
};

class Orchestrator {
  constructor(opts = {}) {
    this.ledger = new ContractLedger({ reopenBudget: opts.reopenBudget != null ? opts.reopenBudget : 2, path: opts.ledgerPath || null });
    this.trace = { phases: [], gates: [], handoffs: [], signoff: null };
    this.currentPhase = null;
  }

  /** P0：建宪章、拿写者令牌（写者 = 该阶段主责） */
  start(charter) {
    if (!charter || !charter.scope) throw new Error('start: 宪章缺少 scope（range/bases/caliber）');
    this.charter = charter;
    this.ledger.acquireWriter(PHASE_WRITER.P0, 'P0');
    const c0 = this.ledger.registerContract('C0', charter, PHASE_WRITER.P0);
    this.trace.phases.push({ phase: 'P0', writer: PHASE_WRITER.P0 });
    return c0;
  }

  /**
   * 进入某阶段：校验主责 + 交接写者令牌（写者独占）。
   * @param {string} phase  'P0'~'P5'
   * @param {string} expert 申请进入的专家 ID
   */
  enterPhase(phase, expert) {
    const owner = PHASE_WRITER[phase];
    if (!owner) throw new Error(`enterPhase: 未知阶段 ${phase}`);
    if (owner !== expert) {
      throw new Error(`enterPhase ${phase}: 主责应为 ${owner}，收到 ${expert}（禁止越权进入）`);
    }
    if (this.ledger.writer && this.ledger.writer.expert !== expert) {
      this.ledger.transferWriter(this.ledger.writer.expert, expert, phase);
    } else if (!this.ledger.writer) {
      this.ledger.acquireWriter(expert, phase);
    }
    this.currentPhase = phase;
    this.trace.phases.push({ phase, writer: expert });
    return this.ledger.writer;
  }

  /**
   * 阶段退出：跑退出闸门，全绿才放行并冻结该阶段契约（C1~C5）。
   * @param {string} phase
   * @param {object} ctx  闸门上下文（按 PHASE_EXIT_GATES 各闸门需要填充）
   * @returns {{ok:boolean, failed?:Array, results:Array}}
   */
  exitPhase(phase, ctx = {}) {
    const ids = PHASE_EXIT_GATES[phase] || [];
    const results = runAll(ids, ctx);
    const sum = summarize(results);
    this.trace.gates.push(...results);
    if (!sum.allGreen) {
      return { ok: false, failed: sum.failed, results };
    }
    const ckey = 'C' + phase.slice(1);
    this.ledger.registerContract(ckey, ctx.contractPayload || { phase, passed: true }, PHASE_WRITER[phase]);
    return { ok: true, results };
  }

  /**
   * 给 sub-agent 的范围上下文（只装 C0 宪章 + 本阶段契约，非全量历史）。
   * @param {object} phaseContract 本阶段契约（C1~C5 之一）
   * @param {string} expert       接收上下文的专家
   */
  handoff(phaseContract, expert) {
    const sc = buildScopedContext(this.charter, phaseContract, { phase: this.currentPhase, writer: expert });
    this.trace.handoffs.push({ phase: this.currentPhase, expert, sizeKB: sc._estSizeKB });
    return sc;
  }

  /**
   * P5 签发：跑 G5 闸门 + 契约完整性校验，产出签收结论。
   * 稳定性采样（≥3 次 md5 一致）由调用方先行提供 stableMd5 标志。
   * @param {{allGreen:boolean, stableMd5:boolean, userConfirmed:boolean, fingerprint?:object, artifactPath?:string}} opts
   */
  signOff(opts = {}) {
    const g5 = runAll(['G5'], { allGreen: !!opts.allGreen, stableMd5: !!opts.stableMd5, userConfirmed: !!opts.userConfirmed })[0];
    const integrity = this.ledger.verifyIntegrity();
    const result = {
      g5,
      integrity,
      fingerprint: opts.fingerprint || null,
      artifactPath: opts.artifactPath || null,
      ok: g5.pass && integrity.ok && !!opts.userConfirmed
    };
    this.trace.signoff = result;
    return result;
  }

  /** 全链路快照（可落盘 trace） */
  snapshot() {
    return { charter: this.charter, trace: this.trace, ledger: this.ledger.snapshot() };
  }

  save() { this.ledger.save(); }
}

module.exports = { Orchestrator, PHASE_EXIT_GATES, PHASE_WRITER };
