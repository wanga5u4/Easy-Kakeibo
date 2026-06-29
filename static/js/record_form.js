const formEl = document.getElementById('recordForm');
const recordId = formEl.dataset.recordId;
const formEls = {
  date: document.getElementById('date'),
  type: document.getElementById('type'),
  category: document.getElementById('category'),
  amount: document.getElementById('amount'),
  note: document.getElementById('note'),
  submit: document.getElementById('submitBtn'),
};

async function loadRecordForEdit() {
  if (!recordId) {
    formEls.date.value = todayStr();
    updateCategoryOptions(formEls.type, formEls.category);
    return;
  }

  setLoading(true);
  try {
    const record = await api(`/records/${recordId}`);
    formEls.date.value = record.date;
    formEls.type.value = record.type;
    updateCategoryOptions(formEls.type, formEls.category);
    formEls.category.value = record.category;
    formEls.amount.value = record.amount;
    formEls.note.value = record.note || '';
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

formEls.type.addEventListener('change', () => updateCategoryOptions(formEls.type, formEls.category));
formEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = {
    date: formEls.date.value,
    type: formEls.type.value,
    category: formEls.category.value,
    amount: parseFloat(formEls.amount.value),
    note: formEls.note.value.trim(),
  };

  setLoading(true);
  try {
    if (recordId) {
      await api(`/records/${recordId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('记录已更新', 'success');
    } else {
      await api('/records', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('记录已添加', 'success');
    }
    window.location.href = '/records';
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

loadRecordForEdit();
