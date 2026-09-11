'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('HDMI endpoint uses the discovered SoftWinner input contract', () => {
  const hdmi = read('module/files/cgi-bin/hdmi.cgi');

  assert.match(hdmi, /LIVE_PKG="com\.softwinner\.awlivetv"/);
  assert.match(hdmi, /SOURCE_ACTIVITY="com\.softwinner\.awsource\/\.MainActivity"/);
  assert.match(hdmi, /hdmi1\|hdmi2\|hdmi3/);
  assert.match(hdmi, /--es input_source "\$source" --ez manual_set_source true/);
  assert.match(hdmi, /pm enable --user 0 "\$LIVE_PKG"/);
  assert.match(hdmi, /Status: 403 Forbidden/);
  assert.match(hdmi, /Unknown HDMI action/);
});

test('web remote exposes direct HDMI ports and the source picker', () => {
  const html = read('module/files/remote.html');

  for (const action of ['picker', 'hdmi1', 'hdmi2', 'hdmi3']) {
    assert.match(html, new RegExp('data-hdmi="' + action + '"'));
  }
  assert.match(html, /fetch\('\/cgi-bin\/hdmi\.cgi\?' \+ query/);
  assert.match(html, /aria-label="Projector input source"/);
});

test('launcher APK source provides the picker and direct HDMI tiles', () => {
  const manifest = read('src/app/project/AndroidManifest.xml');
  const activity = read('src/app/project/smali/com/tvremoteweb/qr/HdmiActivity.smali');
  const agent = read('agent/beem_agent/server.py');

  assert.match(manifest, /android:name="com\.tvremoteweb\.qr\.HdmiActivity"/);
  assert.match(manifest, /android:name="android\.intent\.category\.LEANBACK_LAUNCHER"/);
  assert.match(activity, /com\.softwinner\.awsource\.MainActivity/);
  for (const port of ['1', '2', '3']) {
    const direct = read(`src/app/project/smali/com/tvremoteweb/qr/Hdmi${port}Activity.smali`);
    assert.match(manifest, new RegExp(`android:name="com\\.tvremoteweb\\.qr\\.Hdmi${port}Activity"`));
    assert.match(direct, /com\.softwinner\.awlivetv\.MainActivity/);
    assert.match(direct, new RegExp(`const-string v2, "HDMI${port}"`));
    assert.match(direct, /const-string v1, "manual_set_source"/);
    assert.match(direct, /invoke-virtual \{v0, v1, v2\}, Landroid\/content\/Intent;->putExtra\(Ljava\/lang\/String;Z\)/);
  }
  assert.match(agent, /"files\/cgi-bin\/hdmi\.cgi": 0o755/);
});
