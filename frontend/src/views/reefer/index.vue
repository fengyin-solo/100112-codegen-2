<template>
  <section class="page" data-module="reefer">
    <header class="page-head">
      <div>
        <h2>冷藏箱温控巡检管理</h2>
        <p class="page-desc">
          按箱号登记设定温度、温度区间与巡检频次，巡检中逐时段录入箱温。
          判定口径：箱温超出区间即标记超温，超温时长 = 超温记录数 × 巡检频次；距上限不足 1℃ 给出预警。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记冷藏箱温控</button>
        <button class="btn" type="button" @click="exportRows">导出温控巡检清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>箱号</span>
        <input v-model="keyword" placeholder="按箱号检索" />
      </label>
      <label class="filter-item">
        <span>巡检状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column" :class="cellClass(column, row)">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="runAction('开始巡检', row)">开始巡检</button>
            <button class="link" type="button" @click="openRecorder(row)">录入温度</button>
            <button class="link" type="button" @click="runAction('结束巡检', row)">结束巡检</button>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无冷藏箱温控数据，可先登记冷藏箱温控</td>
        </tr>
      </tbody>
    </table>

    <section v-if="createOpen" class="panel">
      <h3>登记冷藏箱温控要求</h3>
      <form class="panel-grid" @submit.prevent="submitCreate">
        <label v-for="field in createFields" :key="field.key" class="filter-item">
          <span>{{ field.label }}</span>
          <input v-model="createForm[field.key]" :placeholder="field.placeholder" :type="field.numeric ? 'number' : 'text'" step="0.1" />
        </label>
        <div class="panel-actions">
          <button class="btn primary" type="submit">保存登记</button>
          <button class="btn ghost" type="button" @click="createOpen = false">取消</button>
        </div>
      </form>
    </section>

    <section v-if="recorderRow" class="panel">
      <h3>录入温度记录 · 箱号 {{ recorderRow['箱号'] }}（区间 {{ recorderRow['温度区间'] }}）</h3>
      <form class="panel-grid" @submit.prevent="stageRecord">
        <label class="filter-item">
          <span>记录时间</span>
          <input v-model="recordForm.moment" type="datetime-local" />
        </label>
        <label class="filter-item">
          <span>箱温（℃）</span>
          <input v-model="recordForm.temp" type="number" step="0.1" placeholder="如 -18.5" />
        </label>
        <div class="panel-actions">
          <button class="btn" type="submit">加入待提交</button>
          <button class="btn primary" type="button" :disabled="!stagedRecords.length" @click="submitRecords">提交温度记录（{{ stagedRecords.length }}）</button>
          <button class="btn ghost" type="button" @click="closeRecorder">完成</button>
        </div>
      </form>
      <table v-if="stagedRecords.length" class="data-table">
        <thead>
          <tr><th>记录时间</th><th>箱温（℃）</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in stagedRecords" :key="item.记录时间">
            <td>{{ item.记录时间 }}</td>
            <td>{{ item.温度 }}</td>
            <td><button class="link" type="button" @click="stagedRecords.splice(index, 1)">移除</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="detail" class="panel">
      <h3>温度记录详情 · 箱号 {{ detail['箱号'] }}</h3>
      <p class="panel-summary">
        设定温度 {{ detail['设定温度'] }}℃ · 区间 {{ detail['温度区间'] }} · 每 {{ detail['巡检频次'] }} 分钟巡检一次 ·
        超温 {{ detail['超温记录数'] }} 条 / 持续 {{ detail['超温时长（分钟）'] }} 分钟 · 预警：{{ detail['预警'] }}
      </p>
      <table class="data-table">
        <thead>
          <tr><th>记录时间</th><th>箱温（℃）</th><th>判定</th></tr>
        </thead>
        <tbody>
          <tr v-for="record in detailRecords" :key="record.记录时间">
            <td>{{ record.记录时间 }}</td>
            <td>{{ record.温度 }}</td>
            <td :class="verdictClass(record.判定)">{{ record.判定 }}</td>
          </tr>
          <tr v-if="!detailRecords.length">
            <td colspan="3" class="empty-state">暂无温度记录，开始巡检后录入</td>
          </tr>
        </tbody>
      </table>
      <div class="panel-actions">
        <button class="btn ghost" type="button" @click="detail = null">关闭详情</button>
      </div>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷藏箱温控记录</span>
      <span v-if="noticeText" class="notice-text">{{ noticeText }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number | string }
type TempRecord = { 记录时间: string; 温度: number; 判定?: string }

