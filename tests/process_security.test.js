'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('Process Monitor is collapsed, last in Stats, and never auto-loads', () => {
  const html = read('module/files/remote.html');
  const statsStart = html.indexOf('<section class="tabpane" data-tab="stats">');
  const statsEnd = html.indexOf('</section>', statsStart);
  const stats = html.slice(statsStart, statsEnd);

  assert.match(stats, /<details class="card proc-vault" id="proc-vault">/);
  assert.doesNotMatch(stats, /id="proc-vault"[^>]*\bopen\b/);
  assert.ok(stats.indexOf('id="proc-vault"') > stats.lastIndexOf('<div class="card">'));
  assert.doesNotMatch(html, /name === '(tools|stats)'[^\n]*pullProcs/);
});

test('Process password stays in memory and is sent as a request header', () => {
  const html = read('module/files/remote.html');

  assert.match(html, /id="proc-password" type="password"/);
  assert.match(html, /let processPassword = '';/);
  assert.match(html, /headers:\{'X-Process-Password':password\}/);
  assert.match(html, /headers:\{'X-Process-Password':processPassword\}/);
  assert.doesNotMatch(html, /(?:localStorage|sessionStorage)\.setItem\(['"]processPassword/);
});

test('Backend requires the process PIN for listing and killing', () => {
  const stats = read('module/files/cgi-bin/stats.cgi');
  const remote = read('module/files/cgi-bin/remote.cgi');

  assert.match(stats, /\$top_n" -gt 0.*HTTP_X_PROCESS_PASSWORD/);
  assert.match(stats, /Status: 403 Forbidden/);
  assert.match(remote, /if \[ -n "\$kill_pid" \]; then[\s\S]*HTTP_X_PROCESS_PASSWORD/);
  assert.match(remote, /process PIN required/);
});
