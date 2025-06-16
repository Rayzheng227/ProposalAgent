<template>
  <div class="background">
    <div class="bg-name-container">
      <div class="name" v-for="(name, index) in names" :key="index">
        {{ name }}
      </div>
    </div>
    <img ref="movingImage" src="/src/assets/imgs/logo.png" class="moving-image" />
    <div class="overlay">
      <div class="main">

        <div class="left-top-hole"></div>
        <div class="right-top-hole"></div>
        <div class="left-bottom-hole"></div>
        <div class="right-bottom-hole"></div>
        <div class="left-menu">
          <div class="menu" :class="{ collapsed: isCollapse }">
            <div class="head">
              <div class="logo-wrapper" :class="{ collapsed: isCollapse }">
                <div class="label">ProposalAgent</div>
              </div>
              <img class="action" :src="isCollapse ? '/src/assets/imgs/expand.png' : '/src/assets/imgs/collapse.png'"
                @click="toggleCollapse" />
            </div>
            <el-button class="new-dialog" type="default" :class="{ collapsed: isCollapse }" @click="toIsland()">
              <template #icon>
                <img class="icon" :class="{ collapsed: isCollapse }" src="/src/assets/imgs/newDialog.png" />
              </template>
              开启新对话
            </el-button>
            <div class="histories">
              <div v-for="item in histories" class="histories-item" :style="activeHistoryId == item.id
                ? { boxShadow: 'inset -2px -2px 5px 0px #aaa' }
                : {}
                " @click="switchHistory(item.id)">
                <div class="status">
                  <div class="status-ball" :style="{ backgroundColor: activeHistoryId == item.id ? 'green' : 'grey' }">
                  </div>
                </div>
                <div class="summary" :class="{ collapsed: isCollapse }">{{ item.title }}</div>
                <img src="/src/assets/imgs/delete.png" class="delete" @click.stop="removeHistory(item.id)" />
              </div>
            </div>
          </div>
        </div>
        <div class="right">
          <div v-if="activeHistoryId != null" class="communication">
            <div v-if="rendered" class="chat-records" ref="chatRecordsRef" v-loading="isLoading"
              element-loading-text="正在连接服务器~~" element-loading-background="rgba(255, 255, 255, 0)">
              <div v-for="(message, index) in histories.find((item) => item.id === activeHistoryId)?.messages">
                <template v-if="message.role === 'user'">
                  <BaseMessagePanel :message="(message as BaseMessage)"></BaseMessagePanel>
                </template>
                <template v-else>
                  <AIMessagePanel :message="(message as (AIAnswerMessage | AIQuestionMessage))" :index="index"
                    :history-id="activeHistoryId" @refresh="refresh(index)">
                  </AIMessagePanel>
                </template>
              </div>
            </div>
            <el-button class="new-dialog" type="default" :class="{ collapsed: isCollapse }" @click="toIsland()">
              <template #icon>
                <img class="icon" :class="{ collapsed: isCollapse }" src="/src/assets/imgs/newDialog.png" />
              </template>
              开启新对话
            </el-button>
            <QueryInput :first-chatting="isChatting" ref="queryInputRef" @send="send" @stop="stopChatting()">
            </QueryInput>
          </div>
          <div v-else class="island">
            <div class="head">
              <img src="/src/assets/imgs/logo.png" class="logo" />
              <div class="hello">我是ProposalAgent，很高兴帮你解答问题！</div>
            </div>
            <div class="prompt">我可以帮你生成调研报告、计划书等，请提交你的任务吧！</div>
            <QueryInput @send="send"></QueryInput>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, nextTick, getCurrentInstance, watch, onUnmounted } from "vue";
import { ElMessage } from 'element-plus';
import type { History, BaseMessage, AIAnswerMessage, AIQuestionMessage, R } from "@/common/interfaces";
import { getRandomId } from "@/utils/stringUtil";
import QueryInput from "@/components/QueryInput.vue";
import BaseMessagePanel from "@/components/BaseMessagePanel.vue";
import AIMessagePanel from "@/components/AiMessagePanel.vue";
import WebSocketUtil from "@/request/Ws";
import { useHistoryStore } from "@/stores/HistoryStore";

