/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PriceCheckerBarcodeScanner extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.barcodeReader = useService("barcode");
        
        this.state = useState({
            barcode: "",
            product: null,
            loading: false,
            lastScan: null,
        });
        
        this.inputRef = useRef("barcodeInput");
        
        onWillStart(async () => {
            // Listen for barcode scanner events
            this.barcodeReader.bus.addEventListener("barcode_scanned", this._onBarcodeScanned.bind(this));
        });
    }
    
    /**
     * Handle barcode scanned from hardware scanner
     */
    _onBarcodeScanned(event) {
        const barcode = event.detail.barcode;
        if (barcode) {
            this.state.barcode = barcode;
            this.searchProduct();
        }
    }
    
    /**
     * Handle manual barcode input
     */
    onBarcodeInput(ev) {
        this.state.barcode = ev.target.value;
    }
    
    /**
     * Handle Enter key press
     */
    onKeyPress(ev) {
        if (ev.key === 'Enter') {
            this.searchProduct();
        }
    }
    
    /**
     * Search for product by barcode
     */
    async searchProduct() {
        const barcode = this.state.barcode.trim();
        
        if (!barcode) {
            this.notification.add("Please enter or scan a barcode", {
                type: "warning",
            });
            return;
        }
        
        this.state.loading = true;
        this.state.product = null;
        
        try {
            // Search for product by barcode
            const products = await this.orm.searchRead(
                "product.template",
                [["barcode", "=", barcode]],
                [
                    "name",
                    "barcode",
                    "list_price",
                    "price_checker_price_with_tax",
                    "price_checker_tax_amount",
                    "taxes_id",
                    "qty_available",
                    "categ_id",
                    "image_128",
                    "uom_id",
                    "default_code",
                    "price_checker_stock_status",
                    "currency_id",
                ],
                { limit: 1 }
            );
            
            if (products.length > 0) {
                this.state.product = products[0];
                this.state.lastScan = new Date().toLocaleTimeString();
                
                // Play success sound (optional)
                this.playBeep();
                
                this.notification.add(`Product found: ${products[0].name}`, {
                    type: "success",
                });
                
                // Auto-focus input for next scan
                setTimeout(() => {
                    if (this.inputRef.el) {
                        this.inputRef.el.select();
                    }
                }, 100);
            } else {
                // Play error sound (optional)
                this.playErrorBeep();
                
                this.notification.add(`No product found with barcode: ${barcode}`, {
                    type: "danger",
                });
                this.state.product = null;
            }
        } catch (error) {
            console.error("Error searching product:", error);
            this.notification.add("Error searching for product", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }
    
    /**
     * Play success beep sound
     */
    playBeep() {
        try {
            // Create a short beep sound
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.1);
        } catch (e) {
            // Audio not supported or blocked, ignore
        }
    }
    
    /**
     * Play error beep sound
     */
    playErrorBeep() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 300;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.3);
        } catch (e) {
            // Audio not supported or blocked, ignore
        }
    }
    
    /**
     * Clear search and reset
     */
    clearSearch() {
        this.state.barcode = "";
        this.state.product = null;
        this.state.lastScan = null;
        
        // Focus input
        if (this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }
    
    /**
     * Open product in detail view
     */
    async openProduct() {
        if (!this.state.product) return;
        
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: this.state.product.id,
            views: [[false, "form"]],
            target: "new",
            context: { create: false, edit: false },
        });
    }
    
    /**
     * Get stock status badge class
     */
    getStatusClass() {
        if (!this.state.product) return "";
        
        const status = this.state.product.price_checker_stock_status;
        if (status === "in_stock") return "badge bg-success";
        if (status === "low_stock") return "badge bg-warning";
        if (status === "out_of_stock") return "badge bg-danger";
        return "badge bg-secondary";
    }
    
    /**
     * Get stock status text
     */
    getStatusText() {
        if (!this.state.product) return "";
        
        const status = this.state.product.price_checker_stock_status;
        if (status === "in_stock") return "In Stock";
        if (status === "low_stock") return "Low Stock";
        if (status === "out_of_stock") return "Out of Stock";
        return "Unknown";
    }
    
    /**
     * Format price with currency
     */
    formatPrice(price) {
        if (!price && price !== 0) return "0.00";
        return price.toFixed(2);
    }
    
    /**
     * Get currency symbol
     */
    getCurrencySymbol() {
        if (!this.state.product || !this.state.product.currency_id) return "";
        return this.state.product.currency_id[1] || "";
    }
    
    /**
     * Check if product has taxes
     */
    hasTaxes() {
        return this.state.product && 
               this.state.product.taxes_id && 
               this.state.product.taxes_id.length > 0;
    }
}

PriceCheckerBarcodeScanner.template = "price_checker.BarcodeScanner";

registry.category("actions").add("price_checker_barcode_scanner", PriceCheckerBarcodeScanner);
