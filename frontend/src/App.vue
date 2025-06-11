<template>
  <el-config-provider :locale="locale">
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component v-if="$route.meta.keepAlive" :is="Component" :key="$route.name" />
      </keep-alive>
      <component v-if="!$route.meta.keepAlive" :is="Component" :key="$route.name" />
    </router-view>
  </el-config-provider>
</template>

<script setup>
import { ElConfigProvider } from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
const locale = zhCn;
</script>