const ENDPOINT = '/api/reefer'
const columns = ["箱号", "设定温度", "温度区间", "巡检频次", "温度记录数", "超温记录数", "超温时长（分钟）", "预警", "巡检状态"]
const statuses = ["待巡检", "巡检中", "已办结"]
const createFields = [
  { key: '箱号', label: '箱号', placeholder: '如 TCLU4821065', numeric: false },
  { key: '设定温度', label: '设定温度（℃）', placeholder: '如 -18', numeric: true },
  { key: '温度下限', label: '温度下限（℃）', placeholder: '如 -20', numeric: true },
  { key: '温度上限', label: '温度上限（℃）', placeholder: '如 -15', numeric: true },
  { key: '巡检频次', label: '巡检频次（分钟）', placeholder: '如 30', numeric: true },
  { key: '巡检人', label: '巡检人', placeholder: '值班巡检员', numeric: false },
]

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const noticeText = ref('')

const createOpen = ref(false)
const createForm = ref<Record<string, string>>({})

const recorderRow = ref<Row | null>(null)
const recordForm = ref({ moment: '', temp: '' })
const stagedRecords = ref<TempRecord[]>([])

const detail = ref<Row | null>(null)
const detailRecords = computed<TempRecord[]>(() => (detail.value?.records as TempRecord[] | undefined) ?? [])

const stats = computed(() => [
  { label: '巡检中箱数', value: rows.value.filter((row) => row['巡检状态'] === '巡检中').length },
  { label: '超温箱数', value: rows.value.filter((row) => Number(row['超温记录数']) > 0).length },
  { label: '预警箱数', value: rows.value.filter((row) => row['预警'] === '是').length },
])

function cellClass(column: string, row: Row) {
  if (column === '超温记录数' && Number(row['超温记录数']) > 0) return 'cell-danger'
  if (column === '预警' && row['预警'] === '是') return 'cell-warn'
  return ''
}

function verdictClass(verdict?: string) {
  if (verdict === '超温') return 'cell-danger'
  if (verdict === '预警') return 'cell-warn'
  return ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createOpen.value = true
}

async function post(path: string, values: Record<string, unknown>, fallback: string): Promise<boolean> {
  errorMessage.value = ''
  noticeText.value = ''
  try {
    const response = await request(path, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? fallback)
    }
    noticeText.value = payload.message ?? ''
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : fallback
    return false
  }
}

async function submitCreate() {
  const ok = await post(ENDPOINT, { ...createForm.value }, '冷藏箱温控登记失败')
  if (ok) {
    createOpen.value = false
    await reload()
  }
}

async function runAction(action: string, row: Row) {
  const ok = await post(`${ENDPOINT}/${row.id}/actions`, { action }, '冷藏箱温控操作失败')
  if (ok) {
    await reload()
    if (detail.value && detail.value.id === row.id) await openDetail(row)
  }
}

function openRecorder(row: Row) {
  recorderRow.value = row
  recordForm.value = { moment: '', temp: '' }
  stagedRecords.value = []
}

function closeRecorder() {
  recorderRow.value = null
  stagedRecords.value = []
}

function stageRecord() {
  errorMessage.value = ''
  const moment = recordForm.value.moment.replace('T', ' ').trim()
  const temp = Number(recordForm.value.temp)
  if (!moment) {
    errorMessage.value = '请先选择记录时间'
    return
  }
  if (recordForm.value.temp.trim() === '' || Number.isNaN(temp)) {
    errorMessage.value = '箱温缺失或不是数值，无法加入待提交'
    return
  }
  // 同一时段只留一条：待提交列表里已有时段直接替换
  const existing = stagedRecords.value.findIndex((item) => item.记录时间 === moment)
  const record: TempRecord = { 记录时间: moment, 温度: temp }
  if (existing >= 0) stagedRecords.value.splice(existing, 1, record)
  else stagedRecords.value.push(record)
  recordForm.value = { moment: '', temp: '' }
}

async function submitRecords() {
  if (!recorderRow.value) return
  const ok = await post(
    `${ENDPOINT}/${recorderRow.value.id}/records`,
    { records: stagedRecords.value },
    '温度记录保存失败',
  )
  if (ok) {
    stagedRecords.value = []
    await reload()
    if (detail.value && detail.value.id === recorderRow.value?.id) await openDetail(recorderRow.value)
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('温度记录详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温度记录详情读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('冷藏箱温控列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏箱温控列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-top: 12px; }
.panel h3 { margin: 0 0 10px; font-size: 14px; }
.panel-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.panel-actions { display: flex; gap: 8px; align-items: center; margin-top: 4px; }
.panel-summary { color: var(--muted); font-size: 13px; margin: 0 0 10px; }
.panel .data-table { margin-top: 10px; }
.cell-danger { color: #b42318; font-weight: 600; }
.cell-warn { color: #b54708; font-weight: 600; }
.notice-text { color: #067647; }
select { border: 1px solid var(--border); border-radius: 4px; padding: 4px 6px; }
</style>
