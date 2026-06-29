const dashboardEls = {
  month: document.getElementById('dashboardMonth'),
  totalIncome: document.getElementById('totalIncome'),
  totalExpense: document.getElementById('totalExpense'),
  balance: document.getElementById('balance'),
};

async function loadDashboard() {
  setLoading(true);
  try {
    const data = await api(`/analytics?month=${dashboardEls.month.value}`);
    dashboardEls.totalIncome.textContent = formatMoney(data.totalIncome);
    dashboardEls.totalExpense.textContent = formatMoney(data.totalExpense);
    dashboardEls.balance.textContent = formatMoney(data.balance);
    applyBudgetView(data.budget);
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

dashboardEls.month.value = currentMonthStr();
dashboardEls.month.addEventListener('change', loadDashboard);
loadDashboard();
