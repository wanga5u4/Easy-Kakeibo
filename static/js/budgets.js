const budgetEls = {
  month: document.getElementById('budgetMonth'),
  amount: document.getElementById('budgetAmount'),
  save: document.getElementById('saveBudgetBtn'),
  prev: document.getElementById('prevBudgetMonth'),
  next: document.getElementById('nextBudgetMonth'),
};

function shiftBudgetMonth(offset) {
  const [year, month] = budgetEls.month.value.split('-').map(Number);
  if (!year || !month) return currentMonthStr();
  const shifted = new Date(year, month - 1 + offset, 1);
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, '0')}`;
}

async function loadBudget() {
  setLoading(true);
  try {
    const data = await api(`/analytics?month=${budgetEls.month.value}`);
    applyBudgetView(data.budget);
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

budgetEls.save.addEventListener('click', async () => {
  setLoading(true);
  try {
    await api('/budget', {
      method: 'POST',
      body: JSON.stringify({
        month: budgetEls.month.value,
        amount: budgetEls.amount.value,
      }),
    });
    showToast(T.budgetSaved || 'Budget saved', 'success');
    await loadBudget();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

budgetEls.month.value = currentMonthStr();
budgetEls.month.addEventListener('change', loadBudget);
budgetEls.prev.addEventListener('click', () => {
  budgetEls.month.value = shiftBudgetMonth(-1);
  loadBudget();
});
budgetEls.next.addEventListener('click', () => {
  budgetEls.month.value = shiftBudgetMonth(1);
  loadBudget();
});
loadBudget();
