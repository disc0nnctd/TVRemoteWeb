'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const k = require('../module/files/keystone.js');

const zero = {lt:[0,0], rt:[0,0], rb:[0,0], lb:[0,0]};

test('parses ChatGPT object schema in normalized coordinate space', () => {
  const parsed = k.parseAnnotation({
    coordinate_space: 1000,
    screen: {lt:[100,100], rt:[900,100], rb:[900,900], lb:[100,900]},
    projection: {lt:[0,0], rt:[1000,0], rb:[1000,1000], lb:[0,1000]}
  });
  assert.deepEqual(parsed.screen[0], [0.1, 0.1]);
  assert.deepEqual(parsed.projection[2], [1, 1]);
});

test('identity annotation keeps current zero correction', () => {
  const quad = {lt:[100,100], rt:[900,100], rb:[900,900], lb:[100,900]};
  assert.deepEqual(k.solveInsets(k.parseAnnotation({coordinate_space:1000, screen:quad, projection:quad}), zero), zero);
});

test('screen inset ten percent produces firmware inset fifty', () => {
  const annotation = k.parseAnnotation({
    coordinate_space: 1000,
    screen: {lt:[100,100], rt:[900,100], rb:[900,900], lb:[100,900]},
    projection: {lt:[0,0], rt:[1000,0], rb:[1000,1000], lb:[0,1000]}
  });
  assert.deepEqual(k.solveInsets(annotation, zero), {lt:[50,50], rt:[50,50], rb:[50,50], lb:[50,50]});
});

test('rejects crossed corner order', () => {
  assert.throws(() => k.parseAnnotation({
    coordinate_space: 1000,
    screen: [[0,0],[1000,1000],[1000,0],[0,1000]],
    projection: [[0,0],[1000,0],[1000,1000],[0,1000]]
  }), /corners cross|collinear/);
});

test('firmware CSV uses LB, LT, RT, RB transport order', () => {
  assert.equal(k.firmwareCsv({lt:[1,2], rt:[3,4], rb:[5,6], lb:[7,8]}), '7,8,1,2,3,4,5,6');
});
