const recordsEls = {
  type: document.getElementById('filterType'),
  month: document.getElementById('filterMonth'),
  clear: document.getElementById('clearFilter'),
  list: document.getElementById('recordList'),
  empty: document.getElementById('emptyTip'),
  modal: document.getElementById('deleteModal'),
  cancelDelete: document.getElementById('cancelDelete'),
  confirmDelete: document.getElementById('confirmDelete'),
};

let records = [];
let deletingId = null;

function buildRecordsQuery() {
  const params = new URLSearchParams();
  if (recordsEls.type.value !== 'all') params.set('type', recordsEls.type.value);
  if (recordsEls.month.value) params.set('month', recordsEls.month.value);
  const query = params.toString();
  return query ? `?${query}` : '';
}

function renderRecords() {
  if (records.length === 0) {
    recordsEls.list.innerHTML = '';
    recordsEls.empty.classList.remove('hidden');
    return;
  }

  recordsEls.empty.classList.add('hidden');
  recordsEls.list.innerHTML = records.map((record) => `
    <tr>
      <td>${formatDate(record.date)}</td>
      <td><span class="tag ${record.type}">${TYPE_LABELS[record.type]}</span></td>
      <td>${escapeHtml(record.category)}</td>
      <td class="amount-${record.type}">${record.type === 'income' ? '+' : '-'}${formatMoney(record.amount)}</td>
      <td>${escapeHtml(record.note || '—')}</td>
      <td>
        <div class="row-actions">
          <a class="btn btn-outline-secondary btn-sm" href="/records/${record.id}/edit">编辑</a>
          <button type="button" class="btn btn-danger btn-sm" data-action="delete" data-id="${record.id}">删除</button>
        </div>
      </td>
    </tr>
  `).join('');
}

async function loadRecords() {
  setLoading(true);
  try {
    records = await api(`/records${buildRecordsQuery()}`);
    renderRecords();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

function closeDeleteModal() {
  deletingId = null;
  recordsEls.modal.classList.add('hidden');
}

recordsEls.type.addEventListener('change', loadRecords);
recordsEls.month.addEventListener('change', loadRecords);
recordsEls.clear.addEventListener('click', () => {
  recordsEls.type.value = 'all';
  recordsEls.month.value = '';
  loadRecords();
});
recordsEls.list.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action="delete"]');
  if (!button) return;
  deletingId = button.dataset.id;
  recordsEls.modal.classList.remove('hidden');
});
recordsEls.cancelDelete.addEventListener('click', closeDeleteModal);
recordsEls.modal.querySelector('.modal-backdrop').addEventListener('click', closeDeleteModal);
recordsEls.confirmDelete.addEventListener('click', async () => {
  if (!deletingId) return;
  setLoading(true);
  try {
    await api(`/records/${deletingId}`, { method: 'DELETE' });
    closeDeleteModal();
    showToast('记录已删除', 'success');
    await loadRecords();
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

recordsEls.month.value = currentMonthStr();
loadRecords();
