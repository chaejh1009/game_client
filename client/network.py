"""Worker-thread coordinator using injected network component contracts."""
import asyncio
from contextlib import AsyncExitStack
from queue import Empty, Queue
from threading import Thread

import aiohttp

from messages import Request, Result
from network_errors import Failure
from ports import (AdsClientFactoryPort, ApiClientFactoryPort, ApiClientPort, AuthFactoryPort, AuthPort,
                   GameSocketFactoryPort, GameSocketPort, ResponseValidatorPort)


class NetworkWorker:
    def __init__(self, origin: str, auth_factory: AuthFactoryPort,
                 api_factory: ApiClientFactoryPort,
                 game_socket_factory: GameSocketFactoryPort,
                 validator: ResponseValidatorPort,
                 ads_origin: str = 'http://127.0.0.1:8001',
                 ads_factory: AdsClientFactoryPort | None = None):
        self.origin = origin
        self.ads_origin = ads_origin
        self._ads_factory = ads_factory
        self.requests = Queue()
        self.results = Queue()
        self.thread = Thread(target=self._run, name='village-network', daemon=False)
        self._auth_factory = auth_factory
        self._api_factory = api_factory
        self._game_socket_factory = game_socket_factory
        self._validator = validator
        self._authenticated = False

    def start(self) -> None:
        self.thread.start()

    def submit(self, request: Request) -> None:
        self.requests.put_nowait(request)

    def stop(self) -> None:
        self.submit(Request('stop'))

    def get_result_nowait(self) -> Result:
        return self.results.get_nowait()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def join(self) -> None:
        self.thread.join()

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception:
            # Never forward raw exception strings, headers, bodies, or tracebacks.
            self.results.put(Result('fatal', '네트워크 worker가 종료되었습니다. 앱을 다시 실행하세요.'))
        finally:
            while True:
                try:
                    request = self.requests.get_nowait()
                    request.password = request.username = ''
                except Empty:
                    break

    async def _serve(self) -> None:
        jar = aiohttp.CookieJar(unsafe=True)
        timeout = aiohttp.ClientTimeout(total=4, connect=2, sock_read=2)
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout,
                                         trust_env=False) as session, AsyncExitStack() as public_stack:
            public_session = None
            if self._ads_factory is not None:
                public_session = await public_stack.enter_async_context(
                    aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(),
                                          timeout=aiohttp.ClientTimeout(total=5),
                                          trust_env=False))
            auth = self._auth_factory(session, self.origin)
            api = self._api_factory(
                session, self.origin, self._validator, self.results.put)
            game_socket = self._game_socket_factory(
                session, self.origin, self._validator, self.results.put)
            ads = (self._ads_factory(public_session, self.ads_origin, self.results.put,
                                     game_session=session, game_origin=self.origin)
                   if self._ads_factory else None)
            ads_tasks = {}
            ad_event_tasks = {}
            active = None
            delivery_task = None
            analytics_task = None
            ingest_task = None
            windows_task = None
            history_task = None
            measurement_tasks = {'load': None, 'metrics': None}
            try:
                while True:
                    for key, task in list(ad_event_tasks.items()):
                        if task.done():
                            await task
                            del ad_event_tasks[key]
                    for slot_id, task in list(ads_tasks.items()):
                        if task.done():
                            await task
                            del ads_tasks[slot_id]
                    if active is not None and active.done():
                        await active
                        active = None
                    if delivery_task is not None and delivery_task.done():
                        await delivery_task
                        delivery_task = None
                    if analytics_task is not None and analytics_task.done():
                        await analytics_task
                        analytics_task = None
                    if ingest_task is not None and ingest_task.done():
                        await ingest_task
                        ingest_task = None
                    if windows_task is not None and windows_task.done():
                        await windows_task
                        windows_task = None
                    if history_task is not None and history_task.done():
                        await history_task
                        history_task = None
                    for kind, task in measurement_tasks.items():
                        if task is not None and task.done():
                            await task
                            measurement_tasks[kind] = None
                    try:
                        request = self.requests.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.02)
                        continue
                    if request.kind == 'stop':
                        break
                    if request.kind == 'ad_event':
                        key = (request.request_id, request.decision_id, request.event_type)
                        if key not in ad_event_tasks:
                            ad_event_tasks[key] = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'ad_event_error', '같은 광고 실적을 전송 중입니다.',
                                request_id=request.request_id, slot_id=request.slot_id,
                                decision_id=request.decision_id, event_type=request.event_type))
                        continue
                    if request.kind == 'ads':
                        if ads is not None and request.slot_id not in ads_tasks:
                            ads_tasks[request.slot_id] = asyncio.create_task(
                                ads.select(request.request_id, request.slot_id))
                        else:
                            self.results.put(Result('ads_error', '광고 요청 대기 중',
                                                    request_id=request.request_id, slot_id=request.slot_id))
                        continue
                    if request.kind == 'delivery':
                        if delivery_task is None:
                            delivery_task = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'delivery_error', '이벤트 전달 상태 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'analytics':
                        if analytics_task is None:
                            analytics_task = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'analytics_error', '통계 읽기 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'ingest':
                        if ingest_task is None:
                            ingest_task = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'ingest_error', '수집 통계 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'windows':
                        if windows_task is None:
                            windows_task = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'windows_error', '시간 창 통계 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'history':
                        if history_task is None:
                            history_task = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(
                                'history_error', '행동 이력 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind in measurement_tasks:
                        if measurement_tasks[request.kind] is None:
                            measurement_tasks[request.kind] = asyncio.create_task(
                                self._dispatch(request, auth, api, game_socket))
                        else:
                            self.results.put(Result(request.kind + '_error',
                                                    '측정 조회가 이미 진행 중입니다.'))
                        continue
                    if active is None:
                        active = asyncio.create_task(
                            self._dispatch(request, auth, api, game_socket))
                    else:
                        if request.kind == 'command':
                            self.results.put(Result(
                                'command_error', '이전 게임 명령의 응답을 기다려 주세요.',
                                direction=request.direction, action=request.action))
                        request.password = request.username = ''
            finally:
                for task in (
                        *ad_event_tasks.values(), *ads_tasks.values(), active, delivery_task, analytics_task, ingest_task,
                        windows_task, history_task):
                    if task is not None:
                        task.cancel()
                for task in measurement_tasks.values():
                    if task is not None:
                        task.cancel()
                await asyncio.gather(
                    *(task for task in (
                        *ad_event_tasks.values(), *ads_tasks.values(), active, delivery_task, analytics_task, ingest_task,
                        windows_task, history_task, *measurement_tasks.values())
                      if task is not None),
                    return_exceptions=True)
                await game_socket.shutdown()
                auth.clear()

    async def _dispatch(self, request: Request, auth: AuthPort, api: ApiClientPort,
                        game_socket: GameSocketPort) -> None:
        try:
            if request.kind == 'login':
                auth.clear()
                self._authenticated = False
                username, password = request.username, request.password
                request.password = request.username = ''
                try:
                    await auth.login(username, password)
                finally:
                    username = password = ''
                self._authenticated = True
                player = await api.get_player()
                player, ws_json = await game_socket.connect(player['player_id'])
                self.results.put(Result(
                    'player', '마을 준비 중', player=player, ws_json=ws_json))
                game_socket.start_listener()
            elif request.kind == 'player':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                player = await api.get_player()
                self.results.put(Result('player', '상태를 갱신했습니다.', player=player))
            elif request.kind == 'ad_event':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                data = await api.post_ad_event(request.decision_id, request.event_type)
                self.results.put(Result(
                    'ad_event', '광고 실적 저장 완료', request_id=request.request_id,
                    slot_id=request.slot_id, decision_id=request.decision_id,
                    event_type=request.event_type, ad_event=data))
            elif request.kind == 'delivery':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                delivery = await api.get_delivery()
                self.results.put(Result(
                    'delivery', '이벤트 전달 상태를 갱신했습니다.', delivery=delivery))
            elif request.kind == 'analytics':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                analytics = await api.get_analytics()
                self.results.put(Result(
                    'analytics', '저장된 통계를 읽었습니다.', player=analytics))
            elif request.kind == 'ingest':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                ingest = await api.get_ingest()
                self.results.put(Result(
                    'ingest', 'Kafka 수집 통계를 읽었습니다.', player=ingest))
            elif request.kind == 'windows':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                windows = await api.get_windows()
                self.results.put(Result(
                    'windows', '확정 시간 창 통계를 읽었습니다.', player=windows))
            elif request.kind == 'history':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                history = await api.get_history()
                self.results.put(Result(
                    'history', '최근 행동 이력을 읽었습니다.', player=history))
            elif request.kind in ('load', 'metrics'):
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                data = await (api.get_load() if request.kind == 'load'
                              else api.get_metrics())
                self.results.put(Result(request.kind, player=data))
            elif request.kind == 'logout':
                try:
                    await game_socket.close()
                    await auth.logout()
                finally:
                    auth.clear()
                    self._authenticated = False
                self.results.put(Result('logged_out', '로그아웃했습니다.'))
            elif request.kind == 'command':
                player = await game_socket.command(request.action, request.direction)
                messages = {
                    'gather': '코인 채굴을 완료했습니다.',
                    'train': '개인 수련을 완료했습니다.',
                    'move': '이동 명령을 완료했습니다.',
                }
                self.results.put(Result(
                    'command', messages[request.action], player=player,
                    direction=request.direction, action=request.action))
                if request.action == 'train':
                    self.requests.put_nowait(Request('history'))
        except (Failure, aiohttp.ClientError, TimeoutError, ValueError) as error:
            message = (str(error) if isinstance(error, Failure)
                       else '서버 연결 실패 또는 시간 초과입니다. 다시 시도하세요.')
            needs_login = isinstance(error, Failure) and error.needs_login
            if request.kind in ('login', 'logout') or needs_login:
                if needs_login:
                    await game_socket.close()
                auth.clear()
                self._authenticated = False
                needs_login = True
            if request.kind == 'logout':
                message += ' 로컬 계정은 지웠으나 서버 로그아웃은 확인되지 않았습니다.'
            if request.kind == 'ad_event':
                kind = 'ad_event_error'
            elif request.kind == 'command':
                kind = 'command_error'
            elif request.kind == 'delivery':
                kind = 'delivery_error'
            elif request.kind == 'analytics':
                kind = 'analytics_error'
            elif request.kind == 'ingest':
                kind = 'ingest_error'
            elif request.kind == 'windows':
                kind = 'windows_error'
            elif request.kind == 'history':
                kind = 'history_error'
            elif request.kind in ('load', 'metrics'):
                kind = request.kind + '_error'
            else:
                kind = 'error'
            self.results.put(Result(
                kind, message, needs_login=needs_login,
                direction=request.direction, action=request.action,
                request_id=request.request_id, slot_id=request.slot_id,
                decision_id=request.decision_id, event_type=request.event_type,
                event_rejected=bool(getattr(error, 'event_rejected', False))))
        finally:
            request.password = request.username = ''
