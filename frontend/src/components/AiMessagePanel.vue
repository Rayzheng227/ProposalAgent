<template>
  <div class="message-container">
    <div class="header">
      <img src="/src/assets/imgs/logo.png" class="logo" />
      <div class="process">运行流程</div>
      <div class="toggle-btn" @click="toggleCollapse" :style="toggleBtnStyle"></div>
    </div>
    <div class="message-content" :class="{ collapsed: isCollapsed }">
      <div v-for="i in 9" :key="i">
        <template v-if="(props.message as any)[stepStyles[i - 1]['propertyName']] !== ''">
          <div class=" title" :style="stepStyles[i - 1].titleStyle">{{ stepStyles[i - 1].stepTitle }}
          </div>
          <div class="content" :style="stepStyles[i - 1].contentStyle">
            {{ (props.message as any)[stepStyles[i - 1]["propertyName"]] }}
            <!-- 判断当前content的最后一个字符是否是"~"，是的话显示加载中的gif -->
            <img v-if="(props.message as any)[stepStyles[i - 1]['propertyName']].slice(-1) === '~'" class="wait"
              src="/src/assets/imgs/textLoading.gif" />
          </div>
        </template>
      </div>
    </div>
    <div v-if="message.step_9_content == ''" class="final-info">
      ✅ 当你看到这条消息时，如果任务还在执行中，请耐心等待~~
      <br />
      ❌ 否则说明已发生错误，请稍后重新发起提问
    </div>
    <div v-else-if="!message.step_9_content.includes('✅')" class="final-info">
      ❌ 任务执行失败，请稍后重新发起提问
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
</template>

<script lang="ts" setup>
import { ref, computed, getCurrentInstance } from 'vue'
import { ElMessage } from 'element-plus'
import { getRandomId } from '@/utils/stringUtil';
import type { AIMessage } from '@/common/interfaces'

const instance: any = getCurrentInstance();
const proxy = instance.proxy;

const props = defineProps<{
  index: number,
  historyId: string,
  message: AIMessage
}>()

const stepStyles = [
  {
    "propertyName": "step_1_content",
    "stepTitle": "**[任务规划]**",
    "titleStyle": {
      "border": "none"
    },
    "contentStyle": {}
  },
  {
    "propertyName": "step_2_content",
    "stepTitle": "**[步骤划分]**",
    "titleStyle": {},
    "contentStyle": {}
  }, {
    "propertyName": "step_3_content",
    "stepTitle": "**[调用工具]**",
    "titleStyle": {
      "color": "darkcyan",
    },
    "contentStyle": {
      "fontSize": "16px",
      "lineHeight": "2"
    }
  }, {
    "propertyName": "step_4_content",
    "stepTitle": "**[生成引言]**",
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#bbb",
      "fontSize": "15px",
      "lineHight": "1.5"
    }
  }, {
    "propertyName": "step_5_content",
    "stepTitle": "**[生成编号引用]**",
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#bbb",
      "fontSize": "15px",
      "lineHight": "1.5"
    }
  }, {
    "propertyName": "step_6_content",
    "stepTitle": "**[生成主体内容]**",
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#bbb",
      "fontSize": "15px",
      "lineHight": "1.5"
    }
  }, {
    "propertyName": "step_7_content",
    "stepTitle": "**[生成结论]**",
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#bbb",
      "fontSize": "15px",
      "lineHight": "1.5"
    }
  }, {
    "propertyName": "step_8_content",
    "stepTitle": "**[生成参考文献]**",
    "titleStyle": {
      "color": "darkgoldenrod",
    },
    "contentStyle": {
      "color": "#bbb",
      "fontSize": "15px",
      "lineHight": "1.5"
    }
  },
  {
    "propertyName": "step_9_content",
    "stepTitle": "**[生成最终报告]**",
    "titleStyle": {
      "color": "green",
    },
    "contentStyle": {
      "color": "#e99a4c",
      "fontSize": "16px",
      "lineHeight": "1.5"
    }
  },
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
  const result = await proxy.Request({
    url: proxy.Api.download,
    data: {
      fileType,
      historyId: props.historyId
    },
    responseType: 'blob',
    errorCallback: (errR: any) => {
      ElMessage.error(errR.mes)
    }
  });
  if (!result) return;
  const url = window.URL.createObjectURL(new Blob([result.data.data]));
  let a = document.createElement('a');
  a.href = url;
  a.download = `${getRandomId()}.${fileType}`;
  a.click()
  a.remove()
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
      width: 60px;
      height: 60px;


    }

    .process {
      width: 70px;
      height: 30px;
      margin-left: 10px;
      font-size: 16px;
      line-height: 30px;
      text-align: center;
      color: #fff;
    }

    .toggle-btn {
      width: 0;
      height: 0;
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      border-top: 15px solid darkcyan;
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

    .title {
      height: 30px;
      padding: 10px 0;
      border-top: 1px solid #777;
      font-size: 18px;
      font-weight: bold;
      color: rgb(102, 150, 167)
    }

    .content {
      margin-bottom: 10px;
      font-size: 14px;
      font-family: '微软雅黑';
      line-height: 1.3;
      color: #aaa;

      .wait {
        display: inline-block;
        vertical-align: middle;
        width: 25px;
      }
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