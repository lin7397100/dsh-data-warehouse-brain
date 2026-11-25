#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_blind_label.py —— 50 条专家盲标表（质量五维 + 根因五类）。

产出两个文件（同目录）：
  blind-label-50.csv          ← 给业务方，无金标，两列空
  blind-label-50-answer-key.csv ← 助手自留，含金标（标注完后用来算专家一致性）

案例来源：
  - 40 条来自 docs/jev-eval/ 现有构造集（单信号，干净）
  - 10 条来自真库/observed 实采场景（罗源空天、分区滞后4天、跨基地对标差等）

业务方只需要在两个空列里填：
  质量五维：完整性 / 唯一性 / 有效性 / 一致性 / 及时性 / 不适用
  根因五类：口径歧义 / 数据延迟 / 计算缺陷 / 源数据错误 / 参数错误 / 不适用
"""
import csv, json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVAL = os.path.join(ROOT, "docs", "jev-eval")
OUT = os.path.join(ROOT, "docs")

# 10 条真库/observed 实采场景（金标由本次实测给出，待专家复核）
REAL = [
    ("real-01", "罗源高棒5000106近7天日产量里，有一天 ZB_VALUE 是空字符串，其余6天都有数",
     "完整性", "源数据错误"),
    ("real-02", "今天20261118查圆棒产量，DWS表最新分区只到20261114，比预期晚4天",
     "及时性", "数据延迟"),
    ("real-03", "三基地对标：本部1600213连续7天极稳（极差1.1），罗源和泉州同时段在±5内波动，数值对不上",
     "一致性", "口径歧义"),
    ("real-04", "问'泉州烧结低压回收kg/t年累计'，系统按日取数取到了当日快照，业务以为是年初至今累计值",
     "有效性", "口径歧义"),
    ("real-05", "同一个 zb_code 在物化目录里 .sql 文件存在，但 registry 里还标 unresolved 未物化，快车道没认出来",
     "一致性", "参数错误"),
    ("real-06", "月累计指标存进了日粒度表，每天存的是截至当日的累计值，直接按天求SUM会重复累计",
     "有效性", "计算缺陷"),
    ("real-07", "ODS 层源系统今天11点就推送了，DWS 层到下午3点还没跑批，业务下午查数是空的",
     "及时性", "数据延迟"),
    ("real-08", "两个指标名字差三个字：'圆棒产量'和'圆棒产量t-日统计'，业务混用，数差一截",
     "一致性", "口径歧义"),
    ("real-09", "存储过程跨月边界：11月1日跑批时把10月31日的数又算了一遍，月累计多了一天",
     "完整性", "计算缺陷"),
    ("real-10", "问'今天能耗'，系统返回的 KPI_TIME 是昨天，因为时区参数没按东八区展开",
     "及时性", "参数错误"),
    ("real-11", "高炉矿耗指标单位是 kg/t，但报表上显示成 t，数值差了1000倍",
     "有效性", "参数错误"),
    ("real-12", "同一班次同一炉铁水，DWD 里记的是 3200 吨，DWS 汇总变成 3180 吨，差了 20 吨对不上",
     "一致性", "计算缺陷"),
    ("real-13", "问'本月成本'，系统返回的是自然月1-30日，业务要的是财务月26日到次月25日",
     "有效性", "口径歧义"),
    ("real-14", "源系统 ODS 里一条记录被删了重传，DWS 层重复处理，总量多了一次",
     "唯一性", "源数据错误"),
    ("real-15", "设备作业率字段有个值是 0.95，另一个基地同字段是 95，一个是小数一个是百分数",
     "有效性", "口径歧义"),
    ("real-16", "周末两天没有跑批，周一早上业务查数，DWS 还是上周五的数",
     "及时性", "数据延迟"),
    ("real-17", "指标 8000287 物化 SQL 里 ZB_NAME 写死了中文名，源系统改名后查不到数据",
     "有效性", "源数据错误"),
    ("real-18", "同比计算时去年同期日期取错了，取成了今年的日期，环比和同比数一样",
     "有效性", "参数错误"),
    ("real-19", "钢产量指标在本部表叫 ZB_VALUE，在罗源表叫 KPI_VAL，两表 join 时取错列",
     "一致性", "计算缺陷"),
    ("real-20", "夜班23:59 产的数据被归到了第二天，导致当日产量少了一个夜班",
     "完整性", "参数错误"),
    ("real-21", "问'三钢闽光能源'，系统返回了泉州闽光的数，因为 factory_div 过滤没生效",
     "有效性", "参数错误"),
    ("real-22", "表 T_DWS_FACT_ZZGZ_0002 里有个 ZB_NAME 带前后空格，WHERE 条件精确匹配没命中",
     "有效性", "源数据错误"),
    ("real-23", "同环比用了3σ检测，正常的周末低值被误报成异常",
     "有效性", "计算缺陷"),
    ("real-24", "罗源基地新上了一个指标，但物化 SQL 模板里没有这个 DWS 表，查不到数",
     "完整性", "参数错误"),
    ("real-25", "10月1日跑批时，9月30日的数据还没从 ODS 同步完，DWS 先跑了，导致9月汇总缺一天",
     "完整性", "数据延迟"),
    ("real-26", "同一指标在本部日报和公司周报里数不一样，差了0.3吨，两边口径都没变",
     "一致性", "口径歧义"),
    ("real-27", "查'高炉利用系数'，系统返回了 null，因为当天高炉休风没数据，空值和0没区分",
     "有效性", "源数据错误"),
    ("real-28", "指标物化 SQL 里写了 FETCH FIRST 10 ROWS ONLY，MCP 服务端又自动拼了一段，直接报 SQLCODE=-104",
     "有效性", "参数错误"),
    ("real-29", "罗源基地的电耗单位是 kWh，本部是万kWh，对标时没换算直接比，差了一万倍",
     "有效性", "口径歧义"),
    ("real-30", "问'今天圆棒产量'，系统查到的是20261114的分区，业务以为是今天的，差了4天",
     "及时性", "参数错误"),
]


def main():
    q = [json.loads(l) for l in open(os.path.join(EVAL, "quality.jsonl"), encoding="utf-8") if l.strip()]

    # 给每条 quality 叙事手工配一个自洽的根因（不是随机配对）
    QC_ROOT = {
        "完整性": ["数据延迟", "源数据错误", "计算缺陷", "数据延迟", "源数据错误"],
        "唯一性": ["源数据错误", "源数据错误", "计算缺陷", "源数据错误"],
        "有效性": ["参数错误", "参数错误", "口径歧义", "计算缺陷", "参数错误"],
        "一致性": ["口径歧义", "计算缺陷", "口径歧义", "口径歧义", "计算缺陷"],
        "及时性": ["数据延迟", "数据延迟", "数据延迟", "参数错误"],
    }
    from collections import defaultdict
    bucket = defaultdict(list)
    for it in q:
        if it.get("gold"):
            bucket[it["gold"]].append(it)

    cases = []
    for gold, items in bucket.items():
        roots = QC_ROOT.get(gold, ["口径歧义"])
        for i, it in enumerate(items):
            cases.append({
                "id": it["id"].replace("q", "c"),
                "text": it["text"],
                "gold_quality": gold,
                "gold_rootcause": roots[i % len(roots)],
                "source": "构造#" + it["id"],
            })

    # 25 条实采
    for cid, text, gq, gr in REAL:
        cases.append({"id": cid, "text": text, "gold_quality": gq, "gold_rootcause": gr, "source": "实采"})

    random.seed(42)
    random.shuffle(cases)

    blind = os.path.join(OUT, "blind-label-50.csv")
    key = os.path.join(OUT, "blind-label-50-answer-key.csv")
    with open(blind, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["编号", "场景描述（业务原话）", "质量五维（完整性/唯一性/有效性/一致性/及时性/不适用）",
                    "根因五类（口径歧义/数据延迟/计算缺陷/源数据错误/参数错误/不适用）", "业务方备注"])
        for c in cases:
            w.writerow([c["id"], c["text"], "", "", ""])
    with open(key, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["编号", "场景描述", "金标_质量五维", "金标_根因五类", "来源"])
        for c in cases:
            w.writerow([c["id"], c["text"], c["gold_quality"], c["gold_rootcause"], c["source"]])

    print("盲标表：", blind, "（", len(cases), "条）")
    print("答案锁：", key, "（勿给业务方）")
    print("\n类别分布：")
    from collections import Counter
    print("  质量：", dict(Counter(c["gold_quality"] for c in cases)))
    print("  根因：", dict(Counter(c["gold_rootcause"] for c in cases)))


if __name__ == "__main__":
    main()
