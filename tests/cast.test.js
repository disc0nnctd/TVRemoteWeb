'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('casting delegates to installed firmware receivers with no resident daemon', () => {
  const cast = read('module/files/cgi-bin/cast.cgi');
  const service = read('module/service.sh');

  assert.match(cast, /MIRACAST_PKG="com\.softwinner\.miracastReceiver"/);
  assert.match(cast, /"\$MIRACAST_PKG\/\.Miracast"/);
  assert.match(cast, /AIRPLAY_PKG="com\.ecloud\.eairplay"/);
  assert.match(cast, /"\$AIRPLAY_PKG\/\.MainActivity"/);
  assert.match(cast, /DLNA_PKG="com\.ecloud\.emedia"/);
  assert.match(cast, /"\$DLNA_PKG\/\.DlnaServer"/);
  assert.match(cast, /am force-stop/);
  assert.match(cast, /pm enable --user 0/);
  assert.match(cast, /pm disable-user --user 0/);
  assert.match(cast, /start_miracast_watchdog/);
  assert.doesNotMatch(service, /cast\.cgi|miracastReceiver|eairplay|emedia/);
});

test('casting endpoint is token protected and actions are allowlisted', () => {
  const cast = read('module/files/cgi-bin/cast.cgi');

  assert.match(cast, /Status: 403 Forbidden/);
  assert.match(cast, /case "\$action" in/);
  assert.match(cast, /\*\) status="err"; detail="Unknown casting action\."/);
});

test('Apps tab exposes available receiver controls and a RAM-releasing stop action', () => {
  const html = read('module/files/remote.html');

  assert.match(html, /data-cast="miracast"/);
  assert.match(html, /data-cast="airplay"/);
  assert.match(html, /data-cast="dlna"/);
  assert.match(html, /data-cast="stop"/);
  assert.match(html, /if \(name === 'apps'\)[\s\S]*pullCastStatus\(\);/);
});
