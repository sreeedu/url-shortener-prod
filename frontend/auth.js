/* ─── auth.js — Auth views ───────────────────────────────────── */

function renderLogin() {
  document.getElementById('auth-view').innerHTML = `
    <div class="auth-card fade-in">
      <h2>Welcome back</h2>
      <p class="subtitle">Sign in to your LinkVault account</p>
      <form id="login-form">
        <div class="form-group">
          <label for="login-email">Email</label>
          <input id="login-email" type="email" placeholder="you@example.com" required autocomplete="email"/>
        </div>
        <div class="form-group">
          <label for="login-pass">Password</label>
          <input id="login-pass" type="password" placeholder="••••••••" required autocomplete="current-password"/>
        </div>
        <div id="login-err" class="form-error mb-16" style="display:none"></div>
        <div style="text-align:right;margin-bottom:16px">
          <a href="#/forgot-password" style="font-size:12.5px">Forgot password?</a>
        </div>
        <button type="submit" class="btn btn--primary btn--full" id="login-btn">Sign In</button>
      </form>
      <div class="auth-switch">
        Don't have an account? <a href="#/signup">Sign up</a>
      </div>
    </div>`;

  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('login-btn');
    const errEl = document.getElementById('login-err');
    errEl.style.display = 'none';
    btn.disabled = true; btn.textContent = 'Signing in…';
    try {
      const data = await AuthAPI.login(
        document.getElementById('login-email').value.trim(),
        document.getElementById('login-pass').value
      );
      Store.setTokens(data.access_token, data.refresh_token);
      const user = await AuthAPI.me();
      Store.setUser(user);
      const redirect = sessionStorage.getItem('redirectAfterLogin');
      if (redirect) {
        sessionStorage.removeItem('redirectAfterLogin');
        window.location.hash = redirect;
      } else {
        window.location.hash = '#/dashboard';
      }
    } catch(err) {
      if (err.message.toLowerCase().includes('not verified')) {
        const email = document.getElementById('login-email').value.trim();
        errEl.innerHTML = `${err.message}. <br><a href="#" onclick="window.resendVerification(event, '${email}')" style="text-decoration:underline; font-weight:bold; margin-top:6px; display:inline-block;">Resend verification email</a>`;
      } else {
        errEl.textContent = err.message;
      }
      errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = 'Sign In';
    }
  });
}

window.resendVerification = async function(e, email) {
  e.preventDefault();
  const errEl = document.getElementById('login-err');
  errEl.innerHTML = 'Sending...';
  try {
    const res = await AuthAPI.resendVerification(email);
    errEl.innerHTML = `<span style="color:var(--success);">${res.message || 'Verification email sent.'}</span>`;
  } catch (err) {
    errEl.innerHTML = `Error: ${err.message}`;
  }
};

function renderSignup() {
  document.getElementById('auth-view').innerHTML = `
    <div class="auth-card fade-in">
      <h2>Create account</h2>
      <p class="subtitle">Start shortening links in seconds</p>
      <form id="signup-form">
        <div class="form-group">
          <label for="su-email">Email</label>
          <input id="su-email" type="email" placeholder="you@example.com" required autocomplete="email"/>
        </div>
        <div class="form-group">
          <label for="su-pass">Password</label>
          <input id="su-pass" type="password" placeholder="Min 8 chars, upper, lower, number" required/>
          <span class="form-hint">At least 8 characters with uppercase, lowercase and a number.</span>
        </div>
        <div class="form-group" style="margin-bottom:20px">
          <label for="su-pass2">Confirm Password</label>
          <input id="su-pass2" type="password" placeholder="••••••••" required/>
        </div>
        <div id="su-err" class="form-error mb-16" style="display:none"></div>
        <button type="submit" class="btn btn--primary btn--full" id="su-btn">Create Account</button>
      </form>
      <div class="auth-switch">Already have an account? <a href="#/login">Sign in</a></div>
    </div>`;

  document.getElementById('signup-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('su-btn');
    const errEl = document.getElementById('su-err');
    errEl.style.display = 'none';
    const pass  = document.getElementById('su-pass').value;
    const pass2 = document.getElementById('su-pass2').value;
    if (pass !== pass2) { errEl.textContent = 'Passwords do not match'; errEl.style.display='block'; return; }
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      await AuthAPI.signup(document.getElementById('su-email').value.trim(), pass);
      Toast.success('Account created! Please check your email to verify your account.');
      window.location.hash = '#/login';
    } catch(err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = 'Create Account';
    }
  });
}

function renderForgotPassword() {
  document.getElementById('auth-view').innerHTML = `
    <div class="auth-card fade-in">
      <h2>Reset password</h2>
      <p class="subtitle">Enter your email and we'll send a reset link.</p>
      <form id="forgot-form">
        <div class="form-group" style="margin-bottom:20px">
          <label for="fp-email">Email</label>
          <input id="fp-email" type="email" placeholder="you@example.com" required/>
        </div>
        <div id="fp-msg" style="display:none;padding:12px;border-radius:8px;background:rgba(34,197,94,0.12);color:#4ade80;font-size:13px;margin-bottom:16px"></div>
        <div id="fp-err" class="form-error mb-16" style="display:none"></div>
        <button type="submit" class="btn btn--primary btn--full" id="fp-btn">Send Reset Link</button>
      </form>
      <div class="auth-switch"><a href="#/login">← Back to login</a></div>
    </div>`;

  document.getElementById('forgot-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('fp-btn');
    const msgEl = document.getElementById('fp-msg');
    const errEl = document.getElementById('fp-err');
    errEl.style.display = 'none'; msgEl.style.display = 'none';
    btn.disabled = true; btn.textContent = 'Sending…';
    try {
      const res = await AuthAPI.forgot(document.getElementById('fp-email').value.trim());
      msgEl.textContent = res.message || 'If that email exists, a reset link has been sent.';
      msgEl.style.display = 'block';
    } catch(err) {
      errEl.textContent = err.message; errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = 'Send Reset Link';
    }
  });
}

function renderResetPassword(token) {
  document.getElementById('auth-view').innerHTML = `
    <div class="auth-card fade-in">
      <h2>Set new password</h2>
      <p class="subtitle">Choose a strong password for your account.</p>
      <form id="reset-form">
        <div class="form-group">
          <label for="rp-pass">New Password</label>
          <input id="rp-pass" type="password" placeholder="Min 8 chars" required/>
        </div>
        <div class="form-group" style="margin-bottom:20px">
          <label for="rp-pass2">Confirm Password</label>
          <input id="rp-pass2" type="password" placeholder="••••••••" required/>
        </div>
        <div id="rp-err" class="form-error mb-16" style="display:none"></div>
        <button type="submit" class="btn btn--primary btn--full" id="rp-btn">Update Password</button>
      </form>
    </div>`;

  document.getElementById('reset-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('rp-btn');
    const errEl = document.getElementById('rp-err');
    errEl.style.display = 'none';
    const pass  = document.getElementById('rp-pass').value;
    const pass2 = document.getElementById('rp-pass2').value;
    if (pass !== pass2) { errEl.textContent = 'Passwords do not match'; errEl.style.display='block'; return; }
    btn.disabled = true; btn.textContent = 'Updating…';
    try {
      await AuthAPI.reset(token, pass);
      Toast.success('Password updated! Please log in.');
      window.location.hash = '#/login';
    } catch(err) {
      errEl.textContent = err.message; errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = 'Update Password';
    }
  });
}
