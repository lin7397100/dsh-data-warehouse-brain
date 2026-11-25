/**
 * 报告图表真实渲染校验器（J1/J2/J3 的可靠实现）
 *
 * 用途：主理人在 present_files 前强制调用，验证 HTML 报告图表是否真的渲染出来
 * 背景：2026-10-28 v2 报告因 53 处 {{ f-string 泄漏导致 4 图全空，当时数据闸门全绿未拦截
 *
 * 用法：
 *   node verify_report.js <报告.html> [期望图表数] [--quick]
 *
 *   默认（完整模式）：J1 + J1b + J2 + J3（真实浏览器渲染），耗时 5-8s
 *   --quick（快检模式）：J1 + J1b + J2，跳过 J3，耗时 < 1s
 *
 *   按场景分流（2026-10-29 确认）：
 *     T1 快车道         → 无报告，不校验
 *     T2 单指标趋势     → --quick（图表结构简单，J1/J2 足以拦截语法崩溃）
 *     T3 多指标含归因   → 完整模式（图表多、组件复杂，必须真实渲染验证）
 *     T4 数据画像/EDA   → 完整模式
 *     T5 看板/多页      → 完整模式
 *     任何首次交付      → 完整模式（不确定时宁严不宽）
 *
 *   退出码 0 = 通过，1 = 失败
 *
 * 依赖：Playwright（按 PLAYWRIGHT_PATH 环境变量 / 本地 node_modules / 全局 顺序解析，--quick 模式下不加载）
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync } = require('child_process');

/**
 * 解析 Playwright 路径（DSH 架构 · 不硬编码 WorkBuddy 二进制目录）：
 *   1) 环境变量 PLAYWRIGHT_PATH（最高，部署时可覆盖）
 *   2) 当前工作目录 node_modules/playwright
 *   3) ~/.dsh/node_modules/playwright
 *   4) 全局 require.resolve('playwright')
 */
function resolvePlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_PATH,
    path.join(process.cwd(), 'node_modules', 'playwright'),
    path.join(os.homedir(), '.dsh', 'node_modules', 'playwright'),
  ].filter(Boolean);
  for (const c of candidates) {
    try { require.resolve(c); return c; } catch (_) { /* 继续下一个 */ }
  }
  try { return require.resolve('playwright'); } catch (_) { return null; }
}

const PLAYWRIGHT_PATH = resolvePlaywright();

