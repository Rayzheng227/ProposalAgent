import App from "./App.vue";

// 引入库
import router from "./router";
import ElementPlus from "element-plus";
import { createApp } from "vue";
import { createPinia } from "pinia";
import piniaPluginPersistedstate from "pinia-plugin-persistedstate";
import Request from "@/request/Request";
import Api from "@/request/Api";
// 引入样式
import "element-plus/dist/index.css";
import "@/assets/styles/base.scss";
// 实例化组件
const app = createApp(App);
const pinia = createPinia();
pinia.use(piniaPluginPersistedstate);
// 挂载组件
app.config.globalProperties.Request = Request;
app.config.globalProperties.Api = Api;
app.use(ElementPlus).use(router).use(pinia).mount("#app");
