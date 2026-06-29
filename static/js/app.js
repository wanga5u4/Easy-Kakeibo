const API_BASE = '/api';

const CATEGORIES = {
  income: ['工资', '奖金', '理财', '兼职', '其他收入'],
  expense: ['餐饮', '交通', '购物', '住房', '娱乐', '医疗', '教育', '其他支出'],
};

const TYPE_LABELS = { income: '收入', expense: '支出' };

let records = [];
let summary = { totalIncome: 0, totalExpense: 0, balance: 0 };
let analytics = null;
let editingId = null;
let deletingId = null;
let currentUser = null;

const els = {
  form: document.getElementById('recordForm'),
  formTitle: document.getElementById('formTitle'),
  recordId: document.getElementById('recordId'),
  date: document.getElementById('date'),
  type: document.getElementById('type'),
  category: document.getElementById('category'),
  amount: document.getElementById('amount'),
  note: document.getElementById('note'),
  submitBtn: document.getElementById('submitBtn'),
  cancelBtn: document.getElementById('cancelBtn'),
  recordList: document.getElementById('recordList'),
  emptyTip: document.getElementById('emptyTip'),
  totalIncome: document.getElementById('totalIncome'),
  totalExpense: document.getElementById('totalExpense'),
  balance: document.getElementById('balance'),
  filterType: document.getElementById('filterType'),
  filterMonth: document.getElementById('filterMonth'),
  clearFilter: document.getElementById('clearFilter'),
  deleteModal: document.getElementById('deleteModal'),
  cancelDelete: document.getElementById('cancelDelete'),
  confirmDelete: document.getElementById('confirmDelete'),
  toast: document.getElementById('toast'),
  loadingOverlay: document.getElementById('loadingOverlay'),
  currentUser: document.getElementById('currentUser'),
  loginLink: document.getElementById('loginLink'),
  registerLink: document.getElementById('registerLink'),
  logoutLink: document.getElementById('logoutLink'),
  guestActions: document.getElementById('guestActions'),
  userActions: document.getElementById('userActions'),
  guestPanel: document.getElementById('guestPanel'),
  dashboard: document.getElementById('dashboard'),
  statsMonth: document.getElementById('statsMonth'),
  budgetAmount: document.getElementById('budgetAmount'),
  saveBudgetBtn: document.getElementById('saveBudgetBtn'),
  budgetUsed: document.getElementById('budgetUsed'),
  budgetPercent: document.getElementById('budgetPercent'),
  budgetProgress: document.getElementById('budgetProgress'),
  budgetStatus: document.getElementById('budgetStatus'),
  categoryChart: document.getElementById('categoryChart'),
  trendChart: document.getElementById('trendChart'),
  categoryEmpty: document.getElementById('categoryEmpty'),
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(data.error || '请求失败，请稍后重试');
    error.status = response.status;
    throw error;
  }

  return data;
}

function setLoading(loading) {
  els.loadingOverlay.classList.toggle('hidden', !loading);
  els.submitBtn.disabled = loading || !currentUser?.loggedIn;
  els.confirmDelete.disabled = loading;
  els.saveBudgetBtn.disabled = loading || !currentUser?.loggedIn;
}

function setRecordControlsEnabled(enabled) {
  els.form
    .querySelectorAll('input, select, button')
    .forEach((el) => {
      el.disabled = !enabled;
    });
  els.filterType.disabled = !enabled;
  els.filterMonth.disabled = !enabled;
  els.clearFilter.disabled = !enabled;
  els.statsMonth.disabled = !enabled;
  els.budgetAmount.disabled = !enabled;
  els.saveBudgetBtn.disabled = !enabled;
}

function showToast(message, type = 'error') {
  els.toast.textContent = message;
  els.toast.className = `toast toast-${type}`;
  els.toast.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    els.toast.classList.add('hidden');
  }, 3000);
}

function formatMoney(value) {
  return '¥' + Number(value).toFixed(2);
}

function formatDate(dateStr) {
  const [y, m, d] = dateStr.split('-');
  return `${y}年${m}月${d}日`;
}

function todayStr() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function currentMonthStr() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
}

function updateCategoryOptions(type) {
  const options = CATEGORIES[type] || [];
  els.category.innerHTML = options
    .map((c) => `<option value="${c}">${c}</option>`)
    .join('');
}

function resetForm() {
  editingId = null;
  els.formTitle.textContent = '添加记录';
  els.submitBtn.textContent = '添加记录';
  els.cancelBtn.classList.add('hidden');
  els.recordId.value = '';
  els.form.reset();
  els.date.value = todayStr();
  updateCategoryOptions(els.type.value);
}

