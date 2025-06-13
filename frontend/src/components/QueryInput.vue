<template>
  <div v-if="isCountDown" class="timer-container">
    <div class="timer-circle">{{ countdown }} </div>
    <div class="tip">请在输入框补充相关信息后发送，或者不提供额外信息直接发送，或者等待计时结束</div>
  </div>
  <div class="query-area">
    <el-input class="input-area" v-model="query" :autosize="{ minRows: 2, maxRows: 10 }" type="textarea"
      placeholder="与ProposalAgent交流吧！" @keydown="handleKeydown" />
    <div class="button-area">
      <img src="/src/assets/imgs/send.png" class="send" @click="send">
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onUnmounted } from 'vue'

const query = ref("");
const isCountDown = ref(false);
const countdown = ref(0);
const timer = ref<number | null>(null);


const handleKeydown = (event: any) => {
  if (event.key === 'Enter') {
    if (event.shiftKey) {
      const start = event.target.selectionStart;
      const end = event.target.selectionEnd;
      query.value = query.value.substring(0, start) + '\n' + query.value.substring(end);
      event.preventDefault();

      setTimeout(() => {
        const textarea = event.target;
        textarea.selectionStart = textarea.selectionEnd = start + 1;
      }, 0);
    } else {
      event.preventDefault();
      send();
    }
  }
}

const send = () => {
  if (isCountDown || (query.value != null && query.value.trim() !== "")) {
    emit('send', query.value, isCountDown.value)
    query.value = ""
    stopCountDown()
  }
}

const startCountDown = () => {
  isCountDown.value = true;
  countdown.value = 60;

  if (timer.value) clearInterval(timer.value);


  timer.value = window.setInterval(() => {
    countdown.value--;
    if (countdown.value <= 0) stopCountDown();
  }, 1000);
}

const stopCountDown = () => {
  isCountDown.value = false;
  if (timer.value) {
    clearInterval(timer.value);
    timer.value = null;
  }
}

const emit = defineEmits(['send'])

onUnmounted(() => {
  if (timer.value) clearInterval(timer.value);
})

defineExpose({
  startCountDown
})
</script>

<style lang="scss" scoped>
.timer-container {
  display: flex;
  align-items: center;
  justify-content: center;

  .timer-circle {
    width: 50px;
    height: 50px;
    margin: 20px 0;
    border-radius: 50%;
    border: 3px solid #666;
    color: #ccc;
    font-size: 20px;
    font-weight: bold;
    text-align: center;
    line-height: 50px;
    background: rgba(200, 200, 200, 0.1);
    animation: ripple 2s infinite ease-in-out, colorChange 2s infinite linear;
    backdrop-filter: blur(8px);
  }

  .tip {
    margin-left: 20px;
    font-size: 16px;
    color: lightblue;
  }
}


@keyframes colorChange {
  0% {
    border-color: #444;
  }

  100% {
    border-color: #ccc;
  }
}

.query-area {
  display: flex;
  flex-direction: column;
  width: 90%;
  max-width: 800px;
  border: 2px solid #444;
  border-radius: 15px;
  backdrop-filter: blur(8px);

  .input-area {
    width: 100%;

    :deep(.el-textarea__inner) {
      color: #fff;
      // opacity: 0.9;
      font-size: 16px;
      border-top-left-radius: 15px;
      border-top-right-radius: 15px;
      background-color: rgba(255, 255, 255, 0.1);
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
    background-color: rgba(255, 255, 255, 0.1);

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

@keyframes ripple {
  0% {
    transform: scale(1);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 5px 10px -0px;
  }

  50% {
    transform: scale(1.1);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 10px 15px -0px;
  }

  100% {
    transform: scale(1);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 5px 10px -0px;
  }
}
</style>
