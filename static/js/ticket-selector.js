function ticketSelector(types, feePercent) {
  return {
    open: false,
    submitting: false,
    method: 'mpesa',
    types: types,
    qty: {},
    inc(id) {
      const t = this.types.find(x => x.id === id);
      const current = this.qty[id] || 0;
      if (current < Math.min(t.remaining, t.max_per_order)) this.qty[id] = current + 1;
    },
    dec(id) {
      const current = this.qty[id] || 0;
      if (current > 0) this.qty[id] = current - 1;
    },
    get subtotal() {
      return this.types.reduce((sum, t) => sum + (this.qty[t.id] || 0) * t.price, 0);
    },
    // Preview only — Order.recalculate_total() is the source of truth for
    // the actual charge. Ticket prices here are always whole KES, so this
    // matches server-side rounding in practice.
    get serviceFee() {
      return Math.round(this.subtotal * feePercent * 100) / 100;
    },
    get total() {
      return this.subtotal + this.serviceFee;
    },
    get totalItems() {
      return Object.values(this.qty).reduce((a, b) => a + b, 0);
    },
  };
}
// countdown() is shared from static/js/motion.js
