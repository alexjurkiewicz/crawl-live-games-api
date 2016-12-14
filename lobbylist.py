#!/usr/bin/env python3
"""Serve a simple API showing currently active games."""

import asyncio
import logging
import urllib.parse
import collections
import json

from webtiles import WebTilesConnection, WebTilesGameConnection
import aiohttp
import aiohttp.server

Server = collections.namedtuple("Server",
                                ('name', 'ws_url', 'ws_proto', 'base_url'))

SERVERS = [
    Server("cao", "ws://crawl.akrasiac.org:8080/socket", 1,
           'http://crawl.akrasiac.org:8080/'),
    Server("cbro", "ws://crawl.berotato.org:8080/socket", 1,
           'http://crawl.berotato.org:8080/'),
    Server("cjr", "wss://crawl.jorgrun.rocks:8081/socket", 1,
           'https://crawl.jorgrun.rocks:8081/'),
    Server("cpo", "wss://crawl.project357.org/socket", 2,
           'https://crawl.project357.org/'),
    Server("cue", "ws://www.underhound.eu:8080/socket", 1,
           'http://underhound.eu:8080/'),
    Server("cwz", "ws://webzook.net:8080/socket", 1,
           'http://webzook.net:8080/'),
    Server("cxc", "ws://crawl.xtahua.com:8080/socket", 1,
           'http://crawl.xtahua.com:8080/'),
    Server("lld", "ws://lazy-life.ddo.jp:8080/socket", 1,
           'http://lazy-life.ddo.jp:8080/'),
]
DATABASE = []

_log = logging.getLogger()
_log.setLevel(logging.INFO)
_log.addHandler(logging.StreamHandler())


class LobbyList(WebTilesConnection):
    def __init__(self, server_abbr, websocket_url, protocol_version, base_url):
        super().__init__()
        self.server_abbr = server_abbr
        self.websocket_url = websocket_url
        self.protocol_version = protocol_version
        self.base_url = base_url

    def watchlink(self, username):
        if self.protocol_version == 1:
            return self.base_url + '#watch-' + username
        else:
            return self.base_url + 'watch/' + username

    async def ensure_connected(self):
        """Connect to the WebTiles server if needed."""
        if not self.connected():
            _log.info("%s: Connecting", self.server_abbr)
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)
            if self.protocol_version > 1:
                _log.info("%s: Requesting initial lobby", self.server_abbr)
                await self.send({"msg": "lobby"})

    async def get_lobby_entries(self):
        """Read and handle messages."""
        while True:
            await self.ensure_connected()
            messages = await self.read()

            if not messages:
                # XXX Not sure why this could happen. Websocket timeout?
                print("{}: No messages?!".format(self.server_abbr))
                break

            for message in messages:
                await self.handle_message(message)

            if self.protocol_version == 1 and not self.lobby_complete:
                continue

            return self.lobby_entries


class GameWatcher(WebTilesGameConnection):
    def __init__(self, server_abbr, websocket_url, protocol_version, username):
        super().__init__()
        self.server_abbr = server_abbr
        self.websocket_url = websocket_url
        self.protocol_version = protocol_version
        self.target_game_id = -1
        self.target_username = username

    async def ensure_connected(self):
        """Connect to the WebTiles server if needed."""
        if not self.connected():
            _log.info("%s: Connecting", self.server_abbr)
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)
            await self.send_watch_game(self.target_username, self.target_game_id)

    async def find_player_info(self):
        """Read and handle messages."""
        while True:
            await self.ensure_connected()
            messages = await self.read()

            if not messages:
                # XXX Not sure why this could happen. Websocket timeout?
                print("{}: No messages?!".format(self.server_abbr))
                break

            for message in messages:
                if message['msg'] == 'player':
                    return message
                await self.handle_message(message)


async def update_database(new_entries, server):
    global DATABASE
    # Remove existing entries for this server
    new_database = [g for g in DATABASE if g['server'] != server]
    # Add the new entries
    for entry in new_entries:
        new_database.append(entry)
    # Always sort in username order (split ties by server)
    new_database = sorted(
        new_database, key=lambda g: g['username'] + g['server'])
    DATABASE = new_database


async def update_lobby_data(lister):
    while True:
        try:
            entries = await lister.get_lobby_entries()
        except KeyboardInterrupt:
            print("Bye")
            break
        except websockets.exceptions.ConnectionClosed:
            continue
        for entry in entries:
            entry['server'] = lister.server_abbr
            entry['watchlink'] = lister.watchlink(entry['username'])
            entry['idle'] = bool(entry['idle_time'] != 0)
        await update_database(entries, lister.server_abbr)
        _log.debug("%s: Updated lobby data", lister.server_abbr)


async def game_info(server_abbr, player):
    server = [s for s in SERVERS if s.name == server_abbr]
    if not server:
        return None
    server = server[0]

    watcher = GameWatcher(server_abbr, server.ws_url, server.ws_proto, player)
    return await watcher.find_player_info()


class ApiRequestHandler(aiohttp.server.ServerHttpProtocol):
    async def handle_request(self, message, payload):
        routes = {
            '/games': self.list_games,
            '/gameinfo': self.game_info,
        }
        url = urllib.parse.urlsplit(message.path)
        args = urllib.parse.parse_qs(url.query)
        if url.path in routes.keys():
            return await routes[url.path](message, payload, url, args)
        else:
            return await self.error_page(404, message, payload, url, args)

    async def list_games(self, message, payload, url, args):
        json_args = {
            'indent': 2,
            'sort_keys': True
        } if 'pretty' in args else {}
        response = aiohttp.Response(
            self.writer, 200, http_version=message.version)
        data = json.dumps(DATABASE, **json_args)
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', str(len(data)))
        response.send_headers()
        response.write(data.encode())
        await response.write_eof()

    async def game_info(self, message, payload, url, args):
        json_args = {
            'indent': 2,
            'sort_keys': True
        } if 'pretty' in args else {}
        if not args.get('player') or not args.get('server'):
            return await self.error_page(400, message, payload, url, args)
        player = args['player'][0]
        server = args['server'][0]
        if not [g for g in DATABASE if g['username'] == player]:
            return await self.error_page(404, message, payload, url, args)

        response = aiohttp.Response(
            self.writer, 200, http_version=message.version)
        info = await game_info(server, player)
        data = json.dumps(info, **json_args)
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', str(len(data)))
        response.send_headers()
        response.write(data.encode())
        await response.write_eof()

    async def error_page(self, code, message, payload, url, args):
        response = aiohttp.Response(
            self.writer, code, http_version=message.version)
        response.send_headers()
        await response.write_eof()


def main():
    loop = asyncio.get_event_loop()
    for server in SERVERS:
        lobby_lister = LobbyList(server.name, server.ws_url, server.ws_proto,
                                 server.base_url)
        loop.create_task(update_lobby_data(lobby_lister))

    httpd = loop.create_server(lambda: ApiRequestHandler(), 'localhost', '5678')
    loop.create_task(httpd)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()


main()
