<template>
  <section class="eff-panel">
    <header class="eff-head">
      <div>
        <h3>近七天转换效率视图</h3>
        <p class="eff-sub">曲线按设备编号排列；红点/红段表示当日效率低于该型号额定区间，下方标注所属方阵。点击图例可定位到列表对应行。</p>
      </div>
      <button v-if="!loading && !errorMessage" class="btn ghost eff-reload" type="button" @click="load">刷新曲线</button>
    </header>

    <div v-if="loading" class="eff-state">效率曲线加载中…</div>

    <div v-else-if="errorMessage" class="eff-state eff-error">
      <span>{{ errorMessage }}</span>
      <button class="btn" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="!overview" class="eff-state">暂无效率数据。</div>

    <div v-else-if="!overview.devices.length && !overview.missing.length" class="eff-state">
      当前列表条件下没有逆变器，调整筛选条件后曲线会同步更新。
    </div>

    <template v-else>
      <div class="eff-bands">
        <span class="eff-band-title">额定转换效率区间：</span>
        <span v-for="band in overview.rated_bands" :key="band.model" class="eff-band">
          {{ band.model }}：{{ band.lower.toFixed(1) }}%–{{ band.upper.toFixed(1) }}%
        </span>
      </div>

      <div v-if="overview.devices.length" class="eff-chart-wrap">
        <svg class="eff-chart" viewBox="0 0 760 340" role="img" aria-label="近七天逆变器转换效率曲线">
          <!-- 额定区间底纹 -->
          <rect
            :x="pad.left"
            :y="yPos(bandMax)"
            :width="plotW"
            :height="maxNonNegative(yPos(bandMin) - yPos(bandMax))"
            class="band-rect"
          />
          <line :x1="pad.left" :x2="pad.left + plotW" :y1="yPos(bandMin)" :y2="yPos(bandMin)" class="band-line" />
          <line :x1="pad.left" :x2="pad.left + plotW" :y1="yPos(bandMax)" :y2="yPos(bandMax)" class="band-line" />
          <text :x="pad.left + plotW" :y="yPos(bandMax) - 4" class="band-label" text-anchor="end">额定区间</text>

          <!-- 纵轴刻度 -->
          <g v-for="tick in ticks" :key="tick">
            <line :x1="pad.left" :x2="pad.left + plotW" :y1="yPos(tick)" :y2="yPos(tick)" class="grid-line" />
            <text :x="pad.left - 6" :y="yPos(tick) + 4" class="axis-label" text-anchor="end">{{ tick.toFixed(1) }}%</text>
          </g>

          <!-- 横轴日期 -->
          <text
            v-for="(label, i) in overview.labels"
            :key="label"
            :x="xPos(i)"
            :y="pad.top + plotH + 20"
            class="axis-label"
            text-anchor="middle"
          >{{ label.slice(5) }}</text>

          <!-- 设备曲线：缺测日断开，低于额定区间的线段与点标红 -->
          <g
            v-for="(line, di) in lines"
            :key="line.device.id"
            :class="['curve-group', { 'is-dim': selectedId !== null && selectedId !== line.device.id }]"
          >
            <path
              v-for="(piece, pi) in line.pieces"
              :key="pi"
              :d="piece.d"
              fill="none"
              :stroke="piece.red ? LOW_COLOR : colors[di % colors.length]"
              :stroke-width="selectedId === line.device.id ? 3 : 1.8"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            <circle
              v-for="dot in line.dots"
              :key="dot.label"
              :cx="dot.x"
              :cy="dot.y"
              :r="dot.low ? 4 : 2.8"
              :fill="dot.low ? LOW_COLOR : colors[di % colors.length]"
              :stroke="dot.low ? '#fff' : 'none'"
              :stroke-width="dot.low ? 1 : 0"
            >
              <title>{{ line.device.设备编号 }}（{{ line.device.所属方阵 }}）{{ dot.label }}：{{ dot.v.toFixed(2) }}%{{ dot.low ? '，低于额定区间' : '' }}</title>
            </circle>
          </g>
        </svg>
        <p class="eff-note">
          <i class="dot low-dot" /> 低于额定区间
          <i class="band-swatch" /> 额定效率区间
          ；缺测当日不连线，全部缺测或未接入采集的设备见下方清单。
        </p>
      </div>

      <ul v-if="overview.devices.length" class="eff-legend">
        <li
          v-for="(device, di) in overview.devices"
          :key="device.id"
          :class="['legend-item', { 'is-selected': selectedId === device.id, 'is-low': device.low_days.length }]"
          @click="emit('select', device.id)"
        >
          <i class="legend-swatch" :style="{ background: device.low_days.length ? LOW_COLOR : colors[di % colors.length] }" />
          <span class="legend-code">{{ device.设备编号 }}</span>
          <span class="legend-array">{{ device.所属方阵 }}</span>
          <span class="legend-mean">近七天均值 {{ device.mean.toFixed(2) }}%</span>
          <span v-if="device.low_days.length" class="tag tag-low">低于额定区间 {{ device.low_days.length }} 天</span>
          <span v-else-if="device.mismatch" class="tag tag-warn">效率异常</span>
          <span v-else class="tag tag-ok">效率正常</span>
          <span v-if="device.mismatch" class="tag tag-warn" :title="mismatchTip(device)">
            ⚠ 与列表均值不符（{{ formatListValue(device.list_efficiency) }}）
          </span>
        </li>
      </ul>

      <div v-if="overview.missing.length" class="eff-missing">
        <h4>未采集到效率数据的设备（{{ overview.missing.length }} 台）</h4>
        <ul>
          <li v-for="device in overview.missing" :key="device.id">
            <span class="legend-code">{{ device.设备编号 }}</span>
            <span class="legend-array">{{ device.所属方阵 }}</span>
            <span class="legend-array">{{ device.设备型号 }} · {{ device.运行状态 }}</span>
            <span class="tag tag-warn">{{ device.reason }}，效率不按正常显示</span>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface RatedBand {
  model: string
  lower: number
  upper: number
}