const instance: any = getCurrentInstance();
const proxy = instance.proxy;
const chatRecordsRef = ref<any>(null); // 聊天记录引用
const queryInputRef = ref<any>(null); // 输入框引用

const historyStore = useHistoryStore(); // 历史记录存储
const isCollapse = ref(false); // 是否折叠左侧菜单
const rendered = ref(false); // 是否渲染聊天记录
const histories = ref<History[]>([]); // 历史记录
const activeHistoryId = ref<string | null>(null); // 当前激活的历史记录ID
const isChatting = ref<boolean>(false); // 是否正在聊天
const isUserScrolling = ref(false); // 是否用户正在手动滚动
const isLoading = ref(false); // 是否正在加载
const currentWs = ref<WebSocketUtil | null>(null); // 当前的WebSocket连接

const nameElements = ref<HTMLElement[]>([]);
const names = ref<string[]>(["郑锐", "谢秋云", "樊彬峰", "禚宣伟", "吴业阳"])

const movingImage = ref<HTMLElement | null>(null);
// 移动参数（全部固定值）
const imageWidth = 300;
const imageHeight = 300;
const speed = 0.5; // 移动速度
let x = 0;
let y = 0;
let vx = speed; // x轴速度（向右为正）
let vy = speed; // y轴速度（向下为正）
let animationFrameId: any = null;
let containerWidth = 0;
let containerHeight = 0;


const loadHistories = () => {
  // 从历史记录存储中加载历史记录
  histories.value = historyStore.loadHistories();
  // 如果当前已经点击了一个历史记录，则直接滚动到底部
  if (activeHistoryId.value != null) scrollToBottom();
  // 否则，如果有历史记录，且不在聊天中，则将第一条历史记录的ID设置为激活的历史记录ID，并滚动到底部
  // 不在聊天中，才允许跳转到第一个记录，否则会因为ws里一直loadHistories导致一直跳到第一个history里
  else if (!isChatting.value && histories.value.length > 0) {
    activeHistoryId.value = histories.value[0].id;
    scrollToBottom();
  }
}

const switchHistory = (id: string) => {
  if (id === activeHistoryId.value) return;
  rendered.value = false; // 切换时先隐藏消息
  activeHistoryId.value = id;
  loadHistories();
  nextTick(() => rendered.value = true)
}

const toggleCollapse = () => isCollapse.value = !isCollapse.value;

const removeHistory = (id: string) => {
  if (activeHistoryId.value === id)
    activeHistoryId.value = null;
  historyStore.removeHistory(id);
  loadHistories();
}

const toIsland = () => activeHistoryId.value = null;

const stopChatting = () => {
  isLoading.value = false;
  isChatting.value = false;
  currentWs.value?.close();
  currentWs.value = null;
  queryInputRef.value.stop(false); // 按钮由可停止改为可发送
}

const send = async (query: string, isClarification: boolean) => {
  // 如果当前正在发送消息，则不允许发送操作
  if (isChatting.value) return;
  // 如果当前是新的对话，则记录到历史记录中
  if (activeHistoryId.value == null) {
    const id = getRandomId();
    const history: History = { id, title: "", messages: [] }
    historyStore.addHistory(history);
    loadHistories()
  }
  // 获取当前的消息记录
  let activeHistory = histories.value.find((item) => item.id === activeHistoryId.value)
  if (activeHistory == null) return;
  // 加载动画
  isLoading.value = true;
  // 构建历史消息
  let realQuery = "";
  activeHistory.messages.forEach((item) => realQuery += item.content);
  realQuery += query;
  // 发起请求
  isChatting.value = true;
  const result = await proxy.Request({
    url: proxy.Api.sendQuery,
    data: {
      query: realQuery,
      historyId: activeHistoryId.value,
      isClarification
    },
    errorCallback: (errR: any) => {
      ElMessage.error(errR.mes)
      isLoading.value = false; // 确保错误时关闭加载
      isChatting.value = false;
    }
  });
  if (!result) {
    isLoading.value = false;
    isChatting.value = false;
    return;
  }
  // 如果是第一条消息，则设置标题
  if (activeHistory.title === "")
    activeHistory.title = query.substring(0, 10);
  // 记录消息
  let message: BaseMessage = {
    sendTime: new Date().toDateString(),
    role: "user",
    content: query
  }
  historyStore.addBaseMessage(activeHistory.id, message);
  loadHistories();

  currentWs.value = new WebSocketUtil({
    url: `${proxy.Api.loadMessageStream}/${activeHistoryId.value}`,
    autoReconnect: true,
    onMessage: (r: any) => {
      // 首次接收消息时，关闭加载动画，同时允许自动向下滚动
      if (isLoading.value) {
        isLoading.value = false
        isUserScrolling.value = false;
      }
      const parsed = JSON.parse(r.data)
      if (!parsed.isAnswer) {  // 处理AI询问消息
        const { proposalId, isFinish, content } = parsed;
        historyStore.addAIQuestionMessageChunk(proposalId, isFinish, content);
        loadHistories();
        if (isFinish) {
          queryInputRef.value.startCountDown() // 开启倒计时
          stopChatting() // 关闭WS连接
        }
      } else { // 处理AI回答消息
        const { proposalId, isFinish, step, title, content } = parsed;
        historyStore.addAIAnswerMessageChunk(proposalId, isFinish, step, title, content);
        loadHistories();
        if (isFinish) stopChatting()

      }
    },
    onError: (err: any) => stopChatting()

  });
}

