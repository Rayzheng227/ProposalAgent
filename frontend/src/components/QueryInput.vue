<template>
  <div class="query-area">
    <el-input class="input-area" v-model="query" :autosize="{ minRows: 2, maxRows: 10 }" type="textarea"
      placeholder="与ProposalAgent交流吧！" @keydown="handleKeydown" />
    <div class="button-area">
      <img src="/src/assets/imgs/send.png" class="send" @click="send">
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'

const query = ref("");

const emit = defineEmits(['send'])

const handleKeydown = (event: any) => {
  // 检测是否按下了回车键
  if (event.key === 'Enter') {
    // 如果同时按下了Shift键，则插入换行符
    if (event.shiftKey) {
      // 手动处理换行逻辑
      const start = event.target.selectionStart;
      const end = event.target.selectionEnd;
      query.value = query.value.substring(0, start) + '\n' + query.value.substring(end);

      // 阻止默认行为（防止表单提交或添加额外换行）
      event.preventDefault();

      // 重新设置光标位置
      setTimeout(() => {
        const textarea = event.target;
        textarea.selectionStart = textarea.selectionEnd = start + 1;
      }, 0);
    } else {
      // 如果没有按下Shift键，则发送消息
      event.preventDefault();
      send();
    }
  }
}

const send = () => {
  if (query.value != null && query.value.trim() !== "") {
    emit('send', query.value)
    query.value = ""
  }
}
</script>

<style lang="scss" scoped>
.query-area {
  display: flex;
  flex-direction: column;
  width: 90%;
  max-width: 800px;
  background-color: #222;
  border: 2px solid #444;
  border-radius: 15px;

  .input-area {
    width: 100%;

    :deep(.el-textarea__inner) {
      color: #fff;
      opacity: 0.9;
      font-size: 16px;
      border-radius: 15px;
      background-color: #222;
      resize: none;
      box-shadow: none;
    }
  }

  .button-area {
    display: flex;
    align-items: center;
    justify-content: right;
    width: 100%;
    height: 60px;

    .send {
      width: 40px;
      margin-right: 20px;

      &:hover {
        scale: 1.3;
        cursor: pointer;
      }
    }
  }
}
</style>