interface DeviceSeries {
  id: number
  设备编号: string
  设备型号: string
  所属方阵: string
  运行状态: string
  series: (number | null)[]
  mean: number
  list_efficiency: number | null
  rated_lower: number
  rated_upper: number
  low_days: string[]
  mismatch: boolean
}

interface MissingDevice {
  id: number
  设备编号: string
  设备型号: string
  所属方阵: string
  运行状态: string
  reason: string
}

interface Overview {
  days: number
  labels: string[]
  rated_bands: RatedBand[]
  devices: DeviceSeries[]
  missing: MissingDevice[]
}

interface Dot {
  x: number
  y: number
  v: number
  low: boolean
  label: string
}

interface Piece {
  d: string
  red: boolean
}

interface ChartLine {
  device: DeviceSeries
  pieces: Piece[]
  dots: Dot[]
}

const props = defineProps<{
  rows: Row[]
  selectedId: number | null
}>()

const emit = defineEmits<{
  (event: 'select', id: number): void
}>()

const ENDPOINT = '/api/inverter/efficiency-overview'
const LOW_COLOR = '#dc2626'
const colors = ['#1f6feb', '#16a34a', '#7c3aed', '#0891b2', '#d97706', '#db2777', '#475569', '#0d9488']

const pad = { top: 18, right: 18, bottom: 34, left: 52 }
const plotW = 760 - pad.left - pad.right
const plotH = 340 - pad.top - pad.bottom

const overview = ref<Overview | null>(null)
const loading = ref(false)
const errorMessage = ref('')
let abortController: AbortController | null = null

// 列表条件变化后（行集合/行内容变了），曲线跟着重新拉取；加载失败时清空旧曲线，
// 避免拿不到数据还把效率画成正常状态。
const rowsSignature = computed(() => JSON.stringify(props.rows.map((row) => [row.id, row.转换效率, row.所属方阵, row.设备型号])))

watch(rowsSignature, () => void load(), { immediate: true })

async function load() {
  abortController?.abort()
  const controller = new AbortController()
  abortController = controller
  loading.value = true
  errorMessage.value = ''
  overview.value = null
  if (!props.rows.length) {
    loading.value = false
    return
  }
  const ids = props.rows.map((row) => String(row.id ?? '')).filter(Boolean).join(',')
  try {
    const response = await request(`${ENDPOINT}?ids=${encodeURIComponent(ids)}`, { signal: controller.signal })
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    overview.value = (await response.json()) as Overview
  } catch (error) {
    if ((error as DOMException)?.name === 'AbortError') {
      return
    }
    const detail = error instanceof Error ? error.message : '请求未送达'
    errorMessage.value = `效率曲线数据获取失败（${detail}），已暂停展示效率数值，避免把缺数据误看成正常。可稍后重试。`
  } finally {
    if (!controller.signal.aborted) {
      loading.value = false
    }
  }
}

const allValues = computed(() =>
  overview.value?.devices.flatMap((device) => device.series.filter((v): v is number => v !== null)) ?? [],
)

const bandMin = computed(() => Math.min(...(overview.value?.rated_bands.map((b) => b.lower) ?? [97])))
const bandMax = computed(() => Math.max(...(overview.value?.rated_bands.map((b) => b.upper) ?? [98.4])))

const yMin = computed(() => {
  const values = allValues.value
  return values.length ? Math.floor(Math.min(...values, bandMin.value) - 0.4) : bandMin.value - 1
})
const yMax = computed(() => {
  const values = allValues.value
  return values.length ? Math.ceil(Math.max(...values, bandMax.value) + 0.4) : bandMax.value + 1
})

