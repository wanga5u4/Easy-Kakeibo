(function () {
  const dataEl = document.getElementById('landingDemoData');
  const categoryCanvas = document.getElementById('landingCategoryChart');
  const trendCanvas = document.getElementById('landingTrendChart');
  if (!dataEl || !categoryCanvas || !trendCanvas || typeof Chart === 'undefined') return;

  const demoData = JSON.parse(dataEl.textContent);
  const sharedOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
          padding: 10,
        },
      },
    },
  };

  new Chart(categoryCanvas, {
    type: 'doughnut',
    data: {
      labels: demoData.categoryLabels,
      datasets: [{
        data: demoData.categoryValues,
        backgroundColor: ['#0d6efd', '#14b8a6', '#60a5fa', '#f97316', '#94a3b8'],
        borderColor: '#ffffff',
        borderWidth: 2,
        hoverOffset: 4,
      }],
    },
    options: {
      ...sharedOptions,
      cutout: '62%',
    },
  });

  new Chart(trendCanvas, {
    type: 'line',
    data: {
      labels: demoData.monthLabels,
      datasets: [
        {
          label: demoData.incomeLabel,
          data: demoData.incomeValues,
          borderColor: '#14b8a6',
          backgroundColor: 'rgba(20, 184, 166, 0.12)',
          pointBackgroundColor: '#14b8a6',
          pointRadius: 2,
          borderWidth: 2,
          tension: 0.35,
        },
        {
          label: demoData.expenseLabel,
          data: demoData.expenseValues,
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.12)',
          pointBackgroundColor: '#ef4444',
          pointRadius: 2,
          borderWidth: 2,
          tension: 0.35,
        },
      ],
    },
    options: {
      ...sharedOptions,
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0 },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(148, 163, 184, 0.18)' },
          ticks: {
            maxTicksLimit: 4,
            callback(value) {
              return `${Math.round(Number(value) / 1000)}k`;
            },
          },
        },
      },
    },
  });
}());
