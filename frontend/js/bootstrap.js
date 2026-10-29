// Initialize
const app = new GeoLogApp();

// ─── Keyboard Shortcuts ────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    const targetTag = e.target?.tagName;
    const isTyping = targetTag === 'INPUT' || targetTag === 'TEXTAREA' || targetTag === 'SELECT';
    const views = ['viewer', 'crossplot', 'pickett', 'petrophysics', 'qc', 'statistics', 'correlation', 'sensitivity', 'facies'];

    switch (e.key) {
        case '1': case '2': case '3': case '4':
        case '5': case '6': case '7': case '8': case '9':
            if (isTyping) return;
            e.preventDefault();
            app.switchView(views[parseInt(e.key) - 1]);
            break;
        case 'ArrowUp':
            if (isTyping) return;
            if (!app.renderer) return;
            e.preventDefault();
            {
                const range = app.renderer.viewStop - app.renderer.viewStart;
                const shift = range * 0.25;
                app.renderer.setView(app.renderer.viewStart - shift, app.renderer.viewStop - shift);
            }
            break;
        case 'ArrowDown':
            if (isTyping) return;
            if (!app.renderer) return;
            e.preventDefault();
            {
                const range = app.renderer.viewStop - app.renderer.viewStart;
                const shift = range * 0.25;
                app.renderer.setView(app.renderer.viewStart + shift, app.renderer.viewStop + shift);
            }
            break;
        case '+': case '=':
            if (isTyping) return;
            if (!app.renderer) return;
            e.preventDefault();
            {
                const mid = (app.renderer.viewStart + app.renderer.viewStop) / 2;
                const newRange = (app.renderer.viewStop - app.renderer.viewStart) * 0.75;
                app.renderer.setView(mid - newRange / 2, mid + newRange / 2);
            }
            break;
        case '-':
            if (isTyping) return;
            if (!app.renderer) return;
            e.preventDefault();
            {
                const mid = (app.renderer.viewStart + app.renderer.viewStop) / 2;
                const newRange = (app.renderer.viewStop - app.renderer.viewStart) * 1.33;
                app.renderer.setView(mid - newRange / 2, mid + newRange / 2);
            }
            break;
        case 'Escape':
            if (GeoModal._resolve) { GeoModal.close(); }
            app.closeShortcutHelp();
            app.closeCmdPalette();
            app._closeAllNavGroups();
            break;
        case '?':
            if (isTyping) return;
            e.preventDefault();
            app.openShortcutHelp();
            break;
        case 'k':
            if (isTyping) return;
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                app.openCmdPalette();
            }
            break;
        case 'z':
            if (isTyping) return;
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                if (e.shiftKey) app.redo();
                else app.undo();
            }
            break;
        case 'y':
            if (isTyping) return;
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                app.redo();
            }
            break;
        case 's':
            if ((e.ctrlKey || e.metaKey) && !isTyping) {
                e.preventDefault();
                app._saveCurrentAnnotations();
            }
            break;
        case 'e':
            if ((e.ctrlKey || e.metaKey) && !isTyping) {
                e.preventDefault();
                app._exportLAS();
            }
            break;
        case 'u':
            if ((e.ctrlKey || e.metaKey) && !isTyping) {
                e.preventDefault();
                app.uploadLAS();
            }
            break;
        case 'Home':
            if (isTyping) return;
            e.preventDefault();
            app._jumpToWellBoundary(false);
            break;
        case 'End':
            if (isTyping) return;
            e.preventDefault();
            app._jumpToWellBoundary(true);
            break;
        case 'f':
        case 'F':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleFullscreenViewer();
            break;
        case 'l':
        case 'L':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app.toggleLithTrack();
            break;
        case 'd':
        case 'D':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleDetailsPanels();
            break;
        case 'a':
        case 'A':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._autoScale();
            break;
        case 'v':
        case 'V':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleAutoLithology();
            break;
        case 'c':
        case 'C':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleCoreOverlay();
            break;
        case 't':
        case 'T':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleDepthRulerPick();
            break;
        case 'r':
            if (isTyping) return;
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            if (app.renderer) app.renderer.render();
            GeoToast.info('Refreshed');
            break;
        case 'g':
        case 'G':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._showCurveLegend();
            break;
        case 'b':
        case 'B':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._toggleFormationLines();
            break;
        case 'e':
        case 'E':
            if (isTyping || e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            app._showRenderMetrics();
            break;

    }
});

// Expose the singleton so standalone modules can read the current role/token.
window.app = app;
