/**
 * Frontend/static/js/historical_news.js
 *
 * Obsługuje formularz wyszukiwania historycznych wiadomości,
 * komunikację z API backendu i wyświetlanie wyników.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Sprawdź, czy element widoku istnieje, zanim cokolwiek zrobimy
    const newsView = document.getElementById('historical-news-view');
    if (!newsView) {
        // console.log("Historical news view not currently active or found.");
        return; // Nie wykonuj reszty skryptu, jeśli widok nie jest załadowany
    }
    console.log("Initializing historical news script...");

    // Załaduj zawartość HTML formularza, jeśli jeszcze nie istnieje
    // (Alternatywnie, backend mógłby renderować to od razu w index.html)
    // Tutaj zakładamy, że #historical-news-view jest pusty i musimy go wypełnić.
    // Dla uproszczenia, na razie zakładamy, że HTML jest już w #historical-news-view
    // dzięki renderowaniu z backendu lub wcześniejszemu ładowaniu.

    const newsForm = document.getElementById('historical-news-form');
    const symbolInput = document.getElementById('news-symbol');
    const fromDateInput = document.getElementById('news-from-date');
    const toDateInput = document.getElementById('news-to-date');
    const submitButton = document.getElementById('submit-news-button');
    const resultsContainer = document.getElementById('news-results-container');
    const messageArea = document.getElementById('news-message-area');

    if (!newsForm || !symbolInput || !fromDateInput || !toDateInput || !submitButton || !resultsContainer || !messageArea) {
        console.error("One or more required elements for historical news not found within #historical-news-view.");
        if (newsView) newsView.innerHTML = '<p style="color: red;">Error: Could not initialize news interface components.</p>';
        return;
    }

    // Funkcja pomocnicza do wyświetlania komunikatów
    const showNewsMessage = (message, type) => {
        messageArea.textContent = message;
        messageArea.className = `auth-message ${type}`; // Użyjmy tej samej klasy co w login dla spójności
        messageArea.style.display = 'block';
    };

    const clearNewsMessage = () => {
        messageArea.textContent = '';
        messageArea.style.display = 'none';
        messageArea.className = 'auth-message';
    };

    // Funkcja do formatowania timestampu UNIX na czytelną datę/czas
    const formatTimestamp = (timestamp) => {
        if (!timestamp) return 'N/A';
        try {
            // Mnożymy przez 1000, bo JS oczekuje milisekund
            const date = new Date(timestamp * 1000);
            return date.toLocaleString(); // Format lokalny (np. 27.04.2025, 16:30:00)
        } catch (e) {
            console.error("Error formatting timestamp:", timestamp, e);
            return 'Invalid Date';
        }
    };

    // Funkcja do renderowania wyników
    const renderNewsResults = (newsItems) => {
        resultsContainer.innerHTML = ''; // Wyczyść poprzednie wyniki

        if (!newsItems || newsItems.length === 0) {
            resultsContainer.innerHTML = '<p>No news found for the selected criteria.</p>';
            return;
        }

        newsItems.forEach(item => {
            const newsElement = document.createElement('div');
            newsElement.classList.add('news-item'); // Użyj stylów zdefiniowanych w HTML/CSS

            // Obrazek (jeśli istnieje)
            const imageElement = item.image ? `<img src="${item.image}" alt="News thumbnail" class="thumbnail">` : '<div class="thumbnail-placeholder" style="width:80px; height:80px; background:#eee; border-radius:4px; flex-shrink:0;"></div>'; // Placeholder

            // Treść wiadomości
            const contentElement = `
                <div class="content">
                    <h3><a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer">${item.headline || 'No Headline'}</a></h3>
                    <p class="summary">${item.summary || 'No summary available.'}</p>
                    <div class="meta">
                        <span><i class="fas fa-calendar-alt"></i> ${formatTimestamp(item.datetime)}</span>
                        <span><i class="fas fa-newspaper"></i> ${item.source || 'Unknown Source'}</span>
                        ${item.related ? `<span><i class="fas fa-tags"></i> Related: ${item.related}</span>` : ''}
                        ${item.category ? `<span><i class="fas fa-folder"></i> Category: ${item.category}</span>` : ''}
                    </div>
                </div>
            `;

            newsElement.innerHTML = imageElement + contentElement;
            resultsContainer.appendChild(newsElement);
        });
    };

    // Obsługa wysłania formularza
    newsForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        clearNewsMessage();
        resultsContainer.innerHTML = ''; // Wyczyść wyniki przed nowym wyszukiwaniem
        submitButton.disabled = true;
        showNewsMessage('Searching for news...', 'loading');

        const symbol = symbolInput.value.trim().toUpperCase();
        const fromDate = fromDateInput.value;
        const toDate = toDateInput.value;

        // Prosta walidacja front-endowa (backend ma swoją)
        if (!symbol || !fromDate || !toDate) {
            showNewsMessage('Please fill in all fields.', 'error');
            submitButton.disabled = false;
            return;
        }

        try {
            // Sprawdzenie, czy funkcja fetchWithAuth jest dostępna globalnie
            // Zakładamy, że index.js ją udostępni lub ten skrypt jest ładowany po index.js
            if (typeof fetchWithAuth !== 'function') {
                 throw new Error('Authentication function (fetchWithAuth) not found.');
            }

            // Budowanie URL z parametrami Query
            const params = new URLSearchParams({
                symbol: symbol,
                from_date: fromDate,
                to_date: toDate
            });
            const url = `/api/news/company-news?${params.toString()}`;

            const response = await fetchWithAuth(url, { method: 'GET' });

            if (!response.ok) {
                let errorDetail = `Server error: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) { /* Ignoruj błąd parsowania JSON błędu */ }
                throw new Error(errorDetail);
            }

            const newsData = await response.json();
            clearNewsMessage(); // Usuń komunikat "Searching..."
            renderNewsResults(newsData);

        } catch (error) {
            console.error('Error fetching or processing news:', error);
            showNewsMessage(`Error: ${error.message || 'Could not fetch news.'}`, 'error');
            resultsContainer.innerHTML = ''; // Wyczyść, jeśli były jakieś częściowe wyniki
        } finally {
            submitButton.disabled = false; // Odblokuj przycisk niezależnie od wyniku
        }
    });

     console.log("Historical news script initialized.");

}); // Koniec DOMContentLoaded

// Potrzebujemy udostępnić fetchWithAuth globalnie lub znaleźć inny sposób
// Na razie zakładamy, że jest dostępna w momencie wykonania.
// Można to poprawić np. przez stworzenie wspólnego modułu Utils.
// Proste (ale nie najlepsze) rozwiązanie:
if (typeof window.fetchWithAuth === 'undefined' && typeof fetchWithAuth === 'function') {
     window.fetchWithAuth = fetchWithAuth;
}