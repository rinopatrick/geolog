/**
 * Correlation, tops-tie and marker-picking methods for GeoLogApp.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
    async _loadCorrelationProfile() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        try {
            const curve = document.getElementById('corrCurve')?.value || 'GR';
            const p = await this._api(`/correlation-profile?well_a_id=${wellAId}&well_b_id=${wellBId}&curve=${curve}`);
            const shiftInput = document.getElementById('corrShift');
            const stretchInput = document.getElementById('corrStretch');
            const snapInput = document.getElementById('corrSnapTops');
            if (shiftInput) shiftInput.value = (p.depth_shift ?? 0).toFixed(1);
            if (stretchInput) stretchInput.value = (p.stretch ?? 1).toFixed(3);
            if (snapInput) snapInput.checked = !!p.snap_to_tops;
        } catch (e) {
            console.error('Failed to load correlation profile:', e);
        }
    },

    async _saveCorrelationProfile() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        const curve = document.getElementById('corrCurve')?.value || 'GR';
        const shift = parseFloat(document.getElementById('corrShift')?.value || '0') || 0;
        const stretch = parseFloat(document.getElementById('corrStretch')?.value || '1') || 1;
        const snap = document.getElementById('corrSnapTops')?.checked ? 1 : 0;
        await this._api('/correlation-profile', {
            method: 'POST',
            body: JSON.stringify({ well_a_id: wellAId, well_b_id: wellBId, curve, depth_shift: shift, stretch, snap_to_tops: snap }),
        });
    },

    _populateCorrelationWellSelectors() {
        const a = document.getElementById('corrWellA');
        const b = document.getElementById('corrWellB');
        if (!a || !b) return;
        const opts = this.wells.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('');
        a.innerHTML = opts;
        b.innerHTML = opts;
        if (this.wells.length > 0) a.value = String(this.wells[0].id);
        if (this.wells.length > 1) b.value = String(this.wells[1].id);
        else if (this.wells.length > 0) b.value = String(this.wells[0].id);
    },

    _currentCorrPair() {
        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        return { wellAId, wellBId };
    },

    async _loadCorrelationMarkers() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        try {
            this.corrMarkers = await this._api(`/correlation-markers?well_a_id=${wellAId}&well_b_id=${wellBId}`);
        } catch {
            this.corrMarkers = [];
        }
    },

    async _saveCorrelationMarkers() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        await this._api('/correlation-markers', {
            method: 'POST',
            body: JSON.stringify({ well_a_id: wellAId, well_b_id: wellBId, markers: this.corrMarkers || [] }),
        });
    },

    _curveFamilyLabel(mnemonic) {
        const m = (mnemonic || '').toUpperCase();
        if (['GR','SGR','CGR'].includes(m)) return 'GR-family';
        if (['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'].includes(m)) return 'RT-family';
        if (['NPHI','NPHI_LS'].includes(m)) return 'NPHI-family';
        if (['RHOB','RHOZ'].includes(m)) return 'RHOB-family';
        if (['DT','DTC','DTP','DTS'].includes(m)) return 'DT-family';
        if (['CAL','CALI','HCAL'].includes(m)) return 'CAL-family';
        return 'OTHER';
    },

    _corrTopQualityColor(top) {
        const q = String(top?.quality ?? top?.confidence ?? top?.rank ?? '').toLowerCase().trim();
        if (q === 'good' || q === 'high' || q === 'a') return '#3fb950';
        if (q === 'fair' || q === 'medium' || q === 'b') return '#d29922';
        if (q === 'poor' || q === 'low' || q === 'c') return '#f85149';
        return top?.color || '#8b949e';
    },

    _corrNormalizeTopName(name) {
        return String(name || '').trim().toLowerCase();
    },

    async _loadCorrelationTops(wellAId, wellBId) {
        try {
            const [topsA, topsB] = await Promise.all([
                this._api(`/wells/${wellAId}/tops`),
                this._api(`/wells/${wellBId}/tops`),
            ]);
            const parse = (arr = [], wellKey = 'A') => arr
                .map((t, idx) => {
                    const depth = Number(t.top_depth ?? t.depth);
                    if (!Number.isFinite(depth)) return null;
                    const name = t.formation_name || t.name || `Top ${idx + 1}`;
                    return {
                        id: t.id || `${wellKey}-${idx}-${name}`,
                        name,
                        nameKey: this._corrNormalizeTopName(name),
                        depth,
                        wellKey,
                        quality: t.quality ?? null,
                        color: this._corrTopQualityColor(t),
                        raw: t,
                    };
                })
                .filter(Boolean)
                .sort((x, y) => x.depth - y.depth);

            this._corrTopOverlay = { a: parse(topsA, 'A'), b: parse(topsB, 'B') };
            this._corrTopCache = {
                a: this._corrTopOverlay.a.map(t => t.depth),
                b: this._corrTopOverlay.b.map(t => t.depth),
            };
        } catch (e) {
            console.error('Failed to load correlation tops:', e);
            this._corrTopOverlay = { a: [], b: [] };
            this._corrTopCache = { a: [], b: [] };
        }
    },

    toggleCorrelationTops() {
        this.corrShowTops = !this.corrShowTops;
        const btn = document.getElementById('corrShowTops');
        if (btn) {
            btn.classList.toggle('active', this.corrShowTops);
            btn.setAttribute('aria-pressed', this.corrShowTops ? 'true' : 'false');
        }
        this.renderCorrelation();
    },

    async renderCorrelation() {
        const canvas = document.getElementById('correlationCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 500;

        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const requestedCurve = document.getElementById('corrCurve')?.value || 'GR';
        const shift = parseFloat(document.getElementById('corrShift')?.value || '0');
        const stretch = parseFloat(document.getElementById('corrStretch')?.value || '1') || 1;
        const snapToTops = !!document.getElementById('corrSnapTops')?.checked;

        if (!wellAId || !wellBId) {
            ctx.fillStyle='#8b949e'; ctx.font='14px DM Sans'; ctx.fillText('Select wells', 40, 40); return;
        }

        const pairKey = `${wellAId}:${wellBId}`;
        if (this._corrLoadedKey !== pairKey) {
            await this._loadCorrelationMarkers();
            await this._loadCorrelationProfile();
            this._corrLoadedKey = pairKey;
        }

        const [wa, wb] = await Promise.all([
            this._api(`/wells/${wellAId}`),
            this._api(`/wells/${wellBId}`),
        ]);
        await this._loadCorrelationTops(wellAId, wellBId);
        const runA = this._activeLogRunForWell(wa);
        const runB = this._activeLogRunForWell(wb);
        if (!runA || !runB) {
            ctx.fillStyle='#8b949e'; ctx.font='14px DM Sans'; ctx.fillText('Both wells need log runs', 40, 40); return;
        }

        const da = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
        const db = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});

        let valsA = da[requestedCurve] || [];
        let valsB = db[requestedCurve] || [];
        let actualCurve = requestedCurve;

        if (!valsA.length || !valsB.length) {
            const fallbackFamilies = {
                RT: ['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'],
                GR: ['GR','SGR','CGR'],
                NPHI: ['NPHI','NPHI_LS'],
                RHOB: ['RHOB','RHOZ'],
            };
            const candidates = fallbackFamilies[requestedCurve] || [requestedCurve];
            for (const cand of candidates) {
                if (cand === requestedCurve) continue;
                const daCand = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
                const dbCand = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});
                if ((daCand[cand] || []).length && (dbCand[cand] || []).length) {
                    valsA = daCand[cand];
                    valsB = dbCand[cand];
                    actualCurve = cand;
                    break;
                }
            }
        }

        const depthA = da.DEPTH || [];
        const rawDepthB = db.DEPTH || [];
        const midB = rawDepthB.length ? (rawDepthB[0] + rawDepthB[rawDepthB.length - 1]) / 2 : 0;
        let depthB = rawDepthB.map(d => (d - midB) * stretch + midB + shift);
        if (snapToTops && this._corrTopCache.a.length && this._corrTopCache.b.length) {
            depthB = this._applyTopSnapDepths(depthB, this._corrTopCache.a, this._corrTopCache.b, shift);
        }
        if (!depthA.length || !depthB.length) { ctx.fillStyle='#8b949e'; ctx.fillText('No data', 40, 40); return; }

        const xMin = Math.min(depthA[0], depthB[0]), xMax = Math.max(depthA[depthA.length-1], depthB[depthB.length-1]);
        const allVals = [...valsA.filter(v=>v!=null), ...valsB.filter(v=>v!=null)];
        let yMin = Infinity, yMax = -Infinity;
        for (const v of allVals) { if (v < yMin) yMin = v; if (v > yMax) yMax = v; }
        if (!isFinite(yMin)) { yMin = 0; yMax = 1; }

        const m={top:30,right:30,bottom:45,left:60}, w=canvas.width-m.left-m.right, h=canvas.height-m.top-m.bottom;
        const sx=v=>m.left+((v-xMin)/(xMax-xMin))*w;
        const sy=v=>m.top+h-((v-yMin)/(yMax-yMin))*h;

        ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.strokeStyle='#21262d'; for(let i=0;i<=8;i++){const x=m.left+w*i/8; ctx.beginPath(); ctx.moveTo(x,m.top); ctx.lineTo(x,m.top+h); ctx.stroke();}
        for(let i=0;i<=6;i++){const y=m.top+h*i/6; ctx.beginPath(); ctx.moveTo(m.left,y); ctx.lineTo(m.left+w,y); ctx.stroke();}

        const draw=(depth,val,color)=>{ ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.beginPath(); let st=false; for(let i=0;i<Math.min(depth.length,val.length);i++){ const v=val[i]; if(v==null||isNaN(v)) continue; const x=sx(depth[i]), y=sy(v); if(!st){ctx.moveTo(x,y); st=true;} else ctx.lineTo(x,y);} ctx.stroke(); };
        draw(depthA, valsA, '#58a6ff');
        draw(depthB, valsB, '#f85149');

        const topHitZones = [];
        if (this.corrShowTops) {
            const topsToDraw = [];
            for (const t of (this._corrTopOverlay.a || [])) {
                topsToDraw.push({ key: `A:${t.id}`, label: t.name, xDepth: t.depth, color: t.color, well: 'A' });
            }
            for (const t of (this._corrTopOverlay.b || [])) {
                topsToDraw.push({ key: `B:${t.id}`, label: t.name, xDepth: ((t.depth - midB) * stretch + midB + shift), color: t.color, well: 'B' });
            }
            ctx.setLineDash([7, 5]);
            topsToDraw.forEach((t, i) => {
                const x = sx(t.xDepth);
                if (x < m.left || x > m.left + w) return;
                const selected = this.corrSelectedTop === t.key;
                ctx.strokeStyle = selected ? '#ffffff' : t.color;
                ctx.lineWidth = selected ? 2.2 : 1.2;
                ctx.beginPath();
                ctx.moveTo(x, m.top);
                ctx.lineTo(x, m.top + h);
                ctx.stroke();

                if (i < 18) {
                    ctx.save();
                    ctx.translate(x + 2, m.top + 4 + (i % 2) * 12);
                    ctx.rotate(-Math.PI / 2);
                    ctx.fillStyle = selected ? '#ffffff' : t.color;
                    ctx.font = selected ? 'bold 10px DM Sans' : '10px DM Sans';
                    ctx.fillText(`${t.label} (${t.well})`, 0, 0);
                    ctx.restore();
                }
                topHitZones.push({ key: t.key, x, label: t.label, well: t.well });
            });
            ctx.setLineDash([]);
        }

        const corrActive = document.getElementById('corrActiveCurve');
        if (corrActive) {
            corrActive.textContent = actualCurve === requestedCurve
                ? `using ${actualCurve}`
                : `requested ${requestedCurve} -> using ${actualCurve}`;
        }

        ctx.fillStyle='#c9d1d9'; ctx.font='12px DM Sans'; ctx.fillText(`Correlation curve: ${actualCurve}`, m.left, 16);
        ctx.fillStyle='#58a6ff'; ctx.fillText(`A: ${wa.name}`, m.left+220, 16);
        ctx.fillStyle='#f85149'; ctx.fillText(`B: ${wb.name} (shift ${shift} ft)`, m.left+360, 16);
        ctx.fillStyle='#c9d1d9'; ctx.fillText('Depth', m.left+w/2, canvas.height-10);

        // Save render context for marker picking
        this.corrLastRender = { m, w, h, xMin, xMax, yMin, yMax, shift, stretch, midB, waName: wa.name, wbName: wb.name, topHitZones };

        // Draw marker ties (interactive handles)
        const markerHitZones = [];
        this.corrMarkers.forEach((mk, idx) => {
            const xA = sx(mk.aDepth);
            const xB = sx(((mk.bDepth - midB) * stretch + midB + shift));
            const yTop = m.top + 10 + (idx % 6) * 16;
            const draggingA = this._corrDragState && this._corrDragState.markerIdx === idx && this._corrDragState.endpoint === 'a';
            const draggingB = this._corrDragState && this._corrDragState.markerIdx === idx && this._corrDragState.endpoint === 'b';

            ctx.strokeStyle = draggingA ? '#ffd33d' : '#f2cc60';
            ctx.setLineDash([4,3]);
            ctx.beginPath(); ctx.moveTo(xA, m.top); ctx.lineTo(xA, m.top+h); ctx.stroke();
            ctx.strokeStyle = draggingB ? '#ff6b6b' : '#ff7b72';
            ctx.beginPath(); ctx.moveTo(xB, m.top); ctx.lineTo(xB, m.top+h); ctx.stroke();
            ctx.setLineDash([]);

            // Endpoints (draggable handles)
            const handleY = m.top + h - 10;
            ctx.beginPath();
            ctx.arc(xA, handleY, 5, 0, Math.PI * 2);
            ctx.fillStyle = draggingA ? '#ffd33d' : '#f2cc60';
            ctx.fill();
            ctx.beginPath();
            ctx.arc(xB, handleY, 5, 0, Math.PI * 2);
            ctx.fillStyle = draggingB ? '#ff6b6b' : '#ff7b72';
            ctx.fill();

            ctx.strokeStyle = '#8b949e';
            ctx.beginPath(); ctx.moveTo(xA, yTop); ctx.lineTo(xB, yTop); ctx.stroke();
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '10px IBM Plex Mono';
            ctx.fillText(`M${idx+1} Δ=${(mk.aDepth - mk.bDepth).toFixed(1)}ft`, Math.min(xA,xB)+4, yTop-2);

            markerHitZones.push({ markerIdx: idx, endpoint: 'a', x: xA, y: handleY, r: 8 });
            markerHitZones.push({ markerIdx: idx, endpoint: 'b', x: xB, y: handleY, r: 8 });
        });

        this.corrLastRender.markerHitZones = markerHitZones;
        this._renderCorrelationMarkerTable();
    },

    async autoTieShift() {
        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const requestedCurve = document.getElementById('corrCurve')?.value || 'GR';
        const info = document.getElementById('corrInfo');
        if (!wellAId || !wellBId) return;

        const [wa, wb] = await Promise.all([
            this._api(`/wells/${wellAId}`),
            this._api(`/wells/${wellBId}`),
        ]);
        await this._loadCorrelationTops(wellAId, wellBId);
        const runA = this._activeLogRunForWell(wa);
        const runB = this._activeLogRunForWell(wb);
        if (!runA || !runB) return;

        const da = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
        const db = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});

        let valsA = da[requestedCurve] || [];
        let valsB = db[requestedCurve] || [];
        let actualCurve = requestedCurve;
        if (!valsA.length || !valsB.length) {
            const fallbackFamilies = {
                RT: ['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'],
                GR: ['GR','SGR','CGR'],
                NPHI: ['NPHI','NPHI_LS'],
                RHOB: ['RHOB','RHOZ'],
            };
            const candidates = fallbackFamilies[requestedCurve] || [requestedCurve];
            for (const cand of candidates) {
                if (cand === requestedCurve) continue;
                const daCand = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
                const dbCand = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});
                if ((daCand[cand] || []).length && (dbCand[cand] || []).length) {
                    valsA = daCand[cand];
                    valsB = dbCand[cand];
                    actualCurve = cand;
                    break;
                }
            }
        }

        const depthA = da.DEPTH || [], depthB0 = db.DEPTH || [];
        if (!depthA.length || !depthB0.length || !valsA.length || !valsB.length) return;

        const mean = a => a.reduce((s,v)=>s+v,0)/a.length;
        const normalize = arr => {
            const v = arr.filter(x=>x!=null && !isNaN(x));
            if (!v.length) return arr;
            const m = mean(v); const sd = Math.sqrt(v.reduce((s,x)=>s+(x-m)**2,0)/v.length) || 1;
            return arr.map(x => (x==null||isNaN(x)) ? null : (x-m)/sd);
        };
        const aN = normalize(valsA), bN = normalize(valsB);

        const interpAt = (depths, vals, d) => {
            // nearest-neighbor for speed
            let lo=0, hi=depths.length-1;
            while (lo<hi){ const mid=(lo+hi)>>1; if (depths[mid]<d) lo=mid+1; else hi=mid; }
            const i = Math.max(0, Math.min(depths.length-1, lo));
            return vals[i];
        };

        let bestShift = 0, bestScore = -1e9;
        let bestPairs = 0;
        const minPairs = 30;
        for (let sh=-100; sh<=100; sh+=0.5) {
            let n=0, sxy=0;
            for (let i=0;i<depthA.length;i+=3) {
                const a = aN[i];
                if (a==null) continue;
                const b = interpAt(depthB0, bN, depthA[i]-sh);
                if (b==null) continue;
                sxy += a*b; n++;
            }
            if (n < minPairs) continue;
            const score = sxy/n;
            if (score > bestScore) { bestScore = score; bestShift = sh; bestPairs = n; }
        }

        const shiftInput = document.getElementById('corrShift');
        if (shiftInput) shiftInput.value = bestShift.toFixed(1);
        const corrActive = document.getElementById('corrActiveCurve');
        if (corrActive) {
            corrActive.textContent = actualCurve === requestedCurve
                ? `using ${actualCurve}`
                : `requested ${requestedCurve} -> using ${actualCurve}`;
        }
        if (info) {
            if (bestPairs < minPairs || !isFinite(bestScore) || bestScore < -1e8) {
                info.textContent = `AutoTie (${actualCurve}): low confidence (pairs<${minPairs}). Keep manual marker ties.`;
            } else {
                info.textContent = `AutoTie (${actualCurve}): shift ${bestShift.toFixed(1)} ft, score ${bestScore.toFixed(3)}, pairs ${bestPairs}`;
            }
        }
        await this.renderCorrelation();
    },

    _applyTopSnapDepths(depthB, topsA, topsB, shift) {
        if (!depthB.length || !topsA.length || !topsB.length) return depthB;
        const maxPairs = Math.min(topsA.length, topsB.length, 6);
        if (maxPairs < 2) return depthB;
        let biasSum = 0;
        let n = 0;
        for (let i = 0; i < maxPairs; i++) {
            const d = topsA[i] - (topsB[i] + shift);
            if (!Number.isFinite(d)) continue;
            biasSum += d;
            n += 1;
        }
        if (!n) return depthB;
        const bias = biasSum / n;
        return depthB.map(d => d + bias);
    },

    applyTopSnap() {
        const info = document.getElementById('corrInfo');
        if (!this._corrTopCache?.a?.length || !this._corrTopCache?.b?.length) {
            if (info) info.textContent = 'Top Snap skipped: missing tops on one/both wells';
            return;
        }
        const shiftInput = document.getElementById('corrShift');
        const shift = parseFloat(shiftInput?.value || '0') || 0;
        const maxPairs = Math.min(this._corrTopCache.a.length, this._corrTopCache.b.length, 6);
        let sumDelta = 0;
        let n = 0;
        for (let i = 0; i < maxPairs; i++) {
            const d = this._corrTopCache.a[i] - (this._corrTopCache.b[i] + shift);
            if (!Number.isFinite(d)) continue;
            sumDelta += d;
            n += 1;
        }
        if (!n) return;
        const extraShift = sumDelta / n;
        if (shiftInput) shiftInput.value = (shift + extraShift).toFixed(1);
        if (info) info.textContent = `Top Snap applied from ${n} top pairs: Δshift ${extraShift.toFixed(1)} ft`;
        this.renderCorrelation();
    },

    _normalizeTopName(name) {
        const raw = (name || '').toLowerCase();
        const synonyms = [
            [/\bformation\b/g, 'fm'],
            [/\bmember\b/g, 'mbr'],
            [/\btop\b/g, 'top'],
            [/\bbase\b/g, 'base'],
            [/\bupper\b/g, 'up'],
            [/\blower\b/g, 'lo'],
            [/\bmiddle\b/g, 'mid'],
            [/\bsandstone\b/g, 'sand'],
            [/\bshale\b/g, 'sh'],
            [/\blimestone\b/g, 'ls'],
            [/\bdolomite\b/g, 'dol'],
        ];
        let n = raw;
        synonyms.forEach(([re, rep]) => { n = n.replace(re, rep); });
        return n.replace(/[^a-z0-9]+/g, ' ').trim();
    },

    _tokenSet(s) {
        return new Set((s || '').split(' ').filter(Boolean));
    },

    _jaccard(a, b) {
        const sa = this._tokenSet(a);
        const sb = this._tokenSet(b);
        if (!sa.size || !sb.size) return 0;
        let inter = 0;
        sa.forEach(t => { if (sb.has(t)) inter += 1; });
        const uni = new Set([...sa, ...sb]).size;
        return uni ? inter / uni : 0;
    },

    _bestTopMatch(nameA, topsB) {
        let best = null;
        let bestScore = 0;
        for (const tb of topsB) {
            const score = this._jaccard(nameA, tb.n);
            if (score > bestScore) {
                bestScore = score;
                best = tb;
            }
        }
        return bestScore >= 0.5 ? { ...best, score: bestScore } : null;
    },

    applyTopNameTie() {
        const info = document.getElementById('corrInfo');
        const shiftInput = document.getElementById('corrShift');
        const waId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wbId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const wa = this.wells.find(w => w.id === waId);
        const wb = this.wells.find(w => w.id === wbId);
        if (!wa || !wb) return;
        Promise.all([this._api(`/wells/${waId}`), this._api(`/wells/${wbId}`)]).then(([a, b]) => {
            const topsA = (a.formation_tops || []).map(t => ({ raw: t.formation_name || '', n: this._normalizeTopName(t.formation_name), d: Number(t.top_depth ?? t.depth) })).filter(x => x.n && Number.isFinite(x.d));
            const topsB = (b.formation_tops || []).map(t => ({ raw: t.formation_name || '', n: this._normalizeTopName(t.formation_name), d: Number(t.top_depth ?? t.depth) })).filter(x => x.n && Number.isFinite(x.d));

            const deltas = [];
            let exact = 0;
            let fuzzy = 0;
            topsA.forEach(t => {
                const exactHit = topsB.find(x => x.n === t.n);
                if (exactHit) {
                    deltas.push(t.d - exactHit.d);
                    exact += 1;
                    return;
                }
                const fuzzyHit = this._bestTopMatch(t.n, topsB);
                if (fuzzyHit) {
                    deltas.push(t.d - fuzzyHit.d);
                    fuzzy += 1;
                }
            });
            if (!deltas.length) {
                if (info) info.textContent = 'Name Tie skipped: no exact/fuzzy top matches';
                return;
            }
            deltas.sort((x,y)=>x-y);
            const mid = Math.floor(deltas.length/2);
            const med = deltas.length % 2 ? deltas[mid] : (deltas[mid-1] + deltas[mid]) / 2;
            if (shiftInput) shiftInput.value = med.toFixed(1);
            if (info) info.textContent = `Name Tie: ${deltas.length} matches (exact ${exact}, fuzzy ${fuzzy}), median shift ${med.toFixed(1)} ft`;
            this.renderCorrelation();
        }).catch(err => {
            if (info) info.textContent = `Name Tie error: ${err.message || err}`;
        });
    },

    async saveCorrelationSettings() {
        await this._saveCorrelationProfile();
        GeoToast.success('Correlation profile saved');
    },

    startMarkerPick() {
        this.corrPickMode = true;
        this._corrPickTemp = null;
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Pick mode: click depth for Well A, then click depth for Well B';
    },

    async clearMarkers() {
        this.corrMarkers = [];
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Markers cleared';
        this._renderCorrelationMarkerTable();
        await this._saveCorrelationMarkers();
        this.renderCorrelation();
    },

    _calcMarkerShift(method = 'median') {
        if (!this.corrMarkers.length) return null;
        const deltas = this.corrMarkers.map(m => m.aDepth - m.bDepth).sort((a,b) => a-b);
        if (method === 'mean') {
            return deltas.reduce((s, v) => s + v, 0) / deltas.length;
        }
        const mid = Math.floor(deltas.length / 2);
        return deltas.length % 2 ? deltas[mid] : (deltas[mid - 1] + deltas[mid]) / 2;
    },

    applyMarkerShift(method = 'median') {
        const shift = this._calcMarkerShift(method);
        const info = document.getElementById('corrInfo');
        if (shift == null) {
            if (info) info.textContent = 'No markers yet. Pick markers first.';
            return;
        }
        const shiftInput = document.getElementById('corrShift');
        if (shiftInput) shiftInput.value = shift.toFixed(1);
        if (info) info.textContent = `Applied ${method} marker shift: ${shift.toFixed(1)} ft`;
        this.renderCorrelation();
    },

    _renderCorrelationMarkerTable() {
        const el = document.getElementById('corrMarkerTable');
        if (!el) return;
        if (!this.corrMarkers.length) {
            el.innerHTML = '<p style="color:#8b949e">No marker ties yet. Use <b>Pick Marker</b> to add A/B depth ties.</p>';
            return;
        }

        const rows = this.corrMarkers.map((m, idx) => {
            const d = m.aDepth - m.bDepth;
            return `<div class="stats-row"><span>M${idx + 1}</span><span>A ${m.aDepth.toFixed(1)} ft</span><span>B ${m.bDepth.toFixed(1)} ft</span><span>Δ ${d.toFixed(1)} ft</span></div>`;
        }).join('');
        const median = this._calcMarkerShift('median');
        const mean = this._calcMarkerShift('mean');
        el.innerHTML = `
            <div class="stats-card">
                <h4>Manual Marker Ties (${this.corrMarkers.length})</h4>
                ${rows}
                <div class="stats-row"><strong>Median Δ</strong><strong>${median.toFixed(1)} ft</strong></div>
                <div class="stats-row"><strong>Mean Δ</strong><strong>${mean.toFixed(1)} ft</strong></div>
            </div>
        `;
    },

    _onCorrelationCanvasClick(ev) {
        if (this._corrDragMoved) {
            this._corrDragMoved = false;
            return;
        }
        if (!this.corrLastRender) return;
        const cv = document.getElementById('correlationCanvas');
        if (!cv) return;
        const rect = cv.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const { m, w, xMin, xMax, shift, stretch, midB, topHitZones = [] } = this.corrLastRender;
        if (x < m.left || x > m.left + w) return;

        if (!this.corrPickMode && this.corrShowTops && topHitZones.length) {
            let best = null;
            for (const z of topHitZones) {
                const dx = Math.abs(z.x - x);
                if (dx <= 8 && (!best || dx < best.dx)) best = { ...z, dx };
            }
            if (best) {
                this.corrSelectedTop = best.key;
                const infoTop = document.getElementById('corrInfo');
                if (infoTop) infoTop.textContent = `Selected top: ${best.label} (${best.well})`;
                this.renderCorrelation();
                return;
            }
        }

        if (!this.corrPickMode) return;

        const depth = xMin + ((x - m.left) / w) * (xMax - xMin);
        const info = document.getElementById('corrInfo');

        if (this._corrPickTemp == null) {
            this._corrPickTemp = depth;
            if (info) info.textContent = `Marker A picked @ ${depth.toFixed(1)} ft. Now click marker B depth.`;
        } else {
            const aDepth = this._corrPickTemp;
            const bDepth = ((depth - shift - midB) / (stretch || 1)) + midB;
            this.corrMarkers.push({ aDepth, bDepth });
            this._corrPickTemp = null;
            const localShift = aDepth - bDepth;
            if (info) info.textContent = `Marker tie added. Local shift Δ=${localShift.toFixed(1)} ft`;
            this._saveCorrelationMarkers().catch(() => {});
            this.renderCorrelation();
        }
    },

    _nearestCorrTopDepth(wellKey, depth) {
        const arr = (wellKey === 'a' ? this._corrTopOverlay?.a : this._corrTopOverlay?.b) || [];
        if (!arr.length || !Number.isFinite(depth)) return depth;
        let best = depth;
        let minD = Infinity;
        for (const t of arr) {
            const d = Number(t.depth);
            if (!Number.isFinite(d)) continue;
            const delta = Math.abs(d - depth);
            if (delta < minD) { minD = delta; best = d; }
        }
        // snap threshold 6 ft
        return minD <= 6 ? best : depth;
    },

    _onCorrelationCanvasMouseDown(ev) {
        if (!this.corrLastRender || !this.corrLastRender.markerHitZones?.length) return;
        const cv = document.getElementById('correlationCanvas');
        if (!cv) return;
        const rect = cv.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        for (const z of this.corrLastRender.markerHitZones) {
            const dx = x - z.x;
            const dy = y - z.y;
            if ((dx * dx + dy * dy) <= (z.r * z.r)) {
                this._corrDragState = { markerIdx: z.markerIdx, endpoint: z.endpoint, startX: x };
                this._corrDragMoved = false;
                cv.style.cursor = 'ew-resize';
                ev.preventDefault();
                return;
            }
        }
    },

    _onCorrelationCanvasMouseMove(ev) {
        const cv = document.getElementById('correlationCanvas');
        if (!cv || !this.corrLastRender) return;
        const rect = cv.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;

        // hover cursor
        if (!this._corrDragState && this.corrLastRender.markerHitZones?.length) {
            let hit = false;
            for (const z of this.corrLastRender.markerHitZones) {
                const dx = x - z.x;
                const dy = y - z.y;
                if ((dx * dx + dy * dy) <= (z.r * z.r)) { hit = true; break; }
            }
            cv.style.cursor = hit ? 'ew-resize' : 'default';
        }

        if (!this._corrDragState) return;
        this._corrDragMoved = true;
        const { m, w, xMin, xMax, shift, stretch, midB } = this.corrLastRender;
        const clampedX = Math.max(m.left, Math.min(m.left + w, x));
        const depthView = xMin + ((clampedX - m.left) / w) * (xMax - xMin);
        const mk = this.corrMarkers[this._corrDragState.markerIdx];
        if (!mk) return;

        if (this._corrDragState.endpoint === 'a') {
            let d = depthView;
            if (document.getElementById('corrSnapTops')?.checked) d = this._nearestCorrTopDepth('a', d);
            mk.aDepth = d;
        } else {
            let bDepth = ((depthView - shift - midB) / (stretch || 1)) + midB;
            if (document.getElementById('corrSnapTops')?.checked) bDepth = this._nearestCorrTopDepth('b', bDepth);
            mk.bDepth = bDepth;
        }
        this.renderCorrelation();
    },

    _onCorrelationCanvasMouseUp(ev) {
        const cv = document.getElementById('correlationCanvas');
        if (cv) cv.style.cursor = 'default';
        if (!this._corrDragState) return;
        this._corrDragState = null;
        this._saveCorrelationMarkers().catch(() => {});
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Marker moved and saved';
    },

    _renderWellHeader(well) {
        document.getElementById('wellName').textContent = well.name || 'Unknown Well';
        document.getElementById('wellInfo').textContent = [
            well.uwi, well.operator, well.depth_unit
        ].filter(Boolean).join(' • ');

        const statsEl = document.getElementById('wellStats');
        if (statsEl && this.currentLogRun) {
            const runNo = this.currentLogRun.run_number ?? 1;
            const file = this.currentLogRun.filename || 'unknown.las';
            const s = Number(this.currentLogRun.start_depth);
            const e = Number(this.currentLogRun.stop_depth);
            const hasDepth = Number.isFinite(s) && Number.isFinite(e);
            const dTop = hasDepth ? Math.min(s, e) : null;
            const dBase = hasDepth ? Math.max(s, e) : null;
            const depthText = hasDepth ? `${dTop.toFixed(2)}-${dBase.toFixed(2)}` : 'n/a';
            const stepAbs = Number.isFinite(Number(this.currentLogRun.step)) ? Math.abs(Number(this.currentLogRun.step)).toFixed(4) : 'n/a';
            const versionLabel = this._formatLASVersion(this.currentLogRun.version || this.currentLogRun.las_version);
            const versionClass = versionLabel.includes('3.0') ? 'las-badge las-badge-v3' : 'las-badge las-badge-v2';
            const versionBadge = versionLabel ? ` <span class="${versionClass}">${versionLabel}</span>` : '';
            statsEl.innerHTML = `Run ${runNo} • ${escapeHtml(file)} • ${this.currentLogRun.num_points} pts • ${depthText} ${escapeHtml(well.depth_unit)} • step ${stepAbs}${versionBadge}`;
        }
    },

    _renderCurvePanel(curves) {
        const panel = document.getElementById('curvePanel');
        if (!panel) return;

        panel.innerHTML = curves.filter(c => c.mnemonic !== (this.currentLogRun?.curves_json ? JSON.parse(this.currentLogRun.curves_json)[0]?.mnemonic : 'DEPT')).map(c => {
            const cfg = this.curveConfig[c.mnemonic] || {};
            const color = cfg.color || '#58a6ff';
            const track = cfg.track || '?';
            return `
                <div class="curve-row">
                    <span class="curve-dot" style="background:${color}"></span>
                    <span class="curve-name">${escapeHtml(c.mnemonic)}</span>
                    <span class="curve-unit">${escapeHtml(c.unit || '')}</span>
                    <span class="curve-track">T${track}</span>
                    <span class="curve-range">${c.min_value?.toFixed(2)} – ${c.max_value?.toFixed(2)}</span>
                </div>
            `;
        }).join('');
    },

    _renderTopsList() {
        const panel = document.getElementById('topsPanel');
        if (!panel) return;

        panel.innerHTML = this.formationTops.map(t => `
            <div class="top-row">
                <span class="top-color" style="background:${t.color}"></span>
                <span class="top-name">${escapeHtml(t.formation_name)}</span>
                <span class="top-depth">${t.depth?.toFixed(1)} ${t.depth_unit || 'FT'}</span>
                <span class="top-lith">${escapeHtml(t.lithology || '')}</span>
                <button class="btn-icon-sm" data-action="app.editTop" data-args='[${t.id}]' title="Edit">
                    <i data-lucide="pencil"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.deleteTop" data-args='[${t.id}]' title="Delete">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    },
});
