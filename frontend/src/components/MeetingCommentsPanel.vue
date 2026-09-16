<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NList, NListItem, NPopconfirm } from 'naive-ui'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { CommentPage, MeetingComment } from '../domain/comments'
import type { Meeting } from '../domain/meetings'
import { formatDateTime } from '../utils/time'
import MentionTextarea from './MentionTextarea.vue'

const props = withDefaults(defineProps<{ meeting: Meeting; focusCommentId?: string | null }>(), { focusCommentId: null })
const comments = ref<MeetingComment[]>([])
const nextCursor = ref<string | null>(null)
const body = ref('')
const mentionIds = ref<string[]>([])
const replyTo = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editBody = ref('')
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const submitting = ref(false)
const savingEdit = ref(false)
const togglingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)
const repliesLoadingId = ref<string | null>(null)
const highlightedId = ref<string | null>(null)
let highlightHandle: number | undefined

const focusFound = computed(() => {
  const id = props.focusCommentId
  if (!id) return true
  return comments.value.some((comment) => comment.id === id
    || comment.replies.some((reply) => reply.id === id))
})

function listQuery(before?: string | null) {
  const params = new URLSearchParams({ target_type: 'meeting', target_id: props.meeting.id, limit: '20', reply_limit: '3' })
  if (before) params.set('before', before)
  return `/api/comments?${params.toString()}`
}

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

async function focusComment() {
  const id = props.focusCommentId
  if (!id) return
  await nextTick()
  const element = document.querySelector(`[data-comment-id="${id}"]`)
  if (!element) return
  if (typeof element.scrollIntoView === 'function') {
    element.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' })
  }
  if (prefersReducedMotion()) return
  highlightedId.value = id
  if (highlightHandle !== undefined) window.clearTimeout(highlightHandle)
  highlightHandle = window.setTimeout(() => { highlightedId.value = null }, 2_000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await api<CommentPage>(listQuery())
    comments.value = page.items
    nextCursor.value = page.next_cursor
  } catch (reason) { error.value = errorMessage(reason, '评论加载失败') }
  finally {
    loading.value = false
    void focusComment()
  }
}

async function loadMore() {
  if (loadingMore.value || !nextCursor.value) return
  loadingMore.value = true
  error.value = ''
  try {
    const page = await api<CommentPage>(listQuery(nextCursor.value))
    comments.value = [...comments.value, ...page.items]
    nextCursor.value = page.next_cursor
  } catch (reason) { error.value = errorMessage(reason, '评论加载失败') }
  finally { loadingMore.value = false }
}

async function submit() {
  if (!body.value.trim() || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    await api('/api/comments', { method: 'POST', body: JSON.stringify({ target_type: 'meeting', target_id: props.meeting.id, parent_id: replyTo.value, body_markdown: body.value, mention_user_ids: mentionIds.value }) })
    body.value = ''
    mentionIds.value = []
    replyTo.value = null
    await load()
  } catch (reason) { error.value = errorMessage(reason, '评论提交失败') }
  finally { submitting.value = false }
}

async function toggle(comment: MeetingComment) {
  if (togglingId.value) return
  togglingId.value = comment.id
  error.value = ''
  try {
    await api(`/api/comments/${comment.id}/${comment.resolved_at ? 'reopen' : 'resolve'}`, { method: 'POST', body: JSON.stringify({ expected_version: comment.version }) })
    await load()
  } catch (reason) { error.value = errorMessage(reason, '状态更新失败') }
  finally { togglingId.value = null }
}

function beginEdit(comment: MeetingComment) {
  editingId.value = comment.id
  editBody.value = comment.body_markdown ?? ''
}

async function saveEdit(comment: MeetingComment) {
  if (!editBody.value.trim() || savingEdit.value) return
  savingEdit.value = true
  error.value = ''
  try {
    await api(`/api/comments/${comment.id}`, { method: 'PUT', body: JSON.stringify({ expected_version: comment.version, body_markdown: editBody.value, mention_user_ids: [] }) })
    editingId.value = null
    await load()
  } catch (reason) { error.value = errorMessage(reason, '评论保存失败') }
  finally { savingEdit.value = false }
}

async function remove(comment: MeetingComment) {
  if (!comment.can_delete || deletingId.value) return
  deletingId.value = comment.id
  error.value = ''
  try {
    await api(`/api/comments/${comment.id}`, { method: 'DELETE', body: JSON.stringify({ expected_version: comment.version }) })
    await load()
  } catch (reason) { error.value = errorMessage(reason, '评论删除失败') }
  finally { deletingId.value = null }
}

function hasMoreReplies(comment: MeetingComment) {
  return (comment.reply_count ?? 0) > comment.replies.length || Boolean(comment.reply_next_cursor)
}

/**
 * The API has no exact reply total: `reply_next_cursor` only proves there is more than
 * what is loaded, so the fallback label is explicitly open-ended (`4+`).
 */
