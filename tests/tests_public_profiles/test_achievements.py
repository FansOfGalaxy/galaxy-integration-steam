from datetime import datetime, timezone

import pytest
from galaxy.api.types import Achievement, GameTime
from galaxy.api.errors import AuthenticationRequired, BackendError, UnknownError
from galaxy.unittest.mock import skip_loop

from public_profiles.steamcommunity_scrapper import SteamHttpClient


@pytest.fixture()
def push_cache(authenticated_plugin, mocker):
    return mocker.patch.object(authenticated_plugin, "push_cache")


@pytest.fixture()
def achievements_complete(authenticated_plugin):
    async def func():
        authenticated_plugin.achievements_import_complete()
        authenticated_plugin.tick()
        await skip_loop(1)  # time to run tasks spawned on tick
    return func


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.prepare_achievements_context(["12", "13"])


@pytest.mark.asyncio
async def test_prepare_achievements_context(authenticated_plugin, steam_http_client):
    steam_http_client.get_games.return_value = [
        {
            "appid": 281990,
            "hours_forever": "1.3",
            "last_played": 1549385500
        },
        {
            "appid": 236850,
            "hours_forever": "1,447",
            "last_played": 1549385500
        }
    ]
    context = await authenticated_plugin.prepare_achievements_context(["281990", "236850"])
    assert context == {
        "236850": GameTime(game_id="236850", time_played=86820, last_played_time=1549385500),
        "281990": GameTime(game_id="281990", time_played=78, last_played_time=1549385500)
    }


@pytest.mark.asyncio
async def test_get_achievements_success(authenticated_plugin, steam_http_client, steam_id):
    context = {
        "236850": GameTime(game_id="236850", time_played=86820, last_played_time=1549385500),
        "281990": GameTime(game_id="281990", time_played=78, last_played_time=1549385500)
    }
    steam_http_client.get_achievements.return_value = [
        (1551887210, "name 1"),
        (1551887134, "name 2")
    ]
    achievements = await authenticated_plugin.get_unlocked_achievements("236850", context)
    assert achievements == [
            Achievement(1551887210, None, "name 1"),
            Achievement(1551887134, None, "name 2")
        ]
    steam_http_client.get_achievements.assert_called_once_with(steam_id, "236850")


@pytest.mark.asyncio
async def test_get_achievements_error(authenticated_plugin, steam_http_client):
    context = {
        "236850": GameTime(game_id="236850", time_played=86820, last_played_time=1549385500),
        "281990": GameTime(game_id="281990", time_played=78, last_played_time=1549385500)
    }
    steam_http_client.get_achievements.side_effect = BackendError()
    with pytest.raises(BackendError):
        await authenticated_plugin.get_unlocked_achievements("281990", context)


@pytest.mark.asyncio
async def test_push_cache(authenticated_plugin, steam_http_client, push_cache, achievements_complete):
    context = {
        "17923": GameTime(game_id="17923", time_played=180, last_played_time=1549385501)
    }
    steam_http_client.get_achievements.return_value = [(1549383000, "name")]
    await authenticated_plugin.get_unlocked_achievements("17923", context)
    await achievements_complete()
    push_cache.assert_called_once_with()
    assert "achievements" in authenticated_plugin.persistent_cache
    assert authenticated_plugin.persistent_cache["achievements"] == {
        "17923": {
            "achievements": [
                {
                    "unlock_time": 1549383000,
                    "achievement_id": None,
                    "achievement_name": "name"
                }
            ],
            "fingerprint": {
                "time_played": 1549385501,
                "last_played_time": 180
            }
        }
    }


@pytest.mark.asyncio
async def test_valid_cache(authenticated_plugin, steam_http_client, push_cache, achievements_complete):
    context = {
        "17923": GameTime(game_id="17923", time_played=180, last_played_time=1549385501)
    }
    steam_http_client.get_achievements.return_value = [(1549383000, "name")]
    await authenticated_plugin.get_unlocked_achievements("17923", context)
    await achievements_complete()
    assert steam_http_client.get_achievements.call_count == 1
    assert push_cache.call_count == 1

    await authenticated_plugin.get_unlocked_achievements("17923", context)
    await achievements_complete()
    assert steam_http_client.get_achievements.call_count == 1 # no new calls to backend
    assert push_cache.call_count == 1


@pytest.mark.asyncio
async def test_invalid_cache(authenticated_plugin, steam_http_client, push_cache, achievements_complete):
    context = {
        "17923": GameTime(game_id="17923", time_played=180, last_played_time=1549385501)
    }
    steam_http_client.get_achievements.return_value = [(1549383000, "name")]
    await authenticated_plugin.get_unlocked_achievements("17923", context)
    await achievements_complete()
    assert steam_http_client.get_achievements.call_count == 1
    assert push_cache.call_count == 1

    context = {
        "17923": GameTime(game_id="17923", time_played=180, last_played_time=1549385600)
    }
    steam_http_client.get_achievements.return_value = [
        (1549383000, "name"),
        (1549385599, "namee")
    ]
    await authenticated_plugin.get_unlocked_achievements("17923", context)
    await achievements_complete()
    assert steam_http_client.get_achievements.call_count == 2
    assert push_cache.call_count == 2
    assert "achievements" in authenticated_plugin.persistent_cache
    assert authenticated_plugin.persistent_cache["achievements"] == {
        "17923": {
            "achievements": [
                {
                    "unlock_time": 1549383000,
                    "achievement_id": None,
                    "achievement_name": "name"
                },
                {
                    "unlock_time": 1549385599,
                    "achievement_id": None,
                    "achievement_name": "namee"
                }
            ],
            "fingerprint": {
                "time_played": 1549385600,
                "last_played_time": 180
            }
        }
    }


@pytest.mark.asyncio
async def test_initialize_cache(create_authenticated_pp_plugin, steam_http_client):
    cache = {
        "achievements": """{
            "17923": {
                "achievements": [
                    {
                        "unlock_time": 1549383000,
                        "achievement_id": null,
                        "achievement_name": "name"
                    }
                ],
                "fingerprint": {
                    "time_played": 1549385501,
                    "last_played_time": 180
                }
            }
        }"""
    }
    plugin_with_cache = await create_authenticated_pp_plugin(cache)

    context = {
        "17923": GameTime(game_id="17923", time_played=180, last_played_time=1549385501)
    }
    achievements = await plugin_with_cache.get_unlocked_achievements("17923", context)
    assert achievements == [
        Achievement(1549383000, None, "name")
    ]
    steam_http_client.get_achievements.assert_not_called()


@pytest.mark.asyncio
async def test_no_game_time(authenticated_plugin):
    context = {}
    with pytest.raises(UnknownError):
        await authenticated_plugin.get_unlocked_achievements("17923", context)


@pytest.mark.parametrize("input_time, parsed_date", [
    ("Unlocked 22 Jan @ 12:12am", datetime(datetime.utcnow().year, 1, 22, 0, 12, tzinfo=timezone.utc)),
    ("Unlocked Feb 1 @ 12:12am", datetime(datetime.utcnow().year, 2, 1, 0, 12, tzinfo=timezone.utc)),
    ("Unlocked 9 Jun, 2017 @ 11:35pm", datetime(2017, 6, 9, 23, 35, tzinfo=timezone.utc)),
    ("Unlocked Feb 20, 2015 @ 9:24pm", datetime(2015, 2, 20, 21, 24, tzinfo=timezone.utc))
])
def test_unlock_time_parsing(input_time, parsed_date):
    assert parsed_date == SteamHttpClient.parse_date(input_time)