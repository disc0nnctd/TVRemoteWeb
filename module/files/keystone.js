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

  function regression(samples, dependentIndex) {
    if (samples.length < 8) fail('not enough edge samples');
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (const sample of samples) {
      const x = sample[1 - dependentIndex], y = sample[dependentIndex];
      sx += x; sy += y; sxx += x * x; sxy += x * y;
    }
    const n = samples.length;
    const divisor = n * sxx - sx * sx;
    if (Math.abs(divisor) < 1e-8) fail('edge samples are degenerate');
    const slope = (n * sxy - sx * sy) / divisor;
    return [slope, (sy - slope * sx) / n];
  }

  function lineIntersection(vertical, horizontal) {
    // x = vertical[0] * y + vertical[1], y = horizontal[0] * x + horizontal[1]
    const divisor = 1 - vertical[0] * horizontal[0];
    if (Math.abs(divisor) < 1e-6) fail('detected edges do not form stable corners');
    const y = (horizontal[0] * vertical[1] + horizontal[1]) / divisor;
    return [vertical[0] * y + vertical[1], y];
  }

  function detectProjectionEdges(rgba, width, height) {
    if (!rgba || rgba.length !== width * height * 4 || width < 32 || height < 32) {
      fail('invalid image pixels');
    }
    const rowMin = new Int32Array(height); rowMin.fill(width);
    const rowMax = new Int32Array(height); rowMax.fill(-1);
    const rowCount = new Int32Array(height);
    const colMin = new Int32Array(width); colMin.fill(height);
    const colMax = new Int32Array(width); colMax.fill(-1);
    const colCount = new Int32Array(width);
    let hits = 0;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const offset = (y * width + x) * 4;
        const r = rgba[offset], g = rgba[offset + 1], b = rgba[offset + 2];
        // The Beem correction view is cyan/blue. Restricting detection to that
        // signal avoids mistaking a wall, frame, doorway, or shadow for light.
        if (b < 80 || g < 55 || b - r < 24 || g - r < 8) continue;
        hits++;
        rowCount[y]++; colCount[x]++;
        if (x < rowMin[y]) rowMin[y] = x;
        if (x > rowMax[y]) rowMax[y] = x;
        if (y < colMin[x]) colMin[x] = y;
        if (y > colMax[x]) colMax[x] = y;
      }
    }
    const coverage = hits / (width * height);
    if (coverage < 0.012) fail('blue correction projection was not found; show the grid, dim the room, and retake the photo');

    let firstRow = height, lastRow = -1, firstCol = width, lastCol = -1;
    const rowNeed = Math.max(5, Math.round(width * 0.015));
    const colNeed = Math.max(5, Math.round(height * 0.015));
    for (let y = 0; y < height; y++) if (rowCount[y] >= rowNeed) { firstRow = Math.min(firstRow, y); lastRow = y; }
    for (let x = 0; x < width; x++) if (colCount[x] >= colNeed) { firstCol = Math.min(firstCol, x); lastCol = x; }
    if (lastRow - firstRow < height * 0.08 || lastCol - firstCol < width * 0.08) {
      fail('detected blue area is too small for reliable corners');
    }

    const left = [], right = [], top = [], bottom = [];
    const rowTrim = Math.max(2, Math.round((lastRow - firstRow) * 0.06));
    const colTrim = Math.max(2, Math.round((lastCol - firstCol) * 0.06));
    for (let y = firstRow + rowTrim; y <= lastRow - rowTrim; y++) {
      if (rowCount[y] >= rowNeed) { left.push([rowMin[y], y]); right.push([rowMax[y], y]); }
    }
    for (let x = firstCol + colTrim; x <= lastCol - colTrim; x++) {
      if (colCount[x] >= colNeed) { top.push([x, colMin[x]]); bottom.push([x, colMax[x]]); }
    }
    const leftLine = regression(left, 0), rightLine = regression(right, 0);
    const topLine = regression(top, 1), bottomLine = regression(bottom, 1);
    const pixels = [
      lineIntersection(leftLine, topLine), lineIntersection(rightLine, topLine),
      lineIntersection(rightLine, bottomLine), lineIntersection(leftLine, bottomLine)
    ];
    const projection = pixels.map(([x, y]) => [x / width, y / height]);
    validateQuad(projection, 'detected projection');
    if (projection.some(pair => pair.some(v => v < -0.04 || v > 1.04))) {
      fail('a projected corner is outside the photo; retake with all four blue edges visible');
    }
    const confidence = Math.max(0.35, Math.min(0.96, 0.45 + Math.min(coverage, 0.25) * 1.8));
    return {projection: projection.map(pair => pair.map(v => Math.max(0, Math.min(1, v)))), confidence};
  }

  function polygonArea(quad) {
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i], b = quad[(i + 1) % 4];
      area += a[0] * b[1] - b[0] * a[1];
    }
    return Math.abs(area) / 2;
  }

  function containsPoint(quad, point) {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i], b = quad[(i + 1) % 4];
      const cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
      if (Math.abs(cross) < 1e-7) continue;
      if (sign && Math.sign(cross) !== sign) return false;
      sign = Math.sign(cross);
    }
    return true;
  }

  function detectScreenEdges(rgba, width, height, projection) {
    if (!rgba || rgba.length !== width * height * 4 || width < 64 || height < 64) fail('invalid image pixels');
    validateQuad(projection, 'projection');
    const luma = new Uint8Array(width * height);
    for (let i = 0, p = 0; i < luma.length; i++, p += 4) {
      luma[i] = Math.round(rgba[p] * .299 + rgba[p + 1] * .587 + rgba[p + 2] * .114);
    }
    const sample = (x, y) => {
      const ix = Math.round(x), iy = Math.round(y);
      if (ix < 0 || iy < 0 || ix >= width || iy >= height) return null;
      return luma[iy * width + ix];
    };
    const projected = projection.map(([x, y]) => [x * width, y * height]);
    const center = projected.reduce((sum, p) => [sum[0] + p[0] / 4, sum[1] + p[1] / 4], [0, 0]);
    const lines = [], qualities = [];
    for (let side = 0; side < 4; side++) {
      const a = projected[side], b = projected[(side + 1) % 4];
      const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
      const direction = [dx / length, dy / length];
      const midpoint = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      let normal = [direction[1], -direction[0]];
      if (normal[0] * (midpoint[0] - center[0]) + normal[1] * (midpoint[1] - center[1]) < 0) {
        normal = [-normal[0], -normal[1]];
      }
      let boundaryDistance = Infinity;
      if (normal[0] > .001) boundaryDistance = Math.min(boundaryDistance, (width - 1 - midpoint[0]) / normal[0]);
      if (normal[0] < -.001) boundaryDistance = Math.min(boundaryDistance, -midpoint[0] / normal[0]);
      if (normal[1] > .001) boundaryDistance = Math.min(boundaryDistance, (height - 1 - midpoint[1]) / normal[1]);
      if (normal[1] < -.001) boundaryDistance = Math.min(boundaryDistance, -midpoint[1] / normal[1]);
      const minDistance = Math.max(7, length * .035);
      const maxDistance = Math.min(boundaryDistance * .88, length * .8);
      if (!(maxDistance > minDistance * 1.5)) fail('not enough room around the projection to detect a screen frame');
      let best = null;
      for (let angle = -18; angle <= 18; angle += 3) {
        const radians = angle * Math.PI / 180, cosine = Math.cos(radians), sine = Math.sin(radians);
        const lineDirection = [direction[0] * cosine - direction[1] * sine, direction[0] * sine + direction[1] * cosine];
        let lineNormal = [lineDirection[1], -lineDirection[0]];
        if (lineNormal[0] * normal[0] + lineNormal[1] * normal[1] < 0) lineNormal = [-lineNormal[0], -lineNormal[1]];
        const step = Math.max(2, Math.round((maxDistance - minDistance) / 60));
        for (let distance = minDistance; distance <= maxDistance; distance += step) {
          const lineCenter = [midpoint[0] + normal[0] * distance, midpoint[1] + normal[1] * distance];
          const count = Math.max(36, Math.round(length / 4));
          let score = 0, continuous = 0, valid = 0;
          for (let j = 0; j < count; j++) {
            const along = ((j / (count - 1)) - .5) * length * .92;
            const x = lineCenter[0] + lineDirection[0] * along;
            const y = lineCenter[1] + lineDirection[1] * along;
            const middle = sample(x, y);
            const inside = sample(x - lineNormal[0] * 4, y - lineNormal[1] * 4);
            const outside = sample(x + lineNormal[0] * 4, y + lineNormal[1] * 4);
            if (middle === null || inside === null || outside === null) continue;
            valid++;
            const gradient = Math.abs(outside - inside);
            const darkness = (255 - middle) / 255;
            score += Math.min(gradient / 70, 1) * .68 + darkness * .32;
            if (gradient >= 16 || middle <= 80) continuous++;
          }
          if (valid < count * .82) continue;
          const continuity = continuous / valid;
          const quality = (score / valid) * (.55 + .45 * continuity);
          if (!best || quality > best.quality) best = {center:lineCenter, direction:lineDirection, quality, continuity};
        }
      }
      if (!best || best.quality < .25 || best.continuity < .28) fail('no continuous physical screen frame found');
      lines.push(best); qualities.push(best.quality);
    }
    function intersect(a, b) {
      const cross = a.direction[0] * b.direction[1] - a.direction[1] * b.direction[0];
      if (Math.abs(cross) < .05) fail('detected screen edges do not form stable corners');
      const delta = [b.center[0] - a.center[0], b.center[1] - a.center[1]];
      const t = (delta[0] * b.direction[1] - delta[1] * b.direction[0]) / cross;
      return [a.center[0] + t * a.direction[0], a.center[1] + t * a.direction[1]];
    }
    const screenPixels = [intersect(lines[3], lines[0]), intersect(lines[0], lines[1]),
                          intersect(lines[1], lines[2]), intersect(lines[2], lines[3])];
    const screen = screenPixels.map(([x, y]) => [x / width, y / height]);
    validateQuad(screen, 'detected screen');
    if (screen.some(pair => pair.some(v => v < -.025 || v > 1.025))) fail('physical screen corners extend outside the photo');
    if (!projection.every(point => containsPoint(screen, point))) fail('detected frame does not enclose the projected image');
    const ratio = polygonArea(screen) / polygonArea(projection);
    if (ratio < 1.08 || ratio > 7) fail('detected frame has an implausible size');
    const confidence = Math.max(.3, Math.min(.95, qualities.reduce((a, b) => a + b, 0) / 4));
    return {screen:screen.map(pair => pair.map(v => Math.max(0, Math.min(1, v)))), confidence};
  }

  return { CORNERS, parseAnnotation, solveInsets, firmwareCsv, chatGptPrompt, detectProjectionEdges, detectScreenEdges };
});
