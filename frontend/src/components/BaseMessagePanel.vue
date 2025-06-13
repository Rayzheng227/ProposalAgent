<template>
  <div class="message-container">
    <div class="message-content-wrapper">
      <div class="message-content">{{ message.content }}</div>
    </div>
    <div class="action-bar">
      <img class="icon" src="/src/assets/imgs/copy.png" title="复制" @click="copyMessage" />
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ElMessage } from 'element-plus'
import type { BaseMessage } from '@/common/interfaces'

const props = defineProps<{
  message: BaseMessage
}>()

const emit = defineEmits(['regenerate'])

const copyMessage = async () => {
  try {
    await navigator.clipboard.writeText(props.message.content)
    ElMessage({
      message: '复制成功',
      type: 'success'
    })
  } catch (err) {
    ElMessage({
      message: '复制失败，请手动复制',
      type: 'error'
    })
  }
}

const regenerateMessage = () => {
  emit('regenerate')
}
</script>

<style lang="scss" scoped>
.message-container {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  margin: 10px 0;
  width: 100%;
  backdrop-filter: blur(4px);

  .message-content-wrapper {
    display: flex;
    justify-content: right;
    width: 80%;
    padding-right: 10px;
    user-select: none;

    .message-content {
      max-width: 80%;
      padding: 15px;
      color: #fff;
      font-size: 16px;
      line-height: 1.5;
      border-radius: 15px 15px 0 15px;
      box-shadow: inset 2px 2px 8px 0px #aaa;
      white-space: pre-wrap;
      word-wrap: break-word;
      word-break: break-all;
    }
  }

  .action-bar {
    display: flex;
    padding-right: 10px;

    .icon {
      width: 40px;

      &:hover {
        scale: 1.2;
        cursor: pointer;
      }
    }
  }
}
</style>