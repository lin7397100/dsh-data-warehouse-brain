// bbox_check.js - measure SVG text bboxes in headless Edge (overflow / overlap)
(function () {
  var out = [];
  var svgs = document.querySelectorAll('#charts-extra svg.sg-svg');
  out.push('svg_count=' + svgs.length);
  svgs.forEach(function (svg, si) {
    var vb = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    var W = vb[2], H = vb[3];
    var sr = svg.getBoundingClientRect();
    var sc = sr.width / W;
    var texts = Array.prototype.slice.call(svg.querySelectorAll('text')).filter(function (t) {
      return t.textContent.trim().length > 0 && !t.closest('defs');
    });
    var boxes = [], over = [];
    texts.forEach(function (t) {
      var b = t.getBoundingClientRect();
      var box = {
        x: (b.left - sr.left) / sc,
        y: (b.top - sr.top) / sc,
        width: b.width / sc,
        height: b.height / sc
      };
      boxes.push({ b: box, s: t.textContent.trim() });
      if (box.x < -1 || box.y < -1 || box.x + box.width > W + 1 || box.y + box.height > H + 1) {
        over.push(t.textContent.trim().slice(0, 22) + ' [' + box.x.toFixed(0) + ',' + box.y.toFixed(0) + ' ' + box.width.toFixed(0) + 'x' + box.height.toFixed(0) + ']');
      }
    });
    var ov = [];
    var i, j;
    for (i = 0; i < boxes.length; i++) {
      for (j = i + 1; j < boxes.length; j++) {
        var a = boxes[i].b, c = boxes[j].b;
        var ix = Math.max(0, Math.min(a.x + a.width, c.x + c.width) - Math.max(a.x, c.x));
        var iy = Math.max(0, Math.min(a.y + a.height, c.y + c.height) - Math.max(a.y, c.y));
        var inter = ix * iy;
        var minA = Math.min(a.width * a.height, c.width * c.height);
        if (minA > 0 && inter / minA > 0.34) {
          ov.push(boxes[i].s.slice(0, 16) + ' X ' + boxes[j].s.slice(0, 16) + ' (' + (inter / minA * 100).toFixed(0) + '%)');
        }
      }
    }
    out.push('--- SVG#' + (si + 1) + ' viewBox=' + W + 'x' + H + ' texts=' + texts.length + ' overflow=' + over.length + ' overlap=' + ov.length);
    over.slice(0, 6).forEach(function (o) { out.push('   OVER ' + o); });
    ov.slice(0, 10).forEach(function (o) { out.push('   OVLAP ' + o); });
  });
  var pre = document.createElement('pre');
  pre.id = 'bbox-out';
  pre.textContent = out.join('\n');
  document.body.appendChild(pre);
})();
