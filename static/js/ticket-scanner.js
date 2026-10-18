function ticketScanner(csrfToken, eventId) {
  return {
    cameraReady: false,
    stream: null,
    frameId: null,
    stopped: false,
    cameraError: '',
    result: null,
    resultHeadline: '',
    resultDetail: '',
    checkedInCount: 0,
    lastCode: null,
    lastScanAt: 0,
    busy: false,

    async start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        if (this.stopped) { stream.getTracks().forEach(track => track.stop()); return; }
        this.stream = stream;
        this.$refs.video.srcObject = stream;
        this.cameraReady = true;
        this.loop();
      } catch (e) {
        this.cameraError = 'Could not access the camera — check permissions and try again.';
      }
    },

    loop() {
      const video = this.$refs.video;
      const canvas = this.$refs.canvas;
      const tick = () => {
        if (this.stopped) return;
        if (video.readyState === video.HAVE_ENOUGH_DATA && !this.busy) {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(imageData.data, imageData.width, imageData.height);
          if (code && code.data) {
            this.handleCode(code.data);
          }
        }
        this.frameId = requestAnimationFrame(tick);
      };
      this.frameId = requestAnimationFrame(tick);
    },

    handleCode(data) {
      const now = Date.now();
      if (data === this.lastCode && now - this.lastScanAt < 3000) return;
      const match = data.match(/\/tickets\/verify\/([0-9a-f-]{36})\/?/i);
      if (!match) return;

      this.lastCode = data;
      this.lastScanAt = now;
      this.busy = true;
      const serial = match[1];

      fetch(`/tickets/scan/api/${serial}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: new URLSearchParams({ event_id: String(eventId) }),
      })
        .then(r => {
          if (r.redirected || r.status === 403 && !r.headers.get('content-type')?.includes('application/json')) return { status: 403, body: { result: 'not_assigned' } };
          return r.json().then(body => ({ status: r.status, body }));
        })
        .then(({ status, body }) => {
          if (status === 404 || body.result === 'not_found') {
            this.showResult('not_found', 'Not a SeroTix ticket', 'This QR code was not recognized.');
          } else if (body.ok) {
            this.checkedInCount++;
            this.showResult('checked_in', 'Checked in ✓', `${body.buyer_name} — ${body.ticket_type}`);
          } else if (body.result === 'not_assigned') {
            this.stopCamera();
            this.showResult('error', 'Access ended', 'Do not admit. Your shift ended or access was revoked. Contact the event manager.');
          } else if (body.result === 'wrong_event') {
            this.showResult('error', 'Wrong event', 'Do not admit. This ticket is not for the event selected on this phone.');
          } else if (body.result === 'select_event') {
            this.showResult('error', 'Choose an event', 'Return to the gate workspace and select your event.');
          } else if (body.result === 'unpaid') {
            this.showResult('already_used', 'Payment not confirmed', 'Do not admit this ticket. Ask an admin to check the booking.');
          } else if (body.result === 'already_used') {
            this.showResult('already_used', 'Already used', `Checked in earlier at ${body.checked_in_at || 'unknown time'}.`);
          } else {
            this.showResult('already_used', body.result === 'cancelled' ? 'Ticket cancelled' : 'Not valid', `${body.ticket_type} — ${body.event_title}`);
          }
        })
        .catch(() => this.showResult('error', 'Connection error', 'Could not reach the server — try again.'))
        .finally(() => {
          if (!this.stopped) setTimeout(() => { this.result = null; this.busy = false; }, 1800);
        });
    },

    stopCamera() {
      this.stopped = true;
      if (this.frameId !== null) cancelAnimationFrame(this.frameId);
      this.stream?.getTracks().forEach(track => track.stop());
      this.cameraReady = false;
      this.cameraError = 'Camera stopped. Choose your event again to restart.';
    },

    destroy() { this.stopCamera(); },

    showResult(kind, headline, detail) {
      this.result = kind;
      this.resultHeadline = headline;
      this.resultDetail = detail;
    },
  };
}
