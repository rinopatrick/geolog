(function () {
  window.ImageLogView = {
    async run() {
      if (!window.app || !app.currentWell) { GeoToast.warn('Select a well first'); return; }
      var data = await app._api('/wells/' + app.currentWell.id + '/image-log');
      this.render(data);
    },
    render: function (data) {
      var canvas = document.getElementById('imageLogCanvas');
      if (!canvas) return;
      var W = canvas.parentElement.getBoundingClientRect().width;
      var nD = (data.depth || []).length, nB = data.n_bins || 72;
      var H = Math.max(400, nD * 2 + 30);
      canvas.width = W * 2; canvas.height = H * 2;
      var ctx = canvas.getContext('2d'); ctx.scale(2, 2);
      ctx.fillStyle = '#0b0f14'; ctx.fillRect(0, 0, W, H);
      var x0 = 55, w = W - 100;
      for (var i = 0; i < nD; i++) {
        for (var b = 0; b < nB; b++) {
          var v = data.image[i][b];
          var r = Math.floor(255 * v), g = Math.floor(180 * (1 - Math.abs(v - 0.5) * 2)), bl = Math.floor(255 * (1 - v));
          ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + bl + ')';
          ctx.fillRect(x0 + b * (w / nB), 15 + i * 2, (w / nB) + 0.3, 2.2);
        }
      }
      var meta = document.getElementById('imageLogMeta');
      if (meta) meta.textContent = 'Curve: ' + data.curve_used + (data.synthetic ? ' (synthetic from GR)' : '');
    }
  };
})();