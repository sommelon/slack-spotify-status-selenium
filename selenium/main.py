from collections import namedtuple
import logging
import os
import time
from actions import Actions
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait, IGNORED_EXCEPTIONS
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import StaleElementReferenceException

# env vars
REFRESH_INTERVAL = int(os.getenv('REFRESH_INTERVAL'))
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
EMOJI = os.getenv('EMOJI')
DEBUG = bool(os.getenv('DEBUG'))

# logging
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
selenium_logger = logging.getLogger('selenium')
selenium_logger.setLevel(logging.WARNING)
spotipy_logger = logging.getLogger('spotipy')
spotipy_logger.setLevel(logging.WARNING)
urllib_logger = logging.getLogger('urllib3')
urllib_logger.setLevel(logging.WARNING)
urllib_logger.propagate = False
logger = logging.getLogger('spotify-slack')


Track = namedtuple('Track', 'name,artist,duration_ms')

def update_status(driver: WebDriver, track: Track):
    try:
        wait = WebDriverWait(driver, 10, ignored_exceptions=IGNORED_EXCEPTIONS + (StaleElementReferenceException,))
        actions = Actions(driver, wait, logger)
        actions.escape(3)
        actions.click_avatar()

        new_status = track.name + " by " + track.artist if track else None
        if actions.get_current_status_text() == new_status:
            logger.debug("Status already set")
            return

        status_emoji_name = actions.get_current_status_emoji()
        if status_emoji_name is None and track is None:
            logger.debug("Nothing to update")
            return
        elif status_emoji_name is not None and status_emoji_name != EMOJI:
            logger.info("Slack status not updated, because it would override a possibly more important status.")
            return

        status_emoji_name = actions.click_update_status_button()

        if not track:
            actions.click_clear_all_button()
            actions.click_save_button()
            logger.info("Status cleared.")
            return

        actions.click_emoji_picker_button()
        actions.select_emoji(EMOJI)
        actions.click_status_duration_dropdown()
        actions.click_choose_date_and_time_option()
        actions.update_status(new_status)
    except Exception as e:
        logger.exception(str(e))


def get_current_track(sp: spotipy.Spotify):
    try:
        current_track = sp.current_playback()
    except Exception:
        current_track = sp.current_playback()  # retry

    if current_track is not None and 'item' in current_track and current_track['is_playing']:
        track_name = current_track['item']['name']
        artist_name = current_track['item']['artists'][0]['name']
        duration = current_track['item']['duration_ms']
        track = Track(track_name, artist_name, duration)
        return track
    else:
        logger.info("No song is currently playing on Spotify.")

def is_slack_workspace_open(driver: WebDriver):
    if len(driver.window_handles) == 1:
        return 'https://app.slack.com/' in driver.current_url

    if 'okta.com' in driver.current_url:
        return False

    for window_handle in driver.window_handles:
        driver.switch_to.window(window_handle)
        if 'https://app.slack.com/' in driver.current_url:
            return True
        elif 'okta.com' in driver.current_url:  # TODO: Handle different auth providers
            return False  # Stop switching windows when we are being authenticated

    return False

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                        client_secret=SPOTIFY_CLIENT_SECRET,
                                        redirect_uri="http://localhost:8000",
                                        scope="user-read-playback-state"))


with webdriver.Chrome() as driver:
    driver.get('https://slack.com/signin')
    wait = WebDriverWait(driver, 120)
    wait.until(is_slack_workspace_open)

    try:
        track = get_current_track(sp)
        update_status(driver, track)

        while True:
            time.sleep(REFRESH_INTERVAL)
            track = get_current_track(sp)
            update_status(driver, track)
    except Exception as e:
        logger.exception(str(e))