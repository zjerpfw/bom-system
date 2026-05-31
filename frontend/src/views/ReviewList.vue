<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { showFailToast, showSuccessToast } from "vant";
import {
  batchConfirm,
  confirmItem,
  getDashboard,
  getPendingItems,
  reassignItem,
  rejectItem,
  type CandidateMaterial,
  type ReviewItem,
} from "@/api";

const items = ref<ReviewItem[]>([]);
const productName = ref("");
const page = ref(1);
const total = ref(0);
const loading = ref(false);
const requesting = ref(false);
const refreshing = ref(false);
const finished = ref(false);
const actionSheetVisible = ref(false);
const selectedItem = ref<ReviewItem | null>(null);
const productOptions = ref<Array<{ text: string; value: string }>>([{ text: "全部产品", value: "" }]);

const visibleItems = computed(() => items.value);

function confidenceColor(value: number) {
  if (value >= 0.85) return "#1D9E75";
  if (value >= 0.7) return "#F59E0B";
  return "#D64545";
}

function matchLabel(level?: string | null) {
  const labels: Record<string, string> = {
    exact: "精确",
    fuzzy: "模糊",
    embedding: "语义",
    llm: "AI推断",
    rule: "规则",
    none: "未匹配",
  };
  return labels[level || "none"] || "未匹配";
}

function primaryCandidate(item: ReviewItem) {
  return item.candidates[0] || {
    code: item.material_code || "",
    name: item.material_name || "",
    spec: "",
    score: item.confidence,
  };
}

async function loadItems(reset = false) {
  if (requesting.value) return;
  requesting.value = true;
  loading.value = true;
  try {
    const currentPage = reset ? 1 : page.value;
    const result = await getPendingItems({
      product_name: productName.value || undefined,
      page: currentPage,
      page_size: 6,
    });
    total.value = result.total;
    items.value = reset ? result.items : [...items.value, ...result.items];
    page.value = currentPage + 1;
    finished.value = items.value.length >= result.total;
  } catch {
    showFailToast("待审核列表加载失败");
  } finally {
    requesting.value = false;
    loading.value = false;
    refreshing.value = false;
  }
}

async function loadProductOptions() {
  try {
    const dashboard = await getDashboard();
    productOptions.value = [
      { text: "全部产品", value: "" },
      ...dashboard.products.map((product) => ({ text: product.name || "未命名产品", value: product.name })),
    ];
  } catch {
    productOptions.value = [{ text: "全部产品", value: "" }];
  }
}

async function refreshItems() {
  refreshing.value = true;
  finished.value = false;
  await loadItems(true);
}

async function handleConfirm(item: ReviewItem) {
  const systemCode = item.material_code || primaryCandidate(item).code;
  if (!systemCode) {
    showFailToast("请先选择候选物料");
    return;
  }
  try {
    await confirmItem(item.id, systemCode);
    showSuccessToast("已确认");
    await refreshItems();
  } catch {
    showFailToast("确认失败");
  }
}

async function handleReject(item: ReviewItem) {
  selectedItem.value = item;
  actionSheetVisible.value = true;
}

async function handleCandidate(candidate: CandidateMaterial) {
  if (!selectedItem.value) return;
  try {
    await reassignItem(selectedItem.value.id, candidate.code);
    showSuccessToast("已改为候选物料");
    actionSheetVisible.value = false;
    await refreshItems();
  } catch {
    showFailToast("候选物料确认失败");
  }
}

async function markMissing() {
  if (!selectedItem.value) return;
  try {
    await rejectItem(selectedItem.value.id);
    showSuccessToast("已转入缺失物料处理");
    actionSheetVisible.value = false;
    await refreshItems();
  } catch {
    showFailToast("操作失败");
  }
}

async function handleBatchConfirm() {
  const highConfidenceIds = items.value.filter((item) => item.confidence >= 0.85).map((item) => item.id);
  if (!highConfidenceIds.length) {
    showFailToast("暂无高置信度条目");
    return;
  }
  try {
    const result = await batchConfirm(highConfidenceIds);
    showSuccessToast(`已确认 ${result.confirmed} 条`);
    await refreshItems();
  } catch {
    showFailToast("批量确认失败");
  }
}

