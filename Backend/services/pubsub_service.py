"""
Asynchroniczny serwis Pub/Sub do odbierania wiadomości rynkowych.
"""
from __future__ import annotations

import logging
import asyncio
import threading
import time
import orjson
from typing import Dict, Any, Optional, Callable
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1
from google.api_core.exceptions import NotFound, PermissionDenied

from Backend.core.config import Settings
from Backend.services.news_service import NewsService

logger = logging.getLogger(__name__)

class PubSubService:
    _instance = None
    _initialized = False

    project_id: str
    subscription_name: str
    topic_name: str

    subscriber: Optional[pubsub_v1.SubscriberClient] = None
    subscription_path: Optional[str] = None
    streaming_pull_future: Optional[Any] = None
    shutdown_event: Optional[threading.Event] = None
    
    # Zadanie asyncio monitorujące subskrypcję
    _monitoring_task: Optional[asyncio.Task] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(PubSubService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings: Settings) -> None:
        if self._initialized:
            return

        logger.info("Inicjalizacja PubSubService...")

        self.project_id = settings.PROJECT_ID
        self.full_topic_path = "projects/vortexanalytica/topics/marketnews"
        self.topic_name = "marketnews"
        self.subscription_name = "marketnews-sub"
        self.shutdown_event = threading.Event()

        try:
            self.subscriber = pubsub_v1.SubscriberClient()
            self.subscription_path = self.subscriber.subscription_path(
                self.project_id, self.subscription_name
            )
            logger.info(f"PubSubService zainicjalizowany dla projektu: {self.project_id}")
            logger.info(f"Temat: {self.full_topic_path}")
            logger.info(f"Subskrypcja: {self.subscription_path}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji PubSubService: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize PubSubService: {e}") from e

    def _ensure_subscription_exists(self) -> bool:
        if not self._initialized or not self.subscriber:
            logger.error("Próba użycia niezainicjalizowanego PubSubService.")
            return False
        try:
            self.subscriber.get_subscription(subscription=self.subscription_path)
            logger.info(f"Znaleziono istniejącą subskrypcję: {self.subscription_name}")
            return True
        except NotFound:
            logger.error(f"Subskrypcja {self.subscription_name} nie istnieje w projekcie {self.project_id}.")
            logger.error("Upewnij się, że nazwa subskrypcji jest poprawna.")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania subskrypcji: {e}", exc_info=True)
            return False

    async def _async_message_callback(self, message_data: bytes, message_id: str, publish_time: str) -> None:
        """Asynchroniczna wersja przetwarzania wiadomości z Pub/Sub."""
        try:
            print(f"\n===== NOWA WIADOMOŚĆ Z MARKETNEWS (RAW JSON) =====")
            print(f"Message ID: {message_id}")
            print(f"Publish Time: {publish_time}")
            print("\n----- SUROWY JSON -----")
            
            try:
                decoded_json = message_data.decode('utf-8')
                print(decoded_json)
                
                # Parsuj JSON i dodaj do serwisu wiadomości
                news_data = orjson.loads(decoded_json)
                news_service = NewsService()
                
                # Użyj asynchronicznej metody
                await news_service.add_message_async(news_data)
                logger.debug(f"Wiadomość przekazana do NewsService asynchronicznie: {news_data.get('news_id', 'unknown')}")
                
            except UnicodeDecodeError:
                print(f"Nie można zdekodować jako UTF-8: {message_data!r}")
                
            print("\n================================================")
        except Exception as e:
            logger.error(f"Błąd podczas asynchronicznego przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)

    def _message_callback(self, message: pubsub_v1.subscriber.message.Message) -> None:
        """
        Synchroniczny callback dla Pub/Sub, który uruchamia asynchroniczne przetwarzanie.
        """
        try:
            data_bytes = message.data
            message_id = message.message_id
            publish_time = message.publish_time
            
            # Uruchom asynchroniczne przetwarzanie w istniejącej pętli zdarzeń
            # lub utwórz nową jeśli nie ma aktywnej
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Jeśli pętla jest uruchomiona, utwórz zadanie
                    asyncio.create_task(self._async_message_callback(data_bytes, message_id, str(publish_time)))
                else:
                    # Jeśli pętla nie jest uruchomiona, wykonaj synchronicznie
                    loop.run_until_complete(self._async_message_callback(data_bytes, message_id, str(publish_time)))
            except RuntimeError:
                # Jeśli nie ma aktywnej pętli zdarzeń, utwórz nową
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_message_callback(data_bytes, message_id, str(publish_time)))
                
            # Potwierdź odebranie wiadomości
            message.ack()
            
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)
            # Zawsze potwierdź wiadomość, aby uniknąć wielokrotnego przetwarzania
            message.ack()

    async def start_listener_async(self) -> bool:
        """Asynchroniczna wersja uruchamiania nasłuchiwania."""
        if not self._initialized or not self.subscriber:
            logger.error("Próba uruchomienia nasłuchiwania na niezainicjalizowanym PubSubService.")
            return False
            
        self.shutdown_event.clear()
        
        if not self._ensure_subscription_exists():
            logger.error("Nie można rozpocząć nasłuchiwania - subskrypcja nie istnieje.")
            return False
            
        try:
            logger.info(f"Rozpoczynam nasłuchiwanie na subskrypcji: {self.subscription_name}")
            
            # Nasłuchiwanie samo w sobie jest synchroniczne z punktu widzenia FastAPI
            # Uruchamiamy je w osobnym wątku i monitorujemy asynchronicznie
            def start_subscription_in_thread():
                self.streaming_pull_future = self.subscriber.subscribe(
                    self.subscription_path,
                    callback=self._message_callback,
                    flow_control=pubsub_v1.types.FlowControl(max_messages=10)
                )
                print(f"\n[MARKETNEWS] Rozpoczęto nasłuchiwanie na temacie '{self.topic_name}' przez subskrypcję '{self.subscription_name}'")
                print("[MARKETNEWS] Czekam na wiadomości...\n")
                
                try:
                    self.streaming_pull_future.result()  # Blokuje do momentu zakończenia
                except Exception as e:
                    if not self.shutdown_event.is_set():
                        logger.error(f"Błąd w subskrypcji Pub/Sub: {e}", exc_info=True)
            
            # Uruchom nasłuchiwanie w osobnym wątku
            subscription_thread = threading.Thread(
                target=start_subscription_in_thread,
                daemon=True
            )
            subscription_thread.start()
            
            # Uruchom asynchroniczne monitorowanie
            self._monitoring_task = asyncio.create_task(self._monitor_subscription_async())
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania nasłuchiwania Pub/Sub: {e}", exc_info=True)
            return False


    def start_listener(self) -> bool:
        """Synchroniczna wersja uruchamiania nasłuchiwania."""
        try:
            # Sprawdź, czy mamy już aktywną pętlę
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # Jeśli nie ma aktywnej pętli, utwórz nową
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.start_listener_async())
            
            # Jeśli pętla jest już uruchomiona (w FastAPI)
            if loop.is_running():
                # Utwórz zadanie w istniejącej pętli
                loop.create_task(self.start_listener_async())
                return True
            else:
                # Pętla istnieje, ale nie jest uruchomiona
                return loop.run_until_complete(self.start_listener_async())
        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania nasłuchiwania: {e}", exc_info=True)
            return False
        

    async def _monitor_subscription_async(self) -> None:
        """Asynchronicznie monitoruje stan subskrypcji."""
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(5)  # Sprawdzaj co 5 sekund
                
                if self.streaming_pull_future and self.streaming_pull_future.done():
                    if not self.shutdown_event.is_set():
                        logger.warning("Subskrypcja Pub/Sub zakończyła się nieoczekiwanie. Ponowne uruchamianie...")
                        await self.start_listener_async()
                    break
                    
        except asyncio.CancelledError:
            logger.info("Monitorowanie subskrypcji zostało anulowane.")
        except Exception as e:
            logger.error(f"Błąd w asynchronicznym monitorowaniu subskrypcji: {e}", exc_info=True)

    async def stop_listener_async(self) -> None:
        """Asynchroniczna wersja zatrzymywania nasłuchiwania."""
        if not self._initialized:
            return
            
        logger.info("Zatrzymuję nasłuchiwanie Pub/Sub...")
        self.shutdown_event.set()
        
        # Anuluj zadanie monitorujące
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        if self.streaming_pull_future:
            try:
                # Cancel jest metodą synchroniczną
                self.streaming_pull_future.cancel()
                logger.info("Anulowano subskrypcję Pub/Sub.")
            except Exception as e:
                logger.warning(f"Błąd podczas anulowania subskrypcji: {e}")
            finally:
                self.streaming_pull_future = None
        
        if self.subscriber:
            try:
                # Close jest metodą synchroniczną
                self.subscriber.close()
                logger.info("Klient Pub/Sub zamknięty.")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania klienta Pub/Sub: {e}")
                
        print("\n[MARKETNEWS] Zakończono nasłuchiwanie.")

    def stop_listener(self) -> None:
        """Synchroniczna wersja zatrzymywania nasłuchiwania."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.stop_listener_async())
        finally:
            loop.close()