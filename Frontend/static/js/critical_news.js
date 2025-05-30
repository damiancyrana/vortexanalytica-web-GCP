/**
 * critical_news.js - Skrypt do wyświetlania krytycznych wiadomości z Pub/Sub
 */

// Zmienne globalne dla połączenia SSE krytycznego
let criticalEventSource = null;
let criticalReconnectAttempt = 0;
let criticalMaxReconnectAttempts = 10;
let criticalReconnectTimeout = null;
let criticalMessages = []; // Array to store up to 2 messages
let criticalMessageTimers = {}; // Object to store timers for each message

// Konfiguracja
const CRITICAL_SSE_CONFIG = {
    url: '/api/news/critical/stream',
    initialBackoff: 1000,
    maxBackoff: 30000,
    backoffFactor: 1.5,
    messageLifetime: 3600000 // 1 godzina w milisekundach
};

// Style CSS dla krytycznych wiadomości
const CRITICAL_STYLES = `
    .critical-news-wrapper {
        display: none;
        width: 100%;
        margin-bottom: 15px;
    }
    
    .critical-news-wrapper.visible {
        display: block;
    }
    
    .critical-news-container {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        width: 100%;
    }
    
    .critical-news-alert {
        background: rgba(24, 28, 36, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 8px;
        padding: 12px 20px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        animation: slideIn 0.3s ease-out;
        transition: all 0.3s ease;
        height: auto;
        min-height: 100px;
    }
    
    .critical-news-alert.signal-buy {
        background: rgba(34, 139, 34, 0.85);
        border-color: rgba(50, 205, 50, 0.4);
    }
    
    .critical-news-alert.signal-sell {
        background: rgba(220, 20, 60, 0.85);
        border-color: rgba(255, 69, 0, 0.4);
    }
    
    .critical-news-alert.signal-hold {
        background: rgba(255, 193, 7, 0.85);
        border-color: rgba(255, 215, 0, 0.4);
    }
    
    .critical-news-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    
    .critical-news-signal {
        font-size: 1rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: flex;
        align-items: center;
        gap: 6px;
        color: #fff;
    }
    
    .critical-news-signal i {
        font-size: 1.1rem;
    }
    
    .critical-news-time {
        font-size: 0.75rem;
        opacity: 0.8;
        color: #fff;
    }
    
    .critical-news-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 5px;
        line-height: 1.3;
        color: #fff;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .critical-news-meta {
        display: flex;
        align-items: center;

        margin-top: 5px;
    }
    
    .critical-news-symbol {
        display: inline-block;
        background: rgba(255, 255, 255, 0.15);
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #fff;
    }
    
    .critical-news-confidence {
        display: inline-block;
        font-size: 0.8rem;
        opacity: 0.8;
        color: #fff;
    }
    
    .critical-news-close {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(255, 255, 255, 0.1);
        border: none;
        color: rgba(255, 255, 255, 0.8);
        cursor: pointer;
        font-size: 0.9rem;
        padding: 4px 8px;
        border-radius: 4px;
        transition: all 0.2s;
        z-index: 10;
    }
    
    .critical-news-close:hover {
        color: #fff;
        background: rgba(255, 255, 255, 0.2);
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Responsive design */
    @media (max-width: 900px) {
        .critical-news-container {
            grid-template-columns: 1fr;
        }
    }
    
    @media (max-width: 768px) {
        .critical-news-alert {
            padding: 12px 16px;
            min-height: 80px;
        }
        
        .critical-news-signal {
            font-size: 0.9rem;
        }
        
        .critical-news-title {
            font-size: 0.8rem;
        }
    }
`;

// Dodaj style do strony
function injectCriticalStyles() {
    const styleElement = document.createElement('style');
    styleElement.textContent = CRITICAL_STYLES;
    document.head.appendChild(styleElement);
}

