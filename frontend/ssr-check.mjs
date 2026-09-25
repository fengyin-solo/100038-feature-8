/**
 * 无头渲染验证：经 Vite SSR 加载真实 .vue 组件（通过虚拟插件把源码里的
 * onMounted 重命名为 onServerPrefetch，使挂载时发起的 fetch 在服务端
 * 渲染前完成），mock fetch 走桩数据，断言面板/列表/老动作的关键渲染。
 */
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import compilerSfc from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { createSSRApp } from 'vue'

const TEMP_FILE = '/workspace/frontend/__inverter_ssr_tmp__.vue'
const source = readFileSync('/workspace/frontend/src/views/inverter/index.vue', 'utf-8')
  .replace('onMounted,', 'onServerPrefetch,')
  .replace('onMounted(reload)', 'onServerPrefetch(reload)')
  .replace(/<style[\s\S]*?<\/style>/, '')
writeFileSync(TEMP_FILE, source)

const server = await createServer({
  root: '/workspace/frontend',
  configFile: false,
  logLevel: 'error',
  plugins: [vue({ compiler: compilerSfc })],
  resolve: {
    alias: { '@': '/workspace/frontend/src' },
  },
  ssr: { noExternal: [] },
})

const efficiencyPayload = {
  days: ['2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25'],
  rated_min: 95.0,
  rated_max: 98.5,
  avg_tolerance: 0.5,
  total: 8,
  below_count: 1,
  mismatch_count: 1,
  devices: [
    {
      id: 2, code: 'INV-0102', array: 'A区1号方阵', model: 'SG250HX', status: '运行中',
      days: [], series: [
        { date: 'd0', value: 97.9 }, { date: 'd1', value: 97.1 }, { date: 'd2', value: 97.6 },
        { date: 'd3', value: 97.5 }, { date: 'd4', value: 97.4 }, { date: 'd5', value: 97.3 },
        { date: 'd6', value: 97.5 },
      ],
      average: 97.48, listed_avg: 97.8, below_rated: false, mismatch: false, present_days: 7,
    },
    {
      id: 3, code: 'INV-0103', array: 'A区2号方阵', model: 'SG225HX', status: '运行中',
      days: [], series: [
        { date: 'd0', value: 93.4 }, { date: 'd1', value: 93.9 }, { date: 'd2', value: 94.0 },
        { date: 'd3', value: 93.8 }, { date: 'd4', value: 93.6 }, { date: 'd5', value: 93.3 },
        { date: 'd6', value: 94.0 },
      ],
      average: 93.7, listed_avg: 93.8, below_rated: true, mismatch: false, present_days: 7,
    },
    {
      id: 7, code: 'INV-0302', array: 'C区2号方阵', model: 'SG250HX', status: '运行中',
      days: [], series: [
        { date: 'd0', value: 97.4 }, { date: 'd1', value: 96.8 }, { date: 'd2', value: 96.8 },
        { date: 'd3', value: 96.6 }, { date: 'd4', value: 96.8 }, { date: 'd5', value: 97.0 },
        { date: 'd6', value: 97.1 },
      ],
      average: 96.91, listed_avg: 97.9, below_rated: false, mismatch: true, present_days: 7,
    },
  ],
  missing_devices: [
    { id: 1, code: 'INV-0101', array: 'A区1号方阵', model: 'SG250HX', status: '待调试', reason: '设备待调试，尚未开始效率采集' },
  ],
}

const listPayload = {
  total: 8,
  items: [
    { id: 2, 设备编号: 'INV-0102', 设备型号: 'SG250HX', 额定功率: '250kW', 转换效率: '97.8%', 所属方阵: 'A区1号方阵', 通讯地址: '10.42.1.12', 投运日期: '2025-11-02', 运行状态: '运行中' },
    { id: 3, 设备编号: 'INV-0103', 设备型号: 'SG225HX', 额定功率: '225kW', 转换效率: '93.8%', 所属方阵: 'A区2号方阵', 通讯地址: '10.42.1.13', 投运日期: '2025-11-02', 运行状态: '运行中' },
    { id: 7, 设备编号: 'INV-0302', 设备型号: 'SG250HX', 额定功率: '250kW', 转换效率: '97.9%', 所属方阵: 'C区2号方阵', 通讯地址: '10.42.3.12', 投运日期: '2025-09-28', 运行状态: '运行中' },
    { id: 1, 设备编号: 'INV-0101', 设备型号: 'SG250HX', 额定功率: '250kW', 转换效率: '—', 所属方阵: 'A区1号方阵', 通讯地址: '10.42.1.11', 投运日期: '2026-09-20', 运行状态: '待调试' },
  ],
}

