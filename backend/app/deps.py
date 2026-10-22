from fastapi import Request

from .download.manager import DownloadManager
from .library.service import LibraryEnricher, LibraryMeta
from .rezka.client import RezkaClient
from .streams import StreamResolver


def get_client(request: Request) -> RezkaClient:
    return request.app.state.client


def get_manager(request: Request) -> DownloadManager:
    return request.app.state.manager


def get_resolver(request: Request) -> StreamResolver:
    return request.app.state.resolver


def get_meta(request: Request) -> LibraryMeta:
    return request.app.state.meta


def get_enricher(request: Request) -> LibraryEnricher:
    return request.app.state.enricher
