(function () {
  window.SeismicTieView = {
    async run() {
      if (!window.app || !app.currentWell) { GeoToast.warn('Select a well first'); return; }
      var f = parseFloat((document.getElementById('seismicTieFreq') || {}).value || '30');
      var data = await app._api('/wells/' + app.currentWell.id + '/seismic-tie', {
        method: 'POST', body: JSON.stringify({ frequency_hz: f })
      });
      this.render(data);
    },
    render: function (data) {
      var container = document.getElementById('seismicResults'); if (!container) return; if (!container.querySelector('canvas')) { container.innerHTML = '<canvas id="seismicTieCanvas" style="width:100%;height:560px;background:var(--bg-primary);border-radius:8px"></canvas>'; } var canvas = container.querySelector('canvas');
      if (!canvas) return;
      var W = canvas.parentElement.getBoundingClientRect().width;
      var H = 560;
      canvas.width = W * 2; canvas.height = H * 2;
      var ctx = canvas.getContext('2d'); ctx.scale(2, 2);
      ctx.fillStyle = '#0b0f14'; ctx.fillRect(0, 0, W, H);
      var depth = data.depth || [], ai = data.ai || [], rc = data.rc || [], syn = data.synthetic || [];
      if (!depth.length) return;

      var pad = { l: 55, r: 20, t: 20, b: 35 }, pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
      var dMin = depth[0], dMax = depth[depth.length - 1];
      function drawTrack(arr, x0, w, col) {
        var min = Infinity, max = -Infinity;
        for (var i = 0; i < arr.length; i++) { if (arr[i] == null) continue; min = Math.min(min, arr[i]); max = Math.max(max, arr[i]); }
        ctx.strokeStyle = col; ctx.lineWidth = 1.2; ctx.beginPath();
        var s = false;
        for (var i = 0; i < depth.length && i < arr.length; i++) {
          if (arr[i] == null) continue;
          var x = x0 + ((arr[i] - min) / ((max - min) || 1)) * w;
          var y = pad.t + ((depth[i] - dMin) / ((dMax - dMin) || 1)) * ph;
          if (!s) { ctx.moveTo(x, y); s = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      drawTrack(ai, pad.l, pw * 0.33, '#58a6ff');
      drawTrack(rc, pad.l + pw * 0.35, pw * 0.2, '#f2cc60');
      drawTrack(syn, pad.l + pw * 0.58, pw * 0.38, '#f78166');
      var meta = document.getElementById('seismicTieMeta');
      if (meta) meta.textContent = 'Ricker ' + data.frequency_hz + ' Hz | samples: ' + depth.length;
    }
  };
})();