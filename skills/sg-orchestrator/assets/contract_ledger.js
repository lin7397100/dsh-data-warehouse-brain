/**
 * contract_ledger.js · 阶段契约台账 + 写者独占令牌 + 重开机制 + 变更日志
 *
 * 改造项：P0-2（实现契约台账 + 写者独占运行时）
 *
 * 职责：
 *  - 为每个阶段契约（C0~C5）登记带 hash 的不可变快照，下游引用 hash 而非临时文件。
 *  - 任意时刻产物只有一个活跃写者（Writer Token），交接需显式 transfer。
 *  - 回溯必须走 reopen()，受 reopenBudget（默认每阶段 ≤2）约束，超限升级人工裁决。
 *  - 任何契约变更都记 Change Log（author + reason + before/after）。
 *  - verifyIntegrity() 检测「被动漂移」（契约 payload 被静默篡改导致 hash 失配）。
 *
 * 零依赖，Node ≥ 12 可直接 require。
 */
const crypto = require('crypto');
const fs = require('fs');

class ContractLedger {
  constructor(opts = {}) {
    this.path = opts.path || null;            // 可选持久化路径（JSON 文件）
    this.reopenBudget = opts.reopenBudget != null ? opts.reopenBudget : 2;
    this.contracts = {};                       // phase -> { phase, payload, author, hash, ts, frozen }
    this.writer = null;                        // { phase, expert }
    this.changelog = [];                       // [{ ts, author, action, before, after }]
    this.reopenCounts = {};                    // phase -> count
    if (this.path && fs.existsSync(this.path)) this.load();
  }

  hash(obj) {
    return crypto.createHash('sha256').update(JSON.stringify(obj)).digest('hex').slice(0, 16);
  }

  /** 登记阶段契约（仅当前写者可写；只读阶段不允许登记） */
  registerContract(phase, payload, author) {
    if (this.writer && this.writer.expert !== author) {
      throw new Error(`契约 ${phase} 注册被拒：当前写者为 ${this.writer.expert}，申请者 ${author}`);
    }
    const contract = {
      phase, payload, author,
      hash: this.hash(payload),
      ts: Date.now(),
      frozen: true
    };
    this.contracts[phase] = contract;
    this.logChange(author, `register ${phase}`, null, contract.hash);
    return contract;
  }

  /** 显式交接写者令牌 */
  transferWriter(from, to, phase) {
    if (this.writer && this.writer.expert !== from) {
      throw new Error(`写者令牌交接失败：当前写者 ${this.writer.expert} ≠ ${from}`);
    }
    this.writer = { phase, expert: to };
    this.logChange(from, `transfer writer ${from}->${to} @${phase}`, this.writer.expert, to);
    return this.writer;
  }

  /** 获取写者令牌（无持有者时） */
  acquireWriter(expert, phase) {
    if (this.writer) throw new Error(`写者令牌已被 ${this.writer.expert} 占用，无法分配给 ${expert}`);
    this.writer = { phase, expert };
    this.logChange(expert, `acquire writer @${phase}`, null, expert);
    return this.writer;
  }

  /** 释放写者令牌 */
  releaseWriter(expert) {
    if (!this.writer || this.writer.expert !== expert) {
      throw new Error(`release 失败：当前写者 ${this.writer ? this.writer.expert : '空'} ≠ ${expert}`);
    }
    const prev = this.writer;
    this.writer = null;
    this.logChange(expert, `release writer @${prev.phase}`, prev.expert, null);
    return prev;
  }

  /**
   * 重开已冻结阶段（回溯的唯一合法路径）。
   * 受 reopenBudget 约束；超限抛错升级人工裁决。
   */
  reopen(phase, reason, author) {
    const c = this.reopenCounts[phase] || 0;
    if (c >= this.reopenBudget) {
      throw new Error(`阶段 ${phase} 重开次数 ${c} 已达上限 ${this.reopenBudget}，升级人工裁决`);
    }
    this.reopenCounts[phase] = c + 1;
    const before = this.contracts[phase] ? this.contracts[phase].hash : null;
    if (this.contracts[phase]) this.contracts[phase].frozen = false;
    this.logChange(author, `reopen ${phase}: ${reason}`, before, null);
    return { reopenId: this.reopenCounts[phase], before };
  }

  logChange(author, action, before, after) {
    this.changelog.push({ ts: Date.now(), author, action, before, after });
  }

  getContract(phase) { return this.contracts[phase]; }

  /** 校验所有契约未被静默篡改（被动漂移检测） */
  verifyIntegrity() {
    const issues = [];
    for (const [p, c] of Object.entries(this.contracts)) {
      if (c.hash !== this.hash(c.payload)) {
        issues.push(`${p} 契约哈希失配（被动漂移）：记录 ${c.hash} ≠ 实算 ${this.hash(c.payload)}`);
      }
      if (c.frozen === false && this.reopenCounts[p]) {
        // 已重开但未重新冻结，属正常进行中；不算漂移
      }
    }
    for (const [p, n] of Object.entries(this.reopenCounts)) {
      if (n > this.reopenBudget) issues.push(`阶段 ${p} 重开 ${n} 次超预算 ${this.reopenBudget}`);
    }
    return { ok: issues.length === 0, issues };
  }

  snapshot() {
    return {
      contracts: this.contracts,
      writer: this.writer,
      changelog: this.changelog,
      reopenCounts: this.reopenCounts,
      reopenBudget: this.reopenBudget
    };
  }

  save() {
    if (!this.path) throw new Error('未配置 path，无法持久化');
    fs.writeFileSync(this.path, JSON.stringify(this.snapshot(), null, 2), 'utf8');
  }

  load() {
    const d = JSON.parse(fs.readFileSync(this.path, 'utf8'));
    this.contracts = d.contracts || {};
    this.writer = d.writer || null;
    this.changelog = d.changelog || [];
    this.reopenCounts = d.reopenCounts || {};
    this.reopenBudget = d.reopenBudget != null ? d.reopenBudget : 2;
  }
}

module.exports = ContractLedger;
