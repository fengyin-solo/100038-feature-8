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

    <EfficiencyPanel :rows="rows" :selected-id="selectedId" @select="locateRow" />

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
          :key="String(row.id)"
          :ref="(el) => setRowRef(el, Number(row.id))"
          :class="{ 'row-selected': selectedId === Number(row.id) }"
        >
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
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
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

import { request } from '@/api/client'

import EfficiencyPanel from './EfficiencyPanel.vue'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/inverter'
const columns = ["设备编号", "设备型号", "额定功率", "转换效率", "所属方阵", "通讯地址", "投运日期", "运行状态"]
const actions = ["完成调试", "登记故障", "退役设备"]
const statuses = ["待调试", "运行中", "故障停机", "已退役"]
const stats = [{"label": "在运逆变器", "value": 0}, {"label": "故障停机", "value": 0}, {"label": "平均转换效率", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const selectedId = ref<number | null>(null)
const rowRefs = new Map<number, HTMLElement>()

function setRowRef(el: Element | unknown, id: number) {
  if (el instanceof HTMLElement) {
    rowRefs.set(id, el)
  } else {
    rowRefs.delete(id)
  }
}

// 面板选中某台设备：列表同步高亮并滚动定位到那一行。
async function locateRow(id: number) {
  selectedId.value = id
  await nextTick()
  rowRefs.get(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
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

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('逆变器列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 条件变化后选中的行若已不在结果里，取消高亮，避免面板和列表指向不一致。
    if (selectedId.value !== null && !rows.value.some((row) => Number(row.id) === selectedId.value)) {
      selectedId.value = null
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '逆变器管理列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.data-table :deep(.row-selected) td {
  background: #eaf2ff;
  box-shadow: inset 3px 0 0 var(--brand);
}
</style>
