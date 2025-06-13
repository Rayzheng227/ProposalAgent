<template>
  <div class="message-container">
    <!-- 询问消息 -->
    <div v-if="!props.message.isAnswer">
      <div class="header">
        <img src="/src/assets/imgs/logo.png" class="logo" />
        <div class="process">ProposalAgent</div>
      </div>
      <div class="message-content">
        <div class="question">{{ props.message.content }}</div>
      </div>
      <div v-if="!props.message.isFinish" class="final-info">
        ✅ 当你看到这条消息时，如果任务还在执行中，请耐心等待~~
        <br />
        ❌ 否则说明已发生错误，请稍后重新发起提问
      </div>
      <div class="action-bar">
        <img class="icon-copy" src="/src/assets/imgs/copy.png" title="复制" @click="copyMessage" />
      </div>
    </div>
    <!-- 回复消息 -->
    <div v-else>
      <div class="header">
        <img src="/src/assets/imgs/logo.png" class="logo" />
        <div class="process">运行流程</div>
        <div class="toggle-btn" @click="toggleCollapse" :style="toggleBtnStyle"></div>
      </div>
      <div class="message-content" :class="{ collapsed: isCollapsed }">
        <div v-for="step, index in (props.message as AIAnswerMessage).steps" :key="step.title">
          <div :style="stepStyles[index % stepStyles.length].titleStyle" class="title">{{ step.title }}</div>
          <div :style="stepStyles[index % stepStyles.length].contentStyle" class="content">
            {{ step.content }}
          </div>
        </div>
      </div>
      <div v-if="!props.message.isFinish" class="final-info">
        当你看到这条消息时，如果任务还在执行中，请耐心等待~~
        <img class="wait" src="/src/assets/imgs/textLoading.gif" />
      </div>
      <div v-else class="download-bar">
        <span class="info">任务执行完成，点击右边按钮下载最终报告吧！</span>
        <img class="icon-pdf" src="/src/assets/imgs/pdf.png" @click="download('pdf')" />
        <img class="icon-md" src="/src/assets/imgs/markdown.png" @click="download('md')" />
      </div>
      <div class="action-bar">
        <img class="icon-copy" src="/src/assets/imgs/copy.png" title="复制" @click="copyMessage" />
        <img class="icon-refresh" src="/src/assets/imgs/refresh.png" title="重新生成" @click="refresh" />
      </div>
    </div>

  </div>
</template>

<script lang="ts" setup>
import { ref, computed, getCurrentInstance } from 'vue'
import { ElMessage } from 'element-plus'
import { getRandomId } from '@/utils/stringUtil';
import type { AIAnswerMessage, AIQuestionMessage } from '@/common/interfaces'

const instance: any = getCurrentInstance();
const proxy = instance.proxy;

const props = defineProps<{
  index: number,
  historyId: string,
  message: AIAnswerMessage | AIQuestionMessage
}>()

const stepStyles = [
  {
    "titleStyle": {
      "color": "skyblue"
    },
    "contentStyle": {
      "color": "#aaa"
    }
  },
  {
    "titleStyle": {
      "color": "darkcyan",
    },
    "contentStyle": {
      "color": "#bbb"
    }
  }, {
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#ccc"
    }
  }
]
const isCollapsed = ref(false)



const toggleBtnStyle = computed(() => ({
  transform: isCollapsed.value ? 'rotate(0deg)' : 'rotate(180deg)'
}))

const toggleCollapse = () => isCollapsed.value = !isCollapsed.value

const emit = defineEmits(['refresh'])

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

const refresh = () => {
  emit('refresh')
}

const download = async (fileType: string) => {
  const result1 = await proxy.Request({
    url: proxy.Api.checkFileExist,
    data: {
      fileType,
      historyId: props.historyId
    }
  });
  // 监测到文件存在，才允许下载
  if (result1) {
    const result2 = await proxy.Request({
      url: proxy.Api.download,
      data: {
        fileType,
        historyId: props.historyId
      },
      responseType: 'blob',
      errorCallback: (errR: any) => {
        console.log(errR)
        ElMessage.error(errR.detail)
      }
    });
    if (!result2) return;
    const url = window.URL.createObjectURL(new Blob([result2.data.data]));
    let a = document.createElement('a');
    a.href = url;
    a.download = `${getRandomId()}.${fileType}`;
    a.click()
    a.remove()
  }

};

</script>

<style lang="scss" scoped>
.message-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  margin: 10px 0;

  .header {
    display: flex;
    align-items: center;

    .logo {
      width: 80px;
      height: 80px;
    }

    .process {
      width: 80px;
      height: 30px;
      margin-left: 10px;
      font-size: 18px;
      line-height: 30px;
      text-align: center;
      color: #468bb9;
    }

    .toggle-btn {
      width: 0;
      height: 0;
      border-left: 10px solid transparent;
      border-right: 10px solid transparent;
      border-top: 18px solid darkcyan;
      margin-left: 10px;
      cursor: pointer;

      &:hover {
        scale: 1.3;
      }
    }
  }


  .message-content {
    margin-left: 60px;
    background-color: rgba(255, 255, 255, 0.1);
    border: 2px solid #444;
    border-radius: 15px 15px 15px 0;
    padding: 15px;
    width: calc(75%);
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-all;
    overflow: hidden;
    transition: all 1s ease;
    backdrop-filter: blur(8px);

    .question {
      font-size: 16px;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      line-height: 1.5;
      color: #ffd67d;
    }

    .title {
      height: 30px;
      padding: 10px 0;
      border-top: 1px solid #777;
      font-size: 18px;
      font-weight: bold;
      color: skyblue;
    }

    .content {
      margin-bottom: 10px;
      font-size: 15px;
      font-family: '微软雅黑';
      line-height: 1.3;
      color: #aaa;
    }

    &.collapsed {
      height: 0;
      padding: 10px 15px;
      background-color: #333;
      opacity: 0.5;
    }
  }

  .final-info {
    margin-left: 60px;
    margin-top: 10px;
    font-size: 15px;
    font-family: Arial, Helvetica, sans-serif;
    font-weight: bold;
    color: #aaa;


    .wait {
      display: inline-block;
      vertical-align: middle;
      width: 25px;
    }
  }

  .download-bar {
    display: flex;
    align-items: center;
    justify-content: right;
    padding-right: 15%;
    margin-top: 10px;

    .info {
      margin-right: 10px;
      font-size: 16px;
      font-weight: bold;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      color: rgb(85, 179, 85);
    }

    .icon-pdf {
      width: 45px;

      &:hover {
        scale: 1.2;
        cursor: pointer;
      }
    }

    .icon-md {
      width: 43px;

      &:hover {
        scale: 1.2;
        cursor: pointer;
      }
    }
  }

  .action-bar {
    display: flex;
    margin-left: 60px;

    .icon-copy {
      width: 40px;

      &:hover {
        scale: 1.2;
        cursor: pointer;
      }
    }

    .icon-refresh {
      width: 28px;
      height: 28px;
      margin-top: 6px;

      &:hover {
        scale: 1.2;
        cursor: pointer;
      }
    }
  }
}
</style>