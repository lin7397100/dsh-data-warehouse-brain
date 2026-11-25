/**
 * gates.js · 六阶段退出闸门 + 既有门禁词汇的可调用校验器
 *
 * 改造项：P1-3（固化 SOP 闸门进编排技能）
 *
 * 设计：每个闸门 = 纯函数 (ctx) => { pass, evidence }。ctx 由调用方按阶段填充，
 * 校验器不读写文件/网络，便于在任意阶段本地跑、可组合、可复现。
 *
 * 复用既有词汇（不另造）：
 *   G0~G5   —— 六阶段退出闸门
 *   C-GOV-3 —— 数据源存在性
 *   C-GOV-4 —— 产物自证（元 + 万元 双单位，11 必含 + 22 禁含）
 *   C-GOV-6 —— 冻结锁前置（build/.LOCK）
 *   C-G11   —— 三形态断言（元 / 千分位 / 万元）
 *   C28/C29 —— 多产品集差异率 / 产品集一致性
 *   D1~D5   —— 下钻表真实落盘（<td> 真实存在）
 */

const GATES = {
  /* ===== 六阶段退出闸门 ===== */
  G0: {
    name: '意图已确认',
    gate: (c) => ({
      pass: !!(c.charter && c.charter.confirmed),
      evidence: c.charter ? (c.charter.confirmed ? '宪章已确认' : '宪章存在但未确认') : '宪章缺失'
    })
  },
  G1: {
    name: '数据源存在 + 取数闭合',
    gate: (c) => ({
      pass: !!c.dataSourceExists && c.rowCountClosed === true,
      evidence: `数据源=${c.dataSourceExists ? '存在' : '缺失'}；行数闭合=${c.rowCountClosed}`
    })
  },
  G2: {
    name: '三重闭合残差 = 0 + 双盲一致',
    gate: (c) => {
      const resid = Math.abs(c.residual || 0);
      const ok = resid < 1e-6 && c.doubleBlind === true;
      return { pass: ok, evidence: `残差=${resid}；双盲一致=${c.doubleBlind}` };
    }
  },
  G3: {
    name: '模板填充完成 + 图表非空',
    gate: (c) => ({
      pass: !!c.tablesFilled && c.chartsNonEmpty === true,
      evidence: `表格填充=${c.tablesFilled}；图表非空=${c.chartsNonEmpty}`
    })
  },
  G4: {
    name: 'C-GOV-4 + C-G11 + 语法零错',
    gate: (c) => {
      const ok = c.cgov4Pass === true && c.cg11Pass === true && c.syntaxOk === true;
      return { pass: ok, evidence: `C-GOV-4=${c.cgov4Pass}；C-G11=${c.cg11Pass}；语法零错=${c.syntaxOk}` };
    }
  },
  G5: {
    name: '全绿 + 稳定性采样 + 用户确认',
    gate: (c) => {
      const ok = c.allGreen === true && c.stableMd5 === true && c.userConfirmed === true;
      return { pass: ok, evidence: `全绿=${c.allGreen}；md5稳定=${c.stableMd5}；用户确认=${c.userConfirmed}` };
    }
  },

  /* ===== 既有门禁词汇 ===== */
  'C-GOV-3': {
    name: '数据源存在性',
    gate: (c) => ({ pass: !!c.srcExists, evidence: `权威源/数据文件存在=${c.srcExists}` })
  },
  'C-GOV-4': {
    name: '产物自证（元 + 万元 双单位）',
    gate: (c) => ({ pass: c.cgov4Pass === true, evidence: c.cgov4Detail || '需传入 cgov4Pass' })
  },
  'C-GOV-6': {
    name: '冻结锁前置（build/.LOCK）',
    gate: (c) => ({ pass: c.lockOk === true, evidence: c.lockDetail || '需传入 lockOk' })
  },
  'C-G11': {
    name: '三形态断言（元 / 千分位 / 万元）',
    gate: (c) => ({ pass: c.cg11Pass === true, evidence: c.cg11Detail || '需传入 cg11Pass' })
  },
  C28: {
    name: '多产品集差异率一致',
    gate: (c) => ({ pass: c.c28Pass === true, evidence: c.c28Detail || '需传入 c28Pass' })
  },
  C29: {
    name: '产品集一致性',
    gate: (c) => ({ pass: c.c29Pass === true, evidence: c.c29Detail || '需传入 c29Pass' })
  },
  D1: {
    name: '明细表真实落盘（<td> 真实存在）',
    gate: (c) => ({ pass: (c.d1TdCount || 0) > 0, evidence: `明细表 td 数=${c.d1TdCount || 0}` })
  }
};

/**
 * 运行单个闸门。若 id 未知，返回 pass=false。
 * @param {string} id
 * @param {object} ctx
 */
function runGate(id, ctx) {
  const g = GATES[id];
  if (!g) return { id, name: '(未知闸门)', pass: false, evidence: `未知闸门 ${id}` };
  const r = g.gate(ctx || {});
  return { id, name: g.name, pass: r.pass, evidence: r.evidence };
}

/** 批量运行一组闸门，返回数组 */
function runAll(ids, ctx) {
  return ids.map((id) => runGate(id, ctx));
}

/** 汇总：是否全绿 + 失败项列表 */
function summarize(results) {
  const failed = results.filter((r) => !r.pass);
  return { allGreen: failed.length === 0, failed, results };
}

module.exports = { GATES, runGate, runAll, summarize };
