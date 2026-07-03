const budgetEls = {
  month: document.getElementById('budgetMonth'),
  amount: document.getElementById('budgetAmount'),
  save: document.getElementById('saveBudgetBtn'),
};

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
loadBudget();
