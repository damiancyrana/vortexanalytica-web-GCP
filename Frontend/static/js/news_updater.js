/**
 * news_updater.js - Skrypt do odbierania i wyświetlania wiadomości z API przy użyciu SSE
 */

// Funkcja dodająca pojedynczą wiadomość do kontenera
function addNewsMessageToContainer(message, container, addToTop = true) {
    // Sprawdź czy wiadomość o takim ID już istnieje w kontenerze
    if (message.news_id && document.querySelector(`.news-item[data-news-id="${message.news_id}"]`)) {
      return; // Pomijaj duplikaty
    }
    
    // Określ klasę na podstawie narrative_impact
    let impactClass = 'medium'; // domyślnie medium (neutralna)
    if (message.narrative_impact && message.narrative_impact.toLowerCase() === 'yes') {
      impactClass = 'positive';
    } else if (message.narrative_impact && message.narrative_impact.toLowerCase() === 'no') {
      impactClass = 'negative';
    }
    
    // Sformatuj datę
    let formattedDate = message.time_reported;
    try {
      const date = new Date(message.time_reported);
      formattedDate = date.toLocaleString();
    } catch (e) {
      console.warn("Nie można sformatować daty:", e);
    }
    
    // Utwórz HTML wiadomości
    const messageHtml = `
      <div class="news-item ${impactClass} fade-in" data-news-id="${message.news_id}">
        <div class="news-header">
          <div class="news-title">${message.title}</div>
          <div class="news-date">${formattedDate}</div>
        </div>
        <div class="news-labels">
          <span class="news-label">Impact: ${message.narrative_impact}</span>
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
  
  // Inicjalne pobranie wiadomości
  async function loadInitialMessages() {
    const newsContainer = document.querySelector('.news-container');
    if (!newsContainer) {
      console.error("Kontener wiadomości nie znaleziony.");
      return;
    }
  
    try {
      const response = await window.fetchWithAuth('/api/news?limit=20');
      
      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (!data.news || !Array.isArray(data.news) || data.news.length === 0) {
        // Tylko jeśli kontener jest pusty, pokazujemy wiadomość o braku wiadomości
        if (newsContainer.querySelector('.news-item') === null) {
          newsContainer.innerHTML = '<p style="text-align: center; padding: 20px; color: var(--current-text-muted);">No news</p>';
        }
        return;
      }
      
      // Usuń komunikat o braku wiadomości, jeśli istnieje
      const noMessagesElem = newsContainer.querySelector('p[style*="text-align: center"]');
      if (noMessagesElem) {
        noMessagesElem.remove();
      }
      
      // Dodaj każdą wiadomość bez czyszczenia kontenera
      data.news.forEach(message => {
        addNewsMessageToContainer(message, newsContainer, false);
      });
      
      console.log(`Załadowano ${data.news.length} wiadomości początkowych.`);
      
    } catch (error) {
      console.error("Błąd podczas pobierania wiadomości początkowych:", error);
      // Dodajemy komunikat o błędzie tylko jeśli nie ma żadnych wiadomości
      if (newsContainer.querySelector('.news-item') === null) {
        newsContainer.innerHTML = `<p style="text-align: center; padding: 20px; color: var(--accent-color);">Błąd podczas ładowania wiadomości: ${error.message}</p>`;
      }
    }
  }
  
  // Obsługa Server-Sent Events
  let eventSource = null;
  
  function setupSSEConnection() {
    if (eventSource) {
      eventSource.close();
    }
    
    const newsContainer = document.querySelector('.news-container');
    if (!newsContainer) {
      console.error("Kontener wiadomości nie znaleziony.");
      return;
    }
    
    try {
      // Utwórz EventSource
      eventSource = new EventSource('/api/news/stream');
      
      eventSource.onopen = (event) => {
        console.log("Połączenie SSE otwarte");
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Ignoruj heartbeat
          if (data.type === "heartbeat") {
            return;
          }
          
          // Ignoruj wiadomość początkową
          if (data.type === "connected") {
            console.log("Połączenie SSE ustanowione pomyślnie");
            return;
          }
          
          // Usuń komunikat o braku wiadomości, jeśli istnieje
          const noMessagesElem = newsContainer.querySelector('p[style*="text-align: center"]');
          if (noMessagesElem) {
            noMessagesElem.remove();
          }
          
          // Dodaj nową wiadomość na górę listy
          console.log("Otrzymano nową wiadomość przez SSE:", data);
          addNewsMessageToContainer(data, newsContainer, true);
          
        } catch (error) {
          console.error("Błąd podczas przetwarzania wiadomości SSE:", error, event.data);
        }
      };
      
      eventSource.onerror = (error) => {
        console.error("Błąd połączenia SSE:", error);
        
        if (eventSource.readyState === EventSource.CLOSED) {
          console.log("Połączenie SSE zamknięte. Próba ponownego połączenia za 3 sekundy...");
          
          // Automatyczna próba ponownego połączenia
          setTimeout(() => {
            setupSSEConnection();
          }, 3000);
        }
      };
      
    } catch (error) {
      console.error("Nie można utworzyć połączenia SSE:", error);
      
      // Automatyczna próba ponownego połączenia
      setTimeout(() => {
        setupSSEConnection();
      }, 5000);
    }
  }
  
  // Inicjalizacja przy załadowaniu strony
  document.addEventListener('DOMContentLoaded', function() {
    // Najpierw pobierz wiadomości początkowe
    loadInitialMessages().then(() => {
      // Następnie ustaw połączenie SSE dla nowych wiadomości
      setupSSEConnection();
    });
    
    // Obsługa przycisku odświeżania
    const refreshButton = document.getElementById('refresh-btn');
    if (refreshButton) {
      refreshButton.addEventListener('click', loadInitialMessages);
    }
  });
  
  // Czyszczenie zasobów przy zamknięciu strony
  window.addEventListener('beforeunload', function() {
    if (eventSource) {
      eventSource.close();
    }
  });