function startEdit(record) {
  editingId = record.id;
  els.formTitle.textContent = '编辑记录';
  els.submitBtn.textContent = '保存修改';
  els.cancelBtn.classList.remove('hidden');
  els.recordId.value = record.id;
  els.date.value = record.date;
  els.type.value = record.type;
  updateCategoryOptions(record.type);
  els.category.value = record.category;
  els.amount.value = record.amount;
  els.note.value = record.note || '';
  els.form.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function buildQuery() {
  const params = new URLSearchParams();
  const type = els.filterType.value;
  const month = els.filterMonth.value;

  if (type !== 'all') params.set('type', type);
  if (month) params.set('month', month);

  const query = params.toString();
  return query ? `?${query}` : '';
}

function renderSummary() {
  els.totalIncome.textContent = formatMoney(summary.totalIncome);
  els.totalExpense.textContent = formatMoney(summary.totalExpense);
  els.balance.textContent = formatMoney(summary.balance);
}

function renderBudget() {
  const budget = analytics?.budget || {
    amount: 0,
    used: 0,
    percent: 0,
    status: '未设置预算',
  };
  const progress = Math.min(Number(budget.percent || 0), 100);

  els.budgetAmount.value = budget.amount ? Number(budget.amount).toFixed(2) : '';
  els.budgetUsed.textContent = `已用 ${formatMoney(budget.used || 0)}`;
  els.budgetPercent.textContent = `${Number(budget.percent || 0).toFixed(1)}%`;
  els.budgetProgress.style.width = `${progress}%`;
  els.budgetProgress.className = 'progress-bar';
  els.budgetStatus.className = 'alert mb-0 py-2';

  if ((budget.amount || 0) <= 0) {
    els.budgetProgress.classList.add('bg-secondary');
    els.budgetStatus.classList.add('alert-secondary');
  } else if ((budget.percent || 0) >= 100) {
    els.budgetProgress.classList.add('bg-danger');
    els.budgetStatus.classList.add('alert-danger');
  } else if ((budget.percent || 0) >= 80) {
    els.budgetProgress.classList.add('bg-warning');
    els.budgetStatus.classList.add('alert-warning');
  } else {
    els.budgetProgress.classList.add('bg-success');
    els.budgetStatus.classList.add('alert-success');
  }

  els.budgetStatus.textContent = `${budget.status}，剩余 ${formatMoney(budget.remaining || 0)}`;
}

function drawEmptyChart(canvas, text) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#6b7280';
  ctx.font = '14px "Segoe UI", sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
}

function drawCategoryChart(categories) {
  const canvas = els.categoryChart;
  const ctx = canvas.getContext('2d');
  const colors = ['#0d6efd', '#dc3545', '#198754', '#ffc107', '#6f42c1', '#20c997'];

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  els.categoryEmpty.classList.toggle('hidden', categories.length > 0);
  if (categories.length === 0) {
    drawEmptyChart(canvas, '暂无支出数据');
    return;
  }

  let start = -Math.PI / 2;
  const cx = 88;
  const cy = 110;
  const radius = 70;
  categories.forEach((item, index) => {
    const angle = (item.percent / 100) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, start + angle);
    ctx.closePath();
    ctx.fillStyle = colors[index % colors.length];
    ctx.fill();
    start += angle;
  });

  ctx.font = '13px "Segoe UI", sans-serif';
  ctx.textAlign = 'left';
  categories.slice(0, 6).forEach((item, index) => {
    const y = 44 + index * 28;
    ctx.fillStyle = colors[index % colors.length];
    ctx.fillRect(190, y - 10, 12, 12);
    ctx.fillStyle = '#1a1d26';
    ctx.fillText(`${item.category} ${item.percent}%`, 210, y);
  });
}