const refresh = (index: number) => {
  const activeHistory = histories.value.find((item) => item.id === activeHistoryId.value)
  if (activeHistory == null) return;
  // 由于每个提问AI都会进行澄清提问，所有真正的问题是最近的一条AIQuestionMessage的上一条
  let aiQuestionMessageIdx = 1;
  for (let i = index - 1; i >= 0; i--) {
    if (activeHistory.messages[i].role === "ai" && !((activeHistory.messages[i] as any).isAnswer)) {
      aiQuestionMessageIdx = i;
      break;
    }
  }
  const oldQuery = activeHistory.messages[aiQuestionMessageIdx - 1].content
  historyStore.removeMessages(activeHistoryId.value, aiQuestionMessageIdx - 1);
  loadHistories();
  send(oldQuery, false);
}

// 滚动事件处理函数
const handleScroll = () => {
  if (!chatRecordsRef.value) return;
  const element = chatRecordsRef.value;
  const { scrollTop, clientHeight, scrollHeight } = element;
  const threshold = 100;
  // 检测是否滚动到底部（阈值范围内）
  isUserScrolling.value = (scrollHeight - (scrollTop + clientHeight) > threshold);
};

const scrollToBottom = () => {
  if (isUserScrolling.value) return;

  nextTick(() => {
    rendered.value = true;

    setTimeout(() => {
      const element = chatRecordsRef.value;
      if (!element) return;

      // 目标滚动位置
      const targetScrollTop = element.scrollHeight;
      let currentScrollTop = element.scrollTop;
      const duration = 300; // 滚动持续时间(毫秒)
      const startTime = performance.now();

      const smoothScroll = (timestamp: number) => {
        const elapsed = timestamp - startTime;
        if (elapsed < duration) {
          // 计算滚动进度 (使用easeOutQuart缓动函数)
          const progress = 1 - Math.pow(1 - elapsed / duration, 4);
          // 计算当前滚动位置
          currentScrollTop = Math.floor(progress * (targetScrollTop - currentScrollTop) + currentScrollTop);
          element.scrollTop = currentScrollTop;
          requestAnimationFrame(smoothScroll);
        } else {
          element.scrollTop = targetScrollTop;
        }
      };

      requestAnimationFrame(smoothScroll);
    }, 100);
  });
}

// 随机打乱名字顺序，并为每个名字设置随机动画速度
const randomNameElementSpeed = () => {
  const array = [...names.value];
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  names.value = array;
  nextTick(() => {
    nameElements.value = Array.from(document.querySelectorAll('.name')).map((element) => element as HTMLElement);
    if (nameElements.value.length === 0) return;
    // 为每个名字设置随机动画速度，范围10s-20s
    nameElements.value.forEach(name => {
      const minSpeed = 20; // 最小动画时长
      const maxSpeed = 50; // 最大动画时长
      const randomSpeed = minSpeed + Math.random() * (maxSpeed - minSpeed);
      name.style.animationDuration = `${randomSpeed}s`;
    });
  })
}

