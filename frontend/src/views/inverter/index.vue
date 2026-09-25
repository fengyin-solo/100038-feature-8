<template>
  <section class="page" data-module="inverter">
    <header class="page-head">
      <div>
        <h2>逆变器管理管理</h2>
        <p class="page-desc">维护逆变器，围绕设备编号、设备型号、额定功率、转换效率做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记逆变器</button>
        <button class="btn" type="button" @click="exportRows">导出逆变器管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <!-- 近七天转换效率视图：与列表共用同一套筛选条件 -->
    <section class="eff-panel" :class="{ collapsed: !panelOpen }">
      <header class="eff-head">
        <div>
          <h3>近七天转换效率视图</h3>
          <p class="page-desc">
            额定区间 {{ efficiency?.rated_min ?? '95.0' }}%–{{ efficiency?.rated_max ?? '98.5' }}%，按设备编号排列；
            低于额定下限的曲线红色高亮，点击卡片可在下方列表定位设备。
          </p>
        </div>
        <div class="eff-head-actions">
          <button class="btn ghost" type="button" @click="loadEfficiency">刷新曲线</button>
          <button class="btn ghost" type="button" @click="panelOpen = !panelOpen">
            {{ panelOpen ? '收起面板' : '展开面板' }}
          </button>
        </div>
      </header>

      <div v-if="panelOpen" class="eff-body">
        <div v-if="effError" class="eff-fetch-error">
          效率数据未获取（{{ effError }}），已隐藏曲线，避免把效率误显示成正常。
          <button class="link" type="button" @click="loadEfficiency">重试</button>
        </div>

        <template v-else>
          <div class="eff-summary">
            <span class="eff-chip">当前条件设备 {{ efficiency?.total ?? 0 }} 台</span>
            <span class="eff-chip" :class="{ 'chip-warn': (efficiency?.below_count ?? 0) > 0 }">
              低于额定区间 {{ efficiency?.below_count ?? 0 }} 台
            </span>
            <span class="eff-chip" :class="{ 'chip-warn': (efficiency?.mismatch_count ?? 0) > 0 }">
              与列表均值对不上 {{ efficiency?.mismatch_count ?? 0 }} 台
            </span>
            <span class="eff-chip" :class="{ 'chip-warn': (efficiency?.missing_devices.length ?? 0) > 0 }">
              无效率数据 {{ efficiency?.missing_devices.length ?? 0 }} 台
            </span>
          </div>

          <div v-if="effLoading" class="eff-loading">效率曲线加载中…</div>

          <template v-else-if="efficiency">
            <div v-if="efficiency.devices.length" class="eff-grid">
              <article
                v-for="device in efficiency.devices"
                :id="`eff-card-${device.id}`"
                :key="device.id"
                class="eff-card"
                :class="{
                  selected: selectedId === device.id,
                  below: device.below_rated,
                  mismatch: device.mismatch,
                }"
                role="button"
                tabindex="0"
                :title="`选中 ${device.code}，并在列表中定位`"
                @click="selectDevice(device.id)"
                @keydown.enter.prevent="selectDevice(device.id)"
              >
                <div class="eff-card-head">
                  <strong>{{ device.code }}</strong>
                  <span class="eff-array">{{ device.array }}</span>
                </div>
                <svg class="eff-chart" viewBox="0 0 220 84" aria-hidden="true">
                  <!-- 额定区间背景带 -->
                  <rect
                    :x="PAD_L"
                    :y="yVal(efficiency.rated_max)"
                    :width="220 - PAD_L - PAD_R"
                    :height="yVal(efficiency.rated_min) - yVal(efficiency.rated_max)"
                    class="rated-band"
                  />
                  <line :x1="PAD_L" :x2="220 - PAD_R" :y1="yVal(efficiency.rated_min)" :y2="yVal(efficiency.rated_min)" class="rated-line" />
                  <line :x1="PAD_L" :x2="220 - PAD_R" :y1="yVal(efficiency.rated_max)" :y2="yVal(efficiency.rated_max)" class="rated-line" />
                  <text :x="2" :y="yVal(efficiency.rated_max) + 3" class="axis-label">{{ efficiency.rated_max }}%</text>
                  <text :x="2" :y="yVal(efficiency.rated_min) + 3" class="axis-label">{{ efficiency.rated_min }}%</text>
                  <!-- 缺测日期之间断开，不连线 -->
                  <polyline
                    v-for="(seg, segIndex) in segments(device)"
                    :key="segIndex"
                    class="eff-line"
                    :points="seg"
                  />
                  <template v-for="(point, pointIndex) in device.series" :key="pointIndex">
                    <circle
                      v-if="point.value !== null"
                      :cx="xIdx(pointIndex)"
                      :cy="yVal(point.value)"
                      r="2.4"
                      class="eff-dot"
                      :class="{ 'dot-low': point.value < efficiency.rated_min }"
                    />
                  </template>
                </svg>
                <div class="eff-card-foot">
                  <span v-if="device.present_days < 7" class="eff-gap-hint">
                    近七天仅 {{ device.present_days }} 天有数据
                  </span>
                  <span class="eff-avg" :class="{ 'avg-low': device.below_rated }">
                    曲线均值 {{ device.average }}%
                  </span>
                  <span
                    v-if="device.mismatch"
                    class="mismatch-tag"
                    :title="`列表登记的转换效率为 ${device.listed_avg}%，与曲线均值偏差超过 ${efficiency.avg_tolerance} 个百分点`"
                  >
                    ⚠ 列表值 {{ device.listed_avg }}% 对不上
                  </span>
                </div>
              </article>
            </div>
            <p v-else class="eff-empty">当前筛选条件下没有采到效率数据的设备。</p>

            <div v-if="efficiency.mismatch_count" class="eff-flag-list">
              <h4>面板效率与列表平均值对不上</h4>
              <ul>
                <li v-for="device in mismatchDevices" :key="device.id">
                  <button class="link" type="button" @click="selectDevice(device.id)">
                    {{ device.code }}
                  </button>
                  <span class="eff-array">（{{ device.array }}）</span>
                  <span class="mismatch-tag">
                    曲线均值 {{ device.average }}% / 列表登记 {{ device.listed_avg }}%
                  </span>
                </li>
              </ul>
            </div>

            <div v-if="efficiency.missing_devices.length" class="eff-flag-list">
              <h4>未采集到效率数据的设备（不绘制曲线，不计入效率均值）</h4>
              <ul>
                <li v-for="device in efficiency.missing_devices" :key="device.id">
                  <button class="link" type="button" @click="selectDevice(device.id)">
                    {{ device.code }}
                  </button>
                  <span class="eff-array">（{{ device.array }}）</span>
                  <span class="missing-reason">{{ device.reason }}</span>
                </li>
              </ul>
            </div>
          </template>
        </template>
      </div>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :id="`inv-row-${row.id}`"
          :key="String(row.id)"
          :class="{ 'row-selected': selectedId === row.id }"
          role="button"
          tabindex="0"
          :title="`在效率视图中高亮 ${String(row['设备编号'] ?? '')}`"
          @click="selectFromList(row)"
          @keydown.enter.prevent="selectFromList(row)"
        >
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions" @click.stop>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无逆变器管理数据，可先登记逆变器</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条逆变器管理记录</span>
      <span v-if="locateMessage" class="locate-text">{{ locateMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface EfficiencyPoint {
  date: string
  value: number | null
}

interface EfficiencyDevice {
  id: number
  code: string
  array: string
  model: string
  status: string
  days: string[]
  series: EfficiencyPoint[]
  average: number
  listed_avg: number | null
  below_rated: boolean
  mismatch: boolean
  present_days: number
}

interface MissingDevice {
  id: number
  code: string
  array: string
  model: string
  status: string
  reason: string
}

interface EfficiencyOverview {
  days: string[]
  rated_min: number
  rated_max: number
  avg_tolerance: number
  total: number
  devices: EfficiencyDevice[]
  missing_devices: MissingDevice[]
  below_count: number
  mismatch_count: number
}

const ENDPOINT = '/api/inverter'
const columns = ["设备编号", "设备型号", "额定功率", "转换效率", "所属方阵", "通讯地址", "投运日期", "运行状态"]
const actions = ["完成调试", "登记故障", "退役设备"]
const statuses = ["待调试", "运行中", "故障停机", "已退役"]
const stats = [{"label": "在运逆变器", "value": 0}, {"label": "故障停机", "value": 0}, {"label": "平均转换效率", "value": 0}]

// 效率曲线坐标：所有小图共用同一纵轴口径，便于横向比较。
const PAD_L = 30
const PAD_R = 6
const PAD_T = 8
const PAD_B = 12
const Y_MIN = 92
const Y_MAX = 99.5

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
// 面板跟随列表原有筛选条件（设备编号、设备型号、额定功率），不新增也不删减检索项。
const filterFields = columns.slice(0, 3)

const panelOpen = ref(true)
const efficiency = ref<EfficiencyOverview | null>(null)
const effLoading = ref(false)
const effError = ref('')
const selectedId = ref<number | null>(null)
const locateMessage = ref('')

const mismatchDevices = computed(() =>
  (efficiency.value?.devices ?? []).filter((device) => device.mismatch),
)

function xIdx(index: number): number {
  const inner = 220 - PAD_L - PAD_R
  return PAD_L + (inner / 6) * index
}

function yVal(value: number): number {
  const inner = 84 - PAD_T - PAD_B
  const ratio = (value - Y_MIN) / (Y_MAX - Y_MIN)
  return PAD_T + inner * (1 - ratio)
}

function segments(device: EfficiencyDevice): string[] {
  // 遇到缺测日期就断开，避免把“没采到”画成效率掉零或连成直线。
  const result: string[] = []
  let current: string[] = []
  device.series.forEach((point, index) => {
    if (point.value === null) {
      if (current.length > 1) result.push(current.join(' '))
      current = []
      return
    }
    current.push(`${xIdx(index).toFixed(1)},${yVal(point.value).toFixed(1)}`)
  })
  if (current.length > 1) result.push(current.join(' '))
  return result
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '逆变器登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('逆变器管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '逆变器管理操作失败'
  }
}

function activeQuery(): string {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) params.set(field, value)
  }
  return params.toString()
}

