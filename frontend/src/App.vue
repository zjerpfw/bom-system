<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();

const navigationItems = [
  { to: "/", icon: "home-o", label: "首页", description: "统计总览" },
  { to: "/review", icon: "passed", label: "审核", description: "待确认BOM" },
  { to: "/upload", icon: "upgrade", label: "上传", description: "图纸和语音" },
  { to: "/materials", icon: "records-o", label: "物料", description: "ERP底库" },
  { to: "/missing", icon: "warning-o", label: "缺失", description: "待新建物料" },
  { to: "/settings", icon: "setting-o", label: "设置", description: "接口和模式" },
];

const routeTitle = computed(() => String(route.meta.title || "首页"));
</script>

<template>
  <div class="app-shell">
    <aside class="desktop-sidebar">
      <div class="brand-block">
        <div class="brand-mark">BOM</div>
        <div>
          <strong>BOM智能采集系统</strong>
          <span>电脑审核工作台</span>
        </div>
      </div>

      <nav class="desktop-nav">
        <RouterLink
          v-for="item in navigationItems"
          :key="item.to"
          class="desktop-nav-item"
          active-class="active"
          :to="item.to"
        >
          <van-icon :name="item.icon" />
          <span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.description }}</small>
          </span>
        </RouterLink>
      </nav>
    </aside>

    <div class="workspace">
      <header class="desktop-header">
        <div>
          <span class="header-kicker">当前页面</span>
          <h1>{{ routeTitle }}</h1>
        </div>
      </header>

      <main class="app-main">
        <RouterView />
      </main>
    </div>

    <van-tabbar class="mobile-tabbar" route safe-area-inset-bottom active-color="#1D9E75" inactive-color="#667085">
      <van-tabbar-item to="/" icon="home-o">首页</van-tabbar-item>
      <van-tabbar-item to="/review" icon="passed">审核</van-tabbar-item>
      <van-tabbar-item to="/upload" icon="upgrade">上传</van-tabbar-item>
      <van-tabbar-item to="/materials" icon="records-o">物料</van-tabbar-item>
      <van-tabbar-item to="/settings" icon="setting-o">设置</van-tabbar-item>
    </van-tabbar>
  </div>
</template>
