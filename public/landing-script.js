/* ============================================================
   MavX Mndset — Landing Page JavaScript (landing-script.js)
   Isolated: Carousel (auto-play only), Accordion, Scroll Animations, Navbar
   ============================================================ */

(function () {
  'use strict';

  /* ── DOM Ready ── */
  document.addEventListener('DOMContentLoaded', function () {
    initNavbar();
    initCarousel();
    initAccordion();
    initScrollAnimations();
    initMobileMenu();
    initParticles();
  });

  /* ══════════════════════════════════════════
     NAVBAR — Scroll Effect
  ══════════════════════════════════════════ */
  function initNavbar() {
    const nav = document.getElementById('l-nav');
    if (!nav) return;

    let ticking = false;
    window.addEventListener('scroll', function () {
      if (!ticking) {
        requestAnimationFrame(function () {
          if (window.scrollY > 30) {
            nav.classList.add('scrolled');
          } else {
            nav.classList.remove('scrolled');
          }
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  /* ══════════════════════════════════════════
     MOBILE MENU
  ══════════════════════════════════════════ */
  function initMobileMenu() {
    const hamburger = document.getElementById('l-hamburger');
    const mobileMenu = document.getElementById('l-mobile-menu');
    if (!hamburger || !mobileMenu) return;

    hamburger.addEventListener('click', function () {
      const isOpen = mobileMenu.classList.toggle('open');
      hamburger.setAttribute('aria-expanded', isOpen);

      const lines = hamburger.querySelectorAll('span');
      if (isOpen) {
        lines[0].style.transform = 'translateY(7px) rotate(45deg)';
        lines[1].style.opacity = '0';
        lines[2].style.transform = 'translateY(-7px) rotate(-45deg)';
      } else {
        lines[0].style.transform = '';
        lines[1].style.opacity = '';
        lines[2].style.transform = '';
      }
    });

    document.addEventListener('click', function (e) {
      if (!hamburger.contains(e.target) && !mobileMenu.contains(e.target)) {
        mobileMenu.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
        const lines = hamburger.querySelectorAll('span');
        lines[0].style.transform = '';
        lines[1].style.opacity = '';
        lines[2].style.transform = '';
      }
    });

    mobileMenu.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileMenu.classList.remove('open');
        const lines = hamburger.querySelectorAll('span');
        lines[0].style.transform = '';
        lines[1].style.opacity = '';
        lines[2].style.transform = '';
      });
    });
  }

  /* ══════════════════════════════════════════
     CAROUSEL — Auto-Play Only (No Manual Arrows)
     Interval: 3500ms, smooth fade+slide transition
  ══════════════════════════════════════════ */
  function initCarousel() {
    const slidesTrack = document.getElementById('l-carousel-slides');
    const dotsContainer = document.getElementById('l-carousel-dots');
    if (!slidesTrack) return;

    const slides = slidesTrack.querySelectorAll('.l-carousel__slide');
    const totalSlides = slides.length;
    let currentIndex = 0;
    let autoplayTimer = null;
    let isTransitioning = false;

    // Build dot indicators
    if (dotsContainer) {
      for (let i = 0; i < totalSlides; i++) {
        const dot = document.createElement('button');
        dot.className = 'l-carousel__dot' + (i === 0 ? ' active' : '');
        dot.setAttribute('aria-label', 'Go to slide ' + (i + 1));
        dot.setAttribute('role', 'tab');
        dot.addEventListener('click', function () {
          goToSlide(i);
          resetAutoplay();
        });
        dotsContainer.appendChild(dot);
      }
    }

    function updateDots() {
      if (!dotsContainer) return;
      const dots = dotsContainer.querySelectorAll('.l-carousel__dot');
      dots.forEach(function (dot, i) {
        dot.classList.toggle('active', i === currentIndex);
      });
    }

    function goToSlide(index) {
      if (isTransitioning) return;
      isTransitioning = true;
      currentIndex = ((index % totalSlides) + totalSlides) % totalSlides;
      slidesTrack.style.transform = 'translateX(-' + (currentIndex * 100) + '%)';
      updateDots();
      setTimeout(function () { isTransitioning = false; }, 800);
    }

    function nextSlide() { goToSlide(currentIndex + 1); }

    function startAutoplay() {
      // Auto-advance every 3.5 seconds
      autoplayTimer = setInterval(nextSlide, 3500);
    }

    function resetAutoplay() {
      clearInterval(autoplayTimer);
      startAutoplay();
    }

    // Touch/swipe support
    let touchStartX = 0;
    let touchEndX = 0;
    const carouselEl = document.getElementById('l-carousel');
    if (carouselEl) {
      carouselEl.addEventListener('touchstart', function (e) {
        touchStartX = e.changedTouches[0].clientX;
      }, { passive: true });

      carouselEl.addEventListener('touchend', function (e) {
        touchEndX = e.changedTouches[0].clientX;
        const diff = touchStartX - touchEndX;
        if (Math.abs(diff) > 40) {
          if (diff > 0) { goToSlide(currentIndex + 1); } else { goToSlide(currentIndex - 1); }
          resetAutoplay();
        }
      }, { passive: true });

      // Pause on hover, resume on leave
      carouselEl.addEventListener('mouseenter', function () { clearInterval(autoplayTimer); });
      carouselEl.addEventListener('mouseleave', function () { startAutoplay(); });
    }

    // Keyboard arrow support
    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft')  { goToSlide(currentIndex - 1); resetAutoplay(); }
      if (e.key === 'ArrowRight') { goToSlide(currentIndex + 1); resetAutoplay(); }
    });

    startAutoplay();
  }

  /* ══════════════════════════════════════════
     ACCORDION — Exclusive Open
  ══════════════════════════════════════════ */
  function initAccordion() {
    const items = document.querySelectorAll('.l-accordion__item');
    if (!items.length) return;

    items.forEach(function (item) {
      const trigger = item.querySelector('.l-accordion__trigger');
      if (!trigger) return;

      trigger.addEventListener('click', function () {
        const isOpen = item.classList.contains('open');

        // Close all
        items.forEach(function (i) {
          i.classList.remove('open');
          const body = i.querySelector('.l-accordion__body');
          if (body) {
            body.style.maxHeight = '0px';
            body.style.opacity = '0';
          }
          const chev = i.querySelector('.l-accordion__chevron');
          if (chev) chev.style.transform = '';
        });

        // Open clicked if it was closed
        if (!isOpen) {
          item.classList.add('open');
          const body = item.querySelector('.l-accordion__body');
          if (body) {
            body.style.maxHeight = body.scrollHeight + 'px';
            body.style.opacity = '1';
          }
        }
      });
    });
  }

  /* ══════════════════════════════════════════
     SCROLL ANIMATIONS — Intersection Observer
  ══════════════════════════════════════════ */
  function initScrollAnimations() {
    const animTargets = document.querySelectorAll('.l-feat-card, .l-accordion__item, .l-cta-banner__inner');

    if (!('IntersectionObserver' in window)) {
      animTargets.forEach(function (el) { el.classList.add('in-view'); });
      return;
    }

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          const siblings = Array.from(entry.target.parentNode.children);
          const idx = siblings.indexOf(entry.target);
          entry.target.style.transitionDelay = (idx * 70) + 'ms';

          entry.target.classList.add('in-view');
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });

    animTargets.forEach(function (el) { observer.observe(el); });
  }

  /* ══════════════════════════════════════════
     CANVAS PARTICLES — Floating Dots
  ══════════════════════════════════════════ */
  function initParticles() {
    const canvas = document.getElementById('l-particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize, { passive: true });

    const PARTICLE_COUNT = window.innerWidth < 768 ? 30 : 60;
    const particles = [];

    const colors = [
      'rgba(139,92,246,0.5)',
      'rgba(6,182,212,0.4)',
      'rgba(236,72,153,0.35)',
      'rgba(255,255,255,0.2)',
    ];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r: Math.random() * 1.8 + 0.3,
        color: colors[Math.floor(Math.random() * colors.length)],
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        opacity: Math.random() * 0.6 + 0.2,
        opacityDir: Math.random() > 0.5 ? 1 : -1,
        opacitySpeed: Math.random() * 0.005 + 0.002,
      });
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach(function (p) {
        p.x += p.vx;
        p.y += p.vy;

        p.opacity += p.opacityDir * p.opacitySpeed;
        if (p.opacity >= 0.8 || p.opacity <= 0.1) p.opacityDir *= -1;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        ctx.save();
        ctx.globalAlpha = p.opacity;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();
        ctx.restore();
      });

      requestAnimationFrame(draw);
    }

    draw();
  }

})();