async function reload() {
  errorMessage.value = ''
  locateMessage.value = ''
  const query = activeQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('逆变器列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 列表条件变化后曲线同步刷新；若选中设备已被滤掉则取消选中。
    await loadEfficiency()
    if (selectedId.value !== null && !rows.value.some((row) => row.id === selectedId.value)) {
      selectedId.value = null
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '逆变器管理列表读取失败'
  }
}

async function loadEfficiency() {
  effLoading.value = true
  effError.value = ''
  try {
    const response = await request(`${ENDPOINT}/efficiency?${activeQuery()}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    efficiency.value = (await response.json()) as EfficiencyOverview
  } catch (error) {
    // 拿不到数据时清空曲线，绝不能沿用上一份数据伪装成正常。
    efficiency.value = null
    effError.value = error instanceof Error ? error.message : '效率数据请求失败'
  } finally {
    effLoading.value = false
  }
}

function selectDevice(id: number) {
  selectedId.value = id
  locateMessage.value = ''
  const row = document.getElementById(`inv-row-${id}`)
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    return
  }
  // 设备不在当前列表页（或被筛选条件排除）时给出可读提示，不静默吞掉。
  const inList = rows.value.some((item) => item.id === id)
  locateMessage.value = inList
    ? '该设备不在当前分页，请调大每页条数后再查看'
    : '该设备不在当前列表筛选结果内，请调整筛选条件'
}

function selectFromList(row: Row) {
  const id = Number(row.id)
  selectedId.value = id
  locateMessage.value = ''
  const card = document.getElementById(`eff-card-${id}`)
  if (card) {
    if (!panelOpen.value) panelOpen.value = true
    // 等展开动画渲染后再滚动，避免滚到收起状态的位置。
    requestAnimationFrame(() => card.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    return
  }
  if (effError.value) {
    locateMessage.value = '效率数据当前不可用，无法在面板中定位该设备'
  } else {
    locateMessage.value = '该设备近七天无效率采集数据，已在面板“未采集到效率数据”区域列出'
  }
}

onMounted(reload)
</script>

<style scoped>
.eff-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}

.eff-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.eff-head h3 {
  margin: 0 0 2px;
  font-size: 15px;
}

.eff-head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.eff-body {
  margin-top: 10px;
}

.eff-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.eff-chip {
  font-size: 12px;
  color: var(--muted);
  background: #f1f5f9;
  border-radius: 999px;
  padding: 2px 10px;
}

.eff-chip.chip-warn {
  color: #b42318;
  background: #fef3f2;
}

.eff-loading,
.eff-empty {
  font-size: 13px;
  color: var(--muted);
  padding: 12px 0;
}

.eff-fetch-error {
  font-size: 13px;
  color: #b42318;
  background: #fef3f2;
  border: 1px solid #fecdca;
  border-radius: 6px;
  padding: 8px 10px;
}

.eff-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.eff-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
  background: #fff;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.eff-card:hover {
  border-color: var(--brand);
}

.eff-card.selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.25);
}

.eff-card.below {
  border-color: #fecdca;
  background: #fffafa;
}

.eff-card.below.selected {
  box-shadow: 0 0 0 2px rgba(180, 35, 24, 0.3);
}

.eff-card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.eff-card-head strong {
  font-size: 13px;
}

.eff-array {
  font-size: 11px;
  color: var(--muted);
}

.eff-chart {
  width: 100%;
  height: auto;
  display: block;
}

.rated-band {
  fill: rgba(31, 111, 235, 0.08);
}

.rated-line {
  stroke: #94a3b8;
  stroke-width: 0.8;
  stroke-dasharray: 3 3;
}

.axis-label {
  font-size: 8px;
  fill: var(--muted);
}

.eff-line {
  fill: none;
  stroke: var(--brand);
  stroke-width: 1.6;
  stroke-linejoin: round;
}

.below .eff-line {
  stroke: #d92d20;
}

.eff-dot {
  fill: var(--brand);
}

.below .eff-dot {
  fill: #d92d20;
}

.eff-dot.dot-low {
  fill: #d92d20;
}

.eff-card-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: center;
  margin-top: 4px;
  font-size: 11px;
}

.eff-avg {
  color: #344054;
}

.avg-low {
  color: #b42318;
  font-weight: 600;
}

.eff-gap-hint {
  color: #b54708;
}

.mismatch-tag {
  color: #b54708;
  background: #fffaeb;
  border: 1px solid #fedf89;
  border-radius: 4px;
  padding: 0 6px;
  font-size: 11px;
}

.eff-flag-list {
  margin-top: 12px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}

.eff-flag-list h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #344054;
}

.eff-flag-list ul {
  margin: 0;
  padding-left: 4px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.eff-flag-list li {
  font-size: 12px;
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.missing-reason {
  color: var(--muted);
}

tr.row-selected {
  background: #eff6ff;
}

tr.row-selected td {
  box-shadow: inset 0 0 0 1px var(--brand);
}

.locate-text {
  color: #b54708;
}

.collapsed .eff-body {
  display: none;
}
</style>
