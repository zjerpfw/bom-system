<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { showFailToast, showSuccessToast } from "vant";
import { downloadBom, getDashboard, type DashboardData } from "@/api";

const router = useRouter();
const loading = ref(false);
const dashboard = ref<DashboardData>({
  total_bom_items: 0,
  pending: 0,
  confirmed: 0,
  rejected: 0,
  missing_materials: 0,
  auto_confirm_rate: 0,
  products: [],
});

const todayText = computed(() => {
  const now = new Date();
  return `${now.getMonth() + 1}月${now.getDate()}日 待审核 ${dashboard.value.pending} 条`;
});

const confirmedOf = (total: number, pending: number) => Math.max(total - pending, 0);

const productPercent = (total: number, pending: number) => {
  if (!total) return 0;
  return Math.round((confirmedOf(total, pending) / total) * 100);
};

async function loadDashboard() {
  loading.value = true;
  try {
    dashboard.value = await getDashboard();
  } catch {
    showFailToast("仪表盘数据加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleExport(productName: string) {
  try {
    await downloadBom(productName);
    showSuccessToast("已开始下载");
  } catch {
    showFailToast("导出失败，请稍后再试");
  }
}

onMounted(loadDashboard);
</script>

<template>
  <div class="page">
    <van-nav-bar title="BOM智能采集系统" fixed placeholder />

    <section class="hero-panel">
      <h1 class="hero-title">研发 BOM 审核台</h1>
      <p class="hero-subtitle">{{ todayText }}</p>
    </section>

    <div class="page-body">
      <van-loading v-if="loading" color="#1D9E75" size="28px" vertical>正在加载</van-loading>

      <van-grid v-else :column-num="2" :border="false" :gutter="10">
        <van-grid-item>
          <div class="surface stat-card">
            <div class="stat-value">{{ dashboard.pending }}</div>
            <div class="stat-label">待审核</div>
          </div>
        </van-grid-item>
        <van-grid-item>
          <div class="surface stat-card">
            <div class="stat-value">{{ dashboard.confirmed }}</div>
            <div class="stat-label">已确认</div>
          </div>
        </van-grid-item>
        <van-grid-item>
          <div class="surface stat-card">
            <div class="stat-value">{{ dashboard.missing_materials }}</div>
            <div class="stat-label">缺失物料</div>
          </div>
        </van-grid-item>
        <van-grid-item>
          <div class="surface stat-card">
            <div class="stat-value">{{ Math.round(dashboard.auto_confirm_rate * 100) }}%</div>
            <div class="stat-label">自动通过</div>
          </div>
        </van-grid-item>
      </van-grid>

      <h2 class="section-title">产品进度</h2>
      <div class="surface">
        <template v-if="dashboard.products.length">
          <van-cell v-for="product in dashboard.products" :key="product.name" :title="product.name || '未命名产品'">
            <template #right-icon>
              <van-button class="export-button" size="small" plain type="primary" @click.stop="handleExport(product.name)">
                导出
              </van-button>
            </template>
            <template #label>
              <div class="product-progress">
                <span>{{ confirmedOf(product.total, product.pending) }}/{{ product.total }}</span>
                <van-progress
                  :percentage="productPercent(product.total, product.pending)"
                  color="#1D9E75"
                  stroke-width="8"
                />
              </div>
            </template>
          </van-cell>
        </template>
        <div v-else class="empty-note">暂无产品数据</div>
      </div>

      <div class="action-row">
        <van-button class="touch-button primary-button" type="primary" block @click="router.push('/review')">
          去审核
        </van-button>
        <van-button class="touch-button" plain type="primary" block @click="router.push('/upload')">
          上传图纸
        </van-button>
        <van-button class="touch-button" plain type="primary" block @click="router.push('/missing')">
          缺失物料
        </van-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.product-progress {
  display: grid;
  grid-template-columns: 52px 1fr;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 16px;
}

.export-button {
  min-width: 64px;
  height: 44px;
  margin-left: 10px;
  border-color: #1D9E75;
  color: #1D9E75;
  font-size: 16px;
}
</style>
