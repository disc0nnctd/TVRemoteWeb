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

test('detects a cyan projected trapezoid from browser image pixels', () => {
  const width = 240, height = 180;
  const rgba = new Uint8ClampedArray(width * height * 4);
  const quad = [[42,35],[205,48],[190,147],[30,135]];
  function inside(x, y) {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i], b = quad[(i + 1) % 4];
      const cross = (b[0]-a[0])*(y-a[1]) - (b[1]-a[1])*(x-a[0]);
      if (Math.abs(cross) < 1e-6) continue;
      if (sign && Math.sign(cross) !== sign) return false;
      sign = Math.sign(cross);
    }
    return true;
  }
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const offset = (y * width + x) * 4;
    if (inside(x, y)) { rgba[offset] = 30; rgba[offset+1] = 155; rgba[offset+2] = 235; }
    else { rgba[offset] = 75; rgba[offset+1] = 70; rgba[offset+2] = 65; }
    rgba[offset+3] = 255;
  }
  const found = k.detectProjectionEdges(rgba, width, height);
  quad.forEach((point, index) => {
    assert.ok(Math.abs(found.projection[index][0] - point[0] / width) < 0.035);
    assert.ok(Math.abs(found.projection[index][1] - point[1] / height) < 0.035);
  });
  assert.ok(found.confidence >= 0.5);
});

test('projection detection rejects a photo without the blue calibration signal', () => {
  const rgba = new Uint8ClampedArray(64 * 64 * 4).fill(90);
  assert.throws(() => k.detectProjectionEdges(rgba, 64, 64), /blue correction projection was not found/);
});

test('detects a dark physical screen frame enclosing the projection', () => {
  const width = 260, height = 190;
  const rgba = new Uint8ClampedArray(width * height * 4);
  const screen = [[20,18],[238,28],[228,174],[12,162]];
  const projection = [[52,48],[207,55],[200,142],[45,135]];
  const inside = (quad, x, y) => {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a=quad[i], b=quad[(i+1)%4], cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);
      if (Math.abs(cross) < 1e-6) continue;
      if (sign && Math.sign(cross) !== sign) return false;
      sign = Math.sign(cross);
    }
    return true;
  };
  const segmentDistance = (p, a, b) => {
    const dx=b[0]-a[0], dy=b[1]-a[1];
    const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)));
    return Math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy));
  };
  for (let y=0;y<height;y++) for (let x=0;x<width;x++) {
    const offset=(y*width+x)*4;
    let value=inside(screen,x,y)?225:175;
    if (screen.some((a,i)=>segmentDistance([x,y],a,screen[(i+1)%4])<3.2)) value=22;
    rgba[offset]=rgba[offset+1]=rgba[offset+2]=value;
    if (inside(projection,x,y)) { rgba[offset]=25; rgba[offset+1]=150; rgba[offset+2]=235; }
    rgba[offset+3]=255;
  }
  const found=k.detectScreenEdges(rgba,width,height,projection.map(([x,y])=>[x/width,y/height]));
  screen.forEach((point,index)=>{
    assert.ok(Math.abs(found.screen[index][0]-point[0]/width)<.06);
    assert.ok(Math.abs(found.screen[index][1]-point[1]/height)<.06);
  });
  assert.ok(found.confidence>=.3);
});

test('screen detection falls back when no enclosing frame is visible', () => {
  const width=160,height=120,rgba=new Uint8ClampedArray(width*height*4);
  for(let i=0;i<rgba.length;i+=4) rgba[i]=rgba[i+1]=rgba[i+2]=190,rgba[i+3]=255;
  const projection=[[.25,.25],[.75,.25],[.75,.75],[.25,.75]];
  assert.throws(()=>k.detectScreenEdges(rgba,width,height,projection),/no continuous physical screen frame found/);
});
