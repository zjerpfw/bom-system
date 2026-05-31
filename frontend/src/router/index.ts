import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("@/views/Dashboard.vue"),
      meta: { title: "首页" },
    },
    {
      path: "/review",
      name: "review",
      component: () => import("@/views/ReviewList.vue"),
      meta: { title: "审核" },
    },
    {
      path: "/missing",
      name: "missing",
      component: () => import("@/views/MissingList.vue"),
      meta: { title: "缺失物料" },
    },
    {
      path: "/upload",
      name: "upload",
      component: () => import("@/views/Upload.vue"),
      meta: { title: "上传" },
    },
    {
      path: "/materials",
      name: "materials",
      component: () => import("@/views/Materials.vue"),
      meta: { title: "物料库" },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/Settings.vue"),
      meta: { title: "设置" },
    },
  ],
});

export default router;
