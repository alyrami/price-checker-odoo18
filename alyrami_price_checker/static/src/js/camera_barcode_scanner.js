/*!
 * alyrami_price_checker — shared camera barcode capture/decode engine
 * (Sprint: Camera Barcode Scanning, Task 2)
 *
 * TASK 1 SPIKE DECISION (2026-08-10, read-only investigation, no runtime change):
 * Before writing this file, checked whether Odoo 18's own camera-scanning
 * components could be reused/adapted instead:
 *
 *   - addons/point_of_sale/static/src/app/screens/product_screen/camera_barcode_scanner.js
 *     (POS's `CameraBarcodeScanner`) hardwires the POS-only `barcode_reader` and
 *     `mail.sound_effects` services inside setup(). It only exists/works inside an
 *     active, authenticated POS session — not reusable for the backend Barcode
 *     Scanner screen (no POS session there) or for the fully public kiosk page.
 *
 *   - addons/web/static/src/core/barcode/barcode_video_scanner.js (+ barcode_dialog.js,
 *     ZXingBarcodeDetector.js) is Odoo core's real "native BarcodeDetector first, ZXing
 *     fallback second" implementation (same technique this file uses), and lazy-loads
 *     its ZXing copy on demand from `web/static/lib/zxing-library/zxing-library.js`
 *     (confirmed: NOT listed in `web.assets_backend`'s eager file list — only present
 *     in `web.tests_assets` — i.e. core itself treats it as lazy-load-only). Good
 *     technique reference, but `BarcodeVideoScanner` is an Owl `Component` with bare
 *     `@odoo/owl` / `@web/core/...` imports. Those bare imports only resolve when the
 *     page has loaded Odoo's module loader + core JS (`web._assets_core`), which the
 *     public, no-login kiosk page (Track B) must NOT depend on per the brief.
 *
 * DECISION: build a new, framework-agnostic engine (this file) that reuses only the
 * BarcodeDetector-first/ZXing-fallback *technique*, with zero Owl/@web/module-loader
 * dependency, so the exact same file can run unmodified:
 *   - loaded as a plain classic <script> inside Track A's Owl modal (Task 4), and
 *   - loaded as a plain classic <script> inside Track B's vanilla-JS kiosk controller
 *     (Task 13), which never loads the authenticated Odoo web client bundle at all.
 * This file is intentionally NOT an `/** @odoo-module **\/`-tagged ES module: it has
 * zero bare imports, is a plain classic script, and registers itself on
 * `window.AlyramiPriceChecker.CameraBarcodeScanner` so both an Owl component (which
 * *is* part of the authenticated backend bundle) and a bundle-free public page can
 * consume it the same way, without either one requiring Odoo's `/** @odoo-module **\/`
 * loader machinery to be present on the page.
 */
