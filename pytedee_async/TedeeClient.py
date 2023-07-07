'''
Created on 01.11.2020

@author: joerg.wolff@gmx.de
'''
import logging
import asyncio

from .const import *
from .helpers import http_request
from .Lock import Lock
from .TedeeClientException import TedeeClientException


_LOGGER = logging.getLogger(__name__)
    
class TedeeClient(object):
    '''Classdocs'''

    def __init__(self, personalToken, timeout=TIMEOUT):
        '''Constructor'''
        self._available = False
        self._personalToken = personalToken
        self._locks_dict = {}
        self._timeout = timeout

        '''Create the api header with new token'''
        self._api_header = {"Content-Type": "application/json", "Authorization": "PersonalKey " + self._personalToken}
        

    @classmethod
    async def create(cls, personalToken, timeout=TIMEOUT):
        self = cls(personalToken, timeout)
        await self.get_locks()
        return self
    
    @property
    def locks(self):
        '''Return a list of locks'''
        return self._locks_dict.values()

    @property
    def locks_dict(self) -> dict:
        return self._locks_dict
    

    async def get_locks(self) -> None:
        '''Get the list of registered locks'''
        r = await http_request(API_URL_LOCK, "GET", self._api_header, self._timeout)
        _LOGGER.debug("Locks %s", r)
        result = r["result"]

        for lock_json in result:            
            lock_id = lock_json["id"]
            lock_name = lock_json["name"]
            lock_type = lock_json["type"]
            lock = Lock(lock_name, lock_id, lock_type)

            lock.is_connected, lock.state, lock.battery_level, lock.is_charging, lock.state_change_result = self.parse_lock_properties(lock_json) 
            lock.is_enabled_pullspring, lock.duration_pullspring = self.parse_pull_spring_settings(lock_json)
            
            
            self._locks_dict[lock_id] = lock

        if lock_id == None:
            raise TedeeClientException("No lock found")


    async def sync(self) -> None:
        '''Sync locks'''
        _LOGGER.debug("Syncing locks...")
        r = await http_request(API_URL_SYNC, "GET", self._api_header, self._timeout)
        result = r["result"]

        for lock_json in result:            
            lock_id = lock_json["id"]

            lock = self.locks_dict[lock_id]

            lock.is_connected, lock.state, lock.battery_level, lock.is_charging, lock.state_change_result = self.parse_lock_properties(lock_json) 
            
            self._locks_dict[lock_id] = lock



    async def unlock(self, lock_id) -> None:
        '''Unlock method'''
        url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=3"
        await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug("unlock command successful, id: %d ", lock_id)
        await asyncio.sleep(UNLOCK_DELAY)
            

    async def lock(self, lock_id) -> None:
        ''''Lock method'''

        url = API_URL_LOCK + str(lock_id) + API_PATH_LOCK
        await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug(f"lock command successful, id: {lock_id}")
        await asyncio.sleep(LOCK_DELAY)


    # pulling  
    async def open(self, lock_id) -> None:
        '''Unlock the door and pull the door latch'''

        url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=4"
        await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug(f"open command successful, id: {lock_id}")
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)
                

    async def pull(self, lock_id) -> None:
        '''Only pull the door latch'''

        url = API_URL_LOCK + str(lock_id) + API_PATH_PULL
        await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug(f"open command successful, id: {lock_id}")
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)
        

    def is_unlocked(self, lock_id) -> bool:
        lock = self._locks_dict[lock_id]
        return lock.state == 2
    
    def is_locked(self, lock_id) -> bool:
        lock = self._locks_dict[lock_id]
        return lock.state == 6

    def parse_lock_properties(self, json: dict):
        if "isConnected" in json:
            connected = json["isConnected"]
        else:
            connected = False

        if "lockProperties" in json:
            lock_properties = json["lockProperties"]
        else:
            lock_properties = None

        if lock_properties:
            state = lock_properties["state"]
            battery_level = lock_properties["batteryLevel"]
            is_charging = lock_properties["isCharging"]
            state_change_result = lock_properties["stateChangeResult"]
        else:
            state = 9
            battery_level = 0
            is_charging = False
            state_change_result = 0

        return connected, state, battery_level, is_charging, state_change_result
    

    def parse_pull_spring_settings(self, settings: dict):

        if "deviceSettings" in settings:
            deviceSettings = settings["deviceSettings"]
        else:
            deviceSettings = {}

        if "pullSpringEnabled" in deviceSettings:
            pullSpringEnabled = deviceSettings["pullSpringEnabled"]
        else:
            pullSpringEnabled = False

        if "pullSpringDuration" in deviceSettings:  
            pullSpringDuration = deviceSettings["pullSpringDuration"]
        else:
            pullSpringDuration = 5

        return pullSpringEnabled, pullSpringDuration
    

    """ Legacy functions for backwards compability"""

    async def update(self, lock_id) -> bool:
        await self.get_locks()
        return lock_id in self._locks_dict
    
    async def get_state(self):
        await self.get_locks()

    def find_lock(self, lock_id):
        return self._locks_dict[lock_id]
    