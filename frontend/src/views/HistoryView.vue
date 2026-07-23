<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import { ChevronDown, ClipboardCheck, FileText, Workflow } from 'lucide-vue-next'
import { clearInspectionHistory, createInspectionReview, deleteInspectionHistory, deleteInspectionReview, fetchInspectionHistory } from '@/api'

const ui = {
  title: '\u68c0\u6d4b\u5386\u53f2',
  subtitle: '\u67e5\u770b\u5df2\u7ecf\u68c0\u6d4b\u8fc7\u7684\u6d88\u9632\u6813\u56fe\u7247\u3001\u7ed3\u8bba\u548c\u5b8c\u6574\u62a5\u544a\u3002',
  total: '\u5171',
  rows: '\u6761\u8bb0\u5f55',
  page: '\u9875',
  all: '\u5168\u90e8',
  verdict: '\u68c0\u6d4b\u7ed3\u8bba',
  keyword: '\u5173\u952e\u8bcd',
  keywordPlaceholder: '\u641c\u7d22 ID\u3001\u56fe\u7247\u540d\u3001\u6807\u7b7e\u6216\u62a5\u544a\u5185\u5bb9',
  reset: '\u91cd\u7f6e',
  clearAll: '\u6e05\u7a7a\u5386\u53f2',
  clearConfirm: '\u786e\u5b9a\u6e05\u7a7a\u6240\u6709\u68c0\u6d4b\u5386\u53f2\u5417\uff1f',
  clearing: '\u6e05\u7a7a\u4e2d...',
  yoloPreview: '\u7ec4\u4ef6\u6807\u8bb0',
  loading: '\u6b63\u5728\u8bfb\u53d6\u68c0\u6d4b\u5386\u53f2...',
  empty: '\u6682\u65e0\u68c0\u6d4b\u5386\u53f2\uff0c\u5b8c\u6210\u4e00\u6b21\u667a\u80fd\u68c0\u6d4b\u540e\u4f1a\u81ea\u52a8\u51fa\u73b0\u5728\u8fd9\u91cc\u3002',
  compliant: '\u5408\u89c4',
  nonCompliant: '\u4e0d\u5408\u89c4',
  unknown: '\u672a\u77e5',
  scope: '\u68c0\u67e5\u8303\u56f4',
  labels: '\u9690\u60a3\u6807\u7b7e',
  noLabels: '\u65e0\u9690\u60a3\u6807\u7b7e',
  report: '\u5b8c\u6574\u62a5\u544a',
  query: '\u68c0\u6d4b\u63d0\u95ee',
  image: '\u68c0\u6d4b\u56fe\u7247',
  createdAt: '\u68c0\u6d4b\u65f6\u95f4',
  firstPage: '\u9996\u9875',
  previous: '\u4e0a\u4e00\u9875',
  next: '\u4e0b\u4e00\u9875',
  lastPage: '\u672b\u9875',
  delete: '\u5220\u9664',
  deleteConfirm: '\u786e\u5b9a\u5220\u9664\u8fd9\u6761\u68c0\u6d4b\u5386\u53f2\u5417\uff1f',
  deleting: '\u5220\u9664\u4e2d...',
  reviewTitle: '\u4eba\u5de5\u590d\u6838',
  reviewSubtitle: '\u8bb0\u5f55\u4eba\u5de5\u5bf9\u6a21\u578b\u7ed3\u8bba\u7684\u8ba4\u53ef\u4e0e\u4fee\u6b63\uff0c\u4fbf\u4e8e\u540e\u7eed\u6392\u67e5\u95ee\u9898\u6765\u6e90',
  reviewNone: '\u6682\u65e0\u590d\u6838\u8bb0\u5f55',
  reviewCount: '\u6761\u590d\u6838',
  reviewLatest: '\u6700\u65b0\u590d\u6838',
  reviewAccept: '\u662f\u5426\u8ba4\u53ef\u6a21\u578b\u7ed3\u679c',
  reviewAcceptUnknown: '\u672a\u9009\u62e9',
  reviewAcceptYes: '\u8ba4\u53ef',
  reviewAcceptNo: '\u4e0d\u8ba4\u53ef',
  reviewCorrectedVerdict: '\u4fee\u6b63\u7ed3\u8bba',
  reviewKeepVerdict: '\u4e0d\u4fee\u6b63',
  reviewCorrectedLabels: '\u4fee\u6b63\u9690\u60a3\u6807\u7b7e',
  reviewLabelsPlaceholder: '\u591a\u4e2a\u6807\u7b7e\u7528\u5206\u53f7\u6216\u6362\u884c\u5206\u9694',
  reviewErrorSource: '\u95ee\u9898\u6765\u6e90',
  reviewSourceUnknown: '\u672a\u5224\u5b9a',
  reviewSourceQwen: '\u57fa\u7840\u5206\u6790',
  reviewSourceYolo: '\u7279\u5f81\u6838\u9a8c',
  reviewSourceJudge: '\u4e00\u81f4\u6027\u6821\u9a8c',
  reviewSourcePrompt: '\u5206\u6790\u89c4\u5219',
  reviewSourceData: '\u53c2\u8003\u6570\u636e',
  reviewSourceOther: '\u5176\u4ed6',
  reviewComment: '\u590d\u6838\u8bf4\u660e',
  reviewCommentPlaceholder: '\u5199\u660e\u4eba\u5de5\u5224\u65ad\u4f9d\u636e\uff0c\u4f8b\u5982\u56fe\u4e2d\u53ef\u89c1\u6c34\u67aa\uff0c\u6a21\u578b\u8bef\u5224\u4e3a\u7f3a\u5931',
  reviewSubmit: '\u4fdd\u5b58\u590d\u6838',
  reviewSubmitting: '\u4fdd\u5b58\u4e2d...',
  reviewDeleteConfirm: '\u786e\u5b9a\u5220\u9664\u8fd9\u6761\u590d\u6838\u8bb0\u5f55\u5417\uff1f',
  reviewModelVerdict: '\u6a21\u578b\u7ed3\u8bba',
  reviewHumanVerdict: '\u4eba\u5de5\u590d\u6838',
  reviewNoComment: '\u672a\u586b\u5199\u590d\u6838\u8bf4\u660e',
  traceTitle: '\u5904\u7406\u8bb0\u5f55',
  traceHint: '\u5206\u6790 \u00b7 \u6838\u9a8c \u00b7 \u7559\u5b58',
  reportHint: '\u7ed3\u8bba\u4e0e\u5b8c\u6574\u8bf4\u660e'
}
const filters = ref({ verdict: '', q: '' })
const page = ref(1)
const pageSize = ref(12)
const payload = ref({ records: [], total: 0, page: 1, pages: 1 })
const loading = ref(false)
const error = ref('')
const selectedImage = ref(null)
const deletingId = ref('')
const clearingAll = ref(false)
const failedImages = ref(new Set())
const reviewForms = ref({})
const reviewSubmittingId = ref('')
const reviewDeletingId = ref('')

