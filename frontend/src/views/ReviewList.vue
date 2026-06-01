<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { showConfirmDialog, showFailToast, showSuccessToast } from "vant";
import {
  batchConfirm,
  confirmItem,
  getDashboard,
  getReviewItems,
  reassignItem,
  rejectItem,
  type CandidateMaterial,
  type ReviewItem,
} from "@/api";

type ReviewStatus = "pending" | "confirmed" | "rejected" | "";

const items = ref<ReviewItem[]>([]);
const productName = ref("");
const statusFilter = ref<ReviewStatus>("pending");
const page = ref(1);
const pageSize = ref(30);
const total = ref(0);
const loading = ref(false);
const actionSheetVisible = ref(false);
const selectedItem = ref<ReviewItem | null>(null);
const manualSystemCode = ref("");
const productOptions = ref<Array<{ text: string; value: string }>>([{ text: "全部产品", value: "" }]);

const statusOptions = [
  { label: "待审核", value: "pending" },
  { label: "已确认", value: "confirmed" },
  { label: "已拒绝", value: "rejected" },
  { label: "全部", value: "" },
];

const totalPages = computed(() => Math.max(Math.ceil(total.value / pageSize.value), 1));
const highConfidenceCount = computed(
  () => items.value.filter((item) => item.status === "pending" && item.confidence >= 0.85 && primaryCode(item)).length,
);

function statusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    pending: "待审核",
    confirmed: "已确认",
    rejected: "已拒绝",
  };
  return labels[status || ""] || "全部";
}

function statusClass(status?: string | null) {
  return `status-${status || "all"}`;
}

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
    spec: item.material_spec || "",
    score: item.confidence,
  };
}

function primaryCode(item: ReviewItem) {
  return item.material_code || primaryCandidate(item).code || "";
}

function primaryName(item: ReviewItem) {
  return item.material_name || primaryCandidate(item).name || "";
}

function primarySpec(item: ReviewItem) {
  return item.material_spec || primaryCandidate(item).spec || "";
}

function formatQuantity(item: ReviewItem) {
  if (item.quantity === null || item.quantity === undefined) return "-";
  return `${Number(item.quantity).toLocaleString("zh-CN", { maximumFractionDigits: 4 })}${item.unit ? ` ${item.unit}` : ""}`;
}

