/**
 * Frontend/static/js/index.js
 *
 * Główny skrypt dla strony index.html.
 * Obsługuje nawigację, przełączanie motywu, interakcje z wiadomościami
 * oraz inicjalizację i obsługę uwierzytelniania Firebase, w tym
 * pobieranie i wysyłanie tokenu ID.
 * Zaimplementowano mechanizm synchronizacji sesji backendu i Firebase.
 */
document.addEventListener('DOMContentLoaded', function() {

  // Stałe i zmienne globalne
  let firebaseApp = null;
  let firebaseAuth = null;
  const FIREBASE_TOKEN_KEY = 'firebaseIdToken';
  const AUTH_STATE_KEY = 'vortexAuthState';
  const TOKEN_REFRESH_INTERVAL = 30 * 60 * 1000; // 30 minut
  let tokenRefreshTimer = null;
  let sessionCheckTimer = null;
  let sessionInitialized = false;

  // Funkcja do pobierania wartości ciasteczka dla CSRF
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  /**
   * Implementacja funkcji do sprawdzania statusu sesji backendowej.
   * Sprawdza czy sesja użytkownika jest aktywna i synchronizuje z Firebase.
   * @returns {Promise<boolean>} True jeśli sesja jest aktywna, false w przeciwnym przypadku
   */
  async function checkBackendSession() {
    try {
      console.log("Sprawdzanie statusu sesji backendowej...");
      const response = await fetch('/api/auth/session-status', {
        method: 'GET',
        credentials: 'same-origin', // Dołącz ciasteczka do żądania
        headers: { 'Accept': 'application/json' }
      });

      if (!response.ok) {
        console.warn(`Błąd sprawdzania sesji: ${response.status}`);
        return false;
      }
      
      const data = await response.json();
      console.log("Status sesji backendowej:", data);
      
      if (data.authenticated && data.user) {
        // Aktualizuj UI z danymi użytkownika z backendu
        updateUserInterface(data.user);
        
        // Zapisz informacje o stanie uwierzytelnienia w SessionStorage
        saveAuthState({
          authenticated: true,
          user: data.user,
          source: 'backend'
        });
        
        // Jeśli Firebase nie jest zainicjowane, nie próbuj synchronizować
        if (!firebaseAuth) return true;
      
        // Sprawdź czy stan Firebase jest zgodny z backendem
        const currentUser = firebaseAuth.currentUser;
        if (!currentUser) {
          // Sesja backendowa jest aktywna, ale Firebase nie ma użytkownika
          // To normalne jeśli strona została odświeżona lub otwarta w nowej karcie
          console.log("Sesja backendowa aktywna, ale brak użytkownika Firebase.");
          
          try {
            // Opcjonalnie: próba silent sign-in w Firebase, jeśli istnieje token
            const savedToken = localStorage.getItem(FIREBASE_TOKEN_KEY);
            if (savedToken) {
              console.log("Próba użycia zapisanego tokenu do odtworzenia sesji Firebase...");
              try {
                await firebaseAuth.signInWithCustomToken(savedToken).catch(() => {
                  console.log("Zapisany token nie jest poprawnym customToken, ignorowanie.");
                });
              } catch (e) {
                console.log("Nie udało się odtworzyć sesji Firebase, korzystamy z sesji backendowej.");
              }
            }
          } catch (e) {
            console.warn("Błąd podczas próby odtworzenia sesji Firebase:", e);
          }
        }
        
        return true;
      } else {
        console.log("Brak aktywnej sesji backendowej.");
        
        // Usuń dane o uwierzytelnieniu
        clearAuthState();
        
        return false;
      }
    } catch (error) {
      console.error("Błąd podczas sprawdzania sesji backendowej:", error);
      return false;
    }
  }

  /**
   * Zapisuje stan uwierzytelnienia w SessionStorage dla lepszej trwałości między odświeżeniami.
   * @param {Object} state - Stan uwierzytelnienia do zapisania
   */
  function saveAuthState(state) {
    try {
      if (!state) return;
      sessionStorage.setItem(AUTH_STATE_KEY, JSON.stringify({
        ...state,
        timestamp: Date.now()
      }));
    } catch (e) {
      console.warn("Nie można zapisać stanu uwierzytelnienia:", e);
    }
  }

  /**
   * Pobiera zapisany stan uwierzytelnienia.
   * @returns {Object|null} Zapisany stan uwierzytelnienia lub null
   */
  function getAuthState() {
    try {
      const stateJson = sessionStorage.getItem(AUTH_STATE_KEY);
      if (!stateJson) return null;
      
      const state = JSON.parse(stateJson);
      // Sprawdź czy stan nie jest zbyt stary (max 12h)
      const maxAge = 12 * 60 * 60 * 1000; // 12 godzin
      if (Date.now() - state.timestamp > maxAge) {
        clearAuthState();
        return null;
      }
      
      return state;
    } catch (e) {
      console.warn("Błąd odczytu stanu uwierzytelnienia:", e);
      return null;
    }
  }

  /**
   * Czyści wszystkie dane o uwierzytelnieniu.
   */
  function clearAuthState() {
    localStorage.removeItem(FIREBASE_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_STATE_KEY);
    sessionStorage.clear();
    stopTokenRefresh();
  }

  /**
   * Aktualizuje interfejs użytkownika na podstawie danych użytkownika.
   * @param {Object} userData - Dane użytkownika
   */
  function updateUserInterface(userData) {
    const userDisplayNameElement = document.getElementById('user-display-name');
    const logoutButton = document.getElementById('logout-btn');
    
    if (!userData) {
      if (userDisplayNameElement) {
        userDisplayNameElement.textContent = 'Logged out';
      }
      if (logoutButton) {
        logoutButton.disabled = true;
        logoutButton.style.display = 'none';
      }
      return;
    }
    
    // Aktualizuj nazwę użytkownika (preferuj name, potem email, na końcu user_id)
    if (userDisplayNameElement) {
      userDisplayNameElement.textContent = userData.name || userData.email || userData.user_id || 'Użytkownik';
    }
    
    // Aktywuj przycisk wylogowania
    if (logoutButton) {
      logoutButton.disabled = false;
      logoutButton.style.display = '';
    }
  }

  /**
   * Rozpoczyna automatyczne odświeżanie tokenu Firebase.
   * @param {firebase.User} user - Obiekt użytkownika Firebase
   */
  function startTokenRefresh(user) {
    if (tokenRefreshTimer) {
      clearInterval(tokenRefreshTimer);
    }
    
    // Funkcja do odświeżenia tokenu
    const refreshToken = async () => {
      if (!user) return;
      
      try {
        console.log("Automatyczne odświeżanie tokenu Firebase...");
        const newToken = await user.getIdToken(true);
        localStorage.setItem(FIREBASE_TOKEN_KEY, newToken);
        console.log("Token Firebase odświeżony pomyślnie.");
      } catch (error) {
        console.error("Błąd odświeżania tokenu Firebase:", error);
      }
    };
    
    // Odśwież token od razu, a potem w regularnych odstępach
    refreshToken();
    tokenRefreshTimer = setInterval(refreshToken, TOKEN_REFRESH_INTERVAL);
  }

  /**
   * Zatrzymuje automatyczne odświeżanie tokenu.
   */
  function stopTokenRefresh() {
    if (tokenRefreshTimer) {
      clearInterval(tokenRefreshTimer);
      tokenRefreshTimer = null;
    }
  }
  
  /**
   * Rozpoczyna okresowe sprawdzanie sesji backendowej.
   * Jest to dodatkowe zabezpieczenie na wypadek wygaśnięcia sesji.
   */
  function startSessionCheck() {
    if (sessionCheckTimer) {
      clearInterval(sessionCheckTimer);
    }
    
    // Sprawdzaj stan sesji co 5 minut
    sessionCheckTimer = setInterval(async () => {
      const isSessionActive = await checkBackendSession();
      if (!isSessionActive) {
        console.log("Sesja backendowa wygasła podczas sprawdzania okresowego.");
        // Jeśli Firebase nadal myśli, że jesteśmy zalogowani, ale backend nie,
        // wylogujmy się z Firebase, aby zsynchronizować stany
        if (firebaseAuth && firebaseAuth.currentUser) {
          console.log("Wylogowanie z Firebase z powodu wygaśnięcia sesji backendowej.");
          await firebaseAuth.signOut().catch(e => console.warn("Błąd wylogowania z Firebase:", e));
        }
        // Zaktualizuj UI
        updateUserInterface(null);
      }
    }, 5 * 60 * 1000); // Co 5 minut
  }

  /**
   * Zatrzymuje okresowe sprawdzanie sesji.
   */
  function stopSessionCheck() {
    if (sessionCheckTimer) {
      clearInterval(sessionCheckTimer);
      sessionCheckTimer = null;
    }
  }

  // === DODANO: Funkcja do udostępnienia globalnie (jeśli potrzeba) ===
  // Robimy to wewnątrz funkcji, aby mieć dostęp do zmiennych lokalnych jak FIREBASE_TOKEN_KEY
  async function fetchWithAuth(url, options = {}) {
    // Pobierz token z localStorage albo z Firebase, jeśli dostępne
    let token = localStorage.getItem(FIREBASE_TOKEN_KEY);
    
    // Jeśli brak tokenu w localStorage, ale Firebase twierdzi, że jesteśmy zalogowani, pobierz nowy token
    if (!token && firebaseAuth && firebaseAuth.currentUser) {
      try {
        token = await firebaseAuth.currentUser.getIdToken(true);
        localStorage.setItem(FIREBASE_TOKEN_KEY, token);
      } catch (error) {
        console.warn("Nie można pobrać tokenu z Firebase:", error);
      }
    }
    
    // Jeśli wciąż brak tokenu, sprawdź sesję backendową
    if (!token) {
      const hasBackendSession = await checkBackendSession();
      if (!hasBackendSession) {
        console.error("Brak tokenu Firebase i aktywnej sesji backendowej.");
        window.location.href = '/login';
        return Promise.reject(new Error("Brak uwierzytelnienia. Przekierowanie do strony logowania."));
      }
    }

    const headers = new Headers(options.headers || {});
    
    // Dodaj token tylko jeśli faktycznie go mamy
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    
    // Automatyczne ustawianie Content-Type dla JSON
    if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
      try {
        JSON.parse(options.body);
        headers.set('Content-Type', 'application/json');
      } catch (e) { /* Ignore if body is not JSON */ }
    }

    try {
      const response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
      
      if (response.status === 401) {
        // Token wygasł lub jest nieprawidłowy po stronie backendu
        console.warn("401 Unauthorized: Sesja wygasła. Sprawdzamy status sesji backendowej...");
        
        // Spróbuj sprawdzić, czy sesja backendowa nadal istnieje
        const hasBackendSession = await checkBackendSession();
        
        if (hasBackendSession) {
          // Sesja backendowa wciąż działa, ale token Firebase wygasł
          console.log("Sesja backendowa aktywna, ale otrzymano 401. Próba ponownego żądania...");
          
          // Usuń token z kolejnego żądania, polegaj tylko na sesji backendowej
          headers.delete('Authorization');
          return fetch(url, { ...options, headers, credentials: 'same-origin' });
        } else {
          // Ani sesja backendowa, ani token Firebase nie działają
          console.warn("Sesja wygasła. Przekierowuję do logowania.");
          localStorage.removeItem(FIREBASE_TOKEN_KEY);
          window.location.href = '/login';
          throw new Error("Sesja wygasła lub token nieprawidłowy.");
        }
      }
      
      // Zwracamy całą odpowiedź, aby można było sprawdzić status itp. w miejscu wywołania
      return response;
    } catch(error) {
      // Loguj tylko błędy inne niż oczekiwane błędy sesji
      if (error.message !== "Sesja wygasła lub token nieprawidłowy." && 
          error.message !== "Brak uwierzytelnienia. Przekierowanie do strony logowania.") {
        console.error(`Błąd zapytania API dla ${url}:`, error);
      }
      // Przekaż błąd dalej, aby obsłużyć go w miejscu wywołania
      throw error;
    }
  }
  // Udostępnienie globalne (proste rozwiązanie)
  window.fetchWithAuth = fetchWithAuth;
  // ================================================================

  // Inicjalizacja systemu uwierzytelniania przy starcie
  initializeAuth();
  setupEventListeners();

  async function initializeAuth() {
    try {
      console.log("Inicjalizacja uwierzytelnienia...");
      
      // Próba wstępnego odtworzenia stanu z SessionStorage (zanim Firebase zacznie działać)
      const savedAuthState = getAuthState();
      if (savedAuthState && savedAuthState.authenticated && savedAuthState.user) {
        console.log("Znaleziono zapisany stan uwierzytelnienia w SessionStorage.");
        updateUserInterface(savedAuthState.user);
      }
      
      // Pobranie konfiguracji Firebase z backendu
      const response = await fetch('/auth/firebase-config');
      if (!response.ok) {
        let errorMsg = 'Błąd pobierania konfiguracji Firebase';
        try {
          const errorData = await response.json();
          errorMsg = errorData.detail || errorData.error || errorMsg;
        } catch (e) { errorMsg = await response.text(); }
        throw new Error(errorMsg);
      }
      const config = await response.json();

      if (!config.apiKey || !config.authDomain) {
        console.error('Niepełne dane konfiguracyjne Firebase.', config);
        displayAuthError('Wystąpił błąd konfiguracji.');
        return;
      }

      // Inicjalizacja Firebase
      if (firebase.apps.length === 0) {
         firebaseApp = firebase.initializeApp({ apiKey: config.apiKey, authDomain: config.authDomain });
      } else {
         firebaseApp = firebase.app();
      }
      firebaseAuth = firebase.auth();
      console.log("Firebase initialized successfully on index page.");
      
      // Jeśli jeszcze nie sprawdziliśmy sesji backendowej, zróbmy to teraz
      if (!sessionInitialized) {
        console.log("Sprawdzanie stanu sesji backendowej przy inicjalizacji...");
        await checkBackendSession();
        sessionInitialized = true;
        
        // Uruchom okresowe sprawdzanie sesji
        startSessionCheck();
      }
      
      // Nasłuchuj na zmiany stanu Firebase
      firebaseAuth.onAuthStateChanged(handleAuthStateChanged);

    } catch (error) {
      console.error('Error initializing Firebase:', error);
      displayAuthError(`Błąd inicjalizacji systemu: ${error.message}. Odśwież stronę.`);
    }
  }

  function displayAuthError(message) {
      const contentWrapper = document.getElementById('contentWrapper');
      if (contentWrapper) {
          contentWrapper.innerHTML = `<p style="color: red; text-align: center; padding: 20px;">${message}</p>`;
      }
      const logoutButton = document.getElementById('logout-btn');
      if(logoutButton) {
        logoutButton.disabled = true;
        logoutButton.style.display = 'none';
      }
  }

 /**
   * Obsługuje zmiany stanu uwierzytelnienia użytkownika.
   * Pobiera i zapisuje token ID, jeśli użytkownik jest zalogowany.
   * Ustawia nazwę użytkownika bezpośrednio z danych Firebase.
   * Dodano synchronizację z sesją backendową.
   * @param {firebase.User | null} user - Obiekt użytkownika Firebase lub null.
   */
  async function handleAuthStateChanged(user) {
    console.log("Firebase onAuthStateChanged wywołany, stan użytkownika:", user ? "zalogowany" : "wylogowany");
    
    if (user) {
      // Użytkownik jest zalogowany w Firebase
      const displayName = user.displayName || user.email || 'User';
      console.log('Firebase user state: Signed in -', displayName);

      try {
        // Pobierz nowy token i zapisz go
        const idToken = await user.getIdToken(true);
        sessionStorage.setItem(FIREBASE_TOKEN_KEY, idToken);
        console.log("Firebase ID Token stored/refreshed.");

        // Ustaw nazwę z Firebase
        updateUserInterface({
          name: displayName,
          email: user.email,
          user_id: user.uid
        });
        
        // Zapisz stan uwierzytelnienia w SessionStorage
        saveAuthState({
          authenticated: true,
          user: {
            name: displayName,
            email: user.email,
            user_id: user.uid
          },
          source: 'firebase'
        });
        
        // Uruchom automatyczne odświeżanie tokenu
        startTokenRefresh(user);

      } catch (error) {
         console.error("Error getting Firebase ID token:", error);
         localStorage.removeItem(FIREBASE_TOKEN_KEY);
         
         // Sprawdź czy mamy aktywną sesję backendową mimo problemu z Firebase
         const hasBackendSession = await checkBackendSession();
         if (!hasBackendSession) {
           displayAuthError(`Błąd sesji: ${error.message}. Spróbuj zalogować się ponownie.`);
           if (firebaseAuth) {
              await firebaseAuth.signOut().catch(e => console.error("Sign out after token failure error:", e));
           }
         }
      }

    } else {
      // Użytkownik nie jest zalogowany w Firebase
      console.log('Firebase user state: Signed out.');
      
      // Usuń token Firebase
      localStorage.removeItem(FIREBASE_TOKEN_KEY);
      
      // Zatrzymaj automatyczne odświeżanie tokenu
      stopTokenRefresh();
      
      // *** WAŻNE: Sprawdź, czy sesja backendowa nadal istnieje mimo braku użytkownika Firebase ***
      const hasBackendSession = await checkBackendSession();
      
      if (!hasBackendSession) {
        // Ani Firebase, ani backend nie mają aktywnej sesji
        console.log("Brak aktywnej sesji Firebase i backendowej. Użytkownik jest wylogowany.");
        
        // Aktualizuj UI dla wylogowanego użytkownika
        updateUserInterface(null);
        
        // Wyczyść zapisany stan uwierzytelnienia
        clearAuthState();
      } else {
        console.log("Firebase twierdzi, że użytkownik jest wylogowany, ale sesja backendowa jest aktywna.");
        // UI został już zaktualizowany w checkBackendSession()
      }
    }
  }

  async function logoutUser() {
    const logoutButton = document.getElementById('logout-btn');
    if (!firebaseAuth) {
        console.error("Firebase Auth not initialized.");
        alert("Błąd wylogowania.");
        return;
    }
    if (logoutButton) logoutButton.disabled = true;

    try {
      // 1. Wyloguj użytkownika z Firebase
      await firebaseAuth.signOut();
      console.log("Firebase sign out successful.");
      
      // 2. Pobierz token CSRF z ciasteczka
      const csrfToken = getCookie("csrftoken");
      console.log("CSRF Token for logout:", csrfToken);
      
      // 3. Przygotuj nagłówki z tokenem CSRF
      const headers = { 
        'Content-Type': 'application/json'
      };
      
      // Dodaj token CSRF w różnych formatach nagłówka, jeśli istnieje
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;  // Popularne w wielu frameworkach
        headers['X-CSRFToken'] = csrfToken;   // Popularne w Django
        headers['CSRF-Token'] = csrfToken;    // Używane w niektórych implementacjach
        headers['CSRFToken'] = csrfToken;     // Prosty wariant
      } else {
        console.warn("CSRF token not found for logout. Request might be rejected.");
      }
      
      // 4. Wywołaj endpoint backendu do usunięcia ciasteczka sesyjnego
      const response = await fetch('/logout', { 
        method: 'POST',
        headers: headers,
        credentials: 'same-origin' // Dołącz ciasteczka do żądania
      });

      if (response.ok) {
        console.log("Backend session cleared successfully.");
        
        // Wyczyść wszystkie dane uwierzytelniania
        clearAuthState();
        
        // Zatrzymaj wszystkie timery
        stopSessionCheck();
        stopTokenRefresh();
        
        window.location.href = '/login'; // Przekieruj na stronę logowania
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error("Backend session clear error:", response.status, errorData.detail || response.statusText);
        // Nawet jeśli jest błąd backendu, wylogowaliśmy się z Firebase, więc przekieruj
        alert("Problem z zakończeniem sesji serwera, ale wylogowano z Firebase.");
        window.location.href = '/login';
      }
    } catch (error) {
      console.error('Logout process error:', error);
      alert(`Błąd wylogowania: ${error.message}`);
      if (logoutButton) logoutButton.disabled = false; // W razie błędu odblokuj
      window.location.href = '/login'; // Przekieruj mimo błędu
    }
  }

  async function fetchProtectedUserData() {
    console.log("Fetching protected data...");
    const contentElement = document.getElementById('user-specific-content');
    try {
      // Użyj globalnej funkcji fetchWithAuth
      const response = await fetchWithAuth('/api/index-data', { method: 'GET' });
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const data = await response.json();
      console.log("Protected data:", data);
      if (contentElement) contentElement.textContent = `API Data: ${JSON.stringify(data, null, 2)}`;
    } catch (error) {
      console.error("Failed to fetch protected data:", error.message);
       if (contentElement) contentElement.textContent = `API Error: ${error.message}`;
    }
  }

  function setupEventListeners() {
    // Nawigacja
    document.querySelectorAll('.nav-btn').forEach(button => {
      button.addEventListener('click', function() {
        const targetView = this.getAttribute('data-view');
        if (!targetView) return;

        // Odznacz wszystkie przyciski
        document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
        // Zaznacz kliknięty przycisk
        this.classList.add('active');

        // Pokaż/ukryj odpowiednie sekcje widoku
        document.querySelectorAll('.view-section').forEach(section => {
           const isActive = section.id === targetView + '-view';

           // === ZMODYFIKOWANO: Logika ustawiania display ===
           let displayStyle = 'none';
           if (isActive) {
               // Zastosuj specyficzne style display dla znanych widoków
               if (targetView === 'feed') {
                   displayStyle = 'grid';
               } else if (targetView === 'overview') {
                   // Zakładamy, że overview używa flex (jak w oryginalnym kodzie)
                   displayStyle = 'flex';
                   // Dodatkowo upewnijmy się, że ma flex-direction: column
                   section.style.flexDirection = 'column';
               } else {
                   // Dla wszystkich innych widoków (w tym 'historical-news')
                   // użyj domyślnego 'block'. Jeśli jakiś widok wymaga innego
                   // stylu (np. grid), dodaj tutaj kolejny warunek `else if`.
                   displayStyle = 'block';
               }
           }
           section.style.display = displayStyle;
           // ===============================================

           // Dodaj/usuń klasę 'active' (może być używana przez inne logiki lub CSS)
           section.classList.toggle('active', isActive);

           // === DODANO: Logika inicjalizacji skryptu widoku (opcjonalne) ===
           // Jeśli skrypt `historical_news.js` działa poprawnie na `DOMContentLoaded`
           // i nie ładujesz zawartości dynamicznie, ta część może nie być konieczna.
           // Jest to przykład, jak można by to zrobić, gdyby inicjalizacja była potrzebna przy przełączeniu.
           if (isActive && targetView === 'historical-news') {
                // Sprawdź, czy skrypt już był "zainicjalizowany" dla tego widoku
                if (!section.dataset.viewInitialized) {
                    console.log("Activating historical news view. Triggering potential init.");
                    // Możesz tutaj wywołać specyficzną funkcję inicjalizującą z historical_news.js,
                    // jeśli została ona udostępniona globalnie, np.:
                    // if (typeof initializeHistoricalNews === 'function') {
                    //     initializeHistoricalNews();
                    // }
                    // Oznacz widok jako zainicjalizowany, aby uniknąć powtórzeń
                    section.dataset.viewInitialized = 'true';
                }
           }
           // ================================================================
        });
      });
    });
    // Aktywuj domyślny widok (np. Feed) przy starcie
    const activeNav = document.querySelector('.nav-btn.active')
                   || document.querySelector('.nav-btn[data-view="feed"]'); // Fallback na feed
    if (activeNav) {
        activeNav.click(); // Symuluj kliknięcie, aby uruchomić logikę przełączania widoku
    } else {
        console.warn("No default active navigation button found.");
    }

    // Filtrowanie (w sekcji Feed)
    const messageFilter = document.getElementById('message-filter');
    if (messageFilter) {
      messageFilter.addEventListener('change', function() {
        const filter = this.value;
        // Filtruj elementy tylko w widoku #feed-view
        document.querySelectorAll('#feed-view .message-list .message-item').forEach(item => {
            const categoryEl = item.querySelector('.message-category');
            let isVisible = false;
            if (filter === 'all') {
                isVisible = true;
            } else if (categoryEl) {
                // Sprawdź, czy klasa kategorii (np. 'equities') jest obecna
                isVisible = categoryEl.classList.contains(filter);
            } else {
                // Jeśli nie ma elementu kategorii, sprawdź klasę samego .message-item
                // (Chociaż obecny HTML ma kategorie w .message-footer)
                isVisible = item.classList.contains(filter);
            }
            // Użyj 'flex', ponieważ .message-item to flex container
            item.style.display = isVisible ? 'flex' : 'none';
        });
      });
    }

    // Odświeżanie (w sekcji Feed)
    const refreshButton = document.getElementById('refresh-btn');
    if (refreshButton) {
      refreshButton.addEventListener('click', async function() {
        const icon = this.querySelector('i');
        if (!icon) return;
        icon.classList.add('fa-spin');
        this.disabled = true;
        console.log("Refreshing feed data..."); // Zaktualizowano log
        try {
            // Sprawdź status sesji przy odświeżaniu danych
            await checkBackendSession();
            
            // TODO: Zaimplementuj faktyczne odświeżanie danych z API
            // await fetchFeedData(); // Przykładowa funkcja
            await new Promise(resolve => setTimeout(resolve, 1500)); // Symulacja opóźnienia
            console.log("Feed refresh complete.");
        } catch (error) {
            console.error("Feed refresh error:", error);
            alert("Feed refresh failed.");
        } finally {
            icon.classList.remove('fa-spin');
            this.disabled = false;
        }
      });
    }

    // Czyszczenie (w sekcji Feed)
    const clearButton = document.getElementById('clear-btn');
    if (clearButton) {
      clearButton.addEventListener('click', () => {
        // Czyść tylko listy w widoku #feed-view
        document.querySelectorAll('#feed-view .message-list').forEach(list => {
            list.innerHTML = '<p style="text-align:center; color: var(--current-text-muted); padding: 20px;">Feed cleared.</p>'; // Komunikat o wyczyszczeniu
        });
        console.log("Feed messages cleared.");
      });
    }

    // Przełączanie Motywu
    const themeToggle = document.getElementById('theme-toggle-btn');
    if (themeToggle) {
        const themeIcon = themeToggle.querySelector('i');
        // Funkcja do ustawiania motywu przy starcie
        const setInitialTheme = () => {
            const savedTheme = localStorage.getItem('theme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const isDark = savedTheme === 'dark' || (savedTheme === null && prefersDark);

            document.body.classList.toggle('dark-theme', isDark);
            if (themeIcon) {
                 themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
            }
             // Upewnij się, że tło Three.js też się aktualizuje
            if (typeof window.updateThemeColors === 'function') {
                 window.updateThemeColors();
            }
        };
        setInitialTheme(); // Ustaw motyw przy ładowaniu strony

        themeToggle.addEventListener('click', () => {
            const isDark = document.body.classList.toggle('dark-theme');
            if (themeIcon) {
                themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
            }
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            // Wywołaj funkcję aktualizacji kolorów w tle Three.js (jeśli istnieje)
            if (typeof window.updateThemeColors === 'function') {
                window.updateThemeColors();
            }
        });
    }


    // Wylogowanie (przycisk animowany)
    const logoutButton = document.getElementById('logout-btn');
    if (logoutButton) {
        // Zainicjuj stan i wyświetlanie przycisku
        logoutButton.disabled = true; // Domyślnie nieaktywny, dopóki Firebase nie potwierdzi użytkownika
        logoutButton.style.display = 'none';
        logoutButton.state = 'default'; // Dodaj niestandardową właściwość stanu

        // Definicje stanów animacji (jak w oryginalnym kodzie)
        const states = {
          'default': { '--figure-duration': '100', '--transform-figure': 'none', '--walking-duration': '100', '--transform-arm1': 'none', '--transform-wrist1': 'none', '--transform-arm2': 'none', '--transform-wrist2': 'none', '--transform-leg1': 'none', '--transform-calf1': 'none', '--transform-leg2': 'none', '--transform-calf2': 'none' },
          'hover': { '--figure-duration': '100', '--transform-figure': 'translateX(1.5px)', '--walking-duration': '100', '--transform-arm1': 'rotate(-5deg)', '--transform-wrist1': 'rotate(-15deg)', '--transform-arm2': 'rotate(5deg)', '--transform-wrist2': 'rotate(6deg)', '--transform-leg1': 'rotate(-10deg)', '--transform-calf1': 'rotate(5deg)', '--transform-leg2': 'rotate(20deg)', '--transform-calf2': 'rotate(-20deg)' },
          'walking1': { '--figure-duration': '300', '--transform-figure': 'translateX(11px)', '--walking-duration': '300', '--transform-arm1': 'translateX(-4px) translateY(-2px) rotate(120deg)', '--transform-wrist1': 'rotate(-5deg)', '--transform-arm2': 'translateX(4px) rotate(-110deg)', '--transform-wrist2': 'rotate(-5deg)', '--transform-leg1': 'translateX(-3px) rotate(80deg)', '--transform-calf1': 'rotate(-30deg)', '--transform-leg2': 'translateX(4px) rotate(-60deg)', '--transform-calf2': 'rotate(20deg)' },
          'walking2': { '--figure-duration': '400', '--transform-figure': 'translateX(17px)', '--walking-duration': '300', '--transform-arm1': 'rotate(60deg)', '--transform-wrist1': 'rotate(-15deg)', '--transform-arm2': 'rotate(-45deg)', '--transform-wrist2': 'rotate(6deg)', '--transform-leg1': 'rotate(-5deg)', '--transform-calf1': 'rotate(10deg)', '--transform-leg2': 'rotate(10deg)', '--transform-calf2': 'rotate(-20deg)' },
          'falling1': { '--figure-duration': '1600', '--walking-duration': '400', '--transform-arm1': 'rotate(-60deg)', '--transform-wrist1': 'none', '--transform-arm2': 'rotate(30deg)', '--transform-wrist2': 'rotate(120deg)', '--transform-leg1': 'rotate(-30deg)', '--transform-calf1': 'rotate(-20deg)', '--transform-leg2': 'rotate(40deg)', '--transform-calf2': 'rotate(-30deg)' },
          'falling2': { '--figure-duration': '1600', '--walking-duration': '400', '--transform-arm1': 'rotate(-60deg)', '--transform-wrist1': 'none', '--transform-arm2': 'rotate(30deg)', '--transform-wrist2': 'rotate(120deg)', '--transform-leg1': 'rotate(80deg)', '--transform-calf1': 'rotate(-20deg)', '--transform-leg2': 'rotate(40deg)', '--transform-calf2': 'rotate(-30deg)' },
          'falling3': { '--figure-duration': '1600', '--walking-duration': '500', '--transform-arm1': 'rotate(-80deg)', '--transform-wrist1': 'none', '--transform-arm2': 'rotate(40deg)', '--transform-wrist2': 'rotate(160deg)', '--transform-leg1': 'rotate(80deg)', '--transform-calf1': 'rotate(-20deg)', '--transform-leg2': 'rotate(40deg)', '--transform-calf2': 'rotate(-30deg)' }
         };
        // Funkcja do aktualizacji stanu animacji
        let updateState = (stateName) => {
            if(states[stateName]){
                logoutButton.state = stateName; // Ustaw aktualny stan
                for(let varName in states[stateName]){
                    let value = states[stateName][varName];
                    // Dodaj 'ms' do wartości liczbowych dla trwania animacji
                    let suffix = (isNaN(value) || !varName.includes('duration')) ? '' : 'ms';
                    logoutButton.style.setProperty(varName, value + suffix);
                }
            }
        };
        // Obsługa zdarzeń myszy dla animacji hover
        logoutButton.addEventListener('mouseenter', () => {
            // Animuj tylko jeśli przycisk jest aktywny i w stanie domyślnym
            if(logoutButton.state === 'default' && !logoutButton.disabled) {
                updateState('hover');
            }
        });
        logoutButton.addEventListener('mouseleave', () => {
            // Wróć do stanu domyślnego tylko jeśli był w stanie hover
            if(logoutButton.state === 'hover' && !logoutButton.disabled) {
                updateState('default');
            }
        });
        // Obsługa kliknięcia - uruchamia sekwencję animacji i wylogowanie
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault(); // Zapobiegaj domyślnej akcji przycisku
            // Uruchom animację tylko jeśli przycisk jest aktywny i w stanie 'default' lub 'hover'
            if ((logoutButton.state === 'default' || logoutButton.state === 'hover') && !logoutButton.disabled) {
                logoutButton.classList.add('clicked'); // Dodaj klasę sygnalizującą kliknięcie
                updateState('walking1'); // Rozpocznij animację chodzenia
                setTimeout(() => {
                    logoutButton.classList.add('door-slammed'); // Dodaj klasę animacji drzwi
                    updateState('walking2'); // Kontynuuj animację chodzenia
                    setTimeout(() => {
                        logoutButton.classList.add('falling'); // Dodaj klasę animacji upadku
                        updateState('falling1'); // Rozpocznij animację upadku
                        // Poczekaj chwilę, aż animacja upadku się rozpocznie,
                        // a następnie wywołaj funkcję wylogowania
                        setTimeout(() => {
                             logoutUser(); // Wywołaj rzeczywiste wylogowanie
                        }, 1000); // Opóźnienie przed wylogowaniem
                    }, 500); // Czas trwania animacji walking2 + slammed
                }, 400); // Czas trwania animacji walking1
            }
        });
    } else {
        console.warn("Logout button not found.");
    }
  } // Koniec setupEventListeners

});