"""
Asynchroniczny serwis Pub/Sub do odbierania wiadomości rynkowych.
Obsługuje zarówno standardowe jak i krytyczne wiadomości.
"""
from __future__ import annotations

import logging
import asyncio
import threading
import time
import orjson
from typing import Dict, Any, Optional, Callable, List
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
    
    # Standard topic configuration
    standard_subscription_name: str
    standard_topic_name: str
    
    # Critical topic configuration
    critical_subscription_name: str
    critical_topic_name: str

    subscriber: Optional[pubsub_v1.SubscriberClient] = None
    
    # Separate streaming futures for each topic
    standard_streaming_pull_future: Optional[Any] = None
    critical_streaming_pull_future: Optional[Any] = None
    
    shutdown_event: Optional[threading.Event] = None
    
    # Monitoring tasks for each subscription
    _standard_monitoring_task: Optional[asyncio.Task] = None
    _critical_monitoring_task: Optional[asyncio.Task] = None
    
    # Store the main event loop reference
    _main_loop: Optional[asyncio.AbstractEventLoop] = None

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
        
        # Standard topic configuration
        self.standard_full_topic_path = "projects/vortexanalytica/topics/chronoengine-marketnews-enriched-standard"
        self.standard_topic_name = "chronoengine-marketnews-enriched-standard"
        self.standard_subscription_name = "chronoengine-marketnews-enriched-standard-sub"
        
        # Critical topic configuration
        self.critical_full_topic_path = "projects/vortexanalytica/topics/chronoengine-marketnews-enriched-critical"
        self.critical_topic_name = "chronoengine-marketnews-enriched-critical"
        self.critical_subscription_name = "chronoengine-marketnews-enriched-critical-sub"
        
        self.shutdown_event = threading.Event()

        try:
            self.subscriber = pubsub_v1.SubscriberClient()
            
            # Create subscription paths
            self.standard_subscription_path = self.subscriber.subscription_path(
                self.project_id, self.standard_subscription_name
            )
            self.critical_subscription_path = self.subscriber.subscription_path(
                self.project_id, self.critical_subscription_name
            )
            
            logger.info(f"PubSubService zainicjalizowany dla projektu: {self.project_id}")
            logger.info(f"Standard topic: {self.standard_full_topic_path}")
            logger.info(f"Critical topic: {self.critical_full_topic_path}")
            logger.info(f"Standard subscription: {self.standard_subscription_path}")
            logger.info(f"Critical subscription: {self.critical_subscription_path}")
            
            self._initialized = True
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji PubSubService: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize PubSubService: {e}") from e

    def _ensure_subscription_exists(self, subscription_path: str, subscription_name: str) -> bool:
        if not self._initialized or not self.subscriber:
            logger.error("Próba użycia niezainicjalizowanego PubSubService.")
            return False
        try:
            self.subscriber.get_subscription(subscription=subscription_path)
            logger.info(f"Znaleziono istniejącą subskrypcję: {subscription_name}")
            return True
        except NotFound:
            logger.error(f"Subskrypcja {subscription_name} nie istnieje w projekcie {self.project_id}.")
            logger.error("Upewnij się, że nazwa subskrypcji jest poprawna.")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania subskrypcji: {e}", exc_info=True)
            return False

    async def _async_message_callback(self, message_data: bytes, message_id: str, publish_time: str, is_critical: bool = False) -> None:
        """Asynchroniczna wersja przetwarzania wiadomości z Pub/Sub."""
        try:
            message_type = "CRITICAL" if is_critical else "STANDARD"
            print(f"\n===== NOWA WIADOMOŚĆ {message_type} Z MARKETNEWS (RAW JSON) =====")
            print(f"Message ID: {message_id}")
            print(f"Publish Time: {publish_time}")
            print("\n----- SUROWY JSON -----")
            
            try:
                decoded_json = message_data.decode('utf-8')
                print(decoded_json)
                
                # Parsuj JSON
                news_data = orjson.loads(decoded_json)
                news_service = NewsService()
                
                if is_critical:
                    # Dla krytycznych wiadomości, dodaj flagę
                    news_data['is_critical'] = True
                    # Użyj dedykowanej metody dla krytycznych wiadomości
                    await news_service.add_critical_message_async(news_data)
                    logger.info(f"Krytyczna wiadomość {message_id} przetworzona i opublikowana")
                else:
                    # Użyj standardowej metody dla zwykłych wiadomości
                    await news_service.add_message_async(news_data)
                    logger.info(f"Standardowa wiadomość {message_id} przetworzona i opublikowana")
                
            except UnicodeDecodeError:
                print(f"Nie można zdekodować jako UTF-8: {message_data!r}")
                
            print("\n================================================")
        except Exception as e:
            logger.error(f"Błąd podczas asynchronicznego przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)

    def _create_message_callback(self, is_critical: bool = False):
        """Tworzy callback dla danego typu wiadomości."""
        def _message_callback(message: pubsub_v1.subscriber.message.Message) -> None:
            """Synchroniczny callback dla Pub/Sub."""
            try:
                data_bytes = message.data
                message_id = message.message_id
                publish_time = message.publish_time
                
                # Schedule processing in the main event loop
                if self._main_loop and not self._main_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, is_critical),
                        self._main_loop
                    )
                else:
                    # Fallback: try to get the running loop or create a new one
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        # No running loop in this thread
                        logger.warning("No running event loop in PubSub callback thread, creating task in new thread")
                        # Create a new thread to run the async task
                        def run_async():
                            asyncio.run(
                                self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, is_critical)
                            )
                        
                        thread = threading.Thread(target=run_async, daemon=True)
                        thread.start()
                        return
                    
                    # We have a running loop, create task
                    task = loop.create_task(
                        self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, is_critical)
                    )
                    task.set_name(f"process_{'critical' if is_critical else 'standard'}_pubsub_message_{message_id}")
                    
            except Exception as e:
                logger.error(f"Błąd podczas przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)
                message.ack()
        
        return _message_callback

    async def _process_message_wrapper(self, data_bytes: bytes, message_id: str, publish_time: str, 
                                     message: pubsub_v1.subscriber.message.Message, is_critical: bool = False) -> None:
        """Wrapper dla przetwarzania wiadomości."""
        try:
            start_time = time.time()
            await self._async_message_callback(data_bytes, message_id, publish_time, is_critical)
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"{'Krytyczna' if is_critical else 'Standardowa'} wiadomość {message_id} przetworzona w {processing_time:.2f}ms")
            message.ack()
        except Exception as e:
            logger.error(f"Błąd w _process_message_wrapper: {e}", exc_info=True)
            message.ack()

    async def start_listener_async(self) -> bool:
        """Asynchroniczna wersja uruchamiania nasłuchiwania dla obu topiców."""
        if not self._initialized or not self.subscriber:
            logger.error("Próba uruchomienia nasłuchiwania na niezainicjalizowanym PubSubService.")
            return False
        
        # Store the current event loop
        self._main_loop = asyncio.get_running_loop()
        
        self.shutdown_event.clear()
        
        # Sprawdź obie subskrypcje
        standard_exists = self._ensure_subscription_exists(self.standard_subscription_path, self.standard_subscription_name)
        critical_exists = self._ensure_subscription_exists(self.critical_subscription_path, self.critical_subscription_name)
        
        if not standard_exists and not critical_exists:
            logger.error("Nie można rozpocząć nasłuchiwania - żadna subskrypcja nie istnieje.")
            return False
            
        try:
            # Uruchom nasłuchiwanie dla standardowego topicu
            if standard_exists:
                logger.info(f"Rozpoczynam nasłuchiwanie na standardowej subskrypcji: {self.standard_subscription_name}")
                
                def start_standard_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=20,
                        max_bytes=10 * 1024 * 1024,
                        max_lease_duration=60
                    )
                    
                    self.standard_streaming_pull_future = self.subscriber.subscribe(
                        self.standard_subscription_path,
                        callback=self._create_message_callback(is_critical=False),
                        flow_control=flow_control
                    )
                    print(f"\n[MARKETNEWS STANDARD] Rozpoczęto nasłuchiwanie na temacie '{self.standard_topic_name}'")
                    
                    try:
                        self.standard_streaming_pull_future.result()
                    except Exception as e:
                        if not self.shutdown_event.is_set():
                            logger.error(f"Błąd w standardowej subskrypcji Pub/Sub: {e}", exc_info=True)
                
                standard_thread = threading.Thread(
                    target=start_standard_subscription,
                    daemon=True,
                    name="PubSub_Standard_Listener_Thread"
                )
                standard_thread.start()
                
                self._standard_monitoring_task = asyncio.create_task(
                    self._monitor_subscription_async("standard")
                )
            
            # Uruchom nasłuchiwanie dla krytycznego topicu
            if critical_exists:
                logger.info(f"Rozpoczynam nasłuchiwanie na krytycznej subskrypcji: {self.critical_subscription_name}")
                
                def start_critical_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=10,  # Mniej wiadomości dla krytycznych
                        max_bytes=5 * 1024 * 1024,
                        max_lease_duration=30  # Krótszy czas dla szybszego przetwarzania
                    )
                    
                    self.critical_streaming_pull_future = self.subscriber.subscribe(
                        self.critical_subscription_path,
                        callback=self._create_message_callback(is_critical=True),
                        flow_control=flow_control
                    )
                    print(f"\n[MARKETNEWS CRITICAL] Rozpoczęto nasłuchiwanie na temacie '{self.critical_topic_name}'")
                    
                    try:
                        self.critical_streaming_pull_future.result()
                    except Exception as e:
                        if not self.shutdown_event.is_set():
                            logger.error(f"Błąd w krytycznej subskrypcji Pub/Sub: {e}", exc_info=True)
                
                critical_thread = threading.Thread(
                    target=start_critical_subscription,
                    daemon=True,
                    name="PubSub_Critical_Listener_Thread"
                )
                critical_thread.start()
                
                self._critical_monitoring_task = asyncio.create_task(
                    self._monitor_subscription_async("critical")
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania nasłuchiwania Pub/Sub: {e}", exc_info=True)
            return False

    async def _monitor_subscription_async(self, subscription_type: str) -> None:
        """Asynchronicznie monitoruje stan subskrypcji."""
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(5)
                
                if subscription_type == "standard" and self.standard_streaming_pull_future:
                    if self.standard_streaming_pull_future.done():
                        if not self.shutdown_event.is_set():
                            logger.warning("Standardowa subskrypcja Pub/Sub zakończyła się nieoczekiwanie. Ponowne uruchamianie...")
                            await self.start_listener_async()
                        break
                elif subscription_type == "critical" and self.critical_streaming_pull_future:
                    if self.critical_streaming_pull_future.done():
                        if not self.shutdown_event.is_set():
                            logger.warning("Krytyczna subskrypcja Pub/Sub zakończyła się nieoczekiwanie. Ponowne uruchamianie...")
                            await self.start_listener_async()
                        break
                    
        except asyncio.CancelledError:
            logger.info(f"Monitorowanie subskrypcji {subscription_type} zostało anulowane.")
        except Exception as e:
            logger.error(f"Błąd w asynchronicznym monitorowaniu subskrypcji {subscription_type}: {e}", exc_info=True)

    async def stop_listener_async(self) -> None:
        """Asynchroniczna wersja zatrzymywania nasłuchiwania."""
        if not self._initialized:
            return
            
        logger.info("Zatrzymuję nasłuchiwanie Pub/Sub...")
        self.shutdown_event.set()
        
        # Clear the main loop reference
        self._main_loop = None
        
        # Anuluj zadania monitorujące
        for task in [self._standard_monitoring_task, self._critical_monitoring_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._standard_monitoring_task = None
        self._critical_monitoring_task = None
        
        # Anuluj subskrypcje
        for future in [self.standard_streaming_pull_future, self.critical_streaming_pull_future]:
            if future:
                try:
                    future.cancel()
                    logger.info("Anulowano subskrypcję Pub/Sub.")
                except Exception as e:
                    logger.warning(f"Błąd podczas anulowania subskrypcji: {e}")
        
        self.standard_streaming_pull_future = None
        self.critical_streaming_pull_future = None
        
        if self.subscriber:
            try:
                self.subscriber.close()
                logger.info("Klient Pub/Sub zamknięty.")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania klienta Pub/Sub: {e}")
                
        print("\n[MARKETNEWS] Zakończono nasłuchiwanie.")
        