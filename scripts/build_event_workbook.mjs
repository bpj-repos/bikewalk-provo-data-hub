// Run a copy beside the bundled artifact-tool node_modules, keeping runtime packages outside the repo.
import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node build_event_workbook.mjs workbook-data.json NEW_OUTPUT_DIRECTORY');
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const wb = Workbook.create();
for (const tab of data.tabs) {
  const sheet = wb.worksheets.add(tab.name);
  sheet.showGridLines = false;
  const rows = tab.rows.map(row => row.map((value, index) => {
    if (!value || !tab.dateColumns.includes(index)) return value === '' ? null : value;
    // Excel stores local wall-clock values. The sheet labels the Mountain Time convention.
    return Date.parse(value.slice(0, 19) + (value.length > 10 ? 'Z' : 'T00:00:00Z')) / 86400000 + 25569;
  }));
  const width = tab.headers.length;
  sheet.getRangeByIndexes(0, 0, 1, width).values = [tab.headers];
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, width).values = rows;
  const used = sheet.getRangeByIndexes(0, 0, rows.length + 1, width);
  used.format.font.name = 'Arial';
  used.format.font.size = 10;
  used.format.verticalAlignment = 'center';
  used.format.rowHeight = 28;
  used.format.columnWidth = 22;
  const header = sheet.getRangeByIndexes(0, 0, 1, width);
  header.format.fill = '#17365D';
  header.format.font.color = '#FFFFFF';
  header.format.font.bold = true;
  header.format.wrapText = true;
  header.format.rowHeight = 42;
  header.format.horizontalAlignment = 'center';
  if (rows.length) {
    const body = sheet.getRangeByIndexes(1, 0, rows.length, width);
    body.format.wrapText = true;
    body.format.autofitRows();
  }
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(tab.name === 'Events' ? 2 : 1);
  sheet.tables.add(`A1:${String.fromCharCode(64 + width)}${rows.length + 1}`, true, tab.name + 'Table');
  tab.widths.forEach((size, index) => { sheet.getRangeByIndexes(0, index, rows.length + 1, 1).format.columnWidth = size; });
  for (const index of tab.dateColumns) {
    if (rows.length) sheet.getRangeByIndexes(1, index, rows.length, 1).setNumberFormat(index === 0 && tab.name === 'Events' ? 'mm/dd/yy' : 'mm/dd/yy h:mm AM/PM');
  }
}
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Events!A1:H5',include:'values',tableMaxRows:5,tableMaxCols:8,maxChars:1800})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
await fs.mkdir(output, {recursive:true});
for (const tab of data.tabs) {
  const blob = await wb.render({sheetName:tab.name,range:tab.name === 'Events' ? 'A1:H8' : 'A1:F8',scale:1.5});
  await fs.writeFile(`${output}/${tab.name.toLowerCase()}-preview.png`,new Uint8Array(await blob.arrayBuffer()));
}
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(`${output}/byu-event-register.xlsx`);
console.log(`${output}/byu-event-register.xlsx`);
