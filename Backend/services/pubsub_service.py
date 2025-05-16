from __future__ import annotations

import logging
import threading
import time
import orjson
from typing import Dict, Any, Optional, Callable
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1
from google.api_core.exceptions import NotFound, PermissionDenied

from Backend.core.config import Settings

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

    def _message_callback(self, message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            data_bytes = message.data
            print("\n===== NOWA WIADOMOŚĆ Z MARKETNEWS (RAW JSON) =====")
            print(f"Message ID: {message.message_id}")
            print(f"Publish Time: {message.publish_time}")
            print("\n----- SUROWY JSON -----")
            try:
                decoded_json = data_bytes.decode('utf-8')
                print(decoded_json)
            except UnicodeDecodeError:
                print(f"Nie można zdekodować jako UTF-8: {data_bytes!r}")
            print("\n================================================")
            message.ack()
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania wiadomości Pub/Sub: {e}", exc_info=True)
            message.ack()

    def start_listener(self) -> bool:
        if not self._initialized or not self.subscriber:
            logger.error("Próba uruchomienia nasłuchiwania na niezainicjalizowanym PubSubService.")
            return False
        self.shutdown_event.clear()
        if not self._ensure_subscription_exists():
            logger.error("Nie można rozpocząć nasłuchiwania - subskrypcja nie istnieje.")
            return False
        try:
            logger.info(f"Rozpoczynam nasłuchiwanie na subskrypcji: {self.subscription_name}")
            self.streaming_pull_future = self.subscriber.subscribe(
                self.subscription_path,
                callback=self._message_callback,
                flow_control=pubsub_v1.types.FlowControl(max_messages=10)
            )
            print(f"\n[MARKETNEWS] Rozpoczęto nasłuchiwanie na temacie '{self.topic_name}' przez subskrypcję '{self.subscription_name}'")
            print("[MARKETNEWS] Czekam na wiadomości...\n")
            monitor_thread = threading.Thread(
                target=self._monitor_subscription,
                daemon=True
            )
            monitor_thread.start()
            return True
        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania nasłuchiwania Pub/Sub: {e}", exc_info=True)
            return False

    def _monitor_subscription(self) -> None:
        try:
            while not self.shutdown_event.is_set() and self.streaming_pull_future:
                try:
                    self.streaming_pull_future.result(timeout=1)
                    logger.warning("Subskrypcja Pub/Sub zakończyła się nieoczekiwanie.")
                    break
                except TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Błąd w subskrypcji Pub/Sub: {e}", exc_info=True)
                    break
                time.sleep(5)
            if not self.shutdown_event.is_set():
                logger.info("Próba ponownego uruchomienia subskrypcji...")
                self.start_listener()
        except Exception as e:
            logger.error(f"Błąd w wątku monitorującym subskrypcję: {e}", exc_info=True)

    def stop_listener(self) -> None:
        if not self._initialized:
            return
        logger.info("Zatrzymuję nasłuchiwanie Pub/Sub...")
        self.shutdown_event.set()
        if self.streaming_pull_future:
            try:
                self.streaming_pull_future.cancel()
                self.streaming_pull_future.result(timeout=30)
                logger.info("Subskrypcja Pub/Sub zatrzymana pomyślnie.")
            except Exception as e:
                logger.warning(f"Błąd podczas zatrzymywania subskrypcji: {e}")
            finally:
                self.streaming_pull_future = None
        if self.subscriber:
            try:
                self.subscriber.close()
                logger.info("Klient Pub/Sub zamknięty.")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania klienta Pub/Sub: {e}")
        print("\n[MARKETNEWS] Zakończono nasłuchiwanie.")