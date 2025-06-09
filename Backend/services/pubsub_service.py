"""
Asynchroniczny serwis Pub/Sub do odbierania wiadomości rynkowych.
Obsługuje standardowe, krytyczne, kalendarzowe, MOC i regularne wiadomości.
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
    
    # Calendar topic configuration
    calendar_subscription_name: str
    calendar_topic_name: str
    
    # MOC market data topic configuration
    moc_subscription_name: str
    moc_topic_name: str
    
    # Regular topic configuration (NEW)
    regular_subscription_name: str
    regular_topic_name: str

    subscriber: Optional[pubsub_v1.SubscriberClient] = None
    
    # Separate streaming futures for each topic
    standard_streaming_pull_future: Optional[Any] = None
    critical_streaming_pull_future: Optional[Any] = None
    calendar_streaming_pull_future: Optional[Any] = None
    moc_streaming_pull_future: Optional[Any] = None
    regular_streaming_pull_future: Optional[Any] = None  # NEW
    
    shutdown_event: Optional[threading.Event] = None
    
    # Monitoring tasks for each subscription
    _standard_monitoring_task: Optional[asyncio.Task] = None
    _critical_monitoring_task: Optional[asyncio.Task] = None
    _calendar_monitoring_task: Optional[asyncio.Task] = None
    _moc_monitoring_task: Optional[asyncio.Task] = None
    _regular_monitoring_task: Optional[asyncio.Task] = None  # NEW
    
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
        
        # Calendar topic configuration
        self.calendar_full_topic_path = "projects/vortexanalytica/topics/chronoengine-calendar-update"
        self.calendar_topic_name = "chronoengine-calendar-update"
        self.calendar_subscription_name = "chronoengine-calendar-update-sub"
        
        # MOC market data topic configuration
        self.moc_full_topic_path = "projects/vortexanalytica/topics/chronoengine-moc-market-data"
        self.moc_topic_name = "chronoengine-moc-market-data"
        self.moc_subscription_name = "chronoengine-moc-market-data-sub"
        
        # Regular topic configuration (NEW)
        self.regular_full_topic_path = "projects/vortexanalytica/topics/chronoengine-marketnews-enriched-regular"
        self.regular_topic_name = "chronoengine-marketnews-enriched-regular"
        self.regular_subscription_name = "chronoengine-marketnews-enriched-regular-sub"
        
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
            self.calendar_subscription_path = self.subscriber.subscription_path(
                self.project_id, self.calendar_subscription_name
            )
            self.moc_subscription_path = self.subscriber.subscription_path(
                self.project_id, self.moc_subscription_name
            )
            self.regular_subscription_path = self.subscriber.subscription_path(
                self.project_id, self.regular_subscription_name
            )
            
            logger.info(f"PubSubService zainicjalizowany dla projektu: {self.project_id}")
            logger.info(f"Standard topic: {self.standard_full_topic_path}")
            logger.info(f"Critical topic: {self.critical_full_topic_path}")
            logger.info(f"Calendar topic: {self.calendar_full_topic_path}")
            logger.info(f"MOC topic: {self.moc_full_topic_path}")
            logger.info(f"Regular topic: {self.regular_full_topic_path}")  # NEW
            
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

    async def _async_message_callback(self, message_data: bytes, message_id: str, publish_time: str, topic_type: str) -> None:
        """Asynchroniczna wersja przetwarzania wiadomości z Pub/Sub."""
        try:
            # Określ typ wiadomości na podstawie topic_type
            if topic_type == "critical":
                message_type = "CRITICAL"
            elif topic_type == "standard":
                message_type = "STANDARD"
            elif topic_type == "calendar":
                message_type = "CALENDAR UPDATE"
            elif topic_type == "moc":
                message_type = "MOC MARKET DATA"
            elif topic_type == "regular":  # NEW
                message_type = "REGULAR"
            else:
                message_type = "UNKNOWN"
            
            print(f"\n===== NOWA WIADOMOŚĆ {message_type} (RAW JSON) =====")
            print(f"Message ID: {message_id}")
            print(f"Publish Time: {publish_time}")
            print(f"Topic Type: {topic_type}")
            print("\n----- SUROWY JSON -----")
            
            try:
                decoded_json = message_data.decode('utf-8')
                print(decoded_json)
                
                # Parsuj JSON dla lepszego wyświetlania
                try:
                    data = orjson.loads(decoded_json)
                    print("\n----- SPARSOWANE DANE -----")
                    import json
                    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
                except Exception as parse_error:
                    print(f"\nNie można sparsować JSON: {parse_error}")
                
                # Dla standardowych i krytycznych wiadomości, przetwarzaj jak wcześniej
                if topic_type in ["standard", "critical"]:
                    news_data = orjson.loads(decoded_json)
                    news_service = NewsService()
                    
                    if topic_type == "critical":
                        news_data['is_critical'] = True
                        await news_service.add_critical_message_async(news_data)
                        logger.info(f"Krytyczna wiadomość {message_id} przetworzona i opublikowana")
                    else:
                        await news_service.add_message_async(news_data)
                        logger.info(f"Standardowa wiadomość {message_id} przetworzona i opublikowana")
                
                # Dla calendar, moc i regular - tylko wyświetlamy (NEW: dodano regular)
                else:
                    logger.info(f"Wiadomość {topic_type} {message_id} wyświetlona w terminalu")
                
            except UnicodeDecodeError:
                print(f"Nie można zdekodować jako UTF-8: {message_data!r}")
                
            print("\n================================================")
        except Exception as e:
            logger.error(f"Błąd podczas asynchronicznego przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)

    def _create_message_callback(self, topic_type: str):
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
                        self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, topic_type),
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
                                self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, topic_type)
                            )
                        
                        thread = threading.Thread(target=run_async, daemon=True)
                        thread.start()
                        return
                    
                    # We have a running loop, create task
                    task = loop.create_task(
                        self._process_message_wrapper(data_bytes, message_id, str(publish_time), message, topic_type)
                    )
                    task.set_name(f"process_{topic_type}_pubsub_message_{message_id}")
                    
            except Exception as e:
                logger.error(f"Błąd podczas przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)
                message.ack()
        
        return _message_callback

    async def _process_message_wrapper(self, data_bytes: bytes, message_id: str, publish_time: str, 
                                     message: pubsub_v1.subscriber.message.Message, topic_type: str) -> None:
        """Wrapper dla przetwarzania wiadomości."""
        try:
            start_time = time.time()
            await self._async_message_callback(data_bytes, message_id, publish_time, topic_type)
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Wiadomość {topic_type} {message_id} przetworzona w {processing_time:.2f}ms")
            message.ack()
        except Exception as e:
            logger.error(f"Błąd w _process_message_wrapper: {e}", exc_info=True)
            message.ack()

    async def start_listener_async(self) -> bool:
        """Asynchroniczna wersja uruchamiania nasłuchiwania dla wszystkich topiców."""
        if not self._initialized or not self.subscriber:
            logger.error("Próba uruchomienia nasłuchiwania na niezainicjalizowanym PubSubService.")
            return False
        
        # Store the current event loop
        self._main_loop = asyncio.get_running_loop()
        
        self.shutdown_event.clear()
        
        # Sprawdź wszystkie subskrypcje (NEW: dodano regular)
        subscriptions = {
            "standard": (self.standard_subscription_path, self.standard_subscription_name),
            "critical": (self.critical_subscription_path, self.critical_subscription_name),
            "calendar": (self.calendar_subscription_path, self.calendar_subscription_name),
            "moc": (self.moc_subscription_path, self.moc_subscription_name),
            "regular": (self.regular_subscription_path, self.regular_subscription_name)  # NEW
        }
        
        existing_subscriptions = {}
        for sub_type, (path, name) in subscriptions.items():
            existing_subscriptions[sub_type] = self._ensure_subscription_exists(path, name)
        
        if not any(existing_subscriptions.values()):
            logger.error("Nie można rozpocząć nasłuchiwania - żadna subskrypcja nie istnieje.")
            return False
            
        try:
            # Uruchom nasłuchiwanie dla standardowego topicu
            if existing_subscriptions["standard"]:
                logger.info(f"Rozpoczynam nasłuchiwanie na standardowej subskrypcji: {self.standard_subscription_name}")
                
                def start_standard_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=20,
                        max_bytes=10 * 1024 * 1024,
                        max_lease_duration=60
                    )
                    
                    self.standard_streaming_pull_future = self.subscriber.subscribe(
                        self.standard_subscription_path,
                        callback=self._create_message_callback("standard"),
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
            if existing_subscriptions["critical"]:
                logger.info(f"Rozpoczynam nasłuchiwanie na krytycznej subskrypcji: {self.critical_subscription_name}")
                
                def start_critical_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=10,
                        max_bytes=5 * 1024 * 1024,
                        max_lease_duration=30
                    )
                    
                    self.critical_streaming_pull_future = self.subscriber.subscribe(
                        self.critical_subscription_path,
                        callback=self._create_message_callback("critical"),
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
            
            # Uruchom nasłuchiwanie dla kalendarza
            if existing_subscriptions["calendar"]:
                logger.info(f"Rozpoczynam nasłuchiwanie na subskrypcji kalendarza: {self.calendar_subscription_name}")
                
                def start_calendar_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=30,
                        max_bytes=10 * 1024 * 1024,
                        max_lease_duration=60
                    )
                    
                    self.calendar_streaming_pull_future = self.subscriber.subscribe(
                        self.calendar_subscription_path,
                        callback=self._create_message_callback("calendar"),
                        flow_control=flow_control
                    )
                    print(f"\n[CALENDAR UPDATE] Rozpoczęto nasłuchiwanie na temacie '{self.calendar_topic_name}'")
                    
                    try:
                        self.calendar_streaming_pull_future.result()
                    except Exception as e:
                        if not self.shutdown_event.is_set():
                            logger.error(f"Błąd w subskrypcji kalendarza Pub/Sub: {e}", exc_info=True)
                
                calendar_thread = threading.Thread(
                    target=start_calendar_subscription,
                    daemon=True,
                    name="PubSub_Calendar_Listener_Thread"
                )
                calendar_thread.start()
                
                self._calendar_monitoring_task = asyncio.create_task(
                    self._monitor_subscription_async("calendar")
                )
            
            # Uruchom nasłuchiwanie dla MOC market data
            if existing_subscriptions["moc"]:
                logger.info(f"Rozpoczynam nasłuchiwanie na subskrypcji MOC: {self.moc_subscription_name}")
                
                def start_moc_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=200,  # Więcej wiadomości dla danych rynkowych
                        max_bytes=20 * 1024 * 1024,
                        max_lease_duration=45
                    )
                    
                    self.moc_streaming_pull_future = self.subscriber.subscribe(
                        self.moc_subscription_path,
                        callback=self._create_message_callback("moc"),
                        flow_control=flow_control
                    )
                    print(f"\n[MOC MARKET DATA] Rozpoczęto nasłuchiwanie na temacie '{self.moc_topic_name}'")
                    
                    try:
                        self.moc_streaming_pull_future.result()
                    except Exception as e:
                        if not self.shutdown_event.is_set():
                            logger.error(f"Błąd w subskrypcji MOC Pub/Sub: {e}", exc_info=True)
                
                moc_thread = threading.Thread(
                    target=start_moc_subscription,
                    daemon=True,
                    name="PubSub_MOC_Listener_Thread"
                )
                moc_thread.start()
                
                self._moc_monitoring_task = asyncio.create_task(
                    self._monitor_subscription_async("moc")
                )
            
            # NEW: Uruchom nasłuchiwanie dla regularnych wiadomości
            if existing_subscriptions["regular"]:
                logger.info(f"Rozpoczynam nasłuchiwanie na regularnej subskrypcji: {self.regular_subscription_name}")
                
                def start_regular_subscription():
                    flow_control = pubsub_v1.types.FlowControl(
                        max_messages=50,  # Umiarkowana liczba wiadomości
                        max_bytes=15 * 1024 * 1024,
                        max_lease_duration=60
                    )
                    
                    self.regular_streaming_pull_future = self.subscriber.subscribe(
                        self.regular_subscription_path,
                        callback=self._create_message_callback("regular"),
                        flow_control=flow_control
                    )
                    print(f"\n[MARKETNEWS REGULAR] Rozpoczęto nasłuchiwanie na temacie '{self.regular_topic_name}'")
                    
                    try:
                        self.regular_streaming_pull_future.result()
                    except Exception as e:
                        if not self.shutdown_event.is_set():
                            logger.error(f"Błąd w regularnej subskrypcji Pub/Sub: {e}", exc_info=True)
                
                regular_thread = threading.Thread(
                    target=start_regular_subscription,
                    daemon=True,
                    name="PubSub_Regular_Listener_Thread"
                )
                regular_thread.start()
                
                self._regular_monitoring_task = asyncio.create_task(
                    self._monitor_subscription_async("regular")
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
                
                future = None
                if subscription_type == "standard":
                    future = self.standard_streaming_pull_future
                elif subscription_type == "critical":
                    future = self.critical_streaming_pull_future
                elif subscription_type == "calendar":
                    future = self.calendar_streaming_pull_future
                elif subscription_type == "moc":
                    future = self.moc_streaming_pull_future
                elif subscription_type == "regular":  # NEW
                    future = self.regular_streaming_pull_future
                
                if future and future.done():
                    if not self.shutdown_event.is_set():
                        logger.warning(f"Subskrypcja {subscription_type} Pub/Sub zakończyła się nieoczekiwanie. Ponowne uruchamianie...")
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
        
        # Anuluj zadania monitorujące (NEW: dodano regular)
        for task in [self._standard_monitoring_task, self._critical_monitoring_task, 
                     self._calendar_monitoring_task, self._moc_monitoring_task, 
                     self._regular_monitoring_task]:  # NEW
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._standard_monitoring_task = None
        self._critical_monitoring_task = None
        self._calendar_monitoring_task = None
        self._moc_monitoring_task = None
        self._regular_monitoring_task = None  # NEW
        
        # Anuluj subskrypcje (NEW: dodano regular)
        for future in [self.standard_streaming_pull_future, self.critical_streaming_pull_future,
                       self.calendar_streaming_pull_future, self.moc_streaming_pull_future,
                       self.regular_streaming_pull_future]:  # NEW
            if future:
                try:
                    future.cancel()
                    logger.info("Anulowano subskrypcję Pub/Sub.")
                except Exception as e:
                    logger.warning(f"Błąd podczas anulowania subskrypcji: {e}")
        
        self.standard_streaming_pull_future = None
        self.critical_streaming_pull_future = None
        self.calendar_streaming_pull_future = None
        self.moc_streaming_pull_future = None
        self.regular_streaming_pull_future = None 
        
        if self.subscriber:
            try:
                self.subscriber.close()
                logger.info("Klient Pub/Sub zamknięty.")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania klienta Pub/Sub: {e}")
                
        print("\n[PUBSUB] Zakończono nasłuchiwanie wszystkich topiców")
