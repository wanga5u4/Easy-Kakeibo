const formEl = document.getElementById('recordForm');
const recordId = formEl.dataset.recordId;
let recordBaseCurrency = formEl.dataset.baseCurrency || T.currentBaseCurrency || 'JPY';

const formEls = {
  date: document.getElementById('date'),
  type: document.getElementById('type'),
  category: document.getElementById('category'),
  amount: document.getElementById('amount'),
  currencyCode: document.getElementById('currencyCode'),
  exchangeRateGroup: document.getElementById('exchangeRateGroup'),
  exchangeRate: document.getElementById('exchangeRate'),
  exchangeRateHelp: document.getElementById('exchangeRateHelp'),
  ratePrefix: document.getElementById('ratePrefix'),
  rateSuffix: document.getElementById('rateSuffix'),
  conversionPreview: document.getElementById('conversionPreview'),
  note: document.getElementById('note'),
  submit: document.getElementById('submitBtn'),
};

function decimalPlacesFor(code) {
  return T.currencies?.[code]?.decimal_places ?? 2;
}

function plainDecimalIsValid(value, maxPlaces) {
  const text = String(value || '').trim();
  if (!/^(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(text)) return false;
  const parts = text.split('.');
  return !parts[1] || parts[1].length <= maxPlaces;
}

function updateAmountInputRules() {
  const code = formEls.currencyCode.value;
  const places = decimalPlacesFor(code);
  formEls.amount.placeholder = places === 0 ? '1000' : '100.00';
  formEls.amount.inputMode = places === 0 ? 'numeric' : 'decimal';
}

function rateHelpText(code, source) {
  let text = (T.rateHelp || '请输入 1 %(source)s 相当于多少 %(target)s。')
    .replace('%(source)s', T.currencyNames?.[code] || code)
    .replace('%(target)s', T.currencyNames?.[recordBaseCurrency] || recordBaseCurrency);
  if (source === 'direct') {
    text += ` ${T.autoFilledRate || '已自动填入你上次使用的汇率，可随时修改。'}`;
  } else if (source === 'inverse') {
    text += ` ${T.inverseRateSuggestion || '已根据反方向汇率推算，可随时修改。'}`;
  }
  return text;
}

async function loadLatestRateForDirection(code) {
  try {
    const data = await api(`/exchange-rate/latest?from=${encodeURIComponent(code)}&to=${encodeURIComponent(recordBaseCurrency)}`);
    if (data.found && data.rate) {
      formEls.exchangeRate.value = data.rate;
      formEls.exchangeRateHelp.textContent = rateHelpText(code, data.source);
    } else {
      formEls.exchangeRate.value = '';
      formEls.exchangeRateHelp.textContent = rateHelpText(code);
    }
  } catch (err) {
    formEls.exchangeRate.value = '';
    formEls.exchangeRateHelp.textContent = rateHelpText(code);
  }
  updateConversionPreview();
}

async function updateExchangeRateVisibility(options = {}) {
  const code = formEls.currencyCode.value;
  const sameCurrency = code === recordBaseCurrency;
  formEls.exchangeRateGroup.classList.toggle('d-none', sameCurrency);
  formEls.exchangeRate.disabled = sameCurrency;
  formEls.ratePrefix.textContent = `1 ${code} =`;
  formEls.rateSuffix.textContent = recordBaseCurrency;
  if (sameCurrency) {
    formEls.exchangeRate.value = '1';
    formEls.exchangeRateHelp.textContent = T.noConversionNeeded || '无需换算';
  } else if (!options.preserveHistoricalRate) {
    await loadLatestRateForDirection(code);
    return;
  } else {
    formEls.exchangeRateHelp.textContent = rateHelpText(code);
  }
  updateConversionPreview();
}

function updateConversionPreview() {
  const code = formEls.currencyCode.value;
  const amountText = formEls.amount.value;
  const rateText = formEls.exchangeRate.value;
  const amountPlaces = decimalPlacesFor(code);
  if (!plainDecimalIsValid(amountText, amountPlaces)) {
    formEls.conversionPreview.textContent = '';
    return;
  }
  const amount = Number(amountText);
  const original = formatMoney(amount, code);
  if (code === recordBaseCurrency) {
    formEls.conversionPreview.textContent = `${original} · ${T.noConversionNeeded || '无需换算'}`;
    return;
  }
  if (!plainDecimalIsValid(rateText, 12) || Number(rateText) <= 0) {
    formEls.conversionPreview.textContent = (T.rateRequired || '请输入换算汇率');
    return;
  }
  const converted = amount * Number(rateText);
  const convertedText = formatMoney(converted, recordBaseCurrency);
  formEls.conversionPreview.textContent = (T.conversionPreview || '%(original)s ≈ %(converted)s')
    .replace('%(original)s', original)
    .replace('%(converted)s', convertedText);
}

async function loadRecordForEdit() {
  if (!recordId) {
    formEls.date.value = todayStr();
    updateCategoryOptions(formEls.type, formEls.category);
    updateAmountInputRules();
    updateExchangeRateVisibility();
    return;
  }

  setLoading(true);
  try {
    const record = await api(`/records/${recordId}`);
    recordBaseCurrency = record.base_currency_code || recordBaseCurrency;
    formEls.date.value = record.date;
    formEls.type.value = record.type;
    updateCategoryOptions(formEls.type, formEls.category);
    formEls.category.value = record.category;
    formEls.amount.value = String(record.original_amount ?? record.amount);
    formEls.currencyCode.value = record.currency_code || recordBaseCurrency;
    formEls.exchangeRate.value = record.exchange_rate || '1';
    formEls.note.value = record.note || '';
    updateAmountInputRules();
    updateExchangeRateVisibility({ preserveHistoricalRate: true });
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

formEls.type.addEventListener('change', () => updateCategoryOptions(formEls.type, formEls.category));
formEls.currencyCode.addEventListener('change', () => {
  updateAmountInputRules();
  updateExchangeRateVisibility();
});
formEls.amount.addEventListener('input', updateConversionPreview);
formEls.exchangeRate.addEventListener('input', updateConversionPreview);

formEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = {
    date: formEls.date.value,
    type: formEls.type.value,
    category: formEls.category.value,
    amount: formEls.amount.value.trim(),
    currency_code: formEls.currencyCode.value,
    exchange_rate: formEls.exchangeRate.value.trim(),
    note: formEls.note.value.trim(),
  };

  setLoading(true);
  try {
    if (recordId) {
      await api(`/records/${recordId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast(T.recordUpdated || 'Record updated', 'success');
    } else {
      await api('/records', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast(T.recordAdded || 'Record added', 'success');
    }
    window.location.href = '/records';
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
});

loadRecordForEdit();
