'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('Bluetooth endpoint uses Android services only on demand', () => {
  const bluetooth = read('module/files/cgi-bin/bluetooth.cgi');
  const service = read('module/service.sh');
  const agent = read('agent/beem_agent/server.py');

  assert.match(bluetooth, /svc bluetooth "\$mode"/);
  assert.match(bluetooth, /android\.settings\.BLUETOOTH_PAIRING_SETTINGS/);
  assert.match(bluetooth, /android\.settings\.BLUETOOTH_SETTINGS/);
  assert.doesNotMatch(service, /bluetooth\.cgi|bluetooth_manager/);
  assert.match(agent, /"files\/cgi-bin\/bluetooth\.cgi": 0o755/);
});

test('Bluetooth endpoint preserves token authentication and allowlists actions', () => {
  const bluetooth = read('module/files/cgi-bin/bluetooth.cgi');

  assert.match(bluetooth, /Status: 403 Forbidden/);
  assert.match(bluetooth, /case "\$action" in/);
  assert.match(bluetooth, /\*\) status="err"; detail="Unknown Bluetooth action\."/);
});

test('Tools exposes Bluetooth power, pairing, settings, and status controls', () => {
  const html = read('module/files/remote.html');

  for (const action of ['enable', 'disable', 'pair', 'settings']) {
    assert.match(html, new RegExp('data-bluetooth="' + action + '"'));
  }
  assert.match(html, /pullBluetoothStatus\(\)/);
});
