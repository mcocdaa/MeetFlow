<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import type { CommentPage, MeetingComment } from '../domain/comments'
import type { Meeting } from '../domain/meetings'
import MentionTextarea from './MentionTextarea.vue'

const props = defineProps<{ meeting: Meeting }>()
const emit = defineEmits<{ changed: [count: number] }>()
const comments = ref<MeetingComment[]>([])
const body = ref('')
const mentionIds = ref<string[]>([])
const replyTo = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editBody = ref('')
const loading = ref(false)
const error = ref('')

async function load() { loading.value = true; try { comments.value = (await api<CommentPage>(`/api/comments?target_type=meeting&target_id=${props.meeting.id}`)).items.reverse(); emit('changed', comments.value.length) } catch (reason) { error.value = reason instanceof Error ? reason.message : '评论加载失败' } finally { loading.value = false } }
async function submit() { if (!body.value.trim()) return; await api('/api/comments', { method: 'POST', body: JSON.stringify({ target_type: 'meeting', target_id: props.meeting.id, parent_id: replyTo.value, body_markdown: body.value, mention_user_ids: mentionIds.value }) }); body.value = ''; mentionIds.value = []; replyTo.value = null; await load() }
async function toggle(comment: MeetingComment) { await api(`/api/comments/${comment.id}/${comment.resolved_at ? 'reopen' : 'resolve'}`, { method: 'POST', body: JSON.stringify({ expected_version: comment.version }) }); await load() }
function beginEdit(comment: MeetingComment) { editingId.value = comment.id; editBody.value = comment.body_markdown ?? '' }
async function saveEdit(comment: MeetingComment) { if (!editBody.value.trim()) return; await api(`/api/comments/${comment.id}`, { method: 'PUT', body: JSON.stringify({ expected_version: comment.version, body_markdown: editBody.value, mention_user_ids: [] }) }); editingId.value = null; await load() }
onMounted(load)
</script>

<template>
  <section class="meeting-comments">
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <article v-for="comment in comments" :key="comment.id" class="comment-thread" :class="{ resolved: comment.resolved_at }">
      <header><strong>{{ comment.creator.display_name }}</strong><button v-if="comment.can_resolve" class="button button-small button-quiet" @click="toggle(comment)">{{ comment.resolved_at ? '重开' : '解决' }}</button></header>
      <textarea v-if="editingId === comment.id" v-model="editBody" aria-label="编辑评论" />
      <p v-else>{{ comment.body_markdown || '评论已删除' }}</p>
      <div class="row-actions"><template v-if="editingId === comment.id"><button class="button button-small button-primary" @click="saveEdit(comment)">保存</button><button class="button button-small button-quiet" @click="editingId = null">取消</button></template><template v-else><button class="text-link" @click="replyTo = comment.id">回复</button><button v-if="comment.can_edit" class="text-link" @click="beginEdit(comment)">编辑</button></template></div>
      <article v-for="reply in comment.replies" :key="reply.id" class="comment-reply"><strong>{{ reply.creator.display_name }}</strong><p>{{ reply.body_markdown }}</p></article>
    </article>
    <p v-if="loading" class="muted">正在加载评论…</p>
    <form @submit.prevent="submit"><p class="muted">输入 @ 可提及会议成员</p><MentionTextarea v-model="body" v-model:mention-ids="mentionIds" label="评论内容" :participants="meeting.participants" /><div class="form-actions"><button v-if="replyTo" type="button" class="button button-quiet" @click="replyTo = null">取消回复</button><button class="button button-primary">发送评论</button></div></form>
  </section>
</template>
