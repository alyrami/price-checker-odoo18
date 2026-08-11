/** @odoo-module **/

/**
 * alyrami_price_checker — backend-only Owl modal wrapping Task 2's shared
 * camera engine (`window.AlyramiPriceChecker.CameraBarcodeScanner`).
 *
 * This component only ever runs inside `web.assets_backend` (an authenticated
 * Odoo web client page), so it is free to use Owl + `@web/core/dialog/dialog`.
 * Track B's public kiosk page (Tasks 11-13) does NOT use this component — it
 * talks to the Task 2 engine directly from plain JS, since the kiosk page must
 * not depend on the authenticated Odoo web client bundle at all.
 *
 * The engine itself (Task 2) is intentionally a plain classic script, not an
 * `/** @odoo-module **\/`-tagged ES module, so it can be shared byte-for-byte
 * between this Owl dialog and Track B's bundle-free kiosk page. It registers
 * itself on `window.AlyramiPriceChecker.CameraBarcodeScanner`, which is what
 * this file reads below instead of a bare `import`.
 */

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class CameraScannerDialog extends Component {
    static template = "alyrami_price_checker.CameraScannerDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onDecode: Function,
        onPermissionDenied: { type: Function, optional: true },
        onError: { type: Function, optional: true },
    };

    setup() {
        this.videoRef = useRef("video");
        const EngineClass =
            window.AlyramiPriceChecker && window.AlyramiPriceChecker.CameraBarcodeScanner;
        this.engine = EngineClass ? new EngineClass() : null;

        this.state = useState({
            status: "starting", // starting | live | denied | error
            errorMessage: "",
            torchSupported: false,
            torchOn: false,
        });

        onMounted(() => this._startCamera());
        onWillUnmount(() => {
            // Camera tracks must always be stopped when this dialog unmounts,
            // no matter how it was closed (decode success, Cancel button,
            // header close/back button, or ESC) — the Dialog component itself
            // handles those interactions and always unmounts us afterwards.
            if (this.engine) {
                this.engine.stop();
            }
        });
    }

    async _startCamera() {
        if (!this.engine) {
            this._onError(new Error(_t("Camera scanning is unavailable on this page.")));
            return;
        }
        await this.engine.start(this.videoRef.el, {
            onDecode: (code) => this._onDecode(code),
            onError: (err) => this._onError(err),
            onPermissionDenied: (err) => this._onPermissionDenied(err),
            onReady: ({ torchSupported }) => {
                this.state.status = "live";
                this.state.torchSupported = torchSupported;
            },
        });
    }

    _onDecode(code) {
        if (this.engine) {
            this.engine.stop();
        }
        this.props.close();
        this.props.onDecode(code);
    }

    _onPermissionDenied(err) {
        this.state.status = "denied";
        this.state.errorMessage = _t("Camera access was denied. You can still type the barcode manually.");
        if (this.props.onPermissionDenied) {
            this.props.onPermissionDenied(err);
        }
    }

    _onError(err) {
        this.state.status = "error";
        this.state.errorMessage =
            (err && err.message) || _t("Camera is unavailable. You can still type the barcode manually.");
        if (this.props.onError) {
            this.props.onError(err);
        }
    }

    async onToggleTorch() {
        if (!this.engine) {
            return;
        }
        const on = await this.engine.toggleTorch();
        this.state.torchOn = on;
    }

    onCancel() {
        if (this.engine) {
            this.engine.stop();
        }
        this.props.close();
    }
}