async function loadItems(targetPage = page.value) {
  loading.value = true;
  try {
    const result = await getReviewItems({
      product_name: productName.value || undefined,
      status: statusFilter.value || undefined,
      page: targetPage,
      page_size: pageSize.value,
    });
    total.value = result.total;
    items.value = result.items;
    page.value = result.page;
  } catch {
    showFailToast("审核列表加载失败");
  } finally {
    loading.value = false;
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
  await loadItems(1);
}

async function handleConfirm(item: ReviewItem) {
  const systemCode = primaryCode(item);
  if (!systemCode) {
    showFailToast("请先选择候选物料");
    return;
  }
  try {
    await confirmItem(item.id, systemCode);
    showSuccessToast("已确认");
    await loadItems(page.value);
  } catch {
    showFailToast("确认失败");
  }
}

async function handleReject(item: ReviewItem) {
  const confirmed = await showConfirmDialog({
    title: "确认拒绝",
    message: `将“${item.raw_name}”标记为不匹配？`,
    confirmButtonText: "拒绝",
    confirmButtonColor: "#D64545",
  }).then(
    () => true,
    () => false,
  );
  if (!confirmed) return;

  try {
    await rejectItem(item.id);
    showSuccessToast("已拒绝");
    await loadItems(page.value);
  } catch {
    showFailToast("拒绝失败");
  }
}

function openCandidateSheet(item: ReviewItem) {
  selectedItem.value = item;
  manualSystemCode.value = "";
  actionSheetVisible.value = true;
}

async function handleCandidate(candidate: CandidateMaterial) {
  if (!selectedItem.value) return;
  try {
    await reassignItem(selectedItem.value.id, candidate.code);
    showSuccessToast("已重新指定物料");
    actionSheetVisible.value = false;
    await loadItems(page.value);
  } catch {
    showFailToast("重新指定失败");
  }
}

async function markMissing() {
  if (!selectedItem.value) return;
  try {
    await rejectItem(selectedItem.value.id);
    showSuccessToast("已标记为不匹配");
    actionSheetVisible.value = false;
    await loadItems(page.value);
  } catch {
    showFailToast("操作失败");
  }
}

async function handleManualReassign() {
  if (!selectedItem.value) return;
  const systemCode = manualSystemCode.value.trim();
  if (!systemCode) {
    showFailToast("请输入ERP物料编码");
    return;
  }
  try {
    await reassignItem(selectedItem.value.id, systemCode);
    showSuccessToast("已按编码指定物料");
    actionSheetVisible.value = false;
    await loadItems(page.value);
  } catch {
    showFailToast("物料编码不存在或指定失败");
  }
}

async function handleBatchConfirm() {
  const highConfidenceIds = items.value
    .filter((item) => item.status === "pending" && item.confidence >= 0.85 && primaryCode(item))
    .map((item) => item.id);
  if (!highConfidenceIds.length) {
    showFailToast("当前页暂无高置信度待确认条目");
    return;
  }
  try {
    const result = await batchConfirm(highConfidenceIds);
    showSuccessToast(`已确认 ${result.confirmed} 条，跳过 ${result.skipped} 条`);
    await refreshItems();
  } catch {
    showFailToast("批量确认失败");
  }
}

function changePage(nextPage: number) {
  const safePage = Math.min(Math.max(nextPage, 1), totalPages.value);
  if (safePage !== page.value) {
    loadItems(safePage);
  }
}

watch([productName, statusFilter], () => {
  refreshItems();
});

onMounted(async () => {
  await loadProductOptions();
  await loadItems(1);
});
</script>

<template>
  <div class="page review-page">
    <van-nav-bar title="BOM审核" fixed placeholder />

    <section class="review-shell surface">
      <header class="review-header">
        <div>
          <h2>审核工作台</h2>
          <p>自动确认、待审核和已拒绝记录都在这里统一复核。</p>
        </div>
        <div class="review-summary">
          <strong>{{ total }}</strong>
          <span>{{ statusLabel(statusFilter) }}记录</span>
        </div>
      </header>

      <div class="review-filters">
        <van-dropdown-menu>
          <van-dropdown-item v-model="productName" :options="productOptions" />
        </van-dropdown-menu>

        <div class="status-tabs" role="tablist" aria-label="审核状态">
          <button
            v-for="option in statusOptions"
            :key="option.value || 'all'"
            class="status-tab"
            :class="{ active: statusFilter === option.value }"
            type="button"
            @click="statusFilter = option.value as ReviewStatus"
          >
            {{ option.label }}
          </button>
        </div>

        <div class="toolbar-actions">
          <van-button plain type="primary" icon="replay" :loading="loading" @click="refreshItems">刷新</van-button>
          <van-button
            type="primary"
            icon="success"
            :disabled="!highConfidenceCount"
            @click="handleBatchConfirm"
          >
            批量确认 {{ highConfidenceCount }}
          </van-button>
        </div>
      </div>

      <div class="table-wrap">
        <table class="review-table">
          <thead>
            <tr>
              <th class="col-id">ID</th>
              <th class="col-product">产品</th>
              <th class="col-raw">研发叫法</th>
              <th class="col-code">系统编码</th>
              <th class="col-name">系统名称</th>
              <th class="col-spec">规格</th>
              <th class="col-qty">用量</th>
              <th class="col-confidence">置信度</th>
              <th class="col-method">方式</th>
              <th class="col-status">状态</th>
              <th class="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="11">
                <div class="table-loading">
                  <van-loading color="#1D9E75">正在加载审核记录</van-loading>
                </div>
              </td>
            </tr>
            <tr v-for="item in items" v-else :key="item.id" :class="{ 'auto-row': item.auto_confirmed }">
              <td class="muted-cell">#{{ item.id }}</td>
              <td>{{ item.product_name || "未命名产品" }}</td>
              <td>
                <strong class="raw-text">{{ item.raw_name }}</strong>
              </td>
              <td>
                <span class="code-pill" v-if="primaryCode(item)">{{ primaryCode(item) }}</span>
                <span v-else class="empty-inline">未匹配</span>
              </td>
              <td>{{ primaryName(item) || "-" }}</td>
              <td>{{ primarySpec(item) || "-" }}</td>
              <td class="number-cell">{{ formatQuantity(item) }}</td>
              <td>
                <div class="confidence-cell">
                  <span :style="{ color: confidenceColor(item.confidence) }">
                    {{ Math.round(item.confidence * 100) }}%
                  </span>
                  <div class="mini-progress">
                    <i :style="{ width: `${Math.round(item.confidence * 100)}%`, background: confidenceColor(item.confidence) }" />
                  </div>
                </div>
              </td>
              <td>
                <van-tag plain :color="confidenceColor(item.confidence)">{{ matchLabel(item.match_level) }}</van-tag>
              </td>
              <td>
                <div class="status-cell">
                  <span class="status-badge" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
                  <small v-if="item.auto_confirmed">自动确认</small>
                  <small v-else-if="item.reviewer">人工：{{ item.reviewer }}</small>
                </div>
              </td>
              <td>
                <div class="row-actions">
                  <van-button
                    v-if="item.status !== 'confirmed'"
                    size="small"
                    type="primary"
                    :disabled="!primaryCode(item)"
                    @click="handleConfirm(item)"
                  >
                    确认
                  </van-button>
                  <van-button size="small" plain type="primary" @click="openCandidateSheet(item)">改物料</van-button>
                  <van-button
                    v-if="item.status !== 'rejected'"
                    size="small"
                    plain
                    type="danger"
                    @click="handleReject(item)"
                  >
                    拒绝
                  </van-button>
                </div>
              </td>
            </tr>
            <tr v-if="!loading && !items.length">
              <td colspan="11">
                <div class="empty-note">当前筛选条件下暂无记录</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer class="table-footer">
        <span>第 {{ page }} / {{ totalPages }} 页，每页 {{ pageSize }} 条</span>
        <div class="pager-actions">
          <van-button plain size="small" :disabled="page <= 1" @click="changePage(page - 1)">上一页</van-button>
          <van-button plain size="small" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</van-button>
        </div>
      </footer>
    </section>

    <van-action-sheet v-model:show="actionSheetVisible" title="选择正确物料">
      <div class="candidate-sheet">
        <div class="candidate-title" v-if="selectedItem">
          <strong>{{ selectedItem.raw_name }}</strong>
          <span>请选择一个候选物料，确认后会写入命名对照表。</span>
        </div>
        <van-cell
          v-for="candidate in selectedItem?.candidates || []"
          :key="candidate.code"
          clickable
          :title="`${candidate.code} ${candidate.name}`"
          :label="`${candidate.spec || '无规格'} · 相似度 ${Math.round((candidate.score || 0) * 100)}%`"
          @click="handleCandidate(candidate)"
        />
        <div v-if="!(selectedItem?.candidates || []).length" class="empty-note">暂无候选物料，可先拒绝后进入缺失物料处理。</div>
        <div class="manual-reassign">
          <van-field
            v-model="manualSystemCode"
            label="ERP编码"
            placeholder="输入正确物料编码"
            clearable
            @keyup.enter="handleManualReassign"
          />
          <van-button type="primary" block @click="handleManualReassign">按编码指定</van-button>
        </div>
        <van-button class="missing-button" block type="danger" plain @click="markMissing">
          标记为不匹配
        </van-button>
      </div>
    </van-action-sheet>
  </div>
</template>

<style scoped>
.review-page {
  display: block;
}

.review-shell {
  overflow: hidden;
}

.review-header {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
  background: #ffffff;
}

.review-header h2 {
  margin: 0;
  font-size: 22px;
  line-height: 1.3;
}

.review-header p {
  margin: 4px 0 0;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.5;
}

.review-summary {
  display: grid;
  min-width: 128px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #f7fbf9;
}

.review-summary strong {
  color: var(--color-primary-dark);
  font-size: 28px;
  line-height: 1.1;
}

.review-summary span {
  margin-top: 4px;
  color: var(--color-muted);
  font-size: 14px;
}

.review-filters {
  display: grid;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: #fbfdfc;
}

.review-filters :deep(.van-dropdown-menu) {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: none;
}

.status-tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
}

