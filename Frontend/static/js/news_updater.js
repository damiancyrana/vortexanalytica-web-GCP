/**
 * news_updater.js - Skrypt do natychmiastowego odbierania i wyświetlania wiadomości z Pub/Sub przez SSE
 */

// Zmienne globalne dla połączenia SSE
let eventSource = null;
let reconnectAttempt = 0;
let maxReconnectAttempts = 10;
let reconnectTimeout = null;

// Konfiguracja
const SSE_CONFIG = {
    url: '/api/news/stream',
    initialBackoff: 1000,
    maxBackoff: 30000,
    backoffFactor: 1.5
};

// Formatuje datę do czytelnej postaci
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    
    try {
        const date = new Date(dateStr);
        return date.toLocaleString();
    } catch (e) {
        console.warn("Nie można sformatować daty:", e);
        return dateStr;
    }
}

// Funkcja do escapowania HTML (bezpieczeństwo)
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Formatuje encje jako labele
function formatEntitiesAsLabels(entities) {
    if (!entities || !Array.isArray(entities) || entities.length === 0) {
        return '';
    }
    
    return entities.map(entity => {
        const name = entity.normalized_name || entity.text || 'N/A';
        const type = entity.type || 'Unknown';
        return `<span class="news-label">${escapeHtml(name)} (${escapeHtml(type)})</span>`;
    }).join('');
}

// Dodaje pojedynczą wiadomość do kontenera
function addNewsMessageToContainer(message, container, addToTop = true) {
    // Sprawdź czy wiadomość o takim ID już istnieje w kontenerze
    if (message.news_id && document.querySelector(`.news-item[data-news-id="${message.news_id}"]`)) {
        console.log(`Pomijam duplikat wiadomości: ${message.news_id}`);
        return; // Pomijaj duplikaty
    }
    
    // Ukryj komunikat o braku wiadomości, jeśli istnieje
    const noMessagesElem = container.querySelector('p[style*="text-align: center"]');
    if (noMessagesElem) {
        noMessagesElem.remove();
    }
    
    // Ukryj animację ładowania
    const loadingElem = container.querySelector('.quantum-loading');
    if (loadingElem) {
        loadingElem.style.display = 'none';
    }
    
    // Określ klasę na podstawie narrative_impact
    let impactClass = 'medium'; // domyślnie medium (neutralna)
    if (message.narrative_impact && message.narrative_impact.toLowerCase() === 'yes') {
        impactClass = 'positive';
    } else if (message.narrative_impact && message.narrative_impact.toLowerCase() === 'no') {
        impactClass = 'negative';
    }
    
    // Przygotuj dane do wyświetlenia
    const formattedDate = formatDate(message.time_reported);
    
    // Formatuj encje jako labele
    const entitiesLabelsHtml = formatEntitiesAsLabels(message.extracted_entities);
    
    // Utwórz HTML wiadomości - ZMODYFIKOWANE ZGODNIE Z WYMAGANIAMI
    const messageHtml = `
        <div class="news-item ${impactClass} fade-in" data-news-id="${escapeHtml(message.news_id || '')}">
            <div class="news-header">
                <div class="news-title">${escapeHtml(message.title || 'No title')}</div>
                <div class="news-date">${formattedDate}</div>
            </div>
            
            <div class="news-content">
                <p>${escapeHtml(message.interpretation)}</p>
            </div>
            
            <div class="news-labels">
                ${entitiesLabelsHtml}
            </div>
        </div>
    `;
    
    // Dodaj do kontenera (na górę lub dół)
    if (addToTop) {
        container.insertAdjacentHTML('afterbegin', messageHtml);
    } else {
        container.insertAdjacentHTML('beforeend', messageHtml);
    }
    
    // Ogranicz liczbę wiadomości w kontenerze
    const maxMessages = 50;
    const messages = container.querySelectorAll('.news-item');
    if (messages.length > maxMessages) {
        for (let i = maxMessages; i < messages.length; i++) {
            messages[i].remove();
        }
    }
}

