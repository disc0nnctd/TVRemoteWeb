'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('QR activity destroys its WebView when leaving the foreground', () => {
  const smali = read('src/app/project/smali/com/tvremoteweb/qr/MainActivity.smali');
  assert.match(smali, /\.method protected onStop\(\)V/);
  assert.match(smali, /WebView;->destroy\(\)V/);
  assert.match(smali, /Activity;->finishAndRemoveTask\(\)V/);
});

test('runtime cleanup excludes monitor overhead and stops dormant heavy activities', () => {
  const stats = read('module/files/cgi-bin/stats.cgi');
  const remote = read('module/files/cgi-bin/remote.cgi');
  const keystone = read('module/files/cgi-bin/keystone.cgi');
  assert.match(stats, /name ~ \/\^top\( \|\$\)\//);
  assert.match(remote, /am force-stop com\.tvremoteweb\.qr/);
  assert.match(keystone, /am force-stop com\.htc\.htcsettings/);
});

test('live stats polling uses a low-overhead interval', () => {
  const html = read('module/files/remote.html');
  assert.match(html, /setInterval\(\(\) => pullStats\(false\), 15000\)/);
});
