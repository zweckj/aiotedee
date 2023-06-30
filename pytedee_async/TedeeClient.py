'''
Created on 01.11.2020

@author: joerg.wolff@gmx.de
'''
import logging
import aiohttp
import asyncio

from .const import *
from .Lock import Lock
from .TedeeClientException import *


_LOGGER = logging.getLogger(__name__)
    
class TedeeClient(object):
    '''Classdocs'''

    def __init__(self, personalToken, timeout):
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
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.get(API_URL_LOCK) as response:
                if response.status == 200:
                    r = await response.json()
                    _LOGGER.debug("Locks %s", r)
                    result = r["result"]

                    for lock_json in result:            
                        lock_id = lock_json["id"]
                        lock_name = lock_json["name"]
                        lock_type = lock_json["type"]
                        lock = Lock(lock_name, lock_id, lock_type)

                        lock.connected, lock.state, lock.battery_level, lock.is_charging = self.parse_lock_properties(lock_json) 
                        lock.is_enabled_pullspring, lock.duration_pullspring = self.parse_pull_spring_settings(lock_json)
                        
                        
                        self._locks_dict[lock_id] = lock

                    if lock_id == None:
                        raise TedeeClientException("No lock found")
                elif response.status == 401:
                    raise TedeeAuthException()
                elif response.status == 429:
                    raise TedeeRateLimitException()
                else:
                    raise TedeeClientException(f"Error during listing of devices. Status code {response.status}")
                    
    # unlocking
    async def unlock(self, lock_id) -> None:
        '''Unlock method'''
        url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK
        
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                if response.status == 202:
                    self._locks_dict[lock_id].state = 4
                    _LOGGER.debug("unlock command successful, id: %d ", lock_id)
                    await asyncio.sleep(UNLOCK_DELAY)
                    self._locks_dict[lock_id].state = 2

                    await self.get_locks()

                elif response.status == 401:
                    raise TedeeAuthException()
                elif response.status == 429:
                    raise TedeeRateLimitException()
                else:
                    raise TedeeClientException(f"Error during unlocking of lock {lock_id}. Status code {response.status}")
            
    # locking
    async def lock(self, lock_id) -> None:
        ''''Lock method'''

        url = API_URL_LOCK + str(lock_id) + API_PATH_LOCK
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                if response.status == 202:
                    self._locks_dict[lock_id].state = 5
                    _LOGGER.debug(f"lock command successful, id: {lock_id}")
                    await asyncio.sleep(LOCK_DELAY)
                    self._locks_dict[lock_id].state = 6
                    await self.get_locks()
                elif response.status == 401:
                    raise TedeeAuthException()
                elif response.status == 429:
                    raise TedeeRateLimitException()
                else:
                    raise TedeeClientException(f"Error during locking of lock {lock_id}. Status code {response.status}")

    # pulling  
    async def open(self, lock_id) -> None:
        '''Open the door latch'''

        url = API_URL_LOCK + str(lock_id) + API_PATH_PULL
        self._locks_dict[lock_id].state = 8
        
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                
                if response.status == 202:
                    self._locks_dict[lock_id].state = 7
                    _LOGGER.debug(f"open command successful, id: {lock_id}")

                    await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)
                    await self.get_locks()
                elif response.status == 401:
                    raise TedeeAuthException()
                elif response.status == 429:
                    raise TedeeRateLimitException()
                else: 
                    raise TedeeClientException(f"Error during unlatching of lock {lock_id}. Status code {response.status}")

    def is_unlocked(self, lock_id) -> bool:
        lock = self._locks_dict[lock_id]
        return lock.state == 2
    
    def is_locked(self, lock_id) -> bool:
        lock = self._locks_dict[lock_id]
        return lock.state == 6

    def parse_lock_properties(self, state: dict):
        if state["isConnected"]:
            connected = state["isConnected"]
        else:
            connected = False

        lock_properties = state["lockProperties"]

        if lock_properties["state"]:
            state = lock_properties["state"]
        else:
            state = 9

        if lock_properties["batteryLevel"]:
            battery_level = lock_properties["batteryLevel"]
        else:
            battery_level = 0

        if lock_properties["isCharging"]:
            is_charging = lock_properties["isCharging"]
        else:
            is_charging = False

        return connected, state, battery_level, is_charging
    
    def parse_pull_spring_settings(self, settings: dict):
        if settings["deviceSettings"]["pullSpringEnabled"]:
            pullSpringEnabled = settings["deviceSettings"]["pullSpringEnabled"]
        else:
            pullSpringEnabled = False

        if settings["deviceSettings"]["pullSpringDuration"]:  
            pullSpringDuration = settings["deviceSettings"]["pullSpringDuration"]
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
    