// Obsługa Server-Sent Events z automatycznym reconnect
function setupSSEConnection() {
    // Zamknij istniejące połączenie
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    const newsContainer = document.querySelector('.news-container');
    if (!newsContainer) {
        console.error("Kontener wiadomości nie znaleziony.");
        return;
    }
    
    try {
        // Utwórz EventSource
        eventSource = new EventSource(SSE_CONFIG.url);
        
        // Obsługa otwarcia połączenia
        eventSource.onopen = (event) => {
            console.log("Połączenie SSE otwarte - gotowy do odbierania wiadomości z Pub/Sub");
            reconnectAttempt = 0; // Reset licznika ponownych prób
        };
        
        // Obsługa wiadomości - KLUCZOWA FUNKCJONALNOŚĆ
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Ignoruj heartbeat
                if (data.type === "heartbeat") {
                    console.debug("Otrzymano heartbeat SSE");
                    return;
                }
                
                // Ignoruj wiadomość początkową
                if (data.type === "connected") {
                    console.log("Połączenie SSE ustanowione pomyślnie:", data.message);
                    return;
                }
                
                // Dodaj nową wiadomość natychmiast na górę listy
                console.log("Otrzymano nową wiadomość przez SSE:", data);
                addNewsMessageToContainer(data, newsContainer, true);
                
            } catch (error) {
                console.error("Błąd podczas przetwarzania wiadomości SSE:", error, event.data);
            }
        };
        
        // Obsługa błędów z automatycznym reconnect
        eventSource.onerror = (error) => {
            console.error("Błąd połączenia SSE:", error);
            
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            
            // Wykładnicze opóźnienie przed ponowną próbą
            if (reconnectAttempt < maxReconnectAttempts) {
                const backoff = Math.min(
                    SSE_CONFIG.initialBackoff * Math.pow(SSE_CONFIG.backoffFactor, reconnectAttempt),
                    SSE_CONFIG.maxBackoff
                );
                
                console.log(`Ponowna próba połączenia SSE za ${backoff}ms (próba ${reconnectAttempt + 1}/${maxReconnectAttempts})`);
                
                reconnectTimeout = setTimeout(() => {
                    reconnectAttempt++;
                    setupSSEConnection();
                }, backoff);
            } else {
                console.error(`Osiągnięto maksymalną liczbę prób połączenia SSE (${maxReconnectAttempts})`);
                // Dodaj komunikat o problemie z połączeniem
                if (!newsContainer.querySelector('.connection-error')) {
                    const errorMessage = `
                        <div class="connection-error" style="text-align: center; padding: 20px; color: #ff4b4b;">
                            <p>Nie można połączyć się z serwerem. Spróbuj odświeżyć stronę.</p>
                            <button id="retry-connection" style="padding: 8px 16px; margin-top: 10px; cursor: pointer;">
                                Spróbuj ponownie
                            </button>
                        </div>
                    `;
                    newsContainer.insertAdjacentHTML('afterbegin', errorMessage);
                    
                    // Dodaj obsługę przycisku retry
                    const retryBtn = document.getElementById('retry-connection');
                    if (retryBtn) {
                        retryBtn.addEventListener('click', () => {
                            // Usuń komunikat o błędzie
                            const errorElement = newsContainer.querySelector('.connection-error');
                            if (errorElement) {
                                errorElement.remove();
                            }
                            
                            // Resetuj parametry i spróbuj ponownie
                            reconnectAttempt = 0;
                            if (reconnectTimeout) {
                                clearTimeout(reconnectTimeout);
                                reconnectTimeout = null;
                            }
                            setupSSEConnection();
                        });
                    }
                }
            }
        };
        
    } catch (error) {
        console.error("Nie można utworzyć połączenia SSE:", error);
        
        // Automatyczna próba ponownego połączenia z wykładniczym opóźnieniem
        if (reconnectAttempt < maxReconnectAttempts) {
            const backoff = Math.min(
                SSE_CONFIG.initialBackoff * Math.pow(SSE_CONFIG.backoffFactor, reconnectAttempt),
                SSE_CONFIG.maxBackoff
            );
            
            console.log(`Ponowna próba połączenia SSE za ${backoff}ms (próba ${reconnectAttempt + 1}/${maxReconnectAttempts})`);
            
            reconnectTimeout = setTimeout(() => {
                reconnectAttempt++;
                setupSSEConnection();
            }, backoff);
        }
    }
}


// Inicjalizacja tylko połączenia SSE przy załadowaniu strony
document.addEventListener('DOMContentLoaded', function() {
    console.log("Inicjalizacja skryptu publikowania wiadomości PubSub");
    
    // Inicjalizacja wiadomości powitalnej
    const newsContainer = document.querySelector('.news-container');
    if (newsContainer && newsContainer.querySelector('.quantum-loading')) {
        newsContainer.querySelector('.quantum-loading div:last-child').textContent = 'Oczekiwanie na nowe wiadomości...';
    }
    
    // Natychmiast ustaw połączenie SSE do odbierania wiadomości na żywo
    setupSSEConnection();
    
    // Obsługa przycisku odświeżania - przeładowuje połączenie SSE
    const refreshButton = document.getElementById('refresh-btn');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.add('fa-spin');
            }
            this.disabled = true;
            
            try {
                // Resetuj połączenie SSE
                reconnectAttempt = 0;
                if (reconnectTimeout) {
                    clearTimeout(reconnectTimeout);
                    reconnectTimeout = null;
                }
                setupSSEConnection();
                
                console.log("Połączenie SSE odświeżone, gotowe do odbierania nowych wiadomości");
            } catch (error) {
                console.error("Błąd podczas odświeżania połączenia SSE:", error);
            } finally {
                // Usuń animację ładowania po 1 sekundzie
                setTimeout(() => {
                    if (icon) {
                        icon.classList.remove('fa-spin');
                    }
                    this.disabled = false;
                }, 1000);
            }
        });
    }
    
    // Obsługa przycisku czyszczenia
    const clearButton = document.getElementById('clear-btn');
    if (clearButton) {
        clearButton.addEventListener('click', clearNewsMessages);
    }
});

// Czyszczenie zasobów przy zamknięciu strony
window.addEventListener('beforeunload', function() {
    // Zamknij połączenie SSE
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    // Wyczyść timeout reconnect
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }
});