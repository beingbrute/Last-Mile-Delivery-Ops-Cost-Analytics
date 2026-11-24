/**
 * Kestrel Rentals (fictional): weekly last-mile ops MIS.
 *
 * Reads the CSV exports from src/export_reporting.py that sit in a Google Drive folder,
 * and rebuilds three sheets in this spreadsheet:
 *   Weekly MIS   - latest full week by city with week-on-week change and flags, then every week
 *   Escalations  - vendor check failures that are still open
 *   Refresh log  - when the MIS was rebuilt and how many rows it read
 *
 * Setup (once): set DRIVE_FOLDER below, run refreshMIS, then run createWeeklyTrigger.
 * The trigger rebuilds the MIS every Monday between 8 and 9 AM (script time zone).
 */

const DRIVE_FOLDER = 'kestrel-reporting';   // Drive folder holding daily_ops.csv and escalation_log.csv
const ON_TIME_TARGET = 0.90;                // flag a city-week below this on-time %
const FAILURE_LIMIT = 0.06;                 // flag a city-week above this failure %
const CITY_NAMES = { NOI: 'Noida', GGN: 'Gurugram', BLR: 'Bengaluru' };
const CITY_ORDER = ['NOI', 'GGN', 'BLR'];

const RED = '#F8D7DA', GREEN = '#D4EDDA', HEADER = '#1F4E79', SUB = '#E8EEF5';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('MIS')
    .addItem('Refresh now', 'refreshMIS')
    .addToUi();
}

function refreshMIS() {
  const folder = getFolder_();
  const daily = readCsv_(folder, 'daily_ops.csv');
  const escalations = readCsv_(folder, 'escalation_log.csv');

  const weeks = weeklyByCity_(daily);
  writeWeekly_(weeks);
  writeEscalations_(escalations);
  logRefresh_(daily.length, escalations.length, weeks.weekStarts.length);
}

/** Runs refreshMIS every Monday at 8 AM. Removes any older copy of the trigger first. */
function createWeeklyTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'refreshMIS')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('refreshMIS').timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
}

// ---------- reading ----------

function getFolder_() {
  const it = DriveApp.getFoldersByName(DRIVE_FOLDER);
  if (!it.hasNext()) throw new Error('Drive folder not found: ' + DRIVE_FOLDER);
  return it.next();
}

