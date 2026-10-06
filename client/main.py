"""Run from village_lab: python client/main.py"""
from ads_panel import AdsPanelState
from network_ads import AdsClient
from client_app import ClientApp
from controller import ClientController
from network import NetworkWorker
from network_api import ApiClient
from network_auth import DjangoAuth
from network_validation import ResponseValidator
from network_ws import GameSocketClient
from panels import AnalyticsPanelState, HistoryPanelState
from ports import (AdsPanelPort, AnalyticsPanelPort, ApiClientFactoryPort, ApplicationPort,
                   AuthFactoryPort, ConfigPort, ControllerPort,
                   GameSocketFactoryPort, HistoryPanelPort, NetworkPort,
                   RendererFactoryPort, ResponseValidatorPort, StatePort)
from render import Renderer
from state import Config, State


def main():
    try:
        config: ConfigPort = Config.load()
    except (OSError, ValueError, TypeError, AttributeError):
        print('client/config.json 설정을 확인하세요. origin, 창 크기, 타일 크기, 자산 경로가 필요합니다.')
        return 1

    ads_panel: AdsPanelPort = AdsPanelState()
    state: StatePort = State()
    analytics_panel: AnalyticsPanelPort = AnalyticsPanelState()
    history_panel: HistoryPanelPort = HistoryPanelState()
    auth_factory: AuthFactoryPort = DjangoAuth
    api_factory: ApiClientFactoryPort = ApiClient
    game_socket_factory: GameSocketFactoryPort = GameSocketClient
    validator: ResponseValidatorPort = ResponseValidator()
    worker: NetworkPort = NetworkWorker(
        config.server_base_url, auth_factory, api_factory, game_socket_factory, validator,
        ads_origin=config.ads_base_url, ads_factory=AdsClient)
    controller: ControllerPort = ClientController(
        state, analytics_panel, history_panel, worker)
    renderer_factory: RendererFactoryPort = Renderer
    app: ApplicationPort = ClientApp(
        config, state, analytics_panel, history_panel, worker, controller,
        renderer_factory, ads_panel=ads_panel)
    return app.run()


if __name__ == '__main__':
    raise SystemExit(main())