// 监听activeHistoryId变化，动态绑定/解绑滚动事件
watch(activeHistoryId, (newVal) => {
  if (newVal !== null) {
    // 进入聊天界面，等待DOM渲染后绑定滚动事件
    nextTick(() => {
      if (chatRecordsRef.value)
        chatRecordsRef.value.addEventListener('scroll', handleScroll);
    });
  } else {
    if (chatRecordsRef.value)
      chatRecordsRef.value.removeEventListener('scroll', handleScroll);
  }
});



// 初始化图片移动
const initImageMovement = () => {
  if (!movingImage.value) return;
  // 获取容器尺寸
  const background = document.querySelector('.background') as HTMLElement;
  if (!background) return;
  containerWidth = background.offsetWidth;
  containerHeight = background.offsetHeight;
  // 随机初始位置（避开边界）
  x = Math.random() * (containerWidth - imageWidth);
  y = Math.random() * (containerHeight - imageHeight);
  // 应用初始位置
  updateImagePosition();
  // 开始动画
  startAnimation();
};

// 更新图片位置
const updateImagePosition = () => {
  if (movingImage.value) {
    movingImage.value.style.left = `${x}px`;
    movingImage.value.style.top = `${y}px`;
  }
};
// 动画帧函数
const animate = () => {
  // 更新坐标
  x += vx;
  y += vy;
  // 撞墙反弹检测（固定边界处理）
  if (x < 0 || x > containerWidth - imageWidth)
    vx = -vx; // 反转x轴速度
  if (y < 0 || y > containerHeight - imageHeight)
    vy = -vy; // 反转y轴速度
  // 应用新位置
  updateImagePosition();
  // 继续下一帧
  animationFrameId = requestAnimationFrame(animate);
};

// 开始动画
const startAnimation = () => {
  if (animationFrameId) return;
  animationFrameId = requestAnimationFrame(animate);
};

// 停止动画
const stopAnimation = () => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
};

// 窗口大小变化时重新计算边界
const handleResize = () => {
  const background = document.querySelector('.background') as HTMLElement;
  if (background) {
    containerWidth = background.offsetWidth;
    containerHeight = background.offsetHeight;
  }
};

onMounted(() => {
  loadHistories();
  randomNameElementSpeed()
  initImageMovement();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  stopAnimation();
  window.removeEventListener('resize', handleResize);
})


</script>

