<template>
  <div class="user-message-content">
    <div v-if="resolvedImages.length" class="user-images">
      <img
        v-for="(src, index) in resolvedImages"
        :key="index"
        :src="src"
        alt="用户上传图片"
        class="user-image"
      />
    </div>
    <p v-if="content">{{ content }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useModelStore } from '@/stores/model'

const props = defineProps<{
  content: string
  slashCommand?: string
  slashBody?: string
  images?: string[]
}>()

const modelStore = useModelStore()

const resolvedImages = computed(() => {
  return (props.images || []).map((src) => {
    if (src.startsWith('data:') || src.startsWith('http://') || src.startsWith('https://')) {
      return src
    }
    const path = src.startsWith('/') ? src : `/${src}`
    return `${modelStore.getBaseUrl()}${path}`
  })
})
</script>

<style scoped>
.user-message-content p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.user-image {
  max-width: 240px;
  max-height: 180px;
  border-radius: 10px;
  border: 1px solid var(--border);
  object-fit: cover;
}
</style>