function drawTrendChart(trend) {
  const canvas = els.trendChart;
  const ctx = canvas.getContext('2d');
  const padding = 34;
  const width = canvas.width - padding * 2;
  const height = canvas.height - padding * 2;
  const maxValue = Math.max(
    1,
    ...trend.map((item) => Math.max(item.income, item.expense))
  );

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#e5e7eb';
  ctx.beginPath();
  ctx.moveTo(padding, padding);
  ctx.lineTo(padding, padding + height);
  ctx.lineTo(padding + width, padding + height);
  ctx.stroke();

  const drawLine = (key, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    trend.forEach((item, index) => {
      const x = padding + (width / Math.max(trend.length - 1, 1)) * index;
      const y = padding + height - (item[key] / maxValue) * height;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  drawLine('income', '#198754');
  drawLine('expense', '#dc3545');

  ctx.fillStyle = '#6b7280';
  ctx.font = '11px "Segoe UI", sans-serif';
  ctx.textAlign = 'center';
  trend.forEach((item, index) => {
    const x = padding + (width / Math.max(trend.length - 1, 1)) * index;
    ctx.fillText(item.month.slice(5), x, canvas.height - 10);
  });

  ctx.textAlign = 'left';
  ctx.fillStyle = '#198754';
  ctx.fillText('收入', padding, 16);
  ctx.fillStyle = '#dc3545';
  ctx.fillText('支出', padding + 46, 16);
}

function renderAnalytics() {
  if (!analytics) return;

  summary = {
    totalIncome: analytics.totalIncome,
    totalExpense: analytics.totalExpense,
    balance: analytics.balance,
  };
  renderSummary();
  renderBudget();
  drawCategoryChart(analytics.categories || []);
  drawTrendChart(analytics.trend || []);
}

function renderList() {
  if (records.length === 0) {
    els.recordList.innerHTML = '';
    els.emptyTip.classList.remove('hidden');
    return;
  }

  els.emptyTip.classList.add('hidden');
  els.recordList.innerHTML = records
    .map(
      (r) => `
    <tr>
      <td>${formatDate(r.date)}</td>
      <td><span class="tag ${r.type}">${TYPE_LABELS[r.type]}</span></td>
      <td>${escapeHtml(r.category)}</td>
      <td class="amount-${r.type}">${r.type === 'income' ? '+' : '-'}${formatMoney(r.amount)}</td>
      <td>${escapeHtml(r.note || '—')}</td>
      <td>
        <div class="row-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-action="edit" data-id="${r.id}">编辑</button>
          <button type="button" class="btn btn-danger btn-sm" data-action="delete" data-id="${r.id}">删除</button>
        </div>
      </td>
    </tr>
  `
    )
    .join('');
}

function render() {
  renderAnalytics();
  renderList();
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function loadSummary() {
  summary = await api(`/summary?month=${els.statsMonth.value}`);
}

async function loadRecords() {
  records = await api(`/records${buildQuery()}`);
}

async function loadAnalytics() {
  analytics = await api(`/analytics?month=${els.statsMonth.value}`);
}

async function loadCurrentUser() {
  currentUser = await api('/me');

  els.guestActions.classList.toggle('d-none', currentUser.loggedIn);
  els.userActions.classList.toggle('d-none', !currentUser.loggedIn);
  els.guestPanel.classList.toggle('d-none', currentUser.loggedIn);
  els.dashboard.classList.toggle('d-none', !currentUser.loggedIn);

  if (currentUser.loggedIn) {
    els.currentUser.textContent = `欢迎，${currentUser.username}`;
  }

  setRecordControlsEnabled(currentUser.loggedIn);
}

async function refreshAll() {
  await Promise.all([loadAnalytics(), loadRecords()]);
  render();
}

function openDeleteModal(id) {
  deletingId = id;
  els.deleteModal.classList.remove('hidden');
}

function closeDeleteModal() {
  deletingId = null;
  els.deleteModal.classList.add('hidden');
}

els.type.addEventListener('change', () => {
  updateCategoryOptions(els.type.value);
});

els.form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const data = {
    date: els.date.value,
    type: els.type.value,
    category: els.category.value,
    amount: parseFloat(els.amount.value),
    note: els.note.value.trim(),
  };

  setLoading(true);
  try {
    if (editingId) {
      await api(`/records/${editingId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
      showToast('记录已更新', 'success');
    } else {
      await api('/records', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      showToast('记录已添加', 'success');
    }

    resetForm();
    await refreshAll();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.cancelBtn.addEventListener('click', resetForm);

els.recordList.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;

  const id = btn.dataset.id;
  const record = records.find((r) => r.id === id);
  if (!record) return;

  if (btn.dataset.action === 'edit') {
    startEdit(record);
  } else if (btn.dataset.action === 'delete') {
    openDeleteModal(id);
  }
});

els.filterType.addEventListener('change', async () => {
  setLoading(true);
  try {
    await loadRecords();
    renderList();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.filterMonth.addEventListener('change', async () => {
  setLoading(true);
  try {
    await loadRecords();
    renderList();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.statsMonth.addEventListener('change', async () => {
  setLoading(true);
  try {
    await loadAnalytics();
    renderAnalytics();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.saveBudgetBtn.addEventListener('click', async () => {
  setLoading(true);
  try {
    await api('/budget', {
      method: 'POST',
      body: JSON.stringify({
        month: els.statsMonth.value,
        amount: parseFloat(els.budgetAmount.value || '0'),
      }),
    });
    showToast('预算已保存', 'success');
    await loadAnalytics();
    renderAnalytics();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.clearFilter.addEventListener('click', async () => {
  els.filterType.value = 'all';
  els.filterMonth.value = '';
  setLoading(true);
  try {
    await loadRecords();
    renderList();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

els.cancelDelete.addEventListener('click', closeDeleteModal);
els.deleteModal.querySelector('.modal-backdrop').addEventListener('click', closeDeleteModal);

els.confirmDelete.addEventListener('click', async () => {
  if (!deletingId) return;

  setLoading(true);
  try {
    await api(`/records/${deletingId}`, { method: 'DELETE' });
    if (editingId === deletingId) resetForm();
    closeDeleteModal();
    showToast('记录已删除', 'success');
    await refreshAll();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

async function init() {
  els.statsMonth.value = currentMonthStr();
  els.filterMonth.value = currentMonthStr();
  resetForm();
  setLoading(true);
  try {
    await loadCurrentUser();
    if (currentUser.loggedIn) {
      await refreshAll();
    } else {
      summary = { totalIncome: 0, totalExpense: 0, balance: 0 };
      records = [];
      render();
    }
  } catch (err) {
    showToast('无法连接服务器，请确认后端已启动');
  } finally {
    setLoading(false);
  }
}

init();
