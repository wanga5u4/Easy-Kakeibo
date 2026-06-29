const API_BASE = '/api';

const CATEGORIES = {
  income: ['工资', '奖金', '理财', '兼职', '其他收入'],
  expense: ['餐饮', '交通', '购物', '住房', '娱乐', '医疗', '教育', '其他支出'],
};

const TYPE_LABELS = { income: '收入', expense: '支出' };

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || '请求失败，请稍后重试');
  }
  return data;
}

function formatMoney(value) {
  return '￥' + Number(value || 0).toFixed(2);
}

function todayStr() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function currentMonthStr() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function formatDate(dateStr) {
  const [year, month, day] = dateStr.split('-');
  return `${year}年${month}月${day}日`;
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showToast(message, type = 'error') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast toast-${type}`;
  toast.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add('hidden'), 3000);
}

function setLoading(loading) {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.toggle('hidden', !loading);
}

function updateCategoryOptions(typeEl, categoryEl) {
  const options = CATEGORIES[typeEl.value] || [];
  categoryEl.innerHTML = options
    .map((category) => `<option value="${category}">${category}</option>`)
    .join('');
}

function applyBudgetView(budget) {
  const usedEl = document.getElementById('budgetUsed');
  const percentEl = document.getElementById('budgetPercent');
  const progressEl = document.getElementById('budgetProgress');
  const statusEl = document.getElementById('budgetStatus');
  const amountEl = document.getElementById('budgetAmount');
  if (!budget || !usedEl || !percentEl || !progressEl || !statusEl) return;

  const percent = Number(budget.percent || 0);
  const progress = Math.min(percent, 100);
  if (amountEl) amountEl.value = budget.amount ? Number(budget.amount).toFixed(2) : '';
  usedEl.textContent = `已用 ${formatMoney(budget.used)}`;
  percentEl.textContent = `${percent.toFixed(1)}%`;
  progressEl.style.width = `${progress}%`;
  progressEl.className = 'progress-bar';
  statusEl.className = 'alert mb-0 py-2';

  if ((budget.amount || 0) <= 0) {
    progressEl.classList.add('bg-secondary');
    statusEl.classList.add('alert-secondary');
  } else if (percent >= 100) {
    progressEl.classList.add('bg-danger');
    statusEl.classList.add('alert-danger');
  } else if (percent >= 80) {
    progressEl.classList.add('bg-warning');
    statusEl.classList.add('alert-warning');
  } else {
    progressEl.classList.add('bg-success');
    statusEl.classList.add('alert-success');
  }

  statusEl.textContent = `${budget.status}，剩余 ${formatMoney(budget.remaining)}`;
}
