const statsEls = {
  month: document.getElementById('statsMonth'),
  totalIncome: document.getElementById('totalIncome'),
  totalExpense: document.getElementById('totalExpense'),
  balance: document.getElementById('balance'),
};

let categoryChart = null;
let trendChart = null;

function renderCategoryChart(categories) {
  const ctx = document.getElementById('categoryChart');
  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: categories.map((item) => item.category),
      datasets: [{
        data: categories.map((item) => item.amount),
        backgroundColor: ['#0d6efd', '#dc3545', '#198754', '#ffc107', '#6f42c1', '#20c997'],
      }],
    },
    options: {
      plugins: {
        legend: { position: 'bottom' },
      },
    },
  });
}

function renderTrendChart(trend) {
  const ctx = document.getElementById('trendChart');
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trend.map((item) => item.month),
      datasets: [
        {
          label: '收入',
          data: trend.map((item) => item.income),
          borderColor: '#198754',
          backgroundColor: 'rgba(25, 135, 84, 0.12)',
          tension: 0.3,
        },
        {
          label: '支出',
          data: trend.map((item) => item.expense),
          borderColor: '#dc3545',
          backgroundColor: 'rgba(220, 53, 69, 0.12)',
          tension: 0.3,
        },
      ],
    },
    options: {
      plugins: {
        legend: { position: 'bottom' },
      },
      scales: {
        y: { beginAtZero: true },
      },
    },
  });
}

async function loadStatistics() {
  setLoading(true);
  try {
    const data = await api(`/analytics?month=${statsEls.month.value}`);
    statsEls.totalIncome.textContent = formatMoney(data.totalIncome);
    statsEls.totalExpense.textContent = formatMoney(data.totalExpense);
    statsEls.balance.textContent = formatMoney(data.balance);
    renderCategoryChart(data.categories);
    renderTrendChart(data.trend);
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

statsEls.month.value = currentMonthStr();
statsEls.month.addEventListener('change', loadStatistics);
loadStatistics();
