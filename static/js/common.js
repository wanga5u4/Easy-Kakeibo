const API_BASE = '/api';
const T = window.I18N || {};

function disableSavedDarkTheme() {
  try {
    ['theme', 'color-theme', 'easy-kakeibo-theme'].forEach((key) => {
      if (localStorage.getItem(key) === 'dark') {
        localStorage.removeItem(key);
      }
    });
  } catch (error) {
    // Storage can be unavailable in private or restricted browser contexts.
  }
  document.documentElement.dataset.theme = 'light';
}

disableSavedDarkTheme();

const CATEGORIES = {
  income: T.categories?.income || [],
  expense: T.categories?.expense || [],
};

const TYPE_LABELS = T.typeLabels || { income: 'income', expense: 'expense' };

async function api(path, options = {}) {
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
  const method = (options.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers['X-CSRFToken'] = csrfToken;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || T.requestFailed || 'Request failed. Please try again later.');
  }
  return data;
}

function formatMoney(value, currencyCode) {
  if (value && typeof value === 'object' && value.formatted) return value.formatted;
  const code = currencyCode || T.currentBaseCurrency || 'JPY';
  const currency = T.currencies?.[code] || { symbol: '¥', decimal_places: 0 };
  const amount = Number(value || 0);
  return `${currency.symbol}${amount.toLocaleString(undefined, {
    minimumFractionDigits: currency.decimal_places,
    maximumFractionDigits: currency.decimal_places,
  })} ${code}`;
}

function formatRecordAmount(record) {
  const original = record.formatted_original_amount
    || formatMoney(record.original_amount ?? record.amount, record.currency_code);
  if (!record.base_currency_code || record.currency_code === record.base_currency_code) {
    return escapeHtml(original);
  }
  const converted = record.formatted_converted_amount
    || formatMoney(record.converted_amount, record.base_currency_code);
  const approximate = (T.approximately || 'About %(amount)s').replace('%(amount)s', converted);
  return `${escapeHtml(original)}<div class="text-muted small">${escapeHtml(approximate)}</div>`;
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
  return (T.dateFormat || '%(year)s-%(month)s-%(day)s')
    .replace('%(year)s', year)
    .replace('%(month)s', month)
    .replace('%(day)s', day);
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
  if (amountEl) amountEl.value = budget.amount ? String(budget.amount) : '';
  const budgetCurrency = budget.currency_code || T.currentBaseCurrency || 'JPY';
  const currencyLabel = document.getElementById('budgetCurrencyLabel');
  const currencyHint = document.getElementById('budgetCurrencyHint');
  if (currencyLabel) currencyLabel.textContent = budgetCurrency;
  if (currencyHint) currencyHint.textContent = `${T.budgetCurrency || '预算币种'}：${budgetCurrency}`;
  usedEl.textContent = (T.used || 'Used %(amount)s')
    .replace('%(amount)s', budget.formatted_used || formatMoney(budget.used, budgetCurrency));
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

  statusEl.textContent = (T.remaining || '%(status)s, remaining %(amount)s')
    .replace('%(status)s', budget.status)
    .replace('%(amount)s', budget.formatted_remaining || formatMoney(budget.remaining, budgetCurrency));
}
