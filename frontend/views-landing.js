/* ─── views-landing.js — Modern Landing Page ──────────────────── */

function renderLanding() {
  document.getElementById('landing-view').innerHTML = `
    <div class="landing-page">
      <nav class="landing-nav fade-in-down">
        <div class="landing-logo">
          <svg class="icon icon--lg text-accent"><use href="#ico-link"/></svg>
          <span>LinkVault</span>
        </div>
        <div class="landing-nav-actions">
          <a href="#/login" class="btn btn--ghost">Sign In</a>
          <a href="#/signup" class="btn btn--primary">Get Started</a>
        </div>
      </nav>

      <main class="landing-main">
        <section class="hero-section">
          <div class="hero-bg-glow"></div>
          <div class="hero-content fade-in-up" style="animation-delay: 0.1s;">
            <div class="hero-badge">Now with AI-Powered Analytics</div>
            <h1 class="hero-title">
              Shorten URLs.<br/>
              <span class="text-gradient">Supercharge links.</span>
            </h1>
            <p class="hero-subtitle">
              The industry-grade URL management platform offering robust API generation, deep real-time analytics, bot detection, and AI comparative reporting.
            </p>
            <div class="hero-ctas">
              <a href="#/signup" class="btn btn--primary btn--lg">Start for Free</a>
              <a href="#/login" class="btn btn--ghost btn--lg">Sign In</a>
            </div>
          </div>
          
          <div class="hero-visual fade-in-up" style="animation-delay: 0.3s;">
            <div class="mockup-window">
              <div class="mockup-header">
                <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
              </div>
              <div class="mockup-body">
                <div class="mock-chart">
                  <div class="mock-bar" style="height: 40%"></div>
                  <div class="mock-bar" style="height: 60%"></div>
                  <div class="mock-bar" style="height: 50%"></div>
                  <div class="mock-bar" style="height: 90%; background: var(--accent)"></div>
                  <div class="mock-bar" style="height: 70%"></div>
                  <div class="mock-bar" style="height: 85%; background: var(--accent)"></div>
                </div>
                <div class="mock-details">
                  <div class="mock-stat">
                    <span class="mock-stat-val">24.5k</span>
                    <span class="mock-stat-lbl">Total Clicks</span>
                  </div>
                  <div class="mock-stat">
                    <span class="mock-stat-val">12</span>
                    <span class="mock-stat-lbl">Peak Hour</span>
                  </div>
                  <div class="mock-stat">
                    <span class="mock-stat-val">1.2%</span>
                    <span class="mock-stat-lbl">Bot Traffic</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="features-section fade-in-up" style="animation-delay: 0.5s;">
          <h2 class="section-heading text-center">Everything you need to scale</h2>
          <div class="features-grid">
            <div class="feature-card">
              <div class="feature-icon"><svg class="icon"><use href="#ico-bar-chart"/></svg></div>
              <h3>Real-Time Analytics</h3>
              <p>Track unique visitors, geolocations, devices, and capture deep traffic insights instantly.</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon"><svg class="icon"><use href="#ico-shield"/></svg></div>
              <h3>Advanced Security</h3>
              <p>Bot detection, SSRF protection, custom code validation, and robust role-based access control.</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon"><svg class="icon"><use href="#ico-folder"/></svg></div>
              <h3>Multi-Project OS</h3>
              <p>Manage discrete campaigns in separate organizational projects. Keep all your links sorted natively.</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon" style="color:var(--accent); background:rgba(99,102,241,0.1);"><svg class="icon"><use href="#ico-eye"/></svg></div>
              <h3>AI Traffic Insights</h3>
              <p>Leverage deterministic LangGraph AI agents to compare traffic across multiple links seamlessly.</p>
            </div>
          </div>
        </section>
      </main>

      <footer class="landing-footer">
        <p>&copy; ${new Date().getFullYear()} LinkVault. All rights reserved.</p>
      </footer>
    </div>
  `;
}
