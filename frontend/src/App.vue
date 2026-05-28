<template>
  <div class="app-shell">
    <main class="app-main">
      <RouterView />
    </main>

    <van-tabbar route safe-area-inset-bottom active-color="#1D9E75" inactive-color="#667085">
      <van-tabbar-item to="/" icon="home-o">首页</van-tabbar-item>
      <van-tabbar-item to="/review" icon="passed">审核</van-tabbar-item>
      <van-tabbar-item to="/upload" icon="upgrade">上传</van-tabbar-item>
      <van-tabbar-item to="/settings" icon="setting-o">设置</van-tabbar-item>
    </van-tabbar>
  </div>
</template>