.status-tab {
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: #ffffff;
  font-weight: 750;
  white-space: nowrap;
}

.status-tab.active {
  border-color: var(--color-primary);
  color: #ffffff;
  background: var(--color-primary);
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-actions .van-button {
  min-height: 40px;
  border-radius: 8px;
}

.table-wrap {
  overflow: auto;
  background: #ffffff;
}

.review-table {
  width: 100%;
  min-width: 1180px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 15px;
}

.review-table th,
.review-table td {
  padding: 9px 10px;
  border-right: 1px solid #e6eee9;
  border-bottom: 1px solid #e6eee9;
  vertical-align: middle;
  text-align: left;
}

.review-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  color: #33423b;
  background: #eaf3ef;
  font-size: 14px;
  font-weight: 850;
  white-space: nowrap;
}

.review-table tbody tr:hover {
  background: #f7fbf9;
}

.review-table tbody tr.auto-row {
  background: #f3fbf6;
}

.col-id {
  width: 68px;
}

.col-product {
  width: 150px;
}

.col-raw {
  width: 180px;
}

.col-code {
  width: 128px;
}

.col-name {
  width: 170px;
}

.col-spec {
  width: 170px;
}

.col-qty {
  width: 96px;
}

.col-confidence {
  width: 120px;
}

.col-method {
  width: 92px;
}

