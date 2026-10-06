'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('lights.cgi checks the PIN and only talks to the loopback relay', () => {
  const cgi = read('module/files/cgi-bin/lights.cgi');
  assert.match(cgi, /Status: 403 Forbidden/);
  assert.match(cgi, /RELAY="http:\/\/127\.0\.0\.1:8790"/);
  assert.match(cgi, /token\|action\) ;;/);
});

test('the relay keeps the Home Assistant token on the PC and whitelists lights', () => {
  const relay = read('tools/ha-relay/ha_relay.py');
  assert.match(relay, /ThreadingHTTPServer\(\("127\.0\.0\.1", PORT\)/);
  assert.match(relay, /LIGHTS\.get\(query\.get\("id", ""\)\)/);
  assert.match(relay, /"reverse", rule, rule/);
});

test('the remote offers the room-light scenes', () => {
  const html = read('module/files/remote.html');
  for (const scene of ['movie', 'half', 'normal', 'off']) assert.match(html, new RegExp(`data-scene="${scene}"`));
  assert.match(html, /\/cgi-bin\/lights\.cgi\?/);
});
