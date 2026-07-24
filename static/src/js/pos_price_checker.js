/** @odoo-module **/

/**
 * price_checker – POS Price Checker  (Odoo 18 Community)
 *
 * ENHANCEMENTS:
 *   - Integrated with Odoo POS barcode service via env.services.barcode.bus
 *   - Proper event subscription using bus.addEventListener/removeEventListener
 *   - Calculates sales price with ONLY sales taxes (customer-facing taxes)
 *   - Excludes purchase taxes from price calculations
 *   - Supports hardware barcode scanners through POS barcode service
 *
 * Pattern: full POS screen (same as Cash In/Out, Close Session).
 *   1. patch(ControlButtons)  – adds onClickPriceChecker() only.
 *        NO setup() override. Calls pos.showScreen().
 *   2. PriceCheckerScreen registered via registry.category("pos_screens").
 *        Owns all state via useState. Has goBack() to return.
 *        Uses POS barcode service bus for hardware barcode scanner support.
 */

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { patch }    from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { rpc }      from "@web/core/network/rpc";
import { usePos }   from "@point_of_sale/app/store/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

/* ── audio ─────────────────────────────────────────────────── */
function playTone(freq, dur, vol = 0.25) {
    try {
        const ctx  = new (window.AudioContext || window.webkitAudioContext)();
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(vol, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + dur);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + dur);
    } catch (_) {}
}
const beepOk  = () => playTone(880, 0.12);
const beepErr = () => playTone(300, 0.30);

/* ── patch ControlButtons – NEW methods only, no setup() ───── */
patch(ControlButtons.prototype, {
    onClickPriceChecker() {
        this.env.services.pos.showScreen("PriceCheckerScreen");
    },
});

/* ── PriceCheckerScreen ────────────────────────────────────── */
export class PriceCheckerScreen extends Component {
    static template = "price_checker.PriceCheckerScreen";
    static props = {};

    setup() {
        super.setup(...arguments);
        this.pos = usePos();

        this.state = useState({
            query:    "",
            product:  null,
            products: [],
            loading:  false,
            mode:     "idle",
        });

        this.inputRef = useRef("pcInput");

        // In POS, barcode events are handled through the hardware proxy
        // We listen to the global barcode_scanned event
        this._barcodeHandler = this._handleBarcode.bind(this);
        
        onMounted(() => {
            // Subscribe to barcode events from the BarcodeReader
            this.env.services.barcode.bus.addEventListener("barcode_scanned", this._barcodeHandler);
            this._focusInput();
        });
        
        onWillUnmount(() => {
            // Unsubscribe from barcode events
            this.env.services.barcode.bus.removeEventListener("barcode_scanned", this._barcodeHandler);
        });
    }

    goBack() {
        this.pos.showScreen("ProductScreen");
    }

    onInput(ev)   { this.state.query = ev.target.value; }
    onKeyDown(ev) { if (ev.key === "Enter") { ev.preventDefault(); this.doSearch(); } }

    _handleBarcode(ev) {
        // POS barcode service event structure
        const barcode = ev.detail?.barcode || ev.detail?.code || ev.code;
        if (barcode) {
            this.state.query = barcode;
            this.searchByBarcode(barcode);
        }
    }

    async doSearch() {
        const q = (this.state.query || "").trim();
        if (!q) return;
        if (/\d/.test(q) && q.length <= 20) {
            await this.searchByBarcode(q);
        } else {
            await this.searchByName(q);
        }
    }

    async searchByBarcode(barcode) {
        this.state.loading  = true;
        this.state.product  = null;
        this.state.products = [];
        this.state.mode     = "idle";
        try {
            const res = await rpc("/web/price_checker/search_by_barcode", { barcode });
            
            // Check for server-side errors
            if (res.error) {
                console.error("[PriceChecker] Server error:", res.error);
                this.state.mode = "notfound";
                beepErr();
                return;
            }
            
            if (res.product) {
                this.state.product = res.product;
                this.state.mode    = "product";
                beepOk();
            } else {
                await this._fetchByName(barcode);
                if (!this.state.products.length) {
                    this.state.mode = "notfound";
                    beepErr();
                }
            }
        } catch (e) {
            console.error("[PriceChecker] barcode rpc error:", e);
            this.state.mode = "notfound";
            beepErr();
        } finally {
            this.state.loading = false;
            this._focusInput();
        }
    }

    async searchByName(query) {
        this.state.loading  = true;
        this.state.product  = null;
        this.state.products = [];
        this.state.mode     = "idle";
        await this._fetchByName(query);
        this.state.loading = false;
        this._focusInput();
    }

    async _fetchByName(query) {
        try {
            const res = await rpc("/web/price_checker/search_by_name", { query, limit: 12 });
            
            // Check for server-side errors
            if (res.error) {
                console.error("[PriceChecker] Server error:", res.error);
                this.state.products = [];
                this.state.mode = "notfound";
                return;
            }
            
            this.state.products = res.products || [];
            this.state.mode     = this.state.products.length ? "list" : "notfound";
        } catch (e) {
            console.error("[PriceChecker] name rpc error:", e);
            this.state.mode = "notfound";
        }
    }

    selectProduct(p) {
        this.state.product  = p;
        this.state.products = [];
        this.state.mode     = "product";
        beepOk();
    }

    clearSearch() {
        this.state.query    = "";
        this.state.product  = null;
        this.state.products = [];
        this.state.mode     = "idle";
        this._focusInput();
    }

    fmtPrice(v)  { return (v || 0).toFixed(2); }
    stockClass(s) { return "pc-stock-badge " + (s || ""); }
    stockLabel(s) {
        return { in_stock: "In Stock", low_stock: "Low Stock", out_of_stock: "Out of Stock" }[s] || s || "";
    }

    _focusInput() {
        setTimeout(() => {
            const el = this.inputRef.el;
            if (el) { el.focus(); el.select(); }
        }, 90);
    }
}

/* ── register as POS screen ─────────────────────────────────── */
registry.category("pos_screens").add("PriceCheckerScreen", PriceCheckerScreen);
