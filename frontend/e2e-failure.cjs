const { chromium } = require('playwright')

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const matcher = (url) => url.pathname === '/api/inverter/efficiency-overview'
  const handler = (route) => route.abort('failed')
  await page.route(matcher, handler)
  await page.goto('http://127.0.0.1:5173/inverter')
  await page.waitForTimeout(1500)
  const failure = await page.evaluate(() => ({
    errorShown: !!document.querySelector('.eff-error'),
    curveCount: document.querySelectorAll('.eff-chart path').length,
    legendCount: document.querySelectorAll('.legend-item').length,
    tableRows: document.querySelectorAll('.data-table tbody tr').length,
  }))
  console.log('接口失败时:', JSON.stringify(failure))
  await page.unroute(matcher, handler)
  await page.getByRole('button', { name: '重试' }).click()
  await page.waitForTimeout(1500)
  const recovered = await page.evaluate(() => ({
    legend: document.querySelectorAll('.legend-item').length,
    missing: document.querySelectorAll('.eff-missing li').length,
  }))
  console.log('重试恢复:', JSON.stringify(recovered))

  // 选中 INVE-2005，再筛 SG250HX（该机不在结果里）→ 高亮应取消
  await page.locator('.legend-item', { hasText: 'INVE-2005' }).click()
  await page.waitForTimeout(500)
  await page.locator('.filter-bar input').nth(1).fill('SG250HX')
  await page.locator('.filter-bar button[type="submit"]').click()
  await page.waitForTimeout(1200)
  const cleared = await page.evaluate(() => ({
    selectedRows: document.querySelectorAll('.row-selected').length,
    selectedLegend: document.querySelectorAll('.legend-item.is-selected').length,
  }))
  console.log('选中行被筛掉后:', JSON.stringify(cleared))
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