const ticks = computed(() => buildTicks(yMin.value, yMax.value))

function xPos(index: number): number {
  const count = overview.value?.labels.length ?? 1
  return pad.left + (index * plotW) / Math.max(count - 1, 1)
}

function yPos(value: number): number {
  return pad.top + ((yMax.value - value) / (yMax.value - yMin.value || 1)) * plotH
}

const lines = computed<ChartLine[]>(() => {
  if (!overview.value) {
    return []
  }
  return overview.value.devices.map((device) => {
    const dots: Dot[] = []
    const pieces: Piece[] = []
    let coords: string[] = []
    let pieceRed = false

    const flush = () => {
      if (coords.length > 1) {
        pieces.push({ d: `M ${coords.join(' L ')}`, red: pieceRed })
      }
      coords = []
      pieceRed = false
    }

    device.series.forEach((value, i) => {
      if (value === null) {
        flush()
        return
      }
      const low = value < device.rated_lower
      const x = xPos(i)
      const y = yPos(value)
      // 相邻点任一点低于额定区间，中间线段就标红，曲线下沉一眼能看出来。
      if (coords.length) {
        pieceRed = pieceRed || low
      }
      coords.push(`${x.toFixed(1)} ${y.toFixed(1)}`)
      dots.push({ x, y, v: value, low, label: overview.value!.labels[i] })
    })
    flush()
    return { device, pieces, dots }
  })
})

function buildTicks(min: number, max: number): number[] {
  const target = 5
  const raw = (max - min) / target
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const residual = raw / magnitude
  const step = (residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 2.5 ? 2.5 : residual <= 5 ? 5 : 10) * magnitude
  const start = Math.ceil(min / step) * step
  const result: number[] = []
  for (let value = start; value <= max + 1e-9; value += step) {
    result.push(Number(value.toFixed(3)))
  }
  return result
}

function mismatchTip(device: DeviceSeries): string {
  return `曲线近七天均值 ${device.mean.toFixed(2)}%，列表登记均值 ${formatListValue(device.list_efficiency)}，两者口径对不上，请核对`
}

function formatListValue(value: number | null): string {
  return value === null ? '列表未填' : `${value.toFixed(1)}%`
}

function maxNonNegative(value: number): number {
  return Math.max(0, value)
}
</script>

<style scoped>
.eff-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.eff-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.eff-head h3 {
  margin: 0;
  font-size: 15px;
}
.eff-sub {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.eff-reload {
  flex-shrink: 0;
}
.eff-state {
  padding: 20px 0;
  color: var(--muted);
  font-size: 13px;
}
.eff-error {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #b42318;
}
.eff-bands {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0;
  font-size: 12px;
}
.eff-band-title {
  color: var(--muted);
}
.eff-band {
  background: #eef4ff;
  border: 1px solid #cfe0ff;
  color: #1f6feb;
  border-radius: 999px;
  padding: 2px 10px;
}
.eff-chart-wrap {
  margin-top: 4px;
}
.eff-chart {
  width: 100%;
  height: auto;
  display: block;
}
.band-rect {
  fill: rgba(22, 163, 74, 0.08);
}
.band-line {
  stroke: #16a34a;
  stroke-width: 1;
  stroke-dasharray: 5 4;
}
.band-label {
  fill: #16a34a;
  font-size: 11px;
}
.grid-line {
  stroke: #e8edf3;
  stroke-width: 1;
}
.axis-label {
  fill: #64748b;
  font-size: 11px;
}
.curve-group {
  transition: opacity 0.15s ease;
}
.curve-group.is-dim {
  opacity: 0.25;
}
.eff-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.low-dot {
  background: #dc2626;
}
.band-swatch {
  display: inline-block;
  width: 14px;
  height: 8px;
  background: rgba(22, 163, 74, 0.14);
  border: 1px dashed #16a34a;
  border-radius: 2px;
}
.eff-legend {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 6px;
}
.legend-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  cursor: pointer;
}
.legend-item:hover {
  border-color: var(--brand);
}
.legend-item.is-selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.18);
}
.legend-item.is-low {
  border-color: #f3b4ad;
  background: #fef6f5;
}
.legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-code {
  font-weight: 600;
}
.legend-array {
  color: var(--muted);
}
.legend-mean {
  color: #1f2937;
}
.tag {
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 11px;
}
.tag-low {
  background: #fee4e2;
  color: #b42318;
}
.tag-warn {
  background: #fef3c7;
  color: #92400e;
}
.tag-ok {
  background: #dcfce7;
  color: #166534;
}
.eff-missing {
  margin-top: 10px;
  border: 1px dashed #d6a018;
  background: #fffdf3;
  border-radius: 6px;
  padding: 8px 10px;
}
.eff-missing h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #92400e;
}
.eff-missing ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 6px;
}
.eff-missing li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
</style>
