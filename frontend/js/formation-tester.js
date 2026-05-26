(function () {
  window.FormationTesterView = {
    async run() {
      if (!window.app || !app.currentWell) { GeoToast.warn('Select a well first'); return; }
      var data = await app._api('/wells/' + app.currentWell.id + '/formation-tester');
      this.render(data);
    },
    render: function (data) {
      var canvas = document.getElementById('formationTesterCanvas');
      if (!canvas) return;
      var W = canvas.parentElement.getBoundingClientRect().width, H = 560;
      canvas.width = W * 2; canvas.height = H * 2;
      var ctx = canvas.getContext('2d'); ctx.scale(2, 2);
      ctx.fillStyle = '#0b0f14'; ctx.fillRect(0, 0, W, H);
      var pts = data.points || [];
      if (pts.length < 2) return;
      var pad = { l: 60, r: 25, t: 20, b: 35 }, pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
      var dMin = Infinity, dMax = -Infinity, pMin = Infinity, pMax = -Infinity;
      pts.forEach(function (p) { dMin = Math.min(dMin, p.depth); dMax = Math.max(dMax, p.depth); pMin = Math.min(pMin, p.pressure || p.formation_pressure); pMax = Math.max(pMax, p.pressure || p.formation_pressure); });

      ctx.fillStyle = '#79c0ff';
      pts.forEach(function (p) {
        var pp = p.pressure || p.formation_pressure;
        var x = pad.l + ((pp - pMin) / ((pMax - pMin) || 1)) * pw;
        var y = pad.t + ((p.depth - dMin) / ((dMax - dMin) || 1)) * ph;
        ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill();
      });
      ctx.strokeStyle = '#8b949e';
      (data.contacts || []).forEach(function (c) {
        var y = pad.t + ((c.depth - dMin) / ((dMax - dMin) || 1)) * ph;
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + pw, y); ctx.stroke();
        ctx.fillStyle = '#f2cc60'; ctx.fillText(c.label + ' @ ' + c.depth.toFixed(1), pad.l + 6, y - 4);
      });

      var meta = document.getElementById('formationTesterMeta');
      if (meta) meta.textContent = 'Gradient: ' + ((data.overall || {}).gradient || 0).toFixed(3) + ' psi/ft | contacts: ' + (data.contacts || []).length;
    }
  };
})();