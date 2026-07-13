import { ref } from 'vue'

export function useImageLightbox() {
  const lightboxOpen = ref(false)
  const lightboxSrc = ref('')
  const lightboxAlt = ref('')

  function openLightbox(src: string, alt = '') {
    lightboxSrc.value = src
    lightboxAlt.value = alt
    lightboxOpen.value = true
  }

  return { lightboxOpen, lightboxSrc, lightboxAlt, openLightbox }
}
