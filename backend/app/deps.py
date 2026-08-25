from fastapi import Request

from .download.manager import DownloadManager
from .rezka.session import RezkaGateway


def get_gateway(request: Request) -> RezkaGateway:
    return request.app.state.gateway


def get_manager(request: Request) -> DownloadManager:
    return request.app.state.manager