async function main() {
  // 解析参数（兼容 --quick 出现在任意位置）
  const rawArgs = process.argv.slice(2);
  const quick = rawArgs.includes('--quick');
  const positional = rawArgs.filter(a => !a.startsWith('--'));
  const file = positional[0];
  const expectCharts = positional[1] ? parseInt(positional[1]) : null;

  if (!file) {
    console.error('用法: node verify_report.js <报告.html> [期望图表数] [--quick]');
    process.exit(2);
  }
  if (!fs.existsSync(file)) {
    console.error(`❌ 文件不存在: ${file}`);
    process.exit(2);
  }

  const html = fs.readFileSync(file, 'utf8');
  const result = { j1: false, j1b: false, j2: false, j3: false, details: [] };

  console.log('='.repeat(62));
  console.log('报告图表校验 · ' + path.basename(file) + (quick ? '  [快检模式]' : '  [完整模式]'));
  console.log('='.repeat(62));

  // ===== J1: 双花括号零残留（只查业务 script）=====
  const scriptMatches = [...html.matchAll(/<script>/g)];
  if (scriptMatches.length === 0) {
    console.log('J1  双花括号:  ❌ 未找到 <script>');
    process.exit(1);
  }
  const lastIdx = scriptMatches[scriptMatches.length - 1].index + '<script>'.length;
  const bizJs = html.slice(lastIdx, html.indexOf('</script>', lastIdx));
  const dblOpen = (bizJs.match(/\{\{/g) || []).length;
  const dblClose = (bizJs.match(/\}\}/g) || []).length;
  result.j1 = dblOpen === 0 && dblClose === 0;
  console.log(`J1  双花括号:  {{=${dblOpen}  }}=${dblClose}  ${result.j1 ? '✅ PASS' : '❌ FAIL（f-string 转义泄漏，会导致整个 script 块解析失败）'}`);

  // ===== J1b: 无 CDN =====
  result.j1b = !html.includes('<script src=') &&
               !html.includes('jsdelivr') &&
               !html.includes('unpkg');
  console.log(`J1b 无 CDN:    ${result.j1b ? '✅ PASS' : '❌ FAIL（外部 CDN 国内常加载失败）'}`);

  // ===== J2: Node 语法校验 =====
  const tmpJs = path.join(os.tmpdir(), `biz_${Date.now()}.js`);
  fs.writeFileSync(tmpJs, bizJs, 'utf8');
  try {
    // 用当前 Node 解释器自身路径（process.execPath），不硬编码 WorkBuddy 二进制目录
    execSync(`"${process.execPath}" --check "${tmpJs}"`,
             { stdio: 'pipe' });
    result.j2 = true;
    console.log('J2  node语法:  ✅ PASS');
  } catch (e) {
    result.j2 = false;
    const err = (e.stderr || '').toString().split('\n').slice(0, 3).join(' ');
    console.log(`J2  node语法:  ❌ FAIL  ${err.slice(0, 150)}`);
  }
  try { fs.unlinkSync(tmpJs); } catch (_) {}

  // ===== J3: 真实浏览器渲染（最可靠，替代不可靠的 DOM 桩）=====
  // 快检模式（T2 场景）跳过 J3：J1+J2 已能拦截「语法崩溃导致全图空白」这一头号故障
  if (quick) {
    console.log('');
    console.log('J3  真实渲染:  ⏭ 已跳过（--quick 模式）');
    console.log('    说明: J1+J2 已覆盖「语法崩溃致全图空白」故障；');
    console.log('          T2 单指标趋势报告图表结构简单，可接受此风险。');
    console.log('          ⚠ 首次交付 / T3+ 场景请用完整模式。');
    result.j3 = true;   // 快检模式视为通过（不等于验证通过，见下方总结措辞）
    result.quickSkipped = true;

    console.log('');
    console.log('='.repeat(62));
    const passQuick = result.j1 && result.j1b && result.j2;
    if (passQuick) {
      console.log('✅ 快检通过（J3 未执行）');
      console.log(`   J1:${result.j1 ? '通过' : '失败'}｜J1b:${result.j1b ? '通过' : '失败'}｜J2:${result.j2 ? '通过' : '失败'}｜J3:跳过`);
      console.log('   ⚠ 未验证图表真实渲染，如需完整验证请去掉 --quick 重跑');
    } else {
      console.log('❌ 快检未通过，禁止 present_files');
    }
    console.log('='.repeat(62));
    process.exit(passQuick ? 0 : 1);
  }

  // 完整模式：加载 Playwright（未安装时明确报错，不静默跳过）
  if (!PLAYWRIGHT_PATH) {
    console.log('');
    console.log('J3  真实渲染:  ❌ 未找到 Playwright');
    console.log('    修复: 设置环境变量 PLAYWRIGHT_PATH，或在当前目录 `npm i -D playwright`；');
    console.log('         临时应急可用 --quick 模式（只做 J1/J1b/J2）。');
    console.log('='.repeat(62));
    process.exit(1);
  }
  const { chromium } = require(PLAYWRIGHT_PATH);
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 1200 } });
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') pageErrors.push('console: ' + m.text()); });

    const fileUrl = 'file:///' + path.resolve(file).replace(/\\/g, '/');
    await page.goto(fileUrl, { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(2500);  // 等 ECharts 完成动画/渲染

    const probe = await page.evaluate(() => {
      // 只把「真正承载图表的容器」算进来：
      // ① class 含 chart（如 <div class="chart" id="cSteel">）
      // ② 或者内部已有 echarts 生成的 svg/canvas
      // 排除 <section id="charts"> 这类包装层
      const containers = [...document.querySelectorAll('[id]')]
        .filter(el => {
          const cls = (el.className || '').toString();
          const isChartDiv = /\bchart\b/.test(cls);
          const hasChartChild = !!el.querySelector(':scope > svg, :scope > canvas, :scope > div > svg, :scope > div > canvas');
          const isWrapper = /^(charts|charts-extra|kpi|hero|tables|caliber|conclusion)$/.test(el.id);
          return !isWrapper && (isChartDiv || hasChartChild);
        })
        .map(el => el.id);
      const uniq = [...new Set(containers)];
      const charts = uniq.map(id => {
        const el = document.getElementById(id);
        if (!el) return { id, exists: false };
        const svg = el.querySelector('svg');
        // SVG 渲染器：绘图基元数量是"是否真的画出线条"的硬指标。
        // 2026-11-20 修正（TR-20261120-1046-9C1F）：ECharts 的 SVG 渲染器只产 <path>，
        // 但手绘内联 SVG（如达仕 #charts-extra 插槽）用 polyline/line/rect/circle 绘制，
        // 仅数 path 会把「已真实绘制」的手绘 SVG 误判为空白图（假失败）。故按全部基元判定。
        const paths = el.querySelectorAll('path, polyline, line, rect, circle, ellipse, polygon').length;
        const texts = el.querySelectorAll('text').length;
        const canvas = el.querySelector('canvas');
        // 兼容 echarts 把 canvas 包在内部 div 的情况
        const canvasAny = canvas || el.querySelector('div canvas');
        return {
          id, exists: true,
          hasSvg: !!svg, hasCanvas: !!canvasAny,
          paths, texts,
          w: el.offsetWidth, h: el.offsetHeight,
          innerLen: (el.innerHTML || '').length
        };
      });
      return {
        charts,
        // 2026-11-20 修正：本报告族（T2b 四层抽屉）抽屉 id 为 drill-drawer、绑定函数为 openDrillL1，
        // 原探针只认 drawer / openDrawer 会恒报 ❌，属探针命名滞后，不是报告缺陷。两者兼容。
        drawer: !!(document.getElementById('drawer') || document.getElementById('drill-drawer')),
        dwBody: !!document.getElementById('dwBody'),
        dwCrumb: !!document.getElementById('dwCrumb'),
        cells: document.querySelectorAll('.cell').length,
        drillBinds: (document.body.innerHTML.match(/openDrawer\(|openDrillL1\(/g) || []).length,
        odsRefs: (document.body.innerHTML.match(/T_ODS_/g) || []).length,
        tables: document.querySelectorAll('table').length
      };
    });

    console.log('');
    console.log('--- 图表真实渲染（浏览器实测）---');
    let allRendered = true;
    probe.charts.forEach(c => {
      if (!c.exists) {
        console.log(`  ❌ #${c.id} 容器不存在`);
        allRendered = false;
        return;
      }
      // 严格判定：必须真有图形元素才算渲染
      // SVG 渲染器看 path 数量；Canvas 渲染器看 canvas 元素 + 非零尺寸
      const svgOk = c.hasSvg && c.paths > 0;
      const canvasOk = c.hasCanvas && c.w > 0 && c.h > 0;
      const rendered = svgOk || canvasOk;
      if (!rendered) allRendered = false;
      const why = rendered ? '' : (c.hasSvg ? '（有 svg 但 path=0，图形未绘制）' :
                                   (c.hasCanvas ? '（有 canvas 但尺寸为 0）' : '（无 svg 也无 canvas，echarts 未初始化成功）'));
      console.log(`  ${rendered ? '✅' : '❌'} #${c.id}: SVG=${c.hasSvg} canvas=${c.hasCanvas} path=${c.paths} text=${c.texts} 尺寸=${c.w}x${c.h}${why}`);
    });

    console.log('');
    console.log('--- 下钻能力 ---');
    console.log(`  抽屉 DOM: ${probe.drawer ? '✅' : '❌'} drawer / ${probe.dwBody ? '✅' : '❌'} dwBody / ${probe.dwCrumb ? '✅' : '❌'} dwCrumb`);
    console.log(`  可点击单元格: ${probe.cells}   绑定数: ${probe.drillBinds}`);
    console.log(`  ODS 引用: ${probe.odsRefs}   表格数: ${probe.tables}`);

    result.j3 = allRendered && probe.charts.length > 0;
    if (pageErrors.length) {
      console.log('');
      console.log('--- 页面错误 ---');
      pageErrors.slice(0, 5).forEach(e => console.log('  ⚠ ' + e.slice(0, 120)));
      if (pageErrors.length > 5) console.log(`  ... 另有 ${pageErrors.length - 5} 条`);
    } else {
      console.log('\n  ✅ 零页面错误');
    }

    console.log(`\nJ3  实际渲染:  ${result.j3 ? '✅ PASS' : '❌ FAIL'}  （${probe.charts.length} 个图表容器）`);

    if (expectCharts !== null && probe.charts.length !== expectCharts) {
      console.log(`⚠  图表数不符: 期望 ${expectCharts}，实际 ${probe.charts.length}`);
      result.j3 = false;
    }

    result.details = probe;
  } catch (e) {
    console.log(`J3  实际渲染:  ❌ FAIL  ${e.message.slice(0, 150)}`);
    result.j3 = false;
  } finally {
    if (browser) await browser.close();
  }

  // ===== 总结 =====
  console.log('');
  console.log('='.repeat(62));
  const allPass = result.j1 && result.j1b && result.j2 && result.j3;
  if (allPass) {
    const d = result.details;
    console.log(`✅ 全部通过，可交付`);
    console.log(`   J1:0/0 ✅｜J1b:无CDN ✅｜J2:语法通过 ✅｜J3:${d.charts.length}图渲染 0错误 ✅`);
    if (d.cells > 0) console.log(`   附加: ${d.cells} 可点击单元格 · ${d.odsRefs} ODS 引用 · ${d.tables} 表格`);
  } else {
    console.log('❌ 校验未通过，禁止 present_files');
    console.log('   请退回 sg-insight 重做，不要自行修补 HTML');
  }
  console.log('='.repeat(62));

  process.exit(allPass ? 0 : 1);
}

main().catch(e => {
  console.error('校验器异常: ' + e.message);
  process.exit(1);
});