.col-status {
  width: 126px;
}

.col-actions {
  width: 210px;
}

.muted-cell,
.empty-inline {
  color: var(--color-muted);
}

.raw-text {
  display: block;
  color: var(--color-text);
  font-size: 16px;
  line-height: 1.35;
}

.code-pill {
  display: inline-flex;
  min-height: 26px;
  align-items: center;
  padding: 0 8px;
  border-radius: 6px;
  color: var(--color-primary-dark);
  background: #eaf7f2;
  font-weight: 800;
}

.number-cell {
  text-align: right;
  white-space: nowrap;
}

.confidence-cell {
  display: grid;
  gap: 5px;
  min-width: 92px;
  font-weight: 850;
}

.mini-progress {
  width: 100%;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2ef;
}

.mini-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.status-cell {
  display: grid;
  gap: 4px;
}

.status-cell small {
  color: var(--color-muted);
  font-size: 12px;
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  min-height: 24px;
  align-items: center;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 850;
}

.status-pending {
  color: #9a5b00;
  background: #fff3d6;
}

.status-confirmed {
  color: var(--color-primary-dark);
  background: #dcf5ea;
}

.status-rejected {
  color: var(--color-danger);
  background: #fde7e7;
}

.status-all {
  color: var(--color-muted);
  background: #eef2f1;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.row-actions .van-button {
  min-width: 56px;
  border-radius: 6px;
}

.table-loading {
  display: grid;
  min-height: 180px;
  place-items: center;
}

.table-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  color: var(--color-muted);
  background: #fbfdfc;
  font-size: 15px;
}

.pager-actions {
  display: flex;
  gap: 8px;
}

.pager-actions .van-button {
  min-width: 76px;
  border-radius: 8px;
}

.candidate-sheet {
  padding: 0 0 18px;
}

.candidate-title {
  display: grid;
  gap: 4px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
}

.candidate-title strong {
  font-size: 18px;
}

.candidate-title span {
  color: var(--color-muted);
  font-size: 15px;
}

.manual-reassign {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-top: 1px solid var(--color-border);
}

.manual-reassign .van-button {
  min-height: 44px;
  border-radius: 8px;
}

.missing-button {
  width: calc(100% - 28px);
  min-height: 44px;
  margin: 14px;
  border-radius: 8px;
}

@media (min-width: 900px) {
  .review-shell {
    width: min(1540px, 100%);
  }

  .review-header {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    padding: 18px 20px;
  }

  .review-filters {
    grid-template-columns: minmax(220px, 320px) minmax(360px, 1fr) auto;
    align-items: center;
  }

  .candidate-sheet {
    width: min(760px, 100vw);
    margin: 0 auto;
  }
}
</style>
