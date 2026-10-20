'use strict';
(() => {
  const button = document.getElementById('install-app');
  let installPrompt;
  if (!window.isSecureContext) {
    button.hidden = false;
    button.disabled = true;
    button.textContent = 'Instalação exige HTTPS';
    button.title = 'Acesse o Ritmo por HTTPS para instalar o aplicativo.';
    return;
  }
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    button.hidden = matchMedia('(display-mode: standalone)').matches;
  });
  button.addEventListener('click', async () => {
    if (!installPrompt) return;
    button.disabled = true;
    try {
      await installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      button.hidden = true;
    } finally { button.disabled = false; }
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    button.hidden = true;
  });
})();
