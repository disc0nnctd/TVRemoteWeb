(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.KeystoneGeometry = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const CORNERS = ['lt', 'rt', 'rb', 'lb'];

  function fail(message) { throw new Error(message); }

  function parsePair(value, label, space) {
    if (!Array.isArray(value) || value.length !== 2) fail(label + ' must be [x, y]');
    const pair = value.map(Number);
    if (!pair.every(Number.isFinite)) fail(label + ' must contain finite numbers');
    if (pair.some(v => v < 0 || v > space)) fail(label + ' must stay inside 0–' + space);
    return pair.map(v => v / space);
  }

  function parseQuad(value, label, space) {
    let quad;
    if (Array.isArray(value)) {
      if (value.length !== 4) fail(label + ' must contain four corners in LT, RT, RB, LB order');
      quad = value.map((pair, i) => parsePair(pair, label + '.' + CORNERS[i], space));
    } else if (value && typeof value === 'object') {
      quad = CORNERS.map(name => parsePair(value[name], label + '.' + name, space));
    } else {
      fail(label + ' must be an object with lt, rt, rb, lb corners');
    }
    validateQuad(quad, label);
    return quad;
  }

  function validateQuad(quad, label) {
    let sign = 0;
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i], b = quad[(i + 1) % 4], c = quad[(i + 2) % 4];
      const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
      if (Math.abs(cross) < 1e-7) fail(label + ' has overlapping or collinear corners');
      const nextSign = Math.sign(cross);
      if (sign && nextSign !== sign) fail(label + ' corners cross; use LT, RT, RB, LB order');
      sign = nextSign;
      area += a[0] * b[1] - b[0] * a[1];
    }
    if (Math.abs(area) < 0.002) fail(label + ' is too small to calibrate reliably');
  }

  function parseAnnotation(input) {
    const data = typeof input === 'string' ? JSON.parse(input) : input;
    if (!data || typeof data !== 'object') fail('annotation must be a JSON object');
    const space = Number(data.coordinate_space || 1000);
    if (!Number.isFinite(space) || space <= 0) fail('coordinate_space must be a positive number');
    return {
      coordinateSpace: space,
      screen: parseQuad(data.screen, 'screen', space),
      projection: parseQuad(data.projection, 'projection', space)
    };
  }

  function solveLinear(rows) {
    const n = rows.length;
    for (let col = 0; col < n; col++) {
      let pivot = col;
      for (let row = col + 1; row < n; row++) {
        if (Math.abs(rows[row][col]) > Math.abs(rows[pivot][col])) pivot = row;
      }
      if (Math.abs(rows[pivot][col]) < 1e-10) fail('corner geometry is singular; retake the photo more square-on');
      [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
      const divisor = rows[col][col];
      for (let j = col; j <= n; j++) rows[col][j] /= divisor;
      for (let row = 0; row < n; row++) {
        if (row === col) continue;
        const factor = rows[row][col];
        for (let j = col; j <= n; j++) rows[row][j] -= factor * rows[col][j];
      }
    }
    return rows.map((row, i) => row[n]);
  }

  function homography(from, to) {
    const rows = [];
    for (let i = 0; i < 4; i++) {
      const x = from[i][0], y = from[i][1], u = to[i][0], v = to[i][1];
      rows.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
      rows.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
    }
    const h = solveLinear(rows);
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  }

  function transform(matrix, point) {
    const x = point[0], y = point[1];
    const w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
    if (Math.abs(w) < 1e-10) fail('corner maps to infinity; check the annotation');
    return [
      (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w,
      (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w
    ];
  }

  function validateInsets(insets) {
    if (!insets || typeof insets !== 'object') fail('projector did not return current keystone values');
    const result = {};
    for (const name of CORNERS) {
      const pair = insets[name];
      if (!Array.isArray(pair) || pair.length !== 2) fail('current ' + name + ' inset is invalid');
      result[name] = pair.map(Number);
      if (!result[name].every(Number.isInteger) || result[name].some(v => v < 0 || v > 500)) {
        fail('current ' + name + ' inset must stay inside firmware range 0–500');
      }
    }
    return result;
  }

  function insetsToSource(insets) {
    const i = validateInsets(insets);
    return [
      [i.lt[0] / 500, i.lt[1] / 500],
      [1 - i.rt[0] / 500, i.rt[1] / 500],
      [1 - i.rb[0] / 500, 1 - i.rb[1] / 500],
      [i.lb[0] / 500, 1 - i.lb[1] / 500]
    ];
  }

  function sourceToInsets(source) {
    const tolerance = 0.002;
    if (source.some(pair => pair.some(v => v < -tolerance || v > 1 + tolerance))) {
      fail('the physical screen extends outside the projector image; move or resize the projector first');
    }
    const s = source.map(pair => pair.map(v => Math.max(0, Math.min(1, v))));
    const round = value => Math.round(value * 500);
    return {
      lt: [round(s[0][0]), round(s[0][1])],
      rt: [round(1 - s[1][0]), round(s[1][1])],
      rb: [round(1 - s[2][0]), round(1 - s[2][1])],
      lb: [round(s[3][0]), round(1 - s[3][1])]
    };
  }

  function solveInsets(annotation, currentInsets) {
    const parsed = annotation && annotation.screen ? annotation : parseAnnotation(annotation);
    const currentSource = insetsToSource(currentInsets);
    const photoToSource = homography(parsed.projection, currentSource);
    return sourceToInsets(parsed.screen.map(point => transform(photoToSource, point)));
  }

  function firmwareCsv(insets) {
    const i = validateInsets(insets);
    return [...i.lb, ...i.lt, ...i.rt, ...i.rb].join(',');
  }

  function chatGptPrompt() {
    return [
      'Analyze the attached photo of a projected image and physical projector screen/frame.',
      'Identify two quadrilaterals: (1) the INNER usable edge of the physical screen/frame, and (2) the visible boundary of the projected image.',
      'Return coordinates normalized to a 0–1000 square, regardless of the photo resolution.',
      'Use exactly LT, RT, RB, LB order. Be precise at the corners; account for perspective in the photo.',
      'Return ONLY valid JSON—no Markdown fence, explanation, comments, or trailing commas—in this exact schema:',
      '{',
      '  "coordinate_space": 1000,',
      '  "screen": {"lt":[x,y],"rt":[x,y],"rb":[x,y],"lb":[x,y]},',
      '  "projection": {"lt":[x,y],"rt":[x,y],"rb":[x,y],"lb":[x,y]}',
      '}',
      'If either complete quadrilateral is not visible, return {"error":"retake photo: <reason>"} instead of guessing.'
    ].join('\n');
  }

  return { CORNERS, parseAnnotation, solveInsets, firmwareCsv, chatGptPrompt };
});
