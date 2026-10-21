/* Shared modal and small helpers for the petrophysics workbench. */
(function () {
  const $ = (id) => document.getElementById(id);
  const PxModal = {
    _opts: null,
    open(opts) {
      this._opts = opts || {};
      $('pxModalTitle').textContent = this._opts.title || '';
      $('pxModalBody').innerHTML = this._opts.body || '';
      const foot = $('pxModalFoot');
      foot.innerHTML = '';
      const add = (label, cls, handler) => {
        if (!label) return;
        const b = document.createElement('button');
        b.type = 'button';
        b.className = `px-button ${cls}`;
        b.textContent = label;
        b.addEventListener('click', handler);
        foot.appendChild(b);
        return b;
      };
      add(this._opts.cancelLabel || 'Cancel', 'px-secondary', () => this.close());
      if (this._opts.secondaryLabel) add(this._opts.secondaryLabel, 'px-secondary', () => this._opts.onSecondary?.());
      if (this._opts.primaryLabel) add(this._opts.primaryLabel, 'px-primary', () => this._opts.onPrimary?.());
      $('pxModal').hidden = false;
      const focus = $('pxModalBody').querySelector('textarea, input, button');
      (focus || foot.querySelector('button'))?.focus();
    },
    close() {
      const modal = $('pxModal');
      if (!modal) return;
      modal.hidden = true;
      $('pxModalBody').innerHTML = '';
      $('pxModalFoot').innerHTML = '';
      this._opts = null;
    },
  };
  window.PxModal = PxModal;
  document.addEventListener('DOMContentLoaded', () => {
    $('pxModalClose')?.addEventListener('click', () => PxModal.close());
    $('pxModal')?.addEventListener('click', (e) => { if (e.target.id === 'pxModal') PxModal.close(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('pxModal')?.hidden) PxModal.close(); });
  });
})();
