<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { inspectFireStream } from '@/api'
import ImageUploader from '@/components/ImageUploader.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

// 固定的检测提示语
const FIXED_QUERY = '请帮我判断这张图片里面的消防栓存在的异常'

const imageBase64 = ref('')
const result = ref('')
const isLoading = ref(false)
const error = ref('')
const yoloResult = ref(null)
const traceResult = ref(null)
const abortController = ref(null)

// 只需要有图片即可提交
const canSubmit = computed(() => {
  return imageBase64.value && !isLoading.value
})

const yoloDetections = computed(() => yoloResult.value?.detections || [])
const yoloStatusText = computed(() => {
  if (!yoloResult.value) return ''
  if (!yoloResult.value.enabled) {
    return `YOLO辅助检测未启用：${yoloResult.value.reason || '无详细信息'}`
  }
  const count = yoloDetections.value.length
  return count
    ? `YOLO辅助检测检出 ${count} 个内部组件候选框，已交给二次复核综合判断。`
    : 'YOLO辅助检测未检出高于阈值的内部组件隐患框，但不代表没有隐患。'
})
const formatConfidence = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const traceStages = computed(() => traceResult.value?.stages || [])
const traceIssues = computed(() => traceResult.value?.summary?.issues || [])
const formatDuration = (value) => `${Number(value || 0)}ms`
const stageStatusText = (status) => {
  if (status === 'warn') return '\u63d0\u9192'
  if (status === 'error') return '\u5f02\u5e38'
  if (status === 'skipped') return '\u8df3\u8fc7'
  return '\u6b63\u5e38'
}
const stageMainText = (stage) => {
  if (stage.name === 'qwen_first') {
    const output = stage.output || {}
    return `${output.verdict || '\u672a\u89e3\u6790\u7ed3\u8bba'} / ${(output.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
  }
  if (stage.name === 'yolo_internal') {
    return `\u5019\u9009\u6846 ${stage.detectionCount || 0} \u4e2a / ${(stage.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
  }
  const output = stage.output || {}
  return `${output.verdict || '\u672a\u89e3\u6790\u7ed3\u8bba'} / ${(output.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
}

const handleImageUpload = (base64) => {
  abortActiveRequest()
  imageBase64.value = base64
  // 清除之前的结果
  result.value = ''
  error.value = ''
  yoloResult.value = null
  traceResult.value = null
}

const handleImageRemove = () => {
  abortActiveRequest()
  imageBase64.value = ''
  result.value = ''
  error.value = ''
  yoloResult.value = null
  traceResult.value = null
}

const abortActiveRequest = () => {
  abortController.value?.abort()
  abortController.value = null
}

const handleSubmit = async () => {
  if (!canSubmit.value) return

  abortActiveRequest()
  isLoading.value = true
  error.value = ''
  result.value = ''
  yoloResult.value = null
  traceResult.value = null
  const controller = new AbortController()
  abortController.value = controller

  try {
    const res = await inspectFireStream({
      query: FIXED_QUERY,
      image: imageBase64.value,
      signal: controller.signal,
      onChunk: (delta) => {
        result.value += delta
      }
    })

    result.value = res.response
    yoloResult.value = res.yolo || null
    traceResult.value = res.trace || null
  } catch (err) {
    if (err.name === 'AbortError') {
      return
    }

    error.value = err.message || '检测失败，请重试'
  } finally {
    if (abortController.value === controller) {
      abortController.value = null
    }
    isLoading.value = false
  }
}

const handleReset = () => {
  abortActiveRequest()
  imageBase64.value = ''
  result.value = ''
  error.value = ''
  yoloResult.value = null
  traceResult.value = null
}

const escapeHtml = (value) => String(value || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const sectionMeta = {
  '一': { label: '01', tone: 'primary' },
  '二': { label: '02', tone: 'neutral' },
  '三': { label: '03', tone: 'neutral' }
}

const renderReportHtml = (text) => {
  const lines = String(text || '').split(/\r?\n/).map((line) => line.trim())
  const html = []

  lines.forEach((line) => {
    if (!line) return
    const sectionMatch = line.match(/^([一二三])、(.+)$/)
    if (sectionMatch) {
      const [, numeral, title] = sectionMatch
      const meta = sectionMeta[numeral] || { label: numeral, tone: 'neutral' }
      const verdictMatch = title.match(/^检测结论：?(.+)?$/)
      const verdict = verdictMatch ? (verdictMatch[1] || '').trim() : ''
      const displayTitle = verdictMatch ? '检测结论' : title.replace(/：$/, '')
      const badgeClass = verdict.includes('不合格') ? 'report-section__badge--bad' : 'report-section__badge--ok'
      html.push(`
        <div class="report-section report-section--${meta.tone}">
          <span class="report-section__index">${meta.label}</span>
          <div class="report-section__title">${escapeHtml(displayTitle)}</div>
          ${verdict ? `<span class="report-section__badge ${badgeClass}">${escapeHtml(verdict)}</span>` : ''}
        </div>
      `)
      return
    }

    html.push(`<p class="report-paragraph">${escapeHtml(line)}</p>`)
  })

  return html.join('')
}

const renderedResult = computed(() => {
  if (!result.value) return ''
  return renderReportHtml(result.value)
})

onBeforeUnmount(() => {
  abortActiveRequest()
})
</script>

<template>
  <div class="inspect">
    <div class="inspect__container container">
      <!-- Header -->
      <header class="inspect__header">
        <h1 class="inspect__title">智能检测</h1>
        <p class="inspect__subtitle">
          上传消防栓图片，AI将自动分析并生成检测报告
        </p>
      </header>
      
      <!-- Main Content -->
      <div class="inspect__content">
        <!-- Input Section -->
        <div class="inspect__input-section">
          <div class="inspect__card card">
            <h2 class="inspect__card-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14" 
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M14 8h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
              </svg>
              上传消防栓图片
            </h2>
            <ImageUploader 
              @upload="handleImageUpload" 
              @remove="handleImageRemove" 
            />
            
            <div class="inspect__hint">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" 
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span>上传图片后，系统将自动检测消防栓存在的异常</span>
            </div>
          </div>
          
          <div class="inspect__actions">
            <button 
              class="btn btn-primary btn-lg inspect__submit"
              :disabled="!canSubmit"
              @click="handleSubmit"
            >
              <template v-if="isLoading">
                <LoadingSpinner size="sm" />
                <span>分析中...</span>
              </template>
              <template v-else>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" 
                        stroke="currentColor" stroke-width="2" 
                        stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span>开始检测</span>
              </template>
            </button>
            
            <button 
              v-if="result || error"
              class="btn btn-secondary btn-lg"
              @click="handleReset"
            >
              重新检测
            </button>
          </div>
        </div>
        
        <!-- Result Section -->
        <div class="inspect__result-section">
          <div class="inspect__card card inspect__result-card">
            <h2 class="inspect__card-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" 
                      stroke="currentColor" stroke-width="1.5" 
                      stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              检测报告
            </h2>
            
            <!-- Error State -->
            <div v-if="error" class="inspect__error">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" 
                      stroke="currentColor" stroke-width="1.5" 
                      stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <p>{{ error }}</p>
            </div>

            <!-- Result State -->
            <div v-else-if="result || isLoading" class="inspect__result">
              <div v-if="isLoading" class="inspect__streaming-status">
                <LoadingSpinner size="sm" />
                <span>AI 正在流式生成检测报告...</span>
              </div>
              <div v-if="result" class="inspect__result-content markdown-body" v-html="renderedResult"></div>
              <div v-if="false && yoloResult" class="inspect__yolo-card">
                <div class="inspect__yolo-head">
                  <strong>YOLO 辅助检测</strong>
                  <span>{{ yoloStatusText }}</span>
                </div>
                <div v-if="yoloDetections.length" class="inspect__yolo-list">
                  <span
                    v-for="item in yoloDetections"
                    :key="`${item.className}-${item.confidence}-${item.bbox?.join('-')}`"
                  >
                    {{ item.label || item.className }} {{ formatConfidence(item.confidence) }}
                  </span>
                </div>
              </div>
              <div v-if="false && traceResult" class="inspect__trace-card">
                <div class="inspect__trace-head">
                  <strong>&#x672c;&#x6b21;&#x94fe;&#x8def;&#x8ffd;&#x8e2a;</strong>
                  <span>&#x603b;&#x8017;&#x65f6; {{ formatDuration(traceResult.summary?.totalDurationMs) }}</span>
                </div>
                <div class="inspect__trace-stages">
                  <div
                    v-for="stage in traceStages"
                    :key="stage.name"
                    :class="['inspect__trace-stage', `inspect__trace-stage--${stage.status || 'ok'}`]"
                  >
                    <div>
                      <strong>{{ stage.title }}</strong>
                      <span>{{ stageStatusText(stage.status) }} &middot; {{ formatDuration(stage.durationMs) }}</span>
                    </div>
                    <p>{{ stageMainText(stage) }}</p>
                  </div>
                </div>
                <div v-if="traceIssues.length" class="inspect__trace-issues">
                  <strong>&#x9700;&#x8981;&#x5173;&#x6ce8;</strong>
                  <span v-for="issue in traceIssues" :key="issue.type">{{ issue.title }}</span>
                </div>
              </div>
              <div v-if="isLoading && !result" class="inspect__loading">
                <LoadingSpinner size="lg" text="AI正在分析图片，请稍候..." />
              </div>
            </div>

            <!-- Empty State -->
            <div v-else class="inspect__empty">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" 
                      stroke="currentColor" stroke-width="1.5" 
                      stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <p>上传消防栓图片后<br />检测报告将显示在这里</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inspect {
  padding: calc(80px + var(--spacing-3xl)) 0 var(--spacing-3xl);
  min-height: 100vh;
  background: var(--bg-secondary);
}

.inspect__header {
  text-align: center;
  margin-bottom: var(--spacing-3xl);
}

.inspect__title {
  font-size: var(--font-size-4xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.inspect__subtitle {
  font-size: var(--font-size-lg);
  color: var(--text-secondary);
}

.inspect__content {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-xl);
}

@media (min-width: 1024px) {
  .inspect__content {
    grid-template-columns: 1fr 1fr;
    align-items: start;
  }
}

.inspect__input-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.inspect__card {
  padding: var(--spacing-xl);
}

.inspect__card-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
}

.inspect__card-title svg {
  color: var(--color-primary);
}

.inspect__hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--color-primary-subtle);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-primary-dark);
}

.inspect__hint svg {
  flex-shrink: 0;
}

.inspect__actions {
  display: flex;
  gap: var(--spacing-md);
}

.inspect__submit {
  flex: 1;
}

.inspect__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.inspect__result-section {
  position: sticky;
  top: 100px;
}

.inspect__result-card {
  min-height: 400px;
  display: flex;
  flex-direction: column;
}

.inspect__loading,
.inspect__error,
.inspect__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-2xl);
}

.inspect__empty svg,
.inspect__error svg {
  color: var(--color-gray-300);
  margin-bottom: var(--spacing-md);
}

.inspect__empty p {
  color: var(--text-tertiary);
  line-height: 1.8;
}

.inspect__error svg {
  color: var(--color-error);
}

.inspect__error p {
  color: var(--color-error);
  font-weight: 500;
}

.inspect__result {
  flex: 1;
  overflow-y: auto;
  max-height: 600px;
}

.inspect__streaming-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary-subtle);
  border-radius: var(--radius-md);
  color: var(--color-primary-dark);
  font-size: var(--font-size-sm);
  position: sticky;
  top: 0;
}

/* 检测报告样式 */
.inspect__result-content.markdown-body {
  display: grid;
  gap: var(--spacing-md);
  color: var(--text-primary);
}

.inspect__result-content :deep(.report-section) {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  border: 1px solid var(--color-gray-100);
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-lg);
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.08), rgba(255, 255, 255, 0.92));
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
}

.inspect__result-content :deep(.report-section:first-child) {
  margin-top: 0;
}

.inspect__result-content :deep(.report-section--neutral) {
  border-left-color: var(--color-gray-300);
  background: linear-gradient(90deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.92));
}

.inspect__result-content :deep(.report-section__index) {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-sm);
  font-weight: 700;
  line-height: 1;
}

.inspect__result-content :deep(.report-section--neutral .report-section__index) {
  background: var(--color-gray-700);
}

.inspect__result-content :deep(.report-section__title) {
  min-width: 0;
  color: var(--text-primary);
  font-size: clamp(1.28rem, 1.8vw, 1.65rem);
  font-weight: 800;
  line-height: 1.25;
  letter-spacing: 0;
}

.inspect__result-content :deep(.report-section__badge) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 var(--spacing-md);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
}

.inspect__result-content :deep(.report-section__badge--ok) {
  color: #047857;
  background: #d1fae5;
}

.inspect__result-content :deep(.report-section__badge--bad) {
  color: #b91c1c;
  background: #fee2e2;
}

.inspect__result-content :deep(.report-paragraph) {
  margin: 0;
  padding: 0 var(--spacing-xs) var(--spacing-sm) calc(40px + var(--spacing-md));
  color: var(--text-primary);
  font-size: clamp(1.04rem, 1.12vw, 1.16rem);
  line-height: 2;
  text-align: justify;
  overflow-wrap: anywhere;
}

.inspect__result-content :deep(.report-paragraph + .report-paragraph) {
  margin-top: calc(var(--spacing-sm) * -1);
}

.inspect__result-content :deep(strong) {
  font-weight: 700;
  color: var(--color-primary);
}


.inspect__trace-card {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.inspect__trace-head,
.inspect__trace-stage > div {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-md);
  align-items: center;
}

.inspect__trace-head span,
.inspect__trace-stage span,
.inspect__trace-stage p {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.inspect__trace-stages {
  display: grid;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.inspect__trace-stage {
  padding: var(--spacing-sm) var(--spacing-md);
  border-left: 4px solid var(--color-success);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.inspect__trace-stage--warn {
  border-left-color: #f59e0b;
}

.inspect__trace-stage--error {
  border-left-color: var(--color-primary);
}

.inspect__trace-stage p {
  margin: var(--spacing-xs) 0 0;
  overflow-wrap: anywhere;
}

.inspect__trace-issues {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-md);
  align-items: center;
}

.inspect__trace-issues span {
  padding: 3px var(--spacing-sm);
  border-radius: var(--radius-full);
  background: #fff1f2;
  color: var(--color-primary-dark);
  font-size: var(--font-size-xs);
}

@media (max-width: 1024px) {
  .inspect__result-section {
    position: static;
  }
}
</style>
