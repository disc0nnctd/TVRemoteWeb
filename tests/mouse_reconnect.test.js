'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('new remote connections replace a stale mouse WebSocket', () => {
  const source = read('src/mousedaemon/mousedaemon.c');

  assert.match(source, /poll\(fds, 2, -1\)/);
  assert.match(source, /if \(cfd >= 0\) close\(cfd\);\s*cfd = nfd;/);
  assert.match(source, /TCP_NODELAY/);
});

test('hidden browser tabs release the native mouse connection', () => {
  const html = read('module/files/remote.html');

  assert.match(html, /if \(document\.hidden && ws\) \{ ws\.close\(\); \}/);
  assert.match(html, /if \(!document\.hidden && !ws\) wsConnect\(\);/);
  assert.match(html, /if \(document\.hidden \|\| ws\) return;/);
});

test('opening the projector tile restores remote access after casting', () => {
  const qr = read('module/files/cgi-bin/qr.cgi');
  const cast = read('module/files/cgi-bin/cast.cgi');
  const service = read('module/service.sh');

  assert.match(qr, /splash_request.*boot_request/s);
  assert.match(qr, /am force-stop "\$pkg"/);
  assert.match(qr, /svc wifi enable/);
  assert.match(cast, /restore_disabled "\$MIRACAST_PKG"\s*svc wifi enable/);
  assert.match(service, /qr\.cgi\?mode=splash&boot=1/);
});
