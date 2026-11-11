// Export the full portal date range for each named city using its public Downloads tab.
const { chromium } = require('playwright')
const fs = require('node:fs/promises')
const path = require('node:path')
const { createHash } = require('node:crypto')

async function capture(page, directory, city) {
  const selection = await page.evaluate(city => {
    const select = id => document.getElementById(id).selectize
    const cityValue = Object.values(select('city_filter').options).find(item => item.label === city || item.text === city || item.value === city)
    if (!cityValue || city === 'All') throw Error('Unknown portal city: ' + city)
    const dates = ['md_start', 'md_end'].map(id => document.querySelector('#' + id + ' input').value)
    const first = Number(dates[0].slice(-4)), last = Number(dates[1].slice(-4))
    if (!first || !last || first > last) throw Error('Invalid portal date controls')
    const years = Array.from({length: last - first + 1}, (_, i) => String(first + i))
    const yearControl = select('years')
    for (const year of years) yearControl.addOption({value: year, label: year, text: year})
    yearControl.setValue(years)
    select('city_filter').setValue([cityValue.value])
    return { dates, years }
  }, city)
  await page.locator('#apply_filters').click()
  await page.waitForFunction(({city, years}) => {
    const text = document.body.innerText.split('Applied Filters:').pop()
    return text?.includes('City: ' + city + '\n') && text.includes('for ' + years.join(', '))
  }, { city, years: selection.years }, { timeout: 120000 })
  const text = await page.locator('body').innerText()
  const count = text.match(/Total Crashes:\s*([\d,]+)/)
  if (!count) throw Error('Missing dashboard count')
  const file = encodeURIComponent(city) + '.xlsx'
  const target = path.join(directory, file)
  const downloading = page.waitForEvent('download', {timeout: 600000})
  await page.locator('#downloadDataFile').click()
  const download = await downloading
  await download.saveAs(target + '.part')
  const sha256 = createHash('sha256').update(await fs.readFile(target + '.part')).digest('hex')
  await fs.rename(target + '.part', target)
  await fs.writeFile(target + '.json', JSON.stringify({
    city, file, ...selection, expectedCrashes: Number(count[1].replaceAll(',', '')),
    sha256, retrievedAt: new Date().toISOString()
  }, null, 2) + '\n', {flag: 'wx'})
  console.log(city, count[1], 'source crashes')
}

async function main() {
  const [directory, ...cities] = process.argv.slice(2)
  if (!cities.length || new Set(cities).size !== cities.length)
    throw Error('Usage: node scripts/capture_city_crash_portal.cjs NEW_PRIVATE_DIRECTORY CITY [CITY ...]')
  process.umask(0o077)
  const parent = await fs.realpath(path.dirname(path.resolve(directory)))
  const privateRoot = await fs.realpath(path.resolve(__dirname, '../private'))
  if (parent !== privateRoot && !parent.startsWith(privateRoot + path.sep)) throw Error('Use private/ for workbook capture')
  await fs.mkdir(directory)
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_EXECUTABLE})
  try {
    const page = await browser.newPage()
    await page.goto('https://utaps.shinyapps.io/DataPortalAWS/')
    await page.getByText('Downloads', {exact: true}).click({timeout: 120000})
    await page.getByText(/Total Crashes:/).first().waitFor({timeout: 120000})
    for (const city of cities) await capture(page, directory, city)
  } finally {
    await browser.close()
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
