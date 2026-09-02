'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const cgi = path.join(root, 'module/files/cgi-bin/settings.cgi');
const remote = path.join(root, 'module/files/remote.html');

test('settings status exposes exactly three empty custom profile slots', () => {
  const output = execFileSync('sh', [cgi], {
    env:{...process.env, REQUEST_METHOD:'GET', QUERY_STRING:''},
    stdio:['ignore', 'pipe', 'ignore']
  }).toString();
  const payload = JSON.parse(output.trim().split('\n').at(-1));
  assert.deepEqual(payload.custom_profiles, {custom1:null, custom2:null, custom3:null});
});

test('remote separates three locked defaults from three editable custom slots', () => {
  const html = fs.readFileSync(remote, 'utf8');
  for (const name of ['safe', 'balanced', 'strong', 'custom1', 'custom2', 'custom3']) {
    assert.match(html, new RegExp('data-pq-profile="' + name + '"'));
  }
  assert.match(html, /Locked defaults/);
  assert.match(html, /Editable custom profiles/);
  assert.match(html, /id="pq-save-custom"/);
});
