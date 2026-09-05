

document.addEventListener('DOMContentLoaded', () => {

  // ==========================================
  // ANNOUNCEMENT BAR CLOSE
  // ==========================================
  const announcementBar = document.getElementById('announcement-bar');
  const announcementClose = document.getElementById('announcement-close');

  if (announcementClose && announcementBar) {
    announcementClose.addEventListener('click', () => {
      announcementBar.style.height = announcementBar.offsetHeight + 'px';
      announcementBar.style.overflow = 'hidden';
      requestAnimationFrame(() => {
        announcementBar.style.transition = 'height 0.3s ease, opacity 0.3s ease';
        announcementBar.style.height = '0';
        announcementBar.style.opacity = '0';
      });
      setTimeout(() => {
        announcementBar.remove();
        // Update CSS variable for mobile menu offset
        document.documentElement.style.setProperty('--announcement-height', '0px');
      }, 320);
    });
  }

  // ==========================================
  // STICKY NAV SHADOW ON SCROLL
  // ==========================================
  const nav = document.getElementById('main-nav');
  const scrollHandler = () => {
    if (window.scrollY > 10) {
      nav.classList.add('scrolled');
    } else {
      nav.classList.remove('scrolled');
    }
  };
  window.addEventListener('scroll', scrollHandler, { passive: true });

  // ==========================================
  // MOBILE HAMBURGER MENU
  // ==========================================
  const hamburger = document.getElementById('hamburger');
  const mobileMenu = document.getElementById('mobile-menu');
  let menuOpen = false;

  if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => {
      menuOpen = !menuOpen;
      mobileMenu.classList.toggle('open', menuOpen);
      hamburger.setAttribute('aria-expanded', menuOpen);
      document.body.style.overflow = menuOpen ? 'hidden' : '';

      // Animate hamburger spans to X
      const spans = hamburger.querySelectorAll('span');
      if (menuOpen) {
        spans[0].style.transform = 'translateY(7px) rotate(45deg)';
        spans[1].style.opacity = '0';
        spans[2].style.transform = 'translateY(-7px) rotate(-45deg)';
      } else {
        spans[0].style.transform = '';
        spans[1].style.opacity = '';
        spans[2].style.transform = '';
      }
    });
  }

  // ==========================================
  // DESKTOP NAV DROPDOWN TOGGLE (click)
  // ==========================================
  const dropdownItems = document.querySelectorAll('.has-dropdown');

  dropdownItems.forEach(item => {
    const btn = item.querySelector('.nav-link-dropdown');
    if (!btn) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = item.classList.contains('open');

      // Close all
      dropdownItems.forEach(d => {
        d.classList.remove('open');
        const b = d.querySelector('.nav-link-dropdown');
        if (b) b.setAttribute('aria-expanded', 'false');
      });

      // Toggle current
      if (!isOpen) {
        item.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });

  // Close dropdowns when clicking outside
  document.addEventListener('click', () => {
    dropdownItems.forEach(d => {
      d.classList.remove('open');
      const b = d.querySelector('.nav-link-dropdown');
      if (b) b.setAttribute('aria-expanded', 'false');
    });
  });

  // ==========================================
  // PRODUCT TABS
  // ==========================================
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.dataset.tab;

      // Update button states
      tabBtns.forEach(b => b.classList.remove('tab-btn--active'));
      btn.classList.add('tab-btn--active');

      // Update panel visibility
      tabPanels.forEach(panel => {
        panel.classList.remove('tab-panel--active');
        if (panel.id === `tab-${targetTab}`) {
          panel.classList.add('tab-panel--active');
        }
      });
    });
  });

  // ==========================================
  // SCROLL-TRIGGERED FADE-IN ANIMATIONS
  // ==========================================
  const addFadeIn = () => {
    const sections = document.querySelectorAll(
      '.split-section, .feature-section, .two-col-section, ' +
      '.fullwidth-section, .features-grid-section, .logos-section, ' +
      '.testimonials-section, .stats-section, .fin-section, .cta-section'
    );

    sections.forEach(section => {
      section.classList.add('fade-in');
    });

    // Also animate individual cards with stagger
    const cards = document.querySelectorAll(
      '.feature-card, .testimonial-card, .stat-block, .fin-metric'
    );
    cards.forEach((card, i) => {
      card.style.transitionDelay = `${(i % 4) * 0.08}s`;
      card.classList.add('fade-in');
    });
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -60px 0px'
  });

  // Apply fade-in classes then observe
  addFadeIn();
  document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

  // ==========================================
  // FIN WIDGET BUTTON
  // ==========================================
  const finWidgetBtn = document.getElementById('fin-widget-btn');
  if (finWidgetBtn) {
    finWidgetBtn.addEventListener('click', () => {
      // Scroll to Fin section or show a pop-up chat
      const finSection = document.getElementById('fin-agent');
      if (finSection) {
        finSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  // ==========================================
  // HERO GALLERY PAUSE ON HOVER
  // ==========================================
  const galleryTrack = document.querySelector('.gallery-track');
  if (galleryTrack) {
    galleryTrack.addEventListener('mouseenter', () => {
      galleryTrack.style.animationPlayState = 'paused';
    });
    galleryTrack.addEventListener('mouseleave', () => {
      galleryTrack.style.animationPlayState = 'running';
    });
  }

  // ==========================================
  // LOGO TRACK PAUSE ON HOVER
  // ==========================================
  const logosTrack = document.getElementById('logos-track');
  if (logosTrack) {
    logosTrack.addEventListener('mouseenter', () => {
      logosTrack.style.animationPlayState = 'paused';
    });
    logosTrack.addEventListener('mouseleave', () => {
      logosTrack.style.animationPlayState = 'running';
    });
  }

  // ==========================================
  // CHAT INPUT INTERACTIVITY (Fin Section)
  // ==========================================
  const chatInput = document.querySelector('.chat-input-bar input');
  const sendBtn = document.querySelector('.send-btn');
  const chatMessages = document.querySelector('.chat-messages');
  const typingIndicator = document.querySelector('.chat-typing');

  const botResponses = [
    "I can help with that! Let me check our system for you right now.",
    "Great question! Based on your account history, here's what I found...",
    "I've looked into this and here's the most relevant information I found.",
    "Sure! I can resolve this for you immediately.",
  ];

  let responseIndex = 0;

  const addUserMessage = (text) => {
    const msg = document.createElement('div');
    msg.className = 'chat-msg user';
    msg.innerHTML = `<div class="user-bubble">${text}</div>`;
    if (typingIndicator) {
      chatMessages.insertBefore(msg, typingIndicator);
    } else {
      chatMessages.appendChild(msg);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const addBotMessage = (text) => {
    const msg = document.createElement('div');
    msg.className = 'chat-msg bot';
    msg.innerHTML = `<div class="bot-icon">⊞</div><div class="bot-bubble">${text}</div>`;
    if (typingIndicator) {
      chatMessages.insertBefore(msg, typingIndicator);
    } else {
      chatMessages.appendChild(msg);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const handleSend = () => {
    if (!chatInput) return;
    const text = chatInput.value.trim();
    if (!text) return;

    addUserMessage(text);
    chatInput.value = '';

    // Show typing
    if (typingIndicator) typingIndicator.style.display = 'flex';

    // Respond after delay
    setTimeout(() => {
      if (typingIndicator) typingIndicator.style.display = 'none';
      addBotMessage(botResponses[responseIndex % botResponses.length]);
      responseIndex++;
    }, 1500);
  };

  if (sendBtn) sendBtn.addEventListener('click', handleSend);
  if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') handleSend();
    });
    // Make it actually editable
    chatInput.removeAttribute('readonly');
  }

  // ==========================================
  // SMOOTH SCROLL FOR ANCHOR LINKS
  // ==========================================
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (href === '#') return;
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth' });
        // Close mobile menu if open
        if (menuOpen && mobileMenu) {
          mobileMenu.classList.remove('open');
          menuOpen = false;
          document.body.style.overflow = '';
        }
      }
    });
  });

  // ==========================================
  // TYPING ANIMATION FOR HERO HEADLINE
  // ==========================================
  const headline = document.querySelector('.hero-headline');
  if (headline) {
    headline.style.opacity = '0';
    headline.style.transform = 'translateY(20px)';
    headline.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
    setTimeout(() => {
      headline.style.opacity = '1';
      headline.style.transform = 'translateY(0)';
    }, 100);

    // Stagger hero right content
    const heroRight = document.querySelector('.hero-right');
    if (heroRight) {
      heroRight.style.opacity = '0';
      heroRight.style.transform = 'translateY(16px)';
      heroRight.style.transition = 'opacity 0.8s ease 0.2s, transform 0.8s ease 0.2s';
      setTimeout(() => {
        heroRight.style.opacity = '1';
        heroRight.style.transform = 'translateY(0)';
      }, 200);
    }
  }

  // ==========================================
  // STAT COUNTER ANIMATION
  // ==========================================
  const statBigs = document.querySelectorAll('.stat-big');
  const statTargets = [];

  statBigs.forEach(stat => {
    const original = stat.textContent.trim();
    statTargets.push({ el: stat, text: original, animated: false });
  });

  const animateCounter = (el, target) => {
    const numMatch = target.match(/[\d.]+/);
    if (!numMatch) return;

    const num = parseFloat(numMatch[0]);
    const prefix = target.replace(/[\d.]+.*/, '');
    const suffix = target.replace(/^[^0-9]*[\d.]+/, '');
    const duration = 1500;
    const start = performance.now();

    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = (num * eased).toFixed(num % 1 !== 0 ? 1 : 0);
      el.textContent = prefix + current + suffix;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        statTargets.forEach(item => {
          if (!item.animated && entry.target.contains(item.el)) {
            item.animated = true;
            animateCounter(item.el, item.text);
          }
        });
      }
    });
  }, { threshold: 0.5 });

  const statsSection = document.querySelector('.stats-section');
  if (statsSection) statsObserver.observe(statsSection);

});