watch(productName, () => {
  refreshItems();
});

onMounted(async () => {
  await loadProductOptions();
  await loadItems(true);
});
</script>

<template>
  <div class="page">
    <van-nav-bar title="BOM审核" fixed placeholder />
    <div class="review-toolbar">
      <van-dropdown-menu>
        <van-dropdown-item v-model="productName" :options="productOptions" />
      </van-dropdown-menu>
      <van-button class="batch-button" type="primary" size="small" @click="handleBatchConfirm">
        批量确认高置信度
      </van-button>
    </div>

    <div class="review-count">
      <span>待审核</span>
      <van-badge :content="total" color="#1D9E75" />
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="refreshItems">
      <van-list v-model:loading="loading" :finished="finished" finished-text="没有更多了" @load="loadItems">
        <div class="review-list">
          <article v-for="item in visibleItems" :key="item.id" class="review-card surface">
            <div class="raw-name">{{ item.raw_name }}</div>
            <div class="match-row">
              <span>{{ primaryCandidate(item).code || "未匹配编码" }}</span>
              <strong>{{ primaryCandidate(item).name || "待选择物料" }}</strong>
            </div>
            <div class="spec-line">{{ primaryCandidate(item).spec || "无规格" }}</div>
            <div class="confidence-block">
              <div class="confidence-header">
                <span>置信度 {{ Math.round(item.confidence * 100) }}%</span>
                <van-tag :color="confidenceColor(item.confidence)" plain>{{ matchLabel(item.match_level) }}</van-tag>
              </div>
              <van-progress
                :percentage="Math.round(item.confidence * 100)"
                :color="confidenceColor(item.confidence)"
                stroke-width="9"
              />
            </div>
            <div class="review-actions">
              <van-button class="decision-button" type="primary" icon="success" @click="handleConfirm(item)">
                正确
              </van-button>
              <van-button class="decision-button reject" plain type="danger" icon="cross" @click="handleReject(item)">
                不对
              </van-button>
            </div>
          </article>
          <div v-if="!loading && !items.length" class="empty-note">暂无待审核条目</div>
        </div>
      </van-list>
    </van-pull-refresh>

    <van-action-sheet v-model:show="actionSheetVisible" title="选择正确物料">
      <div class="candidate-sheet">
        <van-cell
          v-for="candidate in selectedItem?.candidates || []"
          :key="candidate.code"
          clickable
          :title="`${candidate.code} ${candidate.name}`"
          :label="candidate.spec || '无规格'"
          @click="handleCandidate(candidate)"
        />
        <van-button class="missing-button" block type="danger" plain @click="markMissing">
          标记为缺失物料
        </van-button>
      </div>
    </van-action-sheet>
  </div>
</template>

<style scoped>
.review-toolbar {
  position: sticky;
  top: 46px;
  z-index: 3;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--color-bg);
}

.batch-button {
  min-height: 38px;
  border-radius: 8px;
  white-space: nowrap;
}

.review-count {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 17px;
  font-weight: 800;
}

.review-list {
  display: grid;
  gap: 14px;
  padding: 8px 14px 22px;
}

.review-card {
  padding: 18px;
}

.raw-name {
  font-size: 20px;
  line-height: 1.35;
  font-weight: 850;
}

.match-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  font-size: 16px;
}

.spec-line {
  margin-top: 6px;
  color: var(--color-muted);
  font-size: 16px;
}

.confidence-block {
  margin-top: 16px;
}

.confidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 16px;
}

.review-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 18px;
}

.decision-button {
  min-height: 50px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 850;
}

.reject {
  background: #fff;
}

.candidate-sheet {
  padding: 0 0 18px;
}

.missing-button {
  width: calc(100% - 28px);
  min-height: 48px;
  margin: 14px;
  border-radius: 8px;
}
</style>
