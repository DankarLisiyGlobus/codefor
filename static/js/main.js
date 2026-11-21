// Theme
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
    // clock
    const clock = document.getElementById('clock');
    if (clock) {
        const tick = () => {
            const d = new Date();
            const p = n => String(n).padStart(2, '0');
            clock.textContent = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
        };
        tick();
        setInterval(tick, 1000);
    }
});

// keybinding: d = theme
document.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
    if (e.key === 'd' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        toggleTheme();
    }
});

// CSRF для AJAX (на будущее)
window.CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';