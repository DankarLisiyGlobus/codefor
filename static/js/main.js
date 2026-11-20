// Переключение темы
function toggleTheme() {
    const body = document.body;
    const isDark = body.classList.toggle('dark-theme');
    
    // Сохраняем в localStorage
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// Загрузка сохраненной темы при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
    }
});

// Смена языка
function changeLanguage(lang) {
    window.location.href = '/lang/' + lang;
}

// Подтверждение удаления
function confirmDelete(message) {
    return confirm(message || 'Вы уверены?');
}

// Автоматическое расширение textarea
document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });
    });
});