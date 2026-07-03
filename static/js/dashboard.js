const dashboardEls = {
  month: document.getElementById('dashboardMonth'),
  totalIncome: document.getElementById('totalIncome'),
  totalExpense: document.getElementById('totalExpense'),
  balance: document.getElementById('balance'),
  currencyNotice: document.getElementById('currencyNotice'),
};

async function loadDashboard() {
  setLoading(true);
  try {
    const data = await api(`/analytics?month=${dashboardEls.month.value}`);
    dashboardEls.totalIncome.textContent = data.formattedTotalIncome || formatMoney(data.totalIncome, data.currencyCode);
    dashboardEls.totalExpense.textContent = data.formattedTotalExpense || formatMoney(data.totalExpense, data.currencyCode);
    dashboardEls.balance.textContent = data.formattedBalance || formatMoney(data.balance, data.currencyCode);
    applyBudgetView(data.budget);
    document.querySelectorAll('.statCurrency').forEach((el) => { el.textContent = data.currencyCode || ''; });
    if (dashboardEls.currencyNotice) {
      const notices = [data.estimatedRateNotice, data.missingRateNotice].filter(Boolean);
      dashboardEls.currencyNotice.textContent = notices.join(' ');
      dashboardEls.currencyNotice.classList.toggle('hidden', notices.length === 0);
    }
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

dashboardEls.month.value = currentMonthStr();
dashboardEls.month.addEventListener('change', loadDashboard);
loadDashboard();
