/**
 * fast_lane.js · 单指标/已知指标查询短路路由
 *
 * 改造项：P1-4（落地 Fast-Lane 路由）
 *
 * 目标：对「查一下某指标」「某口径怎么算」「某科目 SQL 来源」这类轻量查询，
 * 直接走物化 SQL / 口径注册表，不建 team、不跑 P1~P4 全链，砍 TOKEN 与耗时。
 *
 * 判断逻辑：
 *   - 命中"单指标/单个指标/某指标/某科目" → 短路
 *   - 纯口径/定义/SQL来源 查询（不含 对标/降本/报告/全链路/分析 等重词）→ 短路
 *   - 其余（对标/本周/各工序/降本建议/报告/全链路）→ 走完整 P0~P5
 */

const SINGLE = /(单指标|单个指标|单一指标|某指标|某科目|一个指标|一个科目)/;
const LIGHT_LOOKUP = /(是多少|定义|口径|怎么算|如何计算|来源表|取数SQL|sql|来源|说明|什么意思)/;
const HEAVY = /(对标|本周|上周|各工序|各基地|报告|降本建议|降本|全链路|分析|全部|汇总|三公司|三钢)/;

/**
 * 是否走 Fast-Lane 短路。
 * @param {{text?:string, metric?:string, intent_type?:string}} intent
 */
function isFastLane(intent) {
  if (!intent) return false;
  const t = intent.text || '';
  if (SINGLE.test(t)) return true;
  const light = LIGHT_LOOKUP.test(t) && !HEAVY.test(t);
  // 显式给出单一 metric / intent_type 且非重型意图
  const singleMetric = !!intent.metric && !HEAVY.test(t);
  const singleIntent = intent.intent_type === 'metric_lookup' || intent.intent_type === 'caliber_query';
  return light || singleMetric || singleIntent;
}

/** 返回 'fast' 或 'full' */
function route(intent) {
  return isFastLane(intent) ? 'fast' : 'full';
}

module.exports = { isFastLane, route };
