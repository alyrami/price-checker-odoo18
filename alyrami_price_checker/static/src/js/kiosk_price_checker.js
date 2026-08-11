/*!
 * alyrami_price_checker — Track B public kiosk page controller
 * (Sprint: Camera Barcode Scanning, Task 13 + Task 15 torch toggle)
 *
 * Plain classic script — deliberately NOT an `/** @odoo-module **\/`-tagged
 * ES module and does NOT import anything from @odoo/owl or @web/core. This
 * page is served with zero authentication and must not depend on Odoo's
 * module loader or the authenticated web client bundle at all (see
 * SPRINT_BACKLOG.md Task 12/13). It talks to Task 2's shared camera engine
 * via the global `window.AlyramiPriceChecker.CameraBarcodeScanner` that
 * engine registers itself under, for exactly the same reason.
 *
 * Manual submit and camera decode both funnel through the single
 * lookupBarcode() function below, which is the ONLY code path that ever
 * calls the server — there is no client-side "looks like a name vs. a
 * barcode" branching of any kind, and nothing here calls
 * /web/price_checker/search_by_name or anything name-search-like, since
 * there is no name-search route on this public surface to fall back to.
 */
(function () {
    "use strict";

    function $(id) {
        return document.getElementById(id);
    }

    function jsonRpcCall(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: params || {},
                id: Math.floor(Math.random() * 1e9),
            }),
        }).then(function (response) {
            return response.json().then(function (payload) {
                if (payload.error) {
                    // Odoo JSON-RPC error envelope — surface as a generic failure,
                    // never expose payload.error.data/debug details to the kiosk UI.
                    throw new Error("request_failed");
                }
                return payload.result;
            });
        });
    }

    function init() {
        var body = document.body;
        var token = body.getAttribute("data-kiosk-token");

        var form = $("pc-kiosk-form");
        var input = $("pc-kiosk-barcode-input");
        var submitBtn = $("pc-kiosk-submit-btn");
        var cameraBtn = $("pc-kiosk-camera-btn");
        var cameraCloseBtn = $("pc-kiosk-camera-close-btn");
        var cameraPanel = $("pc-kiosk-camera-panel");
        var video = $("pc-kiosk-video");
        var torchBtn = $("pc-kiosk-torch-btn");
        var messageEl = $("pc-kiosk-message");
        var resultEl = $("pc-kiosk-result");
        var resultImage = $("pc-kiosk-result-image");
        var resultName = $("pc-kiosk-result-name");
        var resultPrice = $("pc-kiosk-result-price");

        if (!token || !form || !input) {
            // Markup missing/unexpected — nothing sensible to wire up.
            return;
        }

        var EngineClass = window.AlyramiPriceChecker && window.AlyramiPriceChecker.CameraBarcodeScanner;
        var engine = EngineClass ? new EngineClass() : null;
        var lookupInFlight = false;

        function showMessage(text) {
            messageEl.textContent = text || "";
        }

        function hideResult() {
            resultEl.classList.add("pc-kiosk-hidden");
            resultImage.removeAttribute("src");
            resultName.textContent = "";
            resultPrice.textContent = "";
        }

        function showResult(product) {
            // Renders ONLY name / image / price+currency from the response —
            // nothing else exists on `product` for this route to render.
            resultName.textContent = product.name || "";
            resultPrice.textContent =
                (product.currency || "") + " " + (typeof product.price === "number" ? product.price.toFixed(2) : product.price);
            if (product.image_128) {
                resultImage.src = "data:image/png;base64," + product.image_128;
                resultImage.classList.remove("pc-kiosk-hidden");
            } else {
                resultImage.removeAttribute("src");
                resultImage.classList.add("pc-kiosk-hidden");
            }
            resultEl.classList.remove("pc-kiosk-hidden");
        }

        /**
         * The single request path used by BOTH manual submit and camera
         * decode. Exact-barcode-match only, via Task 9's public route.
         */
        function lookupBarcode(barcode) {
            barcode = (barcode || "").trim();
            if (!barcode || lookupInFlight) {
                return;
            }
            lookupInFlight = true;
            hideResult();
            showMessage("Checking...");

            jsonRpcCall("/price_checker/kiosk/" + encodeURIComponent(token) + "/lookup", { barcode: barcode })
                .then(function (result) {
                    lookupInFlight = false;
                    if (!result || result.error) {
                        showMessage(result && result.error === "Too many requests, please try again shortly"
                            ? "Too many requests — please wait a moment and try again."
                            : "Something went wrong. Please try again.");
                        return;
                    }
                    if (!result.product) {
                        showMessage('No product found for barcode "' + barcode + '".');
                        return;
                    }
                    showMessage("");
                    showResult(result.product);
                })
                .catch(function () {
                    lookupInFlight = false;
                    showMessage("Something went wrong. Please try again.");
                });
        }

        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            lookupBarcode(input.value);
        });

        function closeCamera() {
            if (engine) {
                engine.stop();
            }
            cameraPanel.classList.add("pc-kiosk-hidden");
            torchBtn.classList.add("pc-kiosk-hidden");
        }

        function openCamera() {
            if (!engine) {
                showMessage("Camera scanning is unavailable on this device/browser. You can still type the barcode.");
                return;
            }
            cameraPanel.classList.remove("pc-kiosk-hidden");
            showMessage("Starting camera...");

            engine.start(video, {
                onDecode: function (code) {
                    showMessage("");
                    closeCamera();
                    input.value = code;
                    lookupBarcode(code);
                },
                onPermissionDenied: function () {
                    showMessage("Camera access was denied. You can still type the barcode.");
                    closeCamera();
                },
                onError: function () {
                    showMessage("Camera is unavailable. You can still type the barcode.");
                    closeCamera();
                },
                onReady: function (info) {
                    showMessage("");
                    // Task 15 — torch button, hidden entirely (not just
                    // disabled) whenever the active camera/browser doesn't
                    // support it; best-effort, never blocks scanning.
                    if (info && info.torchSupported) {
                        torchBtn.classList.remove("pc-kiosk-hidden");
                    } else {
                        torchBtn.classList.add("pc-kiosk-hidden");
                    }
                },
            });
        }

        if (cameraBtn) {
            cameraBtn.addEventListener("click", openCamera);
        }
        if (cameraCloseBtn) {
            cameraCloseBtn.addEventListener("click", closeCamera);
        }
        if (torchBtn) {
            torchBtn.addEventListener("click", function () {
                if (!engine) {
                    return;
                }
                engine.toggleTorch().then(function (on) {
                    torchBtn.textContent = on ? "Torch Off" : "Torch";
                });
            });
        }

        // Camera denied/unsupported must never block manual entry — nothing
        // above disables the form/input at any point, by construction.
        window.addEventListener("beforeunload", function () {
            if (engine) {
                engine.stop();
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
