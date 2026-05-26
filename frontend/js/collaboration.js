/**
 * GeoLog — Real-Time Collaboration via WebSocket
 * Multi-user cursor sharing and edit broadcasting.
 */
(function () {
    window.CollabManager = {
        ws: null,
        wellId: null,
        userId: null,
        userName: null,
        connected: false,
        peers: {},       // { userId: { name, role, depth, color, lastSeen } }
        cursorEls: {},   // { userId: DOM element }
        _reconnectTimer: null,
        _colors: ['#58a6ff', '#f78166', '#3fb950', '#d2a8ff', '#f2cc60', '#ff7b72', '#79c0ff'],

        connect(wellId, userId, userName) {
            this.wellId = wellId;
            this.userId = userId || 'user_' + Math.random().toString(36).substr(2, 6);
            this.userName = userName || this.userId;
            this._disconnect();

            const proto = location.protocol === 'https:' ? 'wss' : 'ws';
            const url = `${proto}://${location.host}/ws/collab/${wellId}?user=${encodeURIComponent(this.userId)}&name=${encodeURIComponent(this.userName)}`;

            try {
                this.ws = new WebSocket(url);
                this.ws.onopen = () => this._onConnect();
                this.ws.onclose = () => this._onDisconnect();
                this.ws.onerror = () => this._onDisconnect();
                this.ws.onmessage = (e) => this._onMessage(e);
            } catch (err) {
                console.warn('Collab WebSocket error:', err);
                this._scheduleReconnect();
            }
        },

        _disconnect() {
            if (this.ws) {
                this.ws.onclose = null;
                this.ws.close();
                this.ws = null;
            }
            this.connected = false;
            this._updateIndicator();
        },

        _onConnect() {
            this.connected = true;
            this._updateIndicator();
            if (typeof GeoToast !== 'undefined') GeoToast.info('Collaboration connected');
        },

        _onDisconnect() {
            this.connected = false;
            this._updateIndicator();
            this._scheduleReconnect();
        },

        _scheduleReconnect() {
            if (this._reconnectTimer) return;
            this._reconnectTimer = setTimeout(() => {
                this._reconnectTimer = null;
                if (this.wellId) this.connect(this.wellId, this.userId, this.userName);
            }, 5000);
        },

        _onMessage(e) {
            let msg;
            try { msg = JSON.parse(e.data); } catch { return; }

            switch (msg.type) {
                case 'peers':
                    this.peers = {};
                    (msg.users || []).forEach(u => {
                        if (u.user_id !== this.userId) {
                            this.peers[u.user_id] = {
                                name: u.name || u.user_id,
                                role: u.role || 'viewer',
                                depth: u.cursor_depth,
                                color: this._colors[Object.keys(this.peers).length % this._colors.length],
                                lastSeen: Date.now(),
                            };
                        }
                    });
                    this._renderPeerCursors();
                    this._renderPeerList();
                    break;

                case 'cursor_move':
                    if (msg.user_id === this.userId) return;
                    if (!this.peers[msg.user_id]) {
                        this.peers[msg.user_id] = {
                            name: msg.name || msg.user_id,
                            color: this._colors[Object.keys(this.peers).length % this._colors.length],
                        };
                    }
                    this.peers[msg.user_id].depth = msg.depth;
                    this.peers[msg.user_id].lastSeen = Date.now();
                    this._renderPeerCursors();
                    break;

                case 'edit':
                    if (msg.user_id === this.userId) return;
                    if (typeof GeoToast !== 'undefined') {
                        GeoToast.info(`${msg.name || msg.user_id} edited ${msg.target}`);
                    }
                    break;
            }
        },

        sendCursorMove(depth) {
            if (!this.connected || !this.ws) return;
            this.ws.send(JSON.stringify({ type: 'cursor_move', depth }));
        },

        sendEdit(target, data) {
            if (!this.connected || !this.ws) return;
            this.ws.send(JSON.stringify({ type: 'edit', target, data }));
        },

        _renderPeerCursors() {
            if (!window.app || !app.renderer) return;
            const renderer = app.renderer;
            const container = renderer.canvas.parentElement;
            if (!container) return;

            // Remove stale cursors
            for (const uid of Object.keys(this.cursorEls)) {
                if (!this.peers[uid] || Date.now() - this.peers[uid].lastSeen > 30000) {
                    this.cursorEls[uid]?.remove();
                    delete this.cursorEls[uid];
                }
            }

            for (const [uid, peer] of Object.entries(this.peers)) {
                if (peer.depth == null) continue;
                if (peer.depth < renderer.viewStart || peer.depth > renderer.viewStop) {
                    if (this.cursorEls[uid]) this.cursorEls[uid].style.display = 'none';
                    continue;
                }

                let el = this.cursorEls[uid];
                if (!el) {
                    el = document.createElement('div');
                    el.style.cssText = 'position:absolute;left:0;right:0;height:2px;pointer-events:none;z-index:5;transition:top 0.15s';
                    el.innerHTML = `<span style="position:absolute;left:4px;top:-16px;font-size:9px;padding:1px 4px;border-radius:3px;white-space:nowrap">${peer.name || uid}</span>`;
                    container.appendChild(el);
                    this.cursorEls[uid] = el;
                }

                const plotTop = renderer.margin.top;
                const plotBottom = renderer.height - renderer.margin.bottom;
                const plotHeight = plotBottom - plotTop;
                const y = plotTop + ((peer.depth - renderer.viewStart) / (renderer.viewStop - renderer.viewStart)) * plotHeight;
                el.style.display = 'block';
                el.style.top = y + 'px';
                el.style.background = peer.color || '#58a6ff';
                el.querySelector('span').style.background = peer.color || '#58a6ff';
                el.querySelector('span').style.color = '#fff';
            }
        },

        _renderPeerList() {
            const el = document.getElementById('collabPeerList');
            if (!el) return;
            const count = Object.keys(this.peers).length;
            if (count === 0) {
                el.innerHTML = '<span style="color:#8b949e;font-size:11px">No other users</span>';
                return;
            }
            el.innerHTML = Object.entries(this.peers).map(([uid, p]) =>
                `<span style="display:inline-flex;align-items:center;gap:4px;margin-right:8px;font-size:11px">
                    <span style="width:8px;height:8px;border-radius:50%;background:${p.color || '#58a6ff'}"></span>
                    ${p.name || uid} (${p.role || 'viewer'})
                </span>`
            ).join('');
        },

        _updateIndicator() {
            const dot = document.getElementById('collabStatusDot');
            if (dot) {
                dot.style.background = this.connected ? '#3fb950' : '#f85149';
                dot.title = this.connected ? 'Connected' : 'Disconnected';
            }
        },

        destroy() {
            this._disconnect();
            for (const el of Object.values(this.cursorEls)) el.remove();
            this.cursorEls = {};
            this.peers = {};
        }
    };
})();
