/**
 * caliber_registry.js · 口径 / 指标 / 字段契约 预注册库
 *
 * 改造项：P2-5（口径/指标预注册成 skill 库，免重复推导）
 *
 * 直接堵住本次 trace 的空白图根因：数据层字段名 = quota/imp/me，而渲染层一度写成
 * quotaW/impact/matchedPC（未赋值 → comparableRows 返回空 → C1/C2 空白）。
 * 本注册表把"字段契约"固化为可校验对象，下游渲染层必须按 FIELD_CONTRACT 字面取数。
 *
 * 零依赖，Node ≥ 12 可直接 require。
 */

const CALIBERS = {
  L3c: {
    id: 'L3c',
    name: 'L3c 同域口径（唯一可加口径）',
    formula: 'Σ(matched-product actual cost) ÷ Σ(7-subject-complete product output)',
    supersedes: ['L3a', 'L3b', 'v1'],
    note: '仅 L3c 具备可加性；L3a/L3b/v1 不可加，已退役，禁止在新任务中切换回退',
    locked: true
  }
};

/** 数据层 → 渲染层 字段契约（字面一致，禁止别名漂移） */
const FIELD_CONTRACT = {
  quota: { meaning: '定额成本', source: 'data_L3C.js / 权威源字段 q', unit: '元', renderAlias: 'quota' },
  imp:   { meaning: '差异影响额(元/4日)', source: 'data_L3C.js imp', unit: '元', renderAlias: 'imp' },
  me:    { meaning: '匹配产量(吨)', source: 'data_L3C.js me', unit: '吨', renderAlias: 'me' },
  vari:  { meaning: '差异额(元/吨)', source: 'data_L3C.js vari', unit: '元/吨', renderAlias: 'vari' },
  rate:  { meaning: '差异率(%)', source: 'data_L3C.js rate', unit: '%', renderAlias: 'rate' },
  act:   { meaning: '实际单位成本(元/吨)', source: 'data_L3C.js act', unit: '元/吨', renderAlias: 'act' }
};

/** 关键指标预注册（免重复推导） */
const INDICATORS = {
  '80030': {
    name: '钢铁料耗',
    caliber: 'L3c',
    ZB: { 本部: '1600213', 罗源: '5000106', 泉州: '6012800' },
    note: '近7日 = 昨天往前推7天含昨天（例 09-24 窗口 = 09-17~09-23）'
  }
};

const FORBIDDEN_ALIASES = ['quotaW', 'impact', 'matchedPC', 'VARIANCE_W', 'VARIANCE_RATE_W', 'IMPACT_4D', 'QUOTA_WEIGHTED'];

function resolveCaliber(id) { return CALIBERS[id] || null; }
function fieldOf(name) { return FIELD_CONTRACT[name] || null; }
function indicator(id) { return INDICATORS[id] || null; }

/**
 * 校验一行数据是否满足字段契约（渲染层取数字段必须与 FIELD_CONTRACT 字面一致）。
 * @param {object} row
 * @returns {{ok:boolean, missing:string[], forbiddenHit:string[]}}
 */
function assertFieldContract(row) {
  const required = Object.keys(FIELD_CONTRACT);
  const missing = required.filter((k) => !(k in row));
  const forbiddenHit = FORBIDDEN_ALIASES.filter((a) => a in row);
  return { ok: missing.length === 0 && forbiddenHit.length === 0, missing, forbiddenHit };
}

module.exports = {
  CALIBERS, FIELD_CONTRACT, INDICATORS, FORBIDDEN_ALIASES,
  resolveCaliber, fieldOf, indicator, assertFieldContract
};
