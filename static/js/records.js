const recordsEls = {
  type: document.getElementById('filterType'),
  month: document.getElementById('filterMonth'),
  perPage: document.getElementById('perPage'),
  clear: document.getElementById('clearFilter'),
  list: document.getElementById('recordList'),
  empty: document.getElementById('emptyTip'),
  paginationBar: document.getElementById('paginationBar'),
  paginationInfo: document.getElementById('paginationInfo'),
  prevPage: document.getElementById('prevPage'),
  nextPage: document.getElementById('nextPage'),
  modal: document.getElementById('deleteModal'),
  cancelDelete: document.getElementById('cancelDelete'),
  confirmDelete: document.getElementById('confirmDelete'),
};

let records = [];
let deletingId = null;
let pagination = { page: 1, per_page: 10, total: 0, total_pages: 0 };

function buildRecordsQuery() {
  const params = new URLSearchParams();
  params.set('page', pagination.page);
  params.set('per_page', recordsEls.perPage.value);
  if (recordsEls.type.value !== 'all') params.set('type', recordsEls.type.value);
  if (recordsEls.month.value) params.set('month', recordsEls.month.value);
  const query = params.toString();
  return query ? `?${query}` : '';
}

function renderRecords() {
  if (records.length === 0) {
    recordsEls.list.innerHTML = '';
    recordsEls.empty.classList.remove('hidden');
    recordsEls.paginationBar.classList.add('hidden');
    return;
  }

  recordsEls.empty.classList.add('hidden');
  recordsEls.paginationBar.classList.remove('hidden');
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

  recordsEls.paginationInfo.textContent = `第 ${pagination.page} / ${pagination.total_pages} 页，共 ${pagination.total} 条`;
  recordsEls.prevPage.disabled = !pagination.has_prev;
  recordsEls.nextPage.disabled = !pagination.has_next;
}

async function loadRecords() {
  setLoading(true);
  try {
    const data = await api(`/records${buildRecordsQuery()}`);
    records = data.items || [];
    pagination = data.pagination || pagination;
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

function reloadFromFirstPage() {
  pagination.page = 1;
  loadRecords();
}

recordsEls.type.addEventListener('change', reloadFromFirstPage);
recordsEls.month.addEventListener('change', reloadFromFirstPage);
recordsEls.perPage.addEventListener('change', reloadFromFirstPage);
recordsEls.clear.addEventListener('click', () => {
  recordsEls.type.value = 'all';
  recordsEls.month.value = '';
  reloadFromFirstPage();
});
recordsEls.prevPage.addEventListener('click', () => {
  if (!pagination.has_prev) return;
  pagination.page -= 1;
  loadRecords();
});
recordsEls.nextPage.addEventListener('click', () => {
  if (!pagination.has_next) return;
  pagination.page += 1;
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
    if (records.length === 0 && pagination.page > 1) {
      pagination.page -= 1;
      await loadRecords();
    }
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

recordsEls.month.value = currentMonthStr();
loadRecords();