<style lang="scss" scoped>
.background {
  width: 100vw;
  height: 100vh;
  background-color: #000;

  .moving-image {
    position: absolute;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    object-fit: cover;
    box-shadow: 0 0px 16px 2px #fff;
  }

  .bg-name-container {
    width: 100%;
    height: 100%;
    font-size: 180px;
    font-weight: bold;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #444;
    white-space: nowrap;
    overflow: hidden;

    .name {
      animation: scroll linear infinite;
    }
  }

  @keyframes scroll {
    0% {
      transform: translateX(0);
    }

    100% {
      transform: translateX(100%);
    }
  }

  .overlay {
    position: fixed;
    top: 0;
    left: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
    z-index: 3;
    background-color: rgba(0, 0, 0, 0.7);

    .main {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 97%;
      height: 97%;
      border-width: 2px;
      border-radius: 20px;
      box-shadow: 0px 0px 12px 6px rgba(184, 184, 184, 0.3);

      .left-top-hole {
        position: absolute;
        top: 10px;
        left: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 0.6;
        background-color: red;

        &:hover {
          scale: 1.3;
        }
      }

      .right-top-hole {
        position: absolute;
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 1;
        background-color: green;

        &:hover {
          scale: 1.3;
        }
      }

      .left-bottom-hole {
        position: absolute;
        bottom: 10px;
        left: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 1;
        background-color: blue;

        &:hover {
          scale: 1.3;
        }
      }

      .right-bottom-hole {
        position: absolute;
        bottom: 10px;
        right: 10px;
        width: 40px;
        height: 40px;
        border-radius: 20px;
        box-shadow: inset 0px 0px 6px 2px rgba(255, 255, 255, 0.3);

        &:hover {
          scale: 1.3;
        }
      }

      .left-menu {
        display: flex;
        flex-direction: column;
        height: calc(100% - 100px);
        padding-left: 20px;
        backdrop-filter: blur(4px);

        .menu {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 250px;
          height: 100%;
          border-radius: 30px;
          background-color: rgba(20, 20, 20, 0.3);
          box-shadow: inset -3px -3px 10px 1px #777;
          transition: width 0.3s ease;

          &.collapsed {
            width: 80px;
          }

          .head {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 50px;

            .logo-wrapper {
              overflow: hidden;
              transition: width 0.3s ease;
              width: 140px;
              margin-right: 10px;

              &.collapsed {
                width: 0;
                margin-right: 0;
              }

              .label {
                display: inline-block;
                text-align: center;
                font-size: 22px;
                font-weight: bold;
                font-family: "Times New Roman", Times, serif;
                color: skyblue;
                white-space: nowrap;
              }
            }

            .action {
              width: 35px;

              &:hover {
                scale: 1.2;
                cursor: pointer;
              }
            }

          }

          .new-dialog {
            width: 70%;
            height: 50px;
            margin-top: 10px;
            text-align: center;
            font-size: 16px;
            color: #cccccc;
            border-width: 1px;
            border-color: blue;
            border-radius: 15px;
            background-color: #000;
            box-shadow: -1px -1px 4px 0px #aaa;

            &:hover {
              background-color: #333;
              box-shadow: -2px -2px 8px 0px #aaa;
            }

            &.collapsed {
              font-size: 0;
            }

            .icon {
              width: 25px;
              padding-right: 20px;

              &.collapsed {
                padding: 0;
              }
            }
          }

          .histories {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
            max-height: calc(100% - 150px);
            overflow: auto;
            margin-top: 20px;
            border-top: 2px solid #333;
            padding-bottom: 5px;

            .histories-item {
              flex-shrink: 0;
              display: flex;
              align-items: center;
              justify-content: space-between;
              width: 90%;
              height: 50px;
              margin-top: 20px;
              color: #ccc;
              border-radius: 10px;
              box-shadow: -1px -1px 5px 0px #aaa;

              .status {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;

                .status-ball {
                  width: 20px;
                  height: 20px;
                  border-radius: 10px;
                  opacity: 0.8;
                }
              }

              .summary {
                line-height: 40px;
                font-size: 16px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;

                &:hover {
                  cursor: pointer;
                }

                &.collapsed {
                  display: none;
                }
              }

              .delete {
                width: 20px;
                padding-right: 10px;

                &:hover {
                  scale: 1.3;
                  cursor: pointer;
                }
              }
            }
          }

        }
      }

      .right {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        overflow: auto;

        .island {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 40%;
          min-width: 600px;
          padding-top: 20px;
          padding-bottom: 20px;
          color: #ccc;
          border-radius: 20px;
          box-shadow: 0px 0px 10px 5px rgba(255, 255, 255, 0.2);
          backdrop-filter: blur(4px);

          .head {
            display: flex;
            align-items: center;
            justify-content: center;

            .logo {
              width: 80px;
            }

            .hello {
              font-size: 24px;
              font-weight: bold;
              font-family: "Arial", sans-serif;
              margin-left: 10px;
              text-shadow: 1px 1px 4px red, 3px 3px 20px rgb(74, 74, 255);
            }
          }

          .prompt {
            margin-top: 10px;
            margin-bottom: 20px;
            font-size: 16px;
            font-family: "Arial", sans-serif;
          }
        }

        .communication {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-evenly;
          width: 100%;
          max-width: 1200px;
          height: 96%;

          .chat-records {
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 80%;
            border-bottom: 1px solid #333;
            color: #fff;
            overflow: auto;
          }

          .new-dialog {
            width: 200px;
            height: 50px;
            margin-top: 10px;
            text-align: center;
            font-size: 16px;
            color: #cccccc;
            border: none;
            border-radius: 15px;
            background-color: #222;

            &:hover {
              background-color: #333;
              box-shadow: -2px -2px 8px 0px #aaa;
            }

            .icon {
              width: 25px;
              padding-right: 20px;
            }
          }
        }

      }
    }
  }
}
</style>