// Formatuje datę do czytelnej postaci
function formatCriticalDate(dateStr) {
    if (!dateStr) return 'N/A';
    
    try {
        const date = new Date(dateStr);
        return date.toLocaleTimeString();
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

// Tworzy wrapper dla krytycznych wiadomości
function createCriticalWrapper() {
    const dashboardContainer = document.querySelector('.dashboard-container');
    if (!dashboardContainer) {
        console.error("Dashboard container not found");
        return null;
    }
    
    let wrapper = document.querySelector('.critical-news-wrapper');
    if (!wrapper) {
        wrapper = document.createElement('div');
        wrapper.className = 'critical-news-wrapper';
        wrapper.innerHTML = '<div class="critical-news-container"></div>';
        dashboardContainer.insertBefore(wrapper, dashboardContainer.firstChild);
    }
    
    return wrapper;
}

// Wyświetla krytyczną wiadomość
function displayCriticalMessage(message) {
    const wrapper = createCriticalWrapper();
    if (!wrapper) return;
    
    const container = wrapper.querySelector('.critical-news-container');
    
    // Generate unique ID for the message
    const messageId = message.news_id || Date.now().toString();
    
    // Check if message already exists
    if (criticalMessages.find(m => m.news_id === messageId)) {
        console.log("Critical message already displayed:", messageId);
        return;
    }
    
    // Mapuj sygnały
    const signalMap = {
        'BUY': { text: 'UP', icon: 'fa-arrow-up', class: 'signal-buy' },
        'SELL': { text: 'DOWN', icon: 'fa-arrow-down', class: 'signal-sell' },
        'HOLD': { text: 'HOLD', icon: 'fa-pause', class: 'signal-hold' }
    };
    
    const signal = signalMap[message.signal] || signalMap['HOLD'];
    const formattedTime = formatCriticalDate(message.time_reported);
    
    // Create message object
    const messageObj = {
        news_id: messageId,
        element: null,
        timestamp: Date.now()
    };
    
    // Utwórz HTML wiadomości
    const messageHtml = `
        <div class="critical-news-alert ${signal.class}" data-message-id="${messageId}">
            <button class="critical-news-close" onclick="closeCriticalMessage('${messageId}')">
                <i class="fas fa-times"></i>
            </button>
            <div class="critical-news-header">
                <div class="critical-news-signal">
                    <i class="fas ${signal.icon}"></i>
                    ${signal.text}
                </div>
                <div class="critical-news-time">${formattedTime}</div>
            </div>
            <div class="critical-news-title">${escapeHtml(message.title)}</div>
            <div class="critical-news-meta">
                <span class="critical-news-symbol">${escapeHtml(message.symbol || 'N/A')}</span>
                ${message.confidence ? `<span class="critical-news-confidence">Confidence: ${message.confidence}%</span>` : ''}
            </div>
        </div>
    `;
    
    // If we already have 2 messages, remove the oldest one
    if (criticalMessages.length >= 2) {
        const oldestMessage = criticalMessages.shift();
        removeCriticalMessage(oldestMessage.news_id);
    }
    
    // Add new message
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = messageHtml;
    const messageElement = tempDiv.firstElementChild;
    container.appendChild(messageElement);
    
    messageObj.element = messageElement;
    criticalMessages.push(messageObj);
    
    // Show wrapper
    wrapper.classList.add('visible');
    
    // Set timer to auto-remove after 1 hour
    criticalMessageTimers[messageId] = setTimeout(() => {
        closeCriticalMessage(messageId);
    }, CRITICAL_SSE_CONFIG.messageLifetime);
}

// Usuwa krytyczną wiadomość
function removeCriticalMessage(messageId) {
    const messageIndex = criticalMessages.findIndex(m => m.news_id === messageId);
    if (messageIndex === -1) return;
    
    const message = criticalMessages[messageIndex];
    if (message.element) {
        message.element.style.opacity = '0';
        message.element.style.transform = 'scale(0.95)';
        setTimeout(() => {
            message.element.remove();
            
            // Hide wrapper if no more messages
            if (criticalMessages.length === 0) {
                const wrapper = document.querySelector('.critical-news-wrapper');
                if (wrapper) {
                    wrapper.classList.remove('visible');
                }
            }
        }, 300);
    }
    
    // Clear timer
    if (criticalMessageTimers[messageId]) {
        clearTimeout(criticalMessageTimers[messageId]);
        delete criticalMessageTimers[messageId];
    }
    
    // Remove from array
    criticalMessages.splice(messageIndex, 1);
}

// Zamyka krytyczną wiadomość (wywołane przez użytkownika)
function closeCriticalMessage(messageId) {
    removeCriticalMessage(messageId);
}

// Ukrywa wszystkie krytyczne wiadomości
function hideAllCriticalMessages() {
    const messageIds = criticalMessages.map(m => m.news_id);
    messageIds.forEach(id => removeCriticalMessage(id));
}

// Obsługa Server-Sent Events dla krytycznych wiadomości
function setupCriticalSSEConnection() {
    // Zamknij istniejące połączenie
    if (criticalEventSource) {
        criticalEventSource.close();
        criticalEventSource = null;
    }
    
    try {
        // Utwórz EventSource
        criticalEventSource = new EventSource(CRITICAL_SSE_CONFIG.url);
        
        // Obsługa otwarcia połączenia
        criticalEventSource.onopen = (event) => {
            console.log("Krytyczne połączenie SSE otwarte");
            criticalReconnectAttempt = 0;
        };
        
        // Obsługa wiadomości
        criticalEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Ignoruj heartbeat
                if (data.type === "heartbeat") {
                    console.debug("Otrzymano heartbeat krytycznego SSE");
                    return;
                }
                
                // Ignoruj wiadomość początkową
                if (data.type === "connected") {
                    console.log("Krytyczne połączenie SSE ustanowione:", data.message);
                    return;
                }
                
                // Ukryj wiadomości jeśli otrzymano sygnał czyszczenia
                if (data.type === "clear_critical") {
                    hideAllCriticalMessages();
                    return;
                }
                
                // Wyświetl krytyczną wiadomość
                if (data.type === "critical") {
                    console.log("Otrzymano krytyczną wiadomość:", data);
                    displayCriticalMessage(data);
                }
                
            } catch (error) {
                console.error("Błąd podczas przetwarzania krytycznej wiadomości SSE:", error, event.data);
            }
        };
        
        // Obsługa błędów z automatycznym reconnect
        criticalEventSource.onerror = (error) => {
            console.error("Błąd krytycznego połączenia SSE:", error);
            
            if (criticalEventSource) {
                criticalEventSource.close();
                criticalEventSource = null;
            }
            
            // Wykładnicze opóźnienie przed ponowną próbą
            if (criticalReconnectAttempt < criticalMaxReconnectAttempts) {
                const backoff = Math.min(
                    CRITICAL_SSE_CONFIG.initialBackoff * Math.pow(CRITICAL_SSE_CONFIG.backoffFactor, criticalReconnectAttempt),
                    CRITICAL_SSE_CONFIG.maxBackoff
                );
                
                console.log(`Ponowna próba krytycznego połączenia SSE za ${backoff}ms (próba ${criticalReconnectAttempt + 1}/${criticalMaxReconnectAttempts})`);
                
                criticalReconnectTimeout = setTimeout(() => {
                    criticalReconnectAttempt++;
                    setupCriticalSSEConnection();
                }, backoff);
            } else {
                console.error(`Osiągnięto maksymalną liczbę prób krytycznego połączenia SSE (${criticalMaxReconnectAttempts})`);
            }
        };
        
    } catch (error) {
        console.error("Nie można utworzyć krytycznego połączenia SSE:", error);
        
        // Automatyczna próba ponownego połączenia
        if (criticalReconnectAttempt < criticalMaxReconnectAttempts) {
            const backoff = Math.min(
                CRITICAL_SSE_CONFIG.initialBackoff * Math.pow(CRITICAL_SSE_CONFIG.backoffFactor, criticalReconnectAttempt),
                CRITICAL_SSE_CONFIG.maxBackoff
            );
            
            console.log(`Ponowna próba krytycznego połączenia SSE za ${backoff}ms (próba ${criticalReconnectAttempt + 1}/${criticalMaxReconnectAttempts})`);
            
            criticalReconnectTimeout = setTimeout(() => {
                criticalReconnectAttempt++;
                setupCriticalSSEConnection();
            }, backoff);
        }
    }
}

// Inicjalizacja przy załadowaniu strony
document.addEventListener('DOMContentLoaded', function() {
    console.log("Inicjalizacja systemu krytycznych wiadomości");
    
    // Wstrzyknij style CSS
    injectCriticalStyles();
    
    // Poczekaj aż dashboard container będzie dostępny
    const checkDashboard = setInterval(() => {
        if (document.querySelector('.dashboard-container')) {
            clearInterval(checkDashboard);
            // Ustaw połączenie SSE dla krytycznych wiadomości
            setupCriticalSSEConnection();
        }
    }, 100);
});

// Czyszczenie zasobów przy zamknięciu strony
window.addEventListener('beforeunload', function() {
    // Zamknij połączenie SSE
    if (criticalEventSource) {
        criticalEventSource.close();
        criticalEventSource = null;
    }
    
    // Wyczyść timeouty
    if (criticalReconnectTimeout) {
        clearTimeout(criticalReconnectTimeout);
        criticalReconnectTimeout = null;
    }
    
    // Wyczyść wszystkie timery wiadomości
    Object.values(criticalMessageTimers).forEach(timer => clearTimeout(timer));
    criticalMessageTimers = {};
});

// Eksportuj funkcje globalne
window.closeCriticalMessage = closeCriticalMessage;