/** Returns the CSV as an array of objects keyed by the header row. */
function readCsv_(folder, name) {
  const files = folder.getFilesByName(name);
  if (!files.hasNext()) throw new Error('File not found in ' + DRIVE_FOLDER + ': ' + name);
  const rows = Utilities.parseCsv(files.next().getBlob().getDataAsString('UTF-8'));
  const head = rows.shift();
  return rows.filter(r => r.length === head.length)
             .map(r => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

// ---------- weekly aggregation ----------

/** Monday of the week, as yyyy-MM-dd. Dates are built from their parts, so time zones cannot shift them. */
function weekStart_(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
  return Utilities.formatDate(dt, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

/**
 * Totals per week and city. Rates are ratios of the weekly totals, with the same definitions as the SQL views.
 * Only full weeks (7 days of data in every city) are kept, so the first and last part-weeks do not look like drops.
 */
function weeklyByCity_(daily) {
  const agg = {};
  daily.forEach(r => {
    const key = weekStart_(r.service_date) + '|' + r.city_code;
    const a = agg[key] || (agg[key] = { days: 0, attempts: 0, completed: 0, failed: 0, cancelled: 0, onTime: 0, sla: 0 });
    a.days += 1;
    a.attempts += Number(r.attempts);
    a.completed += Number(r.completed);
    a.failed += Number(r.failed);
    a.cancelled += Number(r.cancelled);
    a.onTime += Number(r.on_time);
    a.sla += Number(r.sla_breaches);
  });
  const weekStarts = [...new Set(Object.keys(agg).map(k => k.split('|')[0]))]
    .filter(w => CITY_ORDER.every(c => agg[w + '|' + c] && agg[w + '|' + c].days === 7))
    .sort();
  return { agg, weekStarts };
}

function rates_(a) {
  return {
    onTime: a.completed ? a.onTime / a.completed : 0,
    failure: (a.attempts - a.cancelled) ? a.failed / (a.attempts - a.cancelled) : 0,
  };
}

// ---------- writing ----------

function sheet_(name) {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clear();
  sh.clearConditionalFormatRules();
  return sh;
}

function writeWeekly_(weeks) {
  const { agg, weekStarts } = weeks;
  const sh = sheet_('Weekly MIS');
  const latest = weekStarts[weekStarts.length - 1];
  const prev = weekStarts[weekStarts.length - 2];

  sh.getRange('A1').setValue('Kestrel Rentals (fictional): weekly last-mile operations MIS').setFontSize(14).setFontWeight('bold');
  sh.getRange('A2').setValue('Latest full week starting ' + latest + '. Targets: on-time at least '
    + ON_TIME_TARGET * 100 + '%, failures at most ' + FAILURE_LIMIT * 100 + '%. Red = outside target.').setFontColor('#6B7280');

  // Block 1: latest week vs the week before
  const head1 = ['City', 'Completed', 'WoW change', 'On-time %', 'WoW (pts)', 'Failure %', 'WoW (pts)', 'SLA breaches'];
  const rows1 = CITY_ORDER.map(c => {
    const a = agg[latest + '|' + c], p = agg[prev + '|' + c];
    const ra = rates_(a), rp = rates_(p);
    return [CITY_NAMES[c], a.completed, a.completed - p.completed,
            ra.onTime, (ra.onTime - rp.onTime) * 100, ra.failure, (ra.failure - rp.failure) * 100, a.sla];
  });
  sh.getRange(4, 1, 1, head1.length).setValues([head1]);
  sh.getRange(5, 1, rows1.length, head1.length).setValues(rows1);
  styleHeader_(sh.getRange(4, 1, 1, head1.length));
  sh.getRange(5, 2, 3, 2).setNumberFormat('#,##0;-#,##0');
  sh.getRange(5, 4, 3, 1).setNumberFormat('0.0%');
  sh.getRange(5, 5, 3, 1).setNumberFormat('+0.0;-0.0;0.0');
  sh.getRange(5, 6, 3, 1).setNumberFormat('0.0%');
  sh.getRange(5, 7, 3, 1).setNumberFormat('+0.0;-0.0;0.0');
  sh.getRange(5, 8, 3, 1).setNumberFormat('#,##0');
  flag_(sh, 5, 4, 6, rows1.length);

  // Block 2: every full week, one row per week and city
  const top = 10;
  sh.getRange(top - 1, 1).setValue('All full weeks').setFontWeight('bold');
  const head2 = ['Week start', 'City', 'Attempts', 'Completed', 'On-time %', 'Failure %', 'Cancelled', 'SLA breaches', 'Flag'];
  const rows2 = [];
  weekStarts.forEach(w => CITY_ORDER.forEach(c => {
    const a = agg[w + '|' + c], r = rates_(a);
    const flags = [];
    if (r.onTime < ON_TIME_TARGET) flags.push('On-time below target');
    if (r.failure > FAILURE_LIMIT) flags.push('Failures above limit');
    rows2.push([w, CITY_NAMES[c], a.attempts, a.completed, r.onTime, r.failure, a.cancelled, a.sla, flags.join('; ')]);
  }));
  sh.getRange(top, 1, 1, head2.length).setValues([head2]);
  sh.getRange(top + 1, 1, rows2.length, head2.length).setValues(rows2);
  styleHeader_(sh.getRange(top, 1, 1, head2.length));
  sh.getRange(top + 1, 1, rows2.length, 1).setNumberFormat('@');
  sh.getRange(top + 1, 3, rows2.length, 2).setNumberFormat('#,##0');
  sh.getRange(top + 1, 5, rows2.length, 2).setNumberFormat('0.0%');
  sh.getRange(top + 1, 7, rows2.length, 2).setNumberFormat('#,##0');
  flag_(sh, top + 1, 5, 6, rows2.length);

  sh.setFrozenRows(0);
  sh.autoResizeColumns(1, 9);
}

/** Red/green fill: on-time % against the target, failure % against the limit. */
function flag_(sh, firstRow, onTimeCol, failureCol, n) {
  const onTime = sh.getRange(firstRow, onTimeCol, n, 1).getValues();
  const failure = sh.getRange(firstRow, failureCol, n, 1).getValues();
  sh.getRange(firstRow, onTimeCol, n, 1).setBackgrounds(onTime.map(v => [v[0] < ON_TIME_TARGET ? RED : GREEN]));
  sh.getRange(firstRow, failureCol, n, 1).setBackgrounds(failure.map(v => [v[0] > FAILURE_LIMIT ? RED : GREEN]));
}

function styleHeader_(range) {
  range.setBackground(HEADER).setFontColor('#FFFFFF').setFontWeight('bold');
}

function writeEscalations_(rows) {
  const sh = sheet_('Escalations');
  const open = rows.filter(r => r.status === 'Open');
  const cols = ['check_code', 'vendor_name', 'invoice_no', 'service_month', 'scope', 'detail', 'amount_at_stake', 'owner', 'action', 'due_on'];
  const head = ['Check', 'Vendor', 'Invoice', 'Month', 'Scope', 'Detail', 'Amount at stake (INR)', 'Owner', 'Action', 'Due on'];
  sh.getRange('A1').setValue('Open vendor escalations').setFontSize(14).setFontWeight('bold');
  sh.getRange(3, 1, 1, head.length).setValues([head]);
  styleHeader_(sh.getRange(3, 1, 1, head.length));
  if (open.length) {
    const data = open.map(r => cols.map(c => c === 'amount_at_stake' ? Number(r[c]) : r[c]));
    sh.getRange(4, 1, data.length, head.length).setValues(data);
    sh.getRange(4, 7, data.length, 1).setNumberFormat('#,##,##0');
    const total = data.reduce((s, r) => s + r[6], 0);
    sh.getRange(4 + data.length, 6, 1, 2).setValues([['Total open', total]]).setFontWeight('bold').setBackground(SUB);
    sh.getRange(4 + data.length, 7).setNumberFormat('#,##,##0');
  }
  sh.getRange(4, 1, Math.max(open.length, 1), 1).setNumberFormat('@');
  sh.autoResizeColumns(1, head.length);
}

function logRefresh_(dailyRows, escalationRows, weeks) {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName('Refresh log') || ss.insertSheet('Refresh log');
  if (sh.getLastRow() === 0) {
    sh.appendRow(['Refreshed at', 'daily_ops rows', 'escalation rows', 'full weeks']);
    styleHeader_(sh.getRange(1, 1, 1, 4));
  }
  sh.appendRow([new Date(), dailyRows, escalationRows, weeks]);
}
