<script setup lang="ts">
import { publicDataUrl } from '~/utils/publicDataUrl'

const props = defineProps<{
  name: string
  photoUrl?: string | null
  photoPath?: string | null
}>()

const baseURL = useRuntimeConfig().app.baseURL
const failed = ref(false)

const computedPhotoSrc = computed(() => {
  if (failed.value) return null
  if (props.photoUrl) return props.photoUrl
  if (props.photoPath) return publicDataUrl(props.photoPath, baseURL)
  return null
})

watch(() => [props.photoUrl, props.photoPath], () => {
  failed.value = false
})
</script>

<template>
  <span
    class="member-photo"
    aria-hidden="true"
  >
    <img
      v-if="computedPhotoSrc"
      :src="computedPhotoSrc"
      alt=""
      loading="lazy"
      @error="failed = true"
    >
    <span v-else>{{ name.split(' ').slice(0, 2).map(part => part[0]).join('') }}</span>
  </span>
</template>