function replyTotalLabel(comment: MeetingComment) {
  if (comment.reply_count !== undefined) return String(comment.reply_count)
  return `${comment.replies.length + 1}+`
}

function isFocusedComment(comment: MeetingComment) {
  return highlightedId.value === comment.id || comment.replies.some((reply) => reply.id === highlightedId.value)
}

async function loadReplies(comment: MeetingComment) {
  if (repliesLoadingId.value) return
  repliesLoadingId.value = comment.id
  error.value = ''
  try {
    const last = comment.replies[comment.replies.length - 1]?.id
    const params = new URLSearchParams({ limit: '20' })
    if (last) params.set('after', last)
    const page = await api<CommentPage>(`/api/comments/${comment.id}/replies?${params.toString()}`)
    comment.replies = [...comment.replies, ...page.items]
    comment.reply_next_cursor = page.next_cursor
  } catch (reason) { error.value = errorMessage(reason, '回复加载失败') }
  finally { repliesLoadingId.value = null }
}

watch(() => props.focusCommentId, () => { void focusComment() })
onMounted(load)
onBeforeUnmount(() => {
  if (highlightHandle !== undefined) window.clearTimeout(highlightHandle)
})
</script>

<template>
  <section class="meeting-comments">
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <p v-if="!focusFound && !loading" class="empty-inline" data-testid="comment-focus-missing">该评论在更早的讨论中</p>
    <n-list :show-divider="false" class="comment-list">
      <n-list-item v-for="comment in comments" :key="comment.id" :data-comment-id="comment.id" :class="{ 'is-focused': isFocusedComment(comment) }">
        <article class="comment-thread" :class="{ resolved: Boolean(comment.resolved_at) }">
          <header>
            <strong>{{ comment.creator.display_name }}</strong>
            <time v-if="comment.created_at">{{ formatDateTime(comment.created_at) }}</time>
            <n-button v-if="comment.can_resolve" size="small" quaternary :loading="togglingId === comment.id" :disabled="Boolean(togglingId)" @click="toggle(comment)">{{ comment.resolved_at ? '重开' : '解决' }}</n-button>
          </header>
          <n-input v-if="editingId === comment.id" v-model:value="editBody" type="textarea" :autosize="{ minRows: 2 }" :input-props="{ 'aria-label': '编辑评论' }" />
          <template v-else>
            <p v-if="comment.body_markdown !== null" class="comment-body">{{ comment.body_markdown }}</p>
            <p v-else class="comment-body comment-deleted">评论已删除</p>
            <span v-if="comment.edited_at" class="comment-edited">已编辑</span>
            <div v-if="comment.mentions?.length" class="comment-mentions"><span v-for="mention in comment.mentions" :key="mention.id">@{{ mention.display_name }}</span></div>
          </template>
          <div class="row-actions">
            <template v-if="editingId === comment.id">
              <n-button size="small" type="primary" :loading="savingEdit" :disabled="savingEdit" @click="saveEdit(comment)">保存</n-button>
              <n-button size="small" quaternary :disabled="savingEdit" @click="editingId = null">取消</n-button>
            </template>
            <template v-else-if="comment.body_markdown !== null">
              <button class="text-link" @click="replyTo = comment.id">回复</button>
              <button v-if="comment.can_edit" class="text-link" @click="beginEdit(comment)">编辑</button>
              <n-popconfirm v-if="comment.can_delete" positive-text="确认" negative-text="取消" @positive-click="remove(comment)">
                <template #trigger><n-button size="small" quaternary :loading="deletingId === comment.id" :disabled="Boolean(deletingId)">删除</n-button></template>
                确定删除这条评论吗？
              </n-popconfirm>
            </template>
          </div>
          <div v-if="comment.replies.length || hasMoreReplies(comment)" class="comment-replies">
            <article v-for="reply in comment.replies" :key="reply.id" :data-comment-id="reply.id" class="comment-reply"><strong>{{ reply.creator.display_name }}</strong><p>{{ reply.body_markdown }}</p></article>
            <n-button v-if="hasMoreReplies(comment)" size="small" quaternary :loading="repliesLoadingId === comment.id" :disabled="Boolean(repliesLoadingId)" @click="loadReplies(comment)">查看全部回复（{{ replyTotalLabel(comment) }}）</n-button>
          </div>
        </article>
      </n-list-item>
    </n-list>
    <n-button v-if="nextCursor" quaternary :loading="loadingMore" :disabled="loadingMore" @click="loadMore">加载更多</n-button>
    <p v-if="loading" class="muted">正在加载评论…</p>
    <form @submit.prevent="submit"><p class="muted">输入 @ 可提及会议成员</p><MentionTextarea v-model="body" v-model:mention-ids="mentionIds" label="评论内容" :participants="meeting.participants" /><div class="form-actions"><button v-if="replyTo" type="button" class="button button-quiet" @click="replyTo = null">取消回复</button><button class="button button-primary" :disabled="submitting">发送评论</button></div></form>
  </section>
</template>
