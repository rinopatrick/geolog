(function () {
  var styles = [
    { color: '#58a6ff', dash: [] },
    { color: '#f78166', dash: [6, 4] },
    { color: '#3fb950', dash: [2, 4] },
    { color: '#d2a8ff', dash: [10, 3] }
  ];

  window.MultiWellView = {
    async load() {
      if (!window.app || !app.wells || app.wells.length < 2) {
        GeoToast.warn('Need at least 2 wells in project');
        return;
      }
      var sel = document.getElementById('multiWellSelector');
      if (sel && !sel.options.length) {
        sel.innerHTML = app.wells.map(function (w) {
          return '<option value="' + w.id + '">' + w.name + '</option>';
        }).join('');
        if (sel.options.length > 1) {
          sel.options[0].selected = true;
          sel.options[1].selected = true;
        }
      }
      await this.run();
    },

    async run() {
      var sel = document.getElementById('multiWellSelector');
      var curve = (document.getElementById('multiWellCurve') || {}).value || 'GR';
      if (!sel) return;
      var ids = [];
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].selected) ids.push(sel.options[i].value);
      }
      if (ids.length < 2) {
        GeoToast.warn('Select at least 2 wells');
        return;
      }
      var data = await app._api('/well-compare?ids=' + ids.join(','));
      this.render(data, curve);
    },

    render(data, curve) {
      var canvas = document.getElementById('multiWellCanvas');
      if (!canvas || !data || !data.wells) return;
      var W = canvas.parentElement.getBoundingClientRect().width;
      var H = 560;
      canvas.width = W * 2;
      canvas.height = H * 2;
      var ctx = canvas.getContext('2d');
      ctx.scale(2, 2);
      ctx.fillStyle = '#0b0f14';
      ctx.fillRect(0, 0, W, H);

      var pad = { l: 60, r: 20, t: 20, b: 40 };
      var pw = W - pad.l - pad.r;
      var ph = H - pad.t - pad.b;

      var dMin = Infinity, dMax = -Infinity, vMin = Infinity, vMax = -Infinity;
      data.wells.forEach(function (w) {
        var d = w.depth || [];
        var v = (w.curves || {})[curve] || [];
        for (var i = 0; i < d.length; i++) {
          var di = d[i], vi = v[i];
          if (di != null) { dMin = Math.min(dMin, di); dMax = Math.max(dMax, di); }
          if (vi != null) { vMin = Math.min(vMin, vi); vMax = Math.max(vMax, vi); }
        }
      });
      if (!isFinite(dMin) || !isFinite(vMin)) return;

      for (var g = 0; g <= 5; g++) {
        var y = pad.t + ph * g / 5;
        ctx.strokeStyle = 'rgba(80,90,110,0.4)';
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + pw, y); ctx.stroke();
      }

      data.wells.forEach(function (w, idx) {
        var st = styles[idx % styles.length];
        var d = w.depth || [];
        var v = (w.curves || {})[curve] || [];
        ctx.strokeStyle = st.color;
        ctx.lineWidth = 1.6;
        ctx.setLineDash(st.dash);
        ctx.beginPath();
        var started = false;
        for (var i = 0; i < d.length; i++) {
          if (d[i] == null || v[i] == null) continue;
          var x = pad.l + ((v[i] - vMin) / ((vMax - vMin) || 1)) * pw;
          var y = pad.t + ((d[i] - dMin) / ((dMax - dMin) || 1)) * ph;
          if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
        }
        ctx.stroke();
      });
      ctx.setLineDash([]);

      var legend = data.wells.map(function (w, i) {
        return '<span style="margin-right:10px;color:' + styles[i % styles.length].color + '">● ' + w.well_name + '</span>';
      }).join('');
      var stats = document.getElementById('multiWellLegend');
      if (stats) stats.innerHTML = '<strong>' + curve + '</strong> | ' + legend;
    }
  };
})();
