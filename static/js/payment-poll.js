function paymentPoll(reference, eventUrl) {
  return {
    failed: false,
    failMessage: '',
    timedOut: false,
    redirectIn: 5,
    countdown: '',
    eventUrl: eventUrl,
    maxWaitSeconds: 90, // roughly matches how long an STK push prompt stays valid on the phone
    startedAt: Date.now(),
    poll() {
      const tickCountdown = () => {
        const remaining = Math.max(0, this.maxWaitSeconds - Math.floor((Date.now() - this.startedAt) / 1000));
        const m = Math.floor(remaining / 60);
        const s = String(remaining % 60).padStart(2, '0');
        this.countdown = `${m}:${s}`;
      };
      tickCountdown();
      const countdownTimer = setInterval(tickCountdown, 1000);

      const check = () => {
        if (this.failed || this.timedOut) return;

        if (Date.now() - this.startedAt >= this.maxWaitSeconds * 1000) {
          clearInterval(countdownTimer);
          this.timedOut = true;
          const redirectTimer = setInterval(() => {
            this.redirectIn -= 1;
            if (this.redirectIn <= 0) {
              clearInterval(redirectTimer);
              window.location.href = this.eventUrl;
            }
          }, 1000);
          return;
        }

        fetch(`/payments/status/${reference}/`)
          .then(r => r.json())
          .then(data => {
            if (data.order_status === 'paid') {
              clearInterval(countdownTimer);
              window.location.href = `/tickets/order/${reference}/success/`;
            } else if (data.payment_status === 'failed') {
              clearInterval(countdownTimer);
              this.failed = true;
              this.failMessage = data.result_desc || 'Payment was not completed.';
            } else {
              setTimeout(check, 3000);
            }
          })
          .catch(() => setTimeout(check, 4000));
      };
      check();
    },
  };
}
