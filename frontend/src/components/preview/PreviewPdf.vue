<template>
  <div class="pdf-preview">
    <vuePdfEmbed @loaded="loaded" :source="state.source" :page="state.pageNum" />
    <div class="page-tool">
      <div class="page-tool-item" @click="lastPage">上一页</div>
      <div class="page-tool-item">{{ state.pageNum }}/{{ state.numPages }}</div>
      <div class="page-tool-item" @click="nextPage">下一页</div>
    </div>
  </div>

</template>

<script lang="ts" setup>
import vuePdfEmbed from "vue-pdf-embed";
import { reactive, getCurrentInstance, onMounted, computed, onUnmounted } from "vue";

const instance: any = getCurrentInstance();
const proxy = instance.proxy;
const props = defineProps({
  historyId: {
    type: String,
    default: ""
  },
});

const state = reactive({
  source: "",
  pageNum: 1,
  numPages: 0,
});

const lastPage = () => {
  if (state.pageNum > 1) state.pageNum -= 1;
}

const nextPage = () => {
  if (state.pageNum < state.numPages) state.pageNum += 1;
}

const initPdf = async () => {
  const result = await proxy.Request({
    url: proxy.Api.download,
    data: {
      fileType: "pdf",
      historyId: props.historyId
    },
    responseType: 'blob'
  });
  if (!result) return;
  const url = window.URL.createObjectURL(new Blob([result.data.data]));
  state.source = url;
}

const loaded = (pdf: any) => state.numPages = pdf.numPages

onMounted(() => {
  initPdf()
})

onUnmounted(() => {
  window.URL.revokeObjectURL(state.source);
})

</script>
<style lang="scss" scoped>
.pdf-preview {
  position: relative;
  width: 100%;
  height: 100%;

  .page-tool {
    position: absolute;
    bottom: 20px;
    padding: 10px 15px;
    display: flex;
    align-items: center;
    background: rgb(0, 0, 0, 0.8);
    color: #fff;
    border-radius: 20px;
    z-index: 100;
    margin-left: 50%;
    transform: translateX(-50%);

    .page-tool-item {
      padding: 0px 10px;
      cursor: pointer;
      font-weight: bold;
      color: #fff;
      user-select: none;
    }
  }
}
</style>