(function () {
    "use strict";

    // Vendored locally under this module's own static assets (Task 3) — never a CDN.
    // Lazy-loaded on demand, only when the native BarcodeDetector API is unavailable,
    // so it never adds weight to a page load that doesn't need it.
    var ZXING_LIB_URL = "/alyrami_price_checker/static/lib/zxing/zxing-library.js";

    var zxingLoadPromise = null;

    // Real-world packaging issue: some products carry both a QR code and a
    // barcode close together, and the camera would sometimes lock onto the QR
    // code instead of the barcode. QR detection is deliberately excluded on
    // both decode paths below — every other format (EAN-13, EAN-8, UPC-A,
    // UPC-E, Code128, etc.) stays fully enabled, unrestricted.
    var EXCLUDED_BARCODE_FORMAT = "qr_code";

    /**
     * Native BarcodeDetector format list, minus QR codes.
     * @param {string[]} formats as returned by BarcodeDetector.getSupportedFormats()
     * @returns {string[]}
     */
    function excludeQrFromNativeFormats(formats) {
        return formats.filter(function (f) {
            return f !== EXCLUDED_BARCODE_FORMAT;
        });
    }

    /**
     * Every format in the vendored ZXing build's BarcodeFormat enum, minus
     * QR_CODE. Built dynamically (not a hardcoded list) so it stays correct
     * even if the vendored library's supported formats ever change.
     * @param {any} ZXing the loaded ZXing namespace
     * @returns {number[]} ZXing.BarcodeFormat values, for DecodeHintType.POSSIBLE_FORMATS
     */
    function getZxingPossibleFormats(ZXing) {
        var BarcodeFormat = ZXing.BarcodeFormat;
        var formats = [];
        for (var key in BarcodeFormat) {
            if (!Object.prototype.hasOwnProperty.call(BarcodeFormat, key)) {
                continue;
            }
            // TypeScript numeric enums compile to a two-way map (name -> number
            // AND number -> name on the same object) — skip the reverse
            // (numeric-key) entries, only the name keys are real format names.
            if (/^\d+$/.test(key)) {
                continue;
            }
            if (key === "QR_CODE") {
                continue;
            }
            formats.push(BarcodeFormat[key]);
        }
        return formats;
    }

    /**
     * Load the vendored ZXing UMD bundle exactly once per page, however many
     * CameraBarcodeScanner instances end up needing it.
     * @returns {Promise<any>} resolves with the global `window.ZXing` namespace.
     */
    function loadZXing() {
        if (window.ZXing) {
            return Promise.resolve(window.ZXing);
        }
        if (zxingLoadPromise) {
            return zxingLoadPromise;
        }
        zxingLoadPromise = new Promise(function (resolve, reject) {
            var existing = document.querySelector('script[src="' + ZXING_LIB_URL + '"]');
            if (existing) {
                existing.addEventListener("load", function () {
                    resolve(window.ZXing);
                });
                existing.addEventListener("error", function () {
                    reject(new Error("Failed to load the barcode scanning library."));
                });
                return;
            }
            var script = document.createElement("script");
            script.src = ZXING_LIB_URL;
            script.async = true;
            script.onload = function () {
                resolve(window.ZXing);
            };
            script.onerror = function () {
                reject(new Error("Failed to load the barcode scanning library."));
            };
            document.head.appendChild(script);
        });
        return zxingLoadPromise;
    }

    /**
     * CameraBarcodeScanner — plain-JS camera capture + decode engine.
     *
     * Usage:
     *   const engine = new CameraBarcodeScanner();
     *   await engine.start(videoEl, {
     *       onDecode: (code) => ...,          // fires once per code, debounced
     *       onError: (err) => ...,            // camera/decoder error, never thrown
     *       onPermissionDenied: (err) => ...,  // getUserMedia denied
     *       onReady: ({ torchSupported }) => ..., // optional, fires once camera is live
     *       debounceMs: 1500,                 // optional, default 1500
     *   });
     *   engine.stop();
     *   await engine.toggleTorch();
     */
    function CameraBarcodeScanner() {
        this._videoEl = null;
        this._stream = null;
        this._detector = null;
        this._zxingReader = null;
        this._loopTimer = null;
        this._stopped = true;
        this._torchOn = false;

        this._onDecode = function () {};
        this._onError = function () {};
        this._onPermissionDenied = function () {};
        this._onReady = function () {};

        this._debounceMs = 1500;
        this._lastCode = null;
        this._lastCodeAt = 0;
    }

    /**
     * Feature-detect whether this browser can even attempt camera capture.
     * @returns {boolean}
     */
    CameraBarcodeScanner.isCameraSupported = function () {
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    };

    /**
     * Invoke a consumer-supplied callback defensively: a throwing callback must
     * never break the internal decode loop or bubble up as an uncaught error.
     */
    CameraBarcodeScanner.prototype._safeCall = function (fn) {
        var args = Array.prototype.slice.call(arguments, 1);
        try {
            fn.apply(null, args);
        } catch (e) {
            // eslint-disable-next-line no-console
            console.error("[alyrami_price_checker] camera scanner callback error:", e);
        }
    };

    /**
     * Start the camera and begin decoding. Never throws — all failure paths are
     * routed to onError/onPermissionDenied so callers can safely leave manual
     * barcode entry usable no matter what happens here.
     *
     * @param {HTMLVideoElement} videoEl element the live preview will be attached to
     * @param {Object} opts
     * @param {Function} [opts.onDecode]
     * @param {Function} [opts.onError]
     * @param {Function} [opts.onPermissionDenied]
     * @param {Function} [opts.onReady]
     * @param {number} [opts.debounceMs]
     */
    CameraBarcodeScanner.prototype.start = function (videoEl, opts) {
        opts = opts || {};
        var self = this;

        // Always start from a clean slate (defensive: a caller re-using the same
        // engine instance without calling stop() first must not leak a stream).
        this.stop();
        this._stopped = false;

        this._videoEl = videoEl || null;
        this._onDecode = typeof opts.onDecode === "function" ? opts.onDecode : function () {};
        this._onError = typeof opts.onError === "function" ? opts.onError : function () {};
        this._onPermissionDenied =
            typeof opts.onPermissionDenied === "function" ? opts.onPermissionDenied : this._onError;
        this._onReady = typeof opts.onReady === "function" ? opts.onReady : function () {};
        this._debounceMs = typeof opts.debounceMs === "number" ? opts.debounceMs : 1500;
        this._lastCode = null;
        this._lastCodeAt = 0;

        if (!videoEl) {
            this._safeCall(this._onError, new Error("No video element supplied to the camera scanner."));
            return Promise.resolve();
        }

        if (!CameraBarcodeScanner.isCameraSupported()) {
            this._safeCall(this._onError, new Error("Camera capture is not supported on this device/browser."));
            return Promise.resolve();
        }

        return navigator.mediaDevices
            .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
            .then(function (stream) {
                if (self._stopped) {
                    // stop() was called while the permission prompt was still open —
                    // release the camera immediately, don't leave the camera indicator on.
                    stream.getTracks().forEach(function (t) {
                        t.stop();
                    });
                    return;
                }
                self._stream = stream;
                videoEl.srcObject = stream;
                videoEl.setAttribute("playsinline", "true");
                videoEl.muted = true;
                // Do NOT call videoEl.play() here. The native-detector branch below
                // plays it explicitly; the ZXing branch (_startZXing) must be the one
                // to call play() on a not-yet-playing element, because ZXing's own
                // decodeFromVideoElementContinuously() awaits the video's "playing"
                // event before it will start its decode loop. If we play() first,
                // that event has already fired by the time ZXing attaches its
                // listener, so it never fires again — ZXing's internal promise never
                // resolves, and decodeContinuously() is never reached at all (visible
                // as a live preview that silently never decodes anything, with a
                // console warning from zxing-library.js: "Trying to play video that
                // is already playing.").
                return self._beginDetection();
            })
            .catch(function (err) {
                if (self._stopped) {
                    return;
                }
                if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) {
                    self._safeCall(self._onPermissionDenied, err);
                } else {
                    self._safeCall(self._onError, err instanceof Error ? err : new Error(String(err)));
                }
            });
    };

    CameraBarcodeScanner.prototype._beginDetection = function () {
        var self = this;

        if ("BarcodeDetector" in window) {
            return window.BarcodeDetector.getSupportedFormats()
                .then(function (formats) {
                    if (self._stopped) {
                        return;
                    }
                    self._detector = new window.BarcodeDetector({ formats: excludeQrFromNativeFormats(formats) });
                    // Only the native-detector path plays the video itself — see the
                    // comment in start() for why the ZXing path must not be pre-played.
                    return self._playVideo();
                })
                .then(function () {
                    if (self._stopped) {
                        return;
                    }
                    self._safeCall(self._onReady, { torchSupported: self.hasTorchSupport() });
                    self._runNativeLoop();
                })
                .catch(function () {
                    // Native detector construction/playback failed unexpectedly — fall back
                    // to ZXing rather than surfacing an error, since ZXing may still work fine.
                    if (!self._stopped) {
                        return self._startZXing();
                    }
                });
        }

        return this._startZXing();
    };

    /**
     * Plays the video element. Only used by the native-detector path — the ZXing
     * path must reach playVideoOnLoad() with a not-yet-playing element (see start()).
     * @returns {Promise<void>} never rejects.
     */
    CameraBarcodeScanner.prototype._playVideo = function () {
        var videoEl = this._videoEl;
        if (!videoEl) {
            return Promise.resolve();
        }
        var playResult = videoEl.play();
        if (playResult && typeof playResult.catch === "function") {
            return playResult.catch(function () {
                // Some browsers reject play() with AbortError while metadata is still
                // loading; the native detection loop tolerates a not-yet-ready frame.
            });
        }
        return Promise.resolve();
    };

    CameraBarcodeScanner.prototype._startZXing = function () {
        var self = this;
        return loadZXing()
            .then(function (ZXing) {
                if (self._stopped) {
                    return;
                }
                if (!ZXing) {
                    throw new Error("Barcode scanning library failed to load.");
                }
                var hints = new Map([
                    [ZXing.DecodeHintType.POSSIBLE_FORMATS, getZxingPossibleFormats(ZXing)],
                ]);
                self._zxingReader = new ZXing.BrowserMultiFormatReader(hints, 300);
                self._safeCall(self._onReady, { torchSupported: self.hasTorchSupport() });
                self._zxingReader.decodeFromVideoElementContinuously(self._videoEl, function (result) {
                    if (self._stopped || !result || typeof result.getText !== "function") {
                        // ZXing calls this callback continuously with a NotFoundException
                        // while nothing is in frame — that is expected, not an error.
                        return;
                    }
                    self._handleDecoded(result.getText());
                });
            })
            .catch(function (err) {
                if (!self._stopped) {
                    self._safeCall(self._onError, err instanceof Error ? err : new Error(String(err)));
                }
            });
    };

    CameraBarcodeScanner.prototype._runNativeLoop = function () {
        var self = this;
        if (this._stopped || !this._videoEl || !this._detector) {
            return;
        }
        this._detector
            .detect(this._videoEl)
            .then(function (codes) {
                if (self._stopped) {
                    return;
                }
                if (codes && codes.length) {
                    self._handleDecoded(codes[0].rawValue);
                }
            })
            .catch(function (err) {
                if (!self._stopped) {
                    self._safeCall(self._onError, err instanceof Error ? err : new Error(String(err)));
                }
            })
            .then(function () {
                if (!self._stopped) {
                    self._loopTimer = setTimeout(function () {
                        self._runNativeLoop();
                    }, 200);
                }
            });
    };

    CameraBarcodeScanner.prototype._handleDecoded = function (code) {
        if (!code || this._stopped) {
            return;
        }
        var now = Date.now();
        if (code === this._lastCode && now - this._lastCodeAt < this._debounceMs) {
            // Same code re-detected on the next frame(s) within the debounce window —
            // ignore so onDecode fires exactly once per physical scan.
            return;
        }
        this._lastCode = code;
        this._lastCodeAt = now;
        this._safeCall(this._onDecode, code);
    };

    /**
     * Stop the camera and any decode loop. Always safe to call multiple times,
     * or before start() has ever run. Never fires onDecode after this returns.
     */
    CameraBarcodeScanner.prototype.stop = function () {
        this._stopped = true;

        if (this._loopTimer) {
            clearTimeout(this._loopTimer);
            this._loopTimer = null;
        }
        if (this._zxingReader) {
            try {
                this._zxingReader.reset();
            } catch (e) {
                // already stopped/never started — nothing to clean up
            }
            this._zxingReader = null;
        }
        this._detector = null;

        if (this._stream) {
            this._stream.getTracks().forEach(function (t) {
                t.stop();
            });
            this._stream = null;
        }
        if (this._videoEl) {
            try {
                this._videoEl.srcObject = null;
            } catch (e) {
                // ignore — element may already be detached from the DOM
            }
        }
        this._videoEl = null;
        this._torchOn = false;
    };

    /**
     * Whether the currently-active camera stream's video track exposes a torch
     * capability. Safe to call at any time; returns false (never throws) when
     * there is no active stream or the capability is absent (all iPhones today,
     * most laptop webcams, and the ZXing/getUserMedia-polyfill path in general —
     * torch is a native MediaStreamTrack capability, not something a decode
     * library can add).
     * @returns {boolean}
     */
    CameraBarcodeScanner.prototype.hasTorchSupport = function () {
        if (!this._stream) {
            return false;
        }
        var track = this._stream.getVideoTracks()[0];
        if (!track || typeof track.getCapabilities !== "function") {
            return false;
        }
        try {
            var caps = track.getCapabilities();
            return !!(caps && caps.torch);
        } catch (e) {
            return false;
        }
    };

    /**
     * Best-effort torch toggle. Feature-detected; silently no-ops (never throws,
     * never rejects) when unsupported.
     * @returns {Promise<boolean>} resulting torch-on state (always false when unsupported)
     */
    CameraBarcodeScanner.prototype.toggleTorch = function () {
        var self = this;
        if (!this.hasTorchSupport()) {
            return Promise.resolve(false);
        }
        var track = this._stream.getVideoTracks()[0];
        var nextState = !this._torchOn;
        return track
            .applyConstraints({ advanced: [{ torch: nextState }] })
            .then(function () {
                self._torchOn = nextState;
                return self._torchOn;
            })
            .catch(function () {
                self._torchOn = false;
                return false;
            });
    };

    window.AlyramiPriceChecker = window.AlyramiPriceChecker || {};
    window.AlyramiPriceChecker.CameraBarcodeScanner = CameraBarcodeScanner;
})();
