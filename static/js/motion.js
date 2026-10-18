// Self-hosted, dependency-free motion helpers: scroll-reveal + navbar scroll state.
// No CDN, no build step — plain IntersectionObserver + a scroll listener.
(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reduceMotion && 'IntersectionObserver' in window) document.documentElement.classList.add('motion-ready');

  // --- Scroll reveal: elements with [data-reveal] fade/slide in once, on entry ---
  var revealTargets = document.querySelectorAll('[data-reveal]');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealTargets.forEach(function (el) { el.classList.add('is-visible'); });
  } else {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            var delay = entry.target.getAttribute('data-reveal-delay');
            if (delay) entry.target.style.transitionDelay = delay + 'ms';
            entry.target.classList.add('is-visible');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    revealTargets.forEach(function (el) { io.observe(el); });
  }

  // --- Navbar: gains a tighter, more opaque state once the page scrolls ---
  var header = document.querySelector('[data-site-header]');
  if (header) {
    var setState = function () {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    setState();
    window.addEventListener('scroll', setState, { passive: true });
  }

  // --- Lightweight confetti burst for the order-success moment ---
  window.seroxideConfetti = function (root) {
    if (reduceMotion) return;
    var colors = ['#7c3aed', '#a78bfa', '#c81e3a', '#ffb703', '#00b39a'];
    var container = document.createElement('div');
    container.className = 'confetti-burst';
    for (var i = 0; i < 28; i++) {
      var piece = document.createElement('span');
      piece.style.setProperty('--x', (Math.random() * 200 - 100) + 'px');
      piece.style.setProperty('--rot', (Math.random() * 720 - 360) + 'deg');
      piece.style.setProperty('--delay', (Math.random() * 150) + 'ms');
      piece.style.setProperty('--bg', colors[i % colors.length]);
      piece.style.left = (40 + Math.random() * 20) + '%';
      container.appendChild(piece);
    }
    (root || document.body).appendChild(container);
    setTimeout(function () { container.remove(); }, 1800);
  };

  // --- Countdown to a target ISO datetime, used on the hero and event detail pages ---
  window.countdown = function (targetIso) {
    return {
      units: [
        { label: 'Days', value: '00' }, { label: 'Hrs', value: '00' },
        { label: 'Min', value: '00' }, { label: 'Sec', value: '00' },
      ],
      tick() {
        const diff = Math.max(0, new Date(targetIso) - new Date());
        const d = Math.floor(diff / 86400000);
        const h = Math.floor(diff / 3600000) % 24;
        const m = Math.floor(diff / 60000) % 60;
        const s = Math.floor(diff / 1000) % 60;
        this.units = [
          { label: 'Days', value: String(d).padStart(2, '0') },
          { label: 'Hrs', value: String(h).padStart(2, '0') },
          { label: 'Min', value: String(m).padStart(2, '0') },
          { label: 'Sec', value: String(s).padStart(2, '0') },
        ];
      },
    };
  };

  // --- Hero background slideshow: crossfading photos behind the homepage hero ---
  window.heroSlideshow = function (urls, intervalMs) {
    return {
      urls: urls,
      active: 0,
      timer: null,
      init() {
        if (this.urls.length < 2 || reduceMotion) return;
        this.timer = setInterval(() => {
          this.active = (this.active + 1) % this.urls.length;
        }, intervalMs || 5500);
      },
      goTo(i) {
        this.active = i;
        if (this.timer) {
          clearInterval(this.timer);
          this.timer = setInterval(() => {
            this.active = (this.active + 1) % this.urls.length;
          }, intervalMs || 5500);
        }
      },
    };
  };
})();