const fetchCalls = []
globalThis.fetch = async (url) => {
  const u = String(url)
  fetchCalls.push(u)
  if (u.includes('/api/inverter/efficiency')) return { ok: true, json: async () => efficiencyPayload }
  if (u.includes('/api/inverter?')) return { ok: true, json: async () => listPayload }
  throw new Error('unexpected url ' + u)
}

try {
  const Inverter = (await server.ssrLoadModule(TEMP_FILE)).default
  const html = await renderToString(createSSRApp(Inverter))
  writeFileSync('/tmp/inverter-ssr.html', html)

  const checks = [
    ['两个接口都被请求', fetchCalls.length === 2 && fetchCalls.some((u) => u.includes('/efficiency'))],
    ['面板标题', html.includes('近七天转换效率视图')],
    ['额定区间标注', html.includes('95%–98.5%')],
    ['设备 0102 卡片', html.includes('INV-0102')],
    ['设备 0103 卡片', html.includes('INV-0103')],
    ['低效卡片高亮 class', /class="below eff-card"/.test(html)],
    ['不一致卡片 mismatch class', /class="mismatch eff-card"/.test(html)],
    ['低效均值标红文案', html.includes('曲线均值 93.7%')],
    ['卡片标注所属方阵', html.includes('A区2号方阵')],
    ['不一致设备标记', html.includes('列表值 97.9% 对不上')],
    ['不一致单列区块', html.includes('面板效率与列表平均值对不上')],
    ['无数据设备单列区块', html.includes('未采集到效率数据的设备')],
    ['无数据原因', html.includes('设备待调试，尚未开始效率采集')],
    ['统计-低于额定 1 台', html.includes('低于额定区间 1 台')],
    ['统计-对不上 1 台', html.includes('与列表均值对不上 1 台')],
    ['统计-无数据 1 台', html.includes('无效率数据 1 台')],
    ['曲线 polyline 存在', html.includes('<polyline')],
    ['额定区间背景带', html.includes('rated-band')],
    ['列表行 id', html.includes('inv-row-3')],
    ['初始态无选中行', !html.includes('row-selected')],
    ['老表头-转换效率', html.includes('<th>转换效率</th>')],
    ['老表头-可执行动作', html.includes('<th>可执行动作</th>')],
    ['老动作-完成调试', html.includes('完成调试')],
    ['老按钮-登记逆变器', html.includes('登记逆变器')],
    ['老按钮-导出清单', html.includes('导出逆变器管理清单')],
    ['无加载失败提示', !html.includes('效率数据未获取')],
  ]

  let failed = 0
  for (const [name, ok] of checks) {
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`)
    if (!ok) failed++
  }
  console.log('\nfetch calls:', fetchCalls)

  // ---- 场景二：效率接口拿不到数据，不能把效率显示成正常 ----
  globalThis.fetch = async (url) => {
    const u = String(url)
    if (u.includes('/api/inverter/efficiency')) return { ok: false, status: 502, json: async () => ({}) }
    if (u.includes('/api/inverter?')) return { ok: true, json: async () => listPayload }
    throw new Error('unexpected url ' + u)
  }
  const ErrorApp = (await server.ssrLoadModule(TEMP_FILE)).default
  const errorHtml = await renderToString(createSSRApp(ErrorApp))
  const errorChecks = [
    ['失败态显示错误条', errorHtml.includes('效率数据未获取')],
    ['失败态不绘制任何曲线卡片', !errorHtml.includes('eff-chart')],
    ['失败态不显示无数据设备区块', !errorHtml.includes('未采集到效率数据的设备')],
    ['失败态列表仍正常渲染', errorHtml.includes('inv-row-2')],
    ['失败态老动作仍在', errorHtml.includes('登记逆变器')],
  ]
  for (const [name, ok] of errorChecks) {
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`)
    if (!ok) failed++
  }

  process.exitCode = failed ? 1 : 0
} finally {
  await server.close()
  try { unlinkSync(TEMP_FILE) } catch {}
}
