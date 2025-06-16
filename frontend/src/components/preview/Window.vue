<template>
  <div class="window-mask" @click="emit('close')">
    <div class="window-content" @click.stop>
      <PreviewPdf v-if="props.fileType == 'pdf'" :historyId="props.historyId"></PreviewPdf>
      <PreviewMd v-else :historyId="props.historyId"></PreviewMd>
    </div>
  </div>
</template>

<script lang="ts" setup>
import PreviewPdf from "./PreviewPdf.vue";
import PreviewMd from "./PreviewMd.vue";

const props = defineProps({
  fileType: {
    type: String,
    default: "pdf",
  },
  historyId: {
    type: String,
    default: ""
  }
});

const emit = defineEmits(["close"])

</script>
<style lang="scss" scoped>
.window-mask {
  position: fixed;
  top: 0;
  left: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  z-index: 5;
  background-color: rgba(0, 0, 0, 0.5);

  .window-content {
    display: flex;
    overflow: auto;
    width: 75%;
    max-width: 1000px;
    max-height: 80%;
  }
}
</style>
