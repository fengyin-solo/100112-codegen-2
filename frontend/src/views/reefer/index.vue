<template>
  <section class="page" data-module="reefer">
    <header class="page-head">
      <div>
        <h2>冷藏箱温控巡检</h2>
        <p class="page-desc">按箱号登记箱温与温度记录，设定温度区间与巡检频次；超出区间即标记超温并算出持续时间，接近上限提前预警。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">登记冷藏箱</button>
        <button class="btn" type="button" @click="exportRows">导出冷藏箱温控清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="showCreate" class="panel">
      <header class="panel-head">
        <strong>登记冷藏箱</strong>
        <button class="link" type="button" @click="toggleCreate">收起</button>
      </header>
      <form class="panel-form" @submit.prevent="submitCreate">
        <label class="filter-item">
          <span>箱号 *</span>
          <input v-model="createForm.箱号" placeholder="如 REEF-0004" />
        </label>
        <label class="filter-item">
          <span>温度下限(℃) *</span>
          <input v-model="createForm.温度下限" type="number" step="0.1" placeholder="如 -25" />
        </label>
        <label class="filter-item">
          <span>温度上限(℃) *</span>
          <input v-model="createForm.温度上限" type="number" step="0.1" placeholder="如 -18" />
        </label>
        <label class="filter-item">
          <span>巡检频次(小时) *</span>
          <input v-model="createForm.巡检频次" type="number" step="0.5" min="0.5" placeholder="如 4" />
        </label>
        <label class="filter-item">
          <span>箱温(℃) *</span>
          <input v-model="createForm.箱温" type="number" step="0.1" placeholder="如 -20.5" />
        </label>
        <label class="filter-item">
          <span>记录时间</span>
          <input v-model="createForm.记录时间" type="datetime-local" />
        </label>
        <label class="filter-item">
          <span>巡检人</span>
          <input v-model="createForm.巡检人" placeholder="默认值班员" />
        </label>
        <button class="btn primary" type="submit">保存登记</button>
      </form>
    </div>

    <div v-if="inspecting" class="panel">
      <header class="panel-head">
        <strong>巡检登记：{{ inspecting.箱号 }}（区间 {{ inspecting.温度下限 }}℃ ~ {{ inspecting.温度上限 }}℃，每 {{ inspecting['巡检频次(小时)'] }} 小时一次）</strong>
        <button class="link" type="button" @click="inspecting = null">收起</button>
      </header>
      <div v-for="(item, index) in inspectRows" :key="index" class="inspect-row">
        <label class="filter-item">
          <span>记录时间</span>
          <input v-model="item.记录时间" type="datetime-local" />
        </label>
        <label class="filter-item">
          <span>箱温(℃)</span>
          <input v-model="item.箱温" type="number" step="0.1" placeholder="如 -19.2" />
        </label>
        <button class="link" type="button" @click="inspectRows.splice(index, 1)">删除</button>
      </div>
      <div class="panel-actions">
        <button class="btn" type="button" @click="inspectRows.push({ 记录时间: '', 箱温: '' })">添加一条</button>
        <button class="btn primary" type="button" @click="submitReadings">提交巡检记录</button>
      </div>
    </div>

    <div v-if="detail" class="panel">
      <header class="panel-head">
        <strong>
          温度详情：{{ detail.箱号 }} · 判定 {{ detail.判定结果 }}
          <template v-if="detail.判定结果 === '超温'"> · 已超温 {{ detail['超温持续(小时)'] }} 小时</template>
          · 超温记录 {{ detail.超温记录数 }} 条
        </strong>
        <button class="link" type="button" @click="detail = null">收起</button>
      </header>
      <table class="data-table">
        <thead>
          <tr><th>记录时间</th><th>箱温(℃)</th><th>判定</th></tr>
        </thead>
        <tbody>
          <tr v-for="rec in detail.温度记录" :key="rec.记录时间">
            <td>{{ rec.记录时间 }}</td>
            <td>{{ rec.箱温 }}</td>
            <td><span class="tag" :class="tagClass(rec.判定)">{{ rec.判定 }}</span></td>
          </tr>
          <tr v-if="!detail.温度记录?.length">
            <td colspan="3" class="empty-state">暂无温度记录，可先巡检登记</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>箱号</span>
        <input v-model="filters.keyword" placeholder="按箱号检索" />
      </label>
      <label class="filter-item">
        <span>判定结果</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
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
          <td v-for="column in columns" :key="column">
            <span v-if="column === '判定结果'" class="tag" :class="tagClass(row.判定结果)">{{ row.判定结果 }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openInspect(row)">巡检登记</button>
            <button class="link" type="button" @click="openDetail(row)">温度详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无冷藏箱温控数据，可先登记冷藏箱</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷藏箱温控记录</span>
      <span v-if="okMessage" class="ok-text">{{ okMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/reefer'
const columns = ["箱号", "温度下限", "温度上限", "巡检频次(小时)", "当前箱温", "判定结果", "超温持续(小时)", "超温记录数", "上次巡检时间", "下次巡检时间", "巡检人"]
const statuses = ["正常", "预警", "超温"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([{ label: '在港冷藏箱', value: 0 }, { label: '超温箱量', value: 0 }, { label: '预警箱量', value: 0 }])
const errorMessage = ref('')
const okMessage = ref('')
const filters = ref({ keyword: '', status: '' })

const showCreate = ref(false)
const emptyCreate = () => ({ 箱号: '', 温度下限: '', 温度上限: '', 巡检频次: '', 箱温: '', 记录时间: '', 巡检人: '' })
const createForm = ref(emptyCreate())

const inspecting = ref<Row | null>(null)
const inspectRows = ref<{ 记录时间: string; 箱温: string | number }[]>([])
const detail = ref<Row | null>(null)

function tagClass(verdict: string) {
  if (verdict === '超温') return 'tag-danger'
  if (verdict === '预警') return 'tag-warn'
  return 'tag-ok'
}

function toggleCreate() {
  showCreate.value = !showCreate.value
  if (showCreate.value) {
    createForm.value = emptyCreate()
  }
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function openInspect(row: Row) {
  inspecting.value = row
  inspectRows.value = [{ 记录时间: '', 箱温: '' }]
  errorMessage.value = ''
  okMessage.value = ''
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('冷藏箱温度详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏箱温度详情读取失败'
  }
}

async function submitCreate() {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          箱号: createForm.value.箱号,
          温度下限: createForm.value.温度下限,
          温度上限: createForm.value.温度上限,
          '巡检频次(小时)': createForm.value.巡检频次,
          箱温: createForm.value.箱温,
          记录时间: createForm.value.记录时间,
          巡检人: createForm.value.巡检人,
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '冷藏箱登记未生效')
    }
    okMessage.value = payload.message
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏箱登记失败'
  }
}

async function submitReadings() {
  if (!inspecting.value) return
  errorMessage.value = ''
  okMessage.value = ''
  const records = inspectRows.value
    .filter((item) => String(item.记录时间).trim() !== '' || String(item.箱温).trim() !== '')
    .map((item) => ({ 记录时间: item.记录时间, 箱温: item.箱温 }))
  try {
    const response = await request(`${ENDPOINT}/${inspecting.value.id}/readings`, {
      method: 'POST',
      body: JSON.stringify({ values: { 温度记录: records, 巡检人: inspecting.value.巡检人 } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '巡检记录未保存')
    }
    okMessage.value = payload.message
    inspecting.value = null
    await reload()
    if (detail.value && payload.entry) {
      detail.value = payload.entry
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检记录保存失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('冷藏箱列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summary = await summaryResponse.json()
      stats.value = [
        { label: '在港冷藏箱', value: summary.在港冷藏箱 ?? 0 },
        { label: '超温箱量', value: summary.超温箱量 ?? 0 },
        { label: '预警箱量', value: summary.预警箱量 ?? 0 },
      ]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏箱温控列表读取失败'
  }
}

onMounted(reload)
</script>
