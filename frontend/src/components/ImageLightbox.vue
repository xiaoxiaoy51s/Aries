<template>
  <Teleport to="body">
    <Transition name="image-lightbox-fade">
      <div
        v-if="open && src"
        class="image-lightbox-overlay"
        role="dialog"
        aria-modal="true"
        :aria-label="alt || '图片预览'"
        @click.self="close"
      >
        <button type="button" class="image-lightbox-close" aria-label="关闭" @click="close">×</button>
        <img :src="src" :alt="alt" class="image-lightbox-img" @click.stop />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { watch, onUnmounted } from 'vue'

const props = defineProps<{
  open: boolean
  src: string
  alt?: string
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

function close() {
  emit('update:open', false)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) close()
}

watch(
  () => props.open,
  (val) => {
    if (val) {
      document.addEventListener('keydown', onKeydown)
      document.body.style.overflow = 'hidden'
    } else {
      document.removeEventListener('keydown', onKeydown)
      document.body.style.overflow = ''
    }
  },
)

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.image-lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.82);
  cursor: zoom-out;
}

.image-lightbox-img {
  max-width: min(96vw, 1400px);
  max-height: 92vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  cursor: default;
  user-select: none;
}

.image-lightbox-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.image-lightbox-close:hover {
  background: rgba(255, 255, 255, 0.22);
}

.image-lightbox-fade-enter-active,
.image-lightbox-fade-leave-active {
  transition: opacity 0.18s ease;
}

.image-lightbox-fade-enter-from,
.image-lightbox-fade-leave-to {
  opacity: 0;
}
</style>
