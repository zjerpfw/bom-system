<script setup lang="ts">
import { onMounted, ref } from "vue";
import { showFailToast, showSuccessToast } from "vant";
import { getMissingItems, markMissingCreated, type MissingMaterial } from "@/api";

const items = ref<MissingMaterial[]>([]);
const page = ref(1);
const total = ref(0);
const loading = ref(false);
const requesting = ref(false);
const refreshing = ref(false);
const finished = ref(false);

async function loadItems(reset = false) {
  if (requesting.value) return;
  requesting.value = true;
  loading.value = true;
  try {
    const currentPage = reset ? 1 : page.value;
    const result = await getMissingItems({ page: currentPage, page_size: 8 });
    total.value = result.total;
    items.value = reset ? result.items : [...items.value, ...result.items];
    page.value = currentPage + 1;
    finished.value = items.value.length >= result.total;
  } catch {
    showFailToast("缺失物料加载失败");
  } finally {
    requesting.value = false;
    loading.value = false;
    refreshing.value = false;
  }
}

async function refreshItems() {
  refreshing.value = true;
  finished.value = false;
  await loadItems(true);
}

async function handleCreated(item: MissingMaterial) {
  try {
    await markMissingCreated(item.id);
    showSuccessToast("已标记新建");
    await refreshItems();
  } catch {
    showFailToast("标记失败");
  }
}

onMounted(() => loadItems(true));
</script>

<template>
  <div class="page">
    <van-nav-bar title="缺失物料" fixed placeholder />
    <div class="missing-tip">
      先在ERP新建此物料，编码确认后点击按钮
    </div>
    <van-pull-refresh v-model="refreshing" @refresh="refreshItems">
      <van-list v-model:loading="loading" :finished="finished" finished-text="没有更多了" @load="loadItems">
        <div class="missing-list">
          <article v-for="item in items" :key="item.id" class="surface missing-card">
            <div class="missing-name">{{ item.raw_name }}</div>
            <div class="suggestion">
              <span>名称：{{ item.ai_suggested_name || "无建议" }}</span>
              <span>规格：{{ item.ai_suggested_spec || "无建议" }}</span>
              <span>类别：{{ item.ai_suggested_category || "无建议" }}</span>
            </div>
            <van-button class="created-button" type="primary" block @click="handleCreated(item)">
              已在ERP新建
            </van-button>
          </article>
          <div v-if="!loading && !items.length" class="empty-note">暂无缺失物料</div>
        </div>
      </van-list>
    </van-pull-refresh>
  </div>
</template>

<style scoped>
.missing-tip {
  margin: 12px 14px 0;
  padding: 12px 14px;
  border-radius: 8px;
  color: #0f7658;
  background: #e6f7f1;
  font-size: 16px;
  line-height: 1.5;
}

.missing-list {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.missing-card {
  padding: 16px;
}

.missing-name {
  font-size: 20px;
  line-height: 1.35;
  font-weight: 850;
}

.suggestion {
  display: grid;
  gap: 6px;
  margin: 12px 0 16px;
  color: var(--color-muted);
  font-size: 16px;
}

.created-button {
  min-height: 48px;
  border-radius: 8px;
  font-size: 17px;
  font-weight: 800;
}

@media (min-width: 900px) {
  .missing-tip {
    width: min(1180px, 100%);
    margin: 0 0 16px;
  }

  .missing-list {
    width: min(1180px, 100%);
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 0 0 30px;
  }
}

@media (min-width: 1320px) {
  .missing-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