marked.setOptions({ breaks: true, gfm: true })

const visiblePages = computed(() => {
  const pages = payload.value.pages || 1
  const current = page.value
  const start = Math.max(1, current - 2)
  const end = Math.min(pages, current + 2)
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
})

const loadHistory = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchInspectionHistory({
      ...filters.value,
      page: page.value,
      page_size: pageSize.value
    })
  } catch (err) {
    error.value = err.message || 'load history failed'
  } finally {
    loading.value = false
  }
}

const setPage = (target) => {
  const pages = payload.value.pages || 1
  page.value = Math.max(1, Math.min(pages, target))
}

const goPage = (direction) => setPage(page.value + direction)

const resetFilters = () => {
  filters.value = { verdict: '', q: '' }
  page.value = 1
}

const reportHtml = (record) => marked(record.response || record.responseExcerpt || '')
const labelsOf = (record) => record.labels?.length ? record.labels : [ui.noLabels]
const traceStagesOf = (record) => record.trace?.stages || []
const traceIssuesOf = (record) => record.trace?.summary?.issues || []
const formatDuration = (value) => `${Number(value || 0)}ms`
const stageStatusText = (stage) => {
  if (stage?.superseded) return '\u672a\u91c7\u7eb3'
  if (stage?.status === 'warn') return '\u63d0\u9192'
  if (stage?.status === 'error') return '\u5f02\u5e38'
  if (stage?.status === 'skipped') return '\u8df3\u8fc7'
  return '\u6b63\u5e38'
}
const stageTitleOf = (stage) => {
  const name = String(stage?.name || '').toLowerCase()
  const signal = `${name} ${String(stage?.title || '').toLowerCase()}`
  if (name === 'qwen_first') return 'A \u00b7 \u57fa\u7840\u5206\u6790'
  if (signal.includes('missing') || signal.includes('\u7f3a\u5931')) return 'R1 \u00b7 \u5b8c\u6574\u6027\u6821\u9a8c'
  if (signal.includes('kink') || signal.includes('hose') || signal.includes('\u6298\u5f2f') || signal.includes('\u5f2f\u6298')) return 'R2 \u00b7 \u72b6\u6001\u6821\u9a8c'
  if (signal.includes('direction') || signal.includes('outlet') || signal.includes('\u65b9\u5411')) return 'R3 \u00b7 \u5b89\u88c5\u6821\u9a8c'
  if (name.startsWith('yolo_')) return 'B \u00b7 \u7279\u5f81\u6838\u9a8c'
  if (name.includes('review') || name.includes('judge')) return 'C \u00b7 \u4e00\u81f4\u6027\u6821\u9a8c'
  return 'C \u00b7 \u7ed3\u679c\u6821\u9a8c'
}
const issueTitleOf = (issue) => {
  const text = `${issue?.type || ''} ${issue?.title || ''}`.toLowerCase()
  if (text.includes('qwen') || text.includes('\u521d\u68c0')) return '\u521d\u6b65\u7ed3\u8bba\u5df2\u6821\u6b63'
  if (text.includes('yolo') || text.includes('\u68c0\u51fa')) return '\u5019\u9009\u8bc1\u636e\u672a\u91c7\u7eb3'
  if (text.includes('\u7f6e\u4fe1') || text.includes('confidence')) return '\u6821\u9a8c\u7f6e\u4fe1\u4e0d\u8db3'
  if (text.includes('\u7f3a\u5931') || text.includes('missing')) return '\u5b8c\u6574\u6027\u7ed3\u679c\u5df2\u590d\u67e5'
  return '\u9636\u6bb5\u7ed3\u679c\u5df2\u8c03\u6574'
}
const stageMainText = (stage) => {
  if (stage.name === 'qwen_first') {
    const output = stage.output || {}
    return `${output.verdict || '\u672a\u89e3\u6790\u7ed3\u8bba'} / ${(output.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
  }
  if (String(stage.name || '').startsWith('yolo_')) {
    const summary = `\u8bc6\u522b\u5230 ${stage.detectionCount || 0} \u9879\u7ec4\u4ef6\u8bc1\u636e / ${(stage.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
    return stage.superseded ? `\u8be5\u9636\u6bb5\u7ed3\u679c\u672a\u91c7\u7eb3\uff1a${summary}` : summary
  }
  const output = stage.output || {}
  return `${output.verdict || '\u672a\u89e3\u6790\u7ed3\u8bba'} / ${(output.labels || []).join('\uff1b') || '\u65e0\u6807\u7b7e'}`
}
const previewUrlOf = (record) => record?.previewImageUrl || record?.imageUrl || ""

const yoloBoxesOf = (record) => {
  const width = Number(record?.yolo?.imageWidth || 0)
  const height = Number(record?.yolo?.imageHeight || 0)
  if (!width || !height) return []
  return (record?.yolo?.detections || []).map((item, index) => {
    let coords = Array.isArray(item?.bboxNorm) ? item.bboxNorm : []
    if (coords.length !== 4 && Array.isArray(item?.bbox) && item.bbox.length === 4) {
      coords = [
        Number(item.bbox[0]) / width,
        Number(item.bbox[1]) / height,
        Number(item.bbox[2]) / width,
        Number(item.bbox[3]) / height
      ]
    }
    if (coords.length !== 4) return null
    const [x1, y1, x2, y2] = coords.map((value) => Math.max(0, Math.min(1, Number(value) || 0)))
    if (x2 <= x1 || y2 <= y1) return null
    const confidence = Number(item?.confidence || 0)
    const label = item?.label || item?.className || ui.yoloPreview
    return {
      id: `${record?.id || 'record'}-${index}`,
      index: index + 1,
      label,
      confidence,
      legend: `${index + 1}. ${label}${confidence ? ` ${Math.round(confidence * 100)}%` : ''}`,
      left: `${x1 * 100}%`,
      top: `${y1 * 100}%`,
      width: `${(x2 - x1) * 100}%`,
      height: `${(y2 - y1) * 100}%`
    }
  }).filter(Boolean)
}

const hasYoloBoxes = (record) => yoloBoxesOf(record).length > 0
const yoloLegendOf = (record) => yoloBoxesOf(record).map((box) => box.legend)

const imageStyleOf = (record) => {
  const width = Number(record?.yolo?.imageWidth || 0)
  const height = Number(record?.yolo?.imageHeight || 0)
  if (width > 0 && height > 0) {
    return { aspectRatio: `${width} / ${height}` }
  }
  return {}
}

const boxStyleOf = (box) => ({
  left: box.left,
  top: box.top,
  width: box.width,
  height: box.height
})

const openImage = (record) => {
  if (previewUrlOf(record)) selectedImage.value = record
}
const closeImage = () => {
  selectedImage.value = null
}
const markImageFailed = (url) => {
  failedImages.value = new Set([...failedImages.value, url])
}
const canShowImage = (record) => {
  const url = previewUrlOf(record)
  return Boolean(url && !failedImages.value.has(url))
}

const emptyReviewForm = () => ({
  acceptance: '',
  correctedVerdict: '',
  correctedLabels: '',
  errorSource: '',
  comment: ''
})

const reviewFormOf = (record) => {
  const id = record?.id || ''
  if (!id) return emptyReviewForm()
  if (!reviewForms.value[id]) {
    reviewForms.value = { ...reviewForms.value, [id]: emptyReviewForm() }
  }
  return reviewForms.value[id]
}

const reviewsOf = (record) => record?.reviews || []
const latestReviewOf = (record) => reviewsOf(record)[0] || null
const hasReviewCorrection = (record) => Boolean(latestReviewOf(record)?.correctedVerdict || latestReviewOf(record)?.correctedLabels?.length)
const sourceTextOf = (source) => ({
  qwen: ui.reviewSourceQwen,
  yolo: ui.reviewSourceYolo,
  judge: ui.reviewSourceJudge,
  prompt: ui.reviewSourcePrompt,
  data: ui.reviewSourceData,
  other: ui.reviewSourceOther
}[source] || ui.reviewSourceUnknown)
const acceptTextOf = (review) => {
  if (!review) return ui.reviewAcceptUnknown
  if (review.acceptModelResult === true) return ui.reviewAcceptYes
  if (review.acceptModelResult === false) return ui.reviewAcceptNo
  return ui.reviewAcceptUnknown
}
const reviewHumanVerdictOf = (record) => {
  const review = latestReviewOf(record)
  if (!review) return ui.reviewAcceptUnknown
  if (review.correctedVerdict) return review.correctedVerdict
  return acceptTextOf(review)
}
const splitReviewLabels = (value) => String(value || '')
  .split(/[\n;\uFF1B,\uFF0C]/)
  .map((item) => item.trim())
  .filter(Boolean)

const syncRecordReviews = (record, reviews) => {
  record.reviews = reviews
  record.reviewSummary = {
    count: reviews.length,
    latest: reviews[0] || null,
    hasCorrection: Boolean(reviews[0]?.correctedVerdict || reviews[0]?.correctedLabels?.length)
  }
}

const submitReview = async (record) => {
  if (!record?.id) return
  const form = reviewFormOf(record)
  if (!form.correctedVerdict && !form.correctedLabels.trim() && !form.comment.trim() && !form.errorSource && !form.acceptance) {
    error.value = ui.reviewCommentPlaceholder
    return
  }
  reviewSubmittingId.value = record.id
  error.value = ''
  try {
    const review = await createInspectionReview(record.id, {
      acceptModelResult: form.acceptance ? form.acceptance === 'yes' : null,
      correctedVerdict: form.correctedVerdict,
      correctedLabels: splitReviewLabels(form.correctedLabels),
      errorSource: form.errorSource,
      comment: form.comment
    })
    syncRecordReviews(record, [review, ...reviewsOf(record)])
    reviewForms.value = { ...reviewForms.value, [record.id]: emptyReviewForm() }
  } catch (err) {
    error.value = err.message || 'save review failed'
  } finally {
    reviewSubmittingId.value = ''
  }
}

const deleteReviewItem = async (record, review) => {
  if (!review?.id || !window.confirm(ui.reviewDeleteConfirm)) return
  reviewDeletingId.value = review.id
  error.value = ''
  try {
    await deleteInspectionReview(review.id)
    syncRecordReviews(record, reviewsOf(record).filter((item) => item.id !== review.id))
  } catch (err) {
    error.value = err.message || 'delete review failed'
  } finally {
    reviewDeletingId.value = ''
  }
}

const deleteRecord = async (record) => {
  if (!record?.id || !window.confirm(ui.deleteConfirm)) return
  deletingId.value = record.id
  error.value = ''
  try {
    await deleteInspectionHistory(record.id)
    if (payload.value.records.length === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await loadHistory()
    }
  } catch (err) {
    error.value = err.message || 'delete history failed'
  } finally {
    deletingId.value = ''
  }
}


const clearAllHistory = async () => {
  if (!payload.value.records.length || !window.confirm(ui.clearConfirm)) return
  clearingAll.value = true
  error.value = ''
  try {
    await clearInspectionHistory()
    selectedImage.value = null
    page.value = 1
    payload.value = { records: [], total: 0, page: 1, pages: 1 }
    failedImages.value = new Set()
    await loadHistory()
  } catch (err) {
    error.value = err.message || 'clear history failed'
  } finally {
    clearingAll.value = false
  }
}


watch(filters, () => {
  page.value = 1
  loadHistory()
}, { deep: true })

watch(page, loadHistory)
onMounted(loadHistory)
</script>

<template>
  <div class="history-page">
    <div class="history-page__container container">
      <header class="history-hero">
        <div>
          <span class="history-hero__eyebrow">History</span>
          <h1>{{ ui.title }}</h1>
          <p>{{ ui.subtitle }}</p>
        </div>
        <div class="history-hero__stat">
          <strong>{{ payload.total }}</strong>
          <span>{{ ui.rows }}</span>
        </div>
      </header>

      <section class="history-panel">
        <div class="history-toolbar">
          <label>
            <span>{{ ui.verdict }}</span>
            <select v-model="filters.verdict">
              <option value="">{{ ui.all }}</option>
              <option :value="ui.nonCompliant">{{ ui.nonCompliant }}</option>
              <option :value="ui.compliant">{{ ui.compliant }}</option>
            </select>
          </label>
          <label class="history-toolbar__search">
            <span>{{ ui.keyword }}</span>
            <input v-model.trim="filters.q" type="search" :placeholder="ui.keywordPlaceholder" />
          </label>
          <button class="history-button" type="button" @click="resetFilters">{{ ui.reset }}</button>
          <button class="history-button history-button--danger" type="button" :disabled="!payload.total || clearingAll" @click="clearAllHistory">{{ clearingAll ? ui.clearing : ui.clearAll }}</button>
        </div>

        <div class="history-status">
          <span v-if="loading">{{ ui.loading }}</span>
          <span v-else-if="error">{{ error }}</span>
          <span v-else>{{ ui.total }} {{ payload.total }} {{ ui.rows }} / {{ payload.page }} / {{ payload.pages || 1 }} {{ ui.page }}</span>
        </div>

        <div v-if="!loading && payload.records.length === 0" class="history-empty">{{ ui.empty }}</div>

        <div class="history-grid">
          <article v-for="record in payload.records" :key="record.id" class="history-card">
            <button class="history-card__image" type="button" :style="imageStyleOf(record)" :disabled="!previewUrlOf(record)" @click="openImage(record)">
              <img
                v-if="canShowImage(record)"
                :src="previewUrlOf(record)"
                :alt="record.id"
                loading="lazy"
                @error="markImageFailed(previewUrlOf(record))"
              />
              <span v-else>{{ ui.image }}</span>
              <div v-if="hasYoloBoxes(record)" class="history-yolo-overlay">
                <div v-for="box in yoloBoxesOf(record)" :key="box.id" class="history-yolo-box" :style="boxStyleOf(box)">
                  <span>{{ box.index }}</span>
                </div>
              </div>
            </button>
            <div class="history-card__body">
              <div class="history-card__topline">
                <strong>{{ record.id }}</strong>
                <div class="history-card__actions">
                  <span :class="['history-badge', record.verdict === ui.compliant ? 'history-badge--ok' : 'history-badge--bad']">
                    {{ record.verdict || ui.unknown }}
                  </span>
                  <button class="history-delete" type="button" :disabled="deletingId === record.id" @click="deleteRecord(record)">
                    {{ deletingId === record.id ? ui.deleting : ui.delete }}
                  </button>
                </div>
              </div>
              <dl class="history-card__meta">
                <div>
                  <dt>{{ ui.createdAt }}</dt>
                  <dd>{{ record.createdText }}</dd>
                </div>
                <div>
                  <dt>{{ ui.scope }}</dt>
                  <dd>{{ record.scope || ui.unknown }}</dd>
                </div>
                <div>
                  <dt>{{ ui.query }}</dt>
                  <dd>{{ record.query }}</dd>
                </div>
              </dl>
              <div v-if="hasYoloBoxes(record)" class="history-card__hint">{{ ui.yoloPreview }}</div>
              <div v-if="hasYoloBoxes(record)" class="history-yolo-legend history-yolo-legend--card">
                <span v-for="item in yoloLegendOf(record).slice(0, 4)" :key="`${record.id}-${item}`">{{ item }}</span>
              </div>
              <div class="history-labels">
                <span v-for="label in labelsOf(record)" :key="`${record.id}-${label}`">{{ label }}</span>
              </div>
              <details class="history-review">
                <summary class="history-action">
                  <span class="history-action__icon"><ClipboardCheck :size="16" :stroke-width="2" /></span>
                  <strong class="history-action__label">{{ ui.reviewTitle }}</strong>
                  <span class="history-action__meta">
                    {{ reviewsOf(record).length ? `${reviewsOf(record).length} ${ui.reviewCount}` : ui.reviewNone }}
                  </span>
                  <ChevronDown class="history-action__chevron" :size="16" :stroke-width="2" />
                </summary>
                <div class="history-review__body">
                  <p class="history-review__subtitle">{{ ui.reviewSubtitle }}</p>
                  <div v-if="latestReviewOf(record)" class="history-review__latest" :class="{ 'history-review__latest--changed': hasReviewCorrection(record) }">
                    <span>{{ ui.reviewModelVerdict }}: {{ record.verdict || ui.unknown }}</span>
                    <strong>{{ ui.reviewHumanVerdict }}: {{ reviewHumanVerdictOf(record) }}</strong>
                  </div>
                  <div v-if="reviewsOf(record).length" class="history-review__list">
                    <article v-for="review in reviewsOf(record)" :key="review.id" class="history-review__item">
                      <div>
                        <strong>{{ review.correctedVerdict || acceptTextOf(review) }}</strong>
                        <span>{{ review.createdText }} / {{ sourceTextOf(review.errorSource) }}</span>
                      </div>
                      <p>{{ review.comment || ui.reviewNoComment }}</p>
                      <div v-if="review.correctedLabels?.length" class="history-review__labels">
                        <span v-for="label in review.correctedLabels" :key="`${review.id}-${label}`">{{ label }}</span>
                      </div>
                      <button class="history-review__delete" type="button" :disabled="reviewDeletingId === review.id" @click="deleteReviewItem(record, review)">{{ ui.delete }}</button>
                    </article>
                  </div>
                  <form class="history-review__form" @submit.prevent="submitReview(record)">
                    <label>
                      <span>{{ ui.reviewAccept }}</span>
                      <select v-model="reviewFormOf(record).acceptance">
                        <option value="">{{ ui.reviewAcceptUnknown }}</option>
                        <option value="yes">{{ ui.reviewAcceptYes }}</option>
                        <option value="no">{{ ui.reviewAcceptNo }}</option>
                      </select>
                    </label>
                    <label>
                      <span>{{ ui.reviewCorrectedVerdict }}</span>
                      <select v-model="reviewFormOf(record).correctedVerdict">
                        <option value="">{{ ui.reviewKeepVerdict }}</option>
                        <option :value="ui.compliant">{{ ui.compliant }}</option>
                        <option :value="ui.nonCompliant">{{ ui.nonCompliant }}</option>
                        <option :value="ui.unknown">{{ ui.unknown }}</option>
                      </select>
                    </label>
                    <label>
                      <span>{{ ui.reviewErrorSource }}</span>
                      <select v-model="reviewFormOf(record).errorSource">
                        <option value="">{{ ui.reviewSourceUnknown }}</option>
                        <option value="qwen">{{ ui.reviewSourceQwen }}</option>
                        <option value="yolo">{{ ui.reviewSourceYolo }}</option>
                        <option value="judge">{{ ui.reviewSourceJudge }}</option>
                        <option value="prompt">{{ ui.reviewSourcePrompt }}</option>
                        <option value="data">{{ ui.reviewSourceData }}</option>
                        <option value="other">{{ ui.reviewSourceOther }}</option>
                      </select>
                    </label>
                    <label class="history-review__wide">
                      <span>{{ ui.reviewCorrectedLabels }}</span>
                      <textarea v-model="reviewFormOf(record).correctedLabels" rows="2" :placeholder="ui.reviewLabelsPlaceholder"></textarea>
                    </label>
                    <label class="history-review__wide">
                      <span>{{ ui.reviewComment }}</span>
                      <textarea v-model="reviewFormOf(record).comment" rows="3" :placeholder="ui.reviewCommentPlaceholder"></textarea>
                    </label>
                    <button class="history-review__submit" type="submit" :disabled="reviewSubmittingId === record.id">
                      {{ reviewSubmittingId === record.id ? ui.reviewSubmitting : ui.reviewSubmit }}
                    </button>
                  </form>
                </div>
              </details>
              <details class="history-trace">
                <summary class="history-action">
                  <span class="history-action__icon"><Workflow :size="16" :stroke-width="2" /></span>
                  <strong class="history-action__label">{{ ui.traceTitle }}</strong>
                  <span class="history-action__meta">{{ ui.traceHint }}</span>
                  <ChevronDown class="history-action__chevron" :size="16" :stroke-width="2" />
                </summary>
                <div v-if="traceStagesOf(record).length" class="history-trace__body">
                  <p class="history-trace__note">记录本次任务的处理阶段、运行状态和关键结论，用于核对结果形成过程。</p>
                  <div class="history-trace__summary">
                    <span>&#x603b;&#x8017;&#x65f6; {{ formatDuration(record.trace?.summary?.totalDurationMs) }}</span>
                    <span>&#x95ee;&#x9898; {{ traceIssuesOf(record).length }} &#x4e2a;</span>
                  </div>
                  <div
                    v-for="stage in traceStagesOf(record)"
                    :key="`${record.id}-${stage.name}`"
                    :class="['history-trace__stage', `history-trace__stage--${stage.status || 'ok'}`]"
                  >
                    <div>
                      <strong>{{ stageTitleOf(stage) }}</strong>
                      <span>{{ stageStatusText(stage) }} &middot; {{ formatDuration(stage.durationMs) }}</span>
                    </div>
                    <p>{{ stageMainText(stage) }}</p>
                  </div>
                  <div v-if="traceIssuesOf(record).length" class="history-trace__issues">
                    <span v-for="issue in traceIssuesOf(record)" :key="`${record.id}-${issue.type}`">{{ issueTitleOf(issue) }}</span>
                  </div>
                </div>
                <p v-else class="history-trace__empty">{{ ui.traceEmpty }}</p>
              </details>
              <details class="history-report">
                <summary class="history-action">
                  <span class="history-action__icon"><FileText :size="16" :stroke-width="2" /></span>
                  <strong class="history-action__label">{{ ui.report }}</strong>
                  <span class="history-action__meta">{{ ui.reportHint }}</span>
                  <ChevronDown class="history-action__chevron" :size="16" :stroke-width="2" />
                </summary>
                <div class="history-report__content markdown-body" v-html="reportHtml(record)"></div>
              </details>
            </div>
          </article>
        </div>

        <div v-if="payload.records.length" class="history-pager">
          <span>{{ ui.total }} {{ payload.pages || 1 }} {{ ui.page }}</span>
          <button class="history-button" type="button" :disabled="page <= 1 || loading" @click="setPage(1)">{{ ui.firstPage }}</button>
          <button class="history-button" type="button" :disabled="page <= 1 || loading" @click="goPage(-1)">{{ ui.previous }}</button>
          <button
            v-for="item in visiblePages"
            :key="item"
            class="history-button history-button--number"
            :class="{ 'history-button--active': item === page }"
            type="button"
            @click="setPage(item)"
          >
            {{ item }}
          </button>
          <button class="history-button" type="button" :disabled="page >= payload.pages || loading" @click="goPage(1)">{{ ui.next }}</button>
          <button class="history-button" type="button" :disabled="page >= payload.pages || loading" @click="setPage(payload.pages || 1)">{{ ui.lastPage }}</button>
        </div>
      </section>
    </div>

    <div v-if="selectedImage" class="history-preview" @click.self="closeImage">
      <div class="history-preview__dialog">
        <button class="history-preview__close" type="button" @click="closeImage">x</button>
        <div class="history-preview__image" :style="imageStyleOf(selectedImage)">
          <img
            v-if="canShowImage(selectedImage)"
            :src="previewUrlOf(selectedImage)"
            :alt="selectedImage.id"
            @error="markImageFailed(previewUrlOf(selectedImage))"
          />
          <span v-else>{{ ui.image }}</span>
          <div v-if="hasYoloBoxes(selectedImage)" class="history-yolo-overlay history-yolo-overlay--preview">
            <div v-for="box in yoloBoxesOf(selectedImage)" :key="box.id" class="history-yolo-box" :style="boxStyleOf(box)">
              <span>{{ box.index }}</span>
            </div>
          </div>
        </div>
        <div v-if="hasYoloBoxes(selectedImage)" class="history-yolo-legend history-yolo-legend--preview">
          <span v-for="item in yoloLegendOf(selectedImage)" :key="`${selectedImage.id}-${item}`">{{ item }}</span>
        </div>
        <div class="history-preview__meta">
          <strong>{{ selectedImage.id }}</strong>
          <span>{{ selectedImage.createdText }}</span>
          <span>{{ selectedImage.verdict || ui.unknown }} / {{ selectedImage.scope || ui.unknown }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-page {
  min-height: 100vh;
  padding: 96px 0 40px;
  background: var(--bg-secondary);
}

.history-page__container {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.history-hero,
.history-panel,
.history-card {
  background: var(--bg-primary);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
}

.history-hero {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-xl);
  padding: 24px 28px;
  align-items: flex-end;
}

.history-hero__eyebrow {
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.history-hero h1 {
  margin: var(--spacing-xs) 0;
  font-size: var(--font-size-3xl);
  line-height: 1.2;
}

.history-hero p,
.history-status,
.history-card__meta,
.history-report__content {
  color: var(--text-secondary);
}

.history-hero__stat {
  text-align: right;
}

.history-hero__stat strong {
  display: block;
  font-size: var(--font-size-3xl);
  line-height: 1;
}

.history-panel {
  padding: 22px;
}

.history-toolbar {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(240px, 1fr) max-content max-content;
  gap: var(--spacing-md);
  align-items: end;
  margin-bottom: var(--spacing-md);
}

.history-toolbar label {
  display: grid;
  gap: var(--spacing-xs);
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

.history-toolbar select,
.history-toolbar input {
  min-height: 44px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  padding: 0 var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.history-status {
  min-height: 24px;
  margin-bottom: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.history-empty {
  padding: var(--spacing-2xl);
  text-align: center;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.history-card {
  overflow: hidden;
  min-width: 0;
}

.history-card__image {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  background: var(--bg-tertiary);
  cursor: zoom-in;
}

.history-card__image:disabled {
  cursor: default;
}

.history-card__image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #111;
}

.history-card__image > span {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  color: var(--text-secondary);
  background: var(--bg-secondary);
}

.history-card__body {
  padding: 16px 17px 18px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.history-card__topline {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-sm);
  align-items: center;
}

.history-card__actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.history-card__topline strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.history-badge {
  flex: 0 0 auto;
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  color: var(--text-inverse);
  background: var(--color-primary);
  font-size: var(--font-size-xs);
}

.history-badge--ok {
  background: var(--color-success);
}

.history-badge--bad {
  background: var(--color-primary);
}

.history-delete {
  min-height: 28px;
  padding: 0 var(--spacing-sm);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-gray-200);
  background: var(--bg-secondary);
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.history-delete:disabled {
  color: var(--text-tertiary);
  cursor: not-allowed;
}

.history-card__meta {
  display: grid;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
}

.history-card__meta div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: var(--spacing-sm);
}

.history-card__meta dt {
  color: var(--text-tertiary);
}

.history-card__meta dd {
  min-width: 0;
  overflow-wrap: anywhere;
}

.history-labels {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.history-labels span {
  padding: 3px var(--spacing-sm);
  border-radius: var(--radius-full);
  background: var(--color-primary-subtle);
  color: var(--color-primary-dark);
  font-size: var(--font-size-xs);
  line-height: 1.35;
}




.history-review,
.history-trace,
.history-report {
  border-top: 1px solid var(--color-gray-100);
  padding-top: var(--spacing-sm);
}

.history-action {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto 16px;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  cursor: pointer;
  list-style: none;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  padding: 8px 10px;
  background: #fafafa;
  color: var(--text-primary);
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}

.history-action:hover,
details[open] > .history-action {
  border-color: rgba(239, 68, 68, 0.14);
  background: #fff;
  box-shadow: 0 5px 16px rgba(15, 23, 42, 0.05);
}

.history-action::-webkit-details-marker {
  display: none;
}

.history-action__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(239, 68, 68, 0.12);
  border-radius: 8px;
  background: #fff;
  color: var(--color-primary);
}

.history-action__label {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: 700;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-action__meta {
  max-width: 150px;
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.25;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-action__chevron {
  color: var(--text-tertiary);
  transition: transform 0.18s ease, color 0.18s ease;
}

details[open] > .history-action .history-action__chevron {
  color: var(--color-primary);
  transform: rotate(180deg);
}

.history-review__body {
  display: grid;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.history-review__subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  line-height: 1.6;
}

.history-review__latest,
.history-review__item {
  padding: 10px;
  border: 1px solid var(--color-gray-100);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
}

.history-review__latest {
  display: grid;
  gap: 3px;
  border-left: 3px solid var(--color-gray-300);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.history-review__latest--changed {
  border-left-color: var(--color-primary);
  background: #fffafa;
}

.history-review__latest strong {
  color: var(--text-primary);
}

.history-review__list {
  display: grid;
  gap: var(--spacing-xs);
}

.history-review__item {
  position: relative;
  display: grid;
  gap: var(--spacing-xs);
}

.history-review__item > div:first-child {
  display: grid;
  gap: 2px;
  padding-right: 46px;
}

.history-review__item strong {
  color: var(--text-primary);
  font-size: var(--font-size-sm);
}

.history-review__item span,
.history-review__item p {
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  line-height: 1.6;
}

.history-review__item p {
  margin: 0;
}

.history-review__labels {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.history-review__labels span {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  background: var(--color-primary-subtle);
  color: var(--color-primary-dark);
  font-size: var(--font-size-xs);
}

.history-review__delete {
  position: absolute;
  top: var(--spacing-sm);
  right: var(--spacing-sm);
  color: var(--color-primary);
  background: transparent;
  font-size: var(--font-size-xs);
}

.history-review__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-sm);
  padding: 12px;
  border: 1px solid var(--color-gray-100);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, #fff, #fffafa);
}

.history-review__form label {
  display: grid;
  gap: 6px;
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  min-width: 0;
}

.history-review__form select,
.history-review__form textarea {
  width: 100%;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  padding: 9px 10px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  line-height: 1.45;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.history-review__form textarea {
  min-height: 72px;
  resize: vertical;
}

.history-review__form select:focus,
.history-review__form textarea:focus {
  outline: none;
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.08);
}

.history-review__wide,
.history-review__submit {
  grid-column: 1 / -1;
}

.history-review__submit {
  min-height: 42px;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 8px 18px rgba(239, 68, 68, 0.16);
}

.history-review__submit:disabled,
.history-review__delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.history-trace__note {
  margin: 0;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  background: #fff7f7;
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  line-height: 1.6;
}

.history-trace__body {
  display: grid;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.history-trace__summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.history-trace__stage {
  padding: var(--spacing-sm);
  border-left: 4px solid var(--color-success);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}

.history-trace__stage--warn {
  border-left-color: #f59e0b;
}

.history-trace__stage--error {
  border-left-color: var(--color-primary);
}

.history-trace__stage--skipped {
  border-left-color: var(--color-gray-400);
  background: var(--bg-tertiary);
}

.history-trace__stage > div {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-sm);
}

.history-trace__stage span,
.history-trace__stage p,
.history-trace__empty {
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.history-trace__stage p {
  margin: var(--spacing-xs) 0 0;
  overflow-wrap: anywhere;
}

.history-trace__issues {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.history-trace__issues span {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  background: #fff1f2;
  color: var(--color-primary-dark);
  font-size: var(--font-size-xs);
}

.history-report__content {
  margin-top: var(--spacing-sm);
  max-height: 360px;
  overflow: auto;
  line-height: 1.75;
  font-size: var(--font-size-sm);
}

.history-pager {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  overflow-x: auto;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.history-pager span,
.history-yolo-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.history-yolo-box {
  position: absolute;
  border: 2px solid #dc2626;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.history-yolo-box span {
  position: absolute;
  left: 4px;
  top: 4px;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: #dc2626;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 6px 16px rgba(220, 38, 38, 0.22);
}

.history-yolo-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.history-yolo-legend span {
  max-width: 100%;
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: rgba(220, 38, 38, 0.08);
  color: #991b1b;
  font-size: var(--font-size-xs);
  line-height: 1.35;
}

.history-yolo-legend--card span {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-yolo-legend--preview {
  margin-top: var(--spacing-sm);
}

.history-card__hint {
  display: inline-flex;
  align-self: flex-start;
  padding: 3px var(--spacing-sm);
  border-radius: var(--radius-full);
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: var(--font-size-xs);
  line-height: 1.35;
}

.history-button {
  flex: 0 0 auto;
  white-space: nowrap;
}

.history-button {
  min-height: 38px;
  min-width: 58px;
  padding: 0 var(--spacing-md);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-gray-200);
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.history-button:disabled {
  color: var(--text-tertiary);
  cursor: not-allowed;
}

.history-button--number {
  min-width: 38px;
  padding: 0 var(--spacing-sm);
}

.history-button--danger {
  color: var(--text-inverse);
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.history-button--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-inverse);
}

.history-preview {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: var(--spacing-xl);
  background: rgba(17, 24, 39, 0.78);
}

.history-preview__dialog {
  position: relative;
  width: min(980px, 96vw);
  max-height: 92vh;
  padding: var(--spacing-lg);
  border-radius: var(--radius-xl);
  background: var(--bg-primary);
  overflow: auto;
  box-shadow: var(--shadow-lg);
}

.history-preview__close {
  position: absolute;
  top: var(--spacing-sm);
  right: var(--spacing-sm);
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-gray-200);
  background: var(--bg-primary);
}

.history-preview__image {
  position: relative;
  width: 100%;
  max-height: 72vh;
}

.history-preview img {
  width: 100%;
  max-height: 72vh;
  object-fit: contain;
  background: #111;
}

.history-yolo-overlay--preview .history-yolo-box {
  border-width: 3px;
}

.history-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
  color: var(--text-secondary);
}

.history-preview__meta strong {
  color: var(--text-primary);
}

@media (max-width: 1024px) {
  .history-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .history-hero,
  .history-toolbar {
    grid-template-columns: 1fr;
  }

  .history-hero {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .history-hero__stat {
    text-align: left;
  }

  .history-grid {
    grid-template-columns: 1fr;
  }
}
</style>
