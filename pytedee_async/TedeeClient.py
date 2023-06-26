'''
Created on 01.11.2020

@author: joerg.wolff@gmx.de
'''
import logging
import aiohttp
import asyncio
from threading import Timer

from .const import *

try:
    from .Lock import Lock
    from .TedeeClientException import TedeeClientException
except:
    from Lock import Lock
    from TedeeClientException import TedeeClientException

_LOGGER = logging.getLogger(__name__)
    
class TedeeClient(object):
    '''Classdocs'''

    def __init__(self, personalToken, timeout):
        '''Constructor'''
        self._available = False
        self._personalToken = personalToken
        self._sensor_list = []
        self._timeout = timeout
        self._lock_id = None

        '''Create the api header with new token'''
        self._api_header = {"Content-Type": "application/json", "Authorization": "PersonalKey " + self._personalToken}
        

    @classmethod
    async def create(cls, personalToken, timeout=TIMEOUT):
        self = cls(personalToken, timeout)
        await self.get_devices()
        return self
    
    @property
    def locks(self):
        '''Return a list of locks'''
        return self._sensor_list

    async def get_devices(self):
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

                    for x in result:            
                        id = x["id"]
                        name = x["name"]
                        type = x["type"]
                        lock = Lock(name, id, type)

                        lock.connected, lock.state, lock.battery_level, lock.is_charging = self.parse_lock_properties(x) 
                        lock.is_enabled_pullspring, lock.duration_pullspring = self.parse_pull_spring_settings(x)
                        
                        self._lock_id = id
                        '''store the found lock in _sensor_list and get the battery_level'''

                        self._sensor_list.append(lock)

                    if self._lock_id == None:
                        raise TedeeClientException("No lock found")
    
    # unlocking
    async def unlock(self, id):
        '''Unlock method'''
        lock = self.find_lock(id)
        url = API_URL_LOCK + str(id) + API_PATH_UNLOCK
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                if response.status == 202:
                    lock.state = 4
                    _LOGGER.debug("unlock command successful, id: %d ", id)
                    await asyncio.sleep(UNLOCK_DELAY)
                    lock.state = 2
                    await self.get_state()
            
    # locking
    async def lock(self, id):
        ''''Lock method'''
        lock = self.find_lock(id)

        url = API_URL_LOCK + str(id) + API_PATH_LOCK
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                if response.status == 202:
                    lock.state = 5
                    _LOGGER.debug("lock command successful, id: %d ", id)
                    await asyncio.sleep(LOCK_DELAY)
                    lock.state = 6
                    await self.get_state()

    # pulling  
    async def open(self, id):
        '''Open the door latch'''
        lock = self.find_lock(id)

        url = API_URL_LOCK + str(id) + API_PATH_PULL
        lock.state = 8
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.post(url) as response:
                
                if response.status == 202:
                    lock.state = 7
                    _LOGGER.debug("open command successful, id: %d ", id)

                    await asyncio.sleep(lock.duration_pullspring + 1)
                    await self.get_state()

    def is_unlocked(self, id):
        lock = self.find_lock(id)
        return lock.state == 2
    
    def is_locked(self, id):
        lock = self.find_lock(id)
        return lock.state == 6
    
    async def get_battery(self, id):
        lock = self.find_lock(id)
        
        url = API_URL_DEVICE + str(id) + API_PATH_BATTERY
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    r = await response.json()
                    _LOGGER.debug("result: %s", r)
                    result = r["result"]
                    try:
                        success = result["success"]
                        if success:
                            for lock in self._sensor_list:
                                if id == lock.id:
                                    lock.battery_level = result["level"]
                                    _LOGGER.debug("id: %d, battery level: %d", id, lock.battery_level)
                        return success
                    except KeyError:
                        _LOGGER.error("result: %s", result)
                        return False
            
    async def get_state(self):
        async with aiohttp.ClientSession(
                headers=self._api_header, 
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
            async with session.get(API_URL_STATE) as response:
                if response.status == 200:
                    r = await response.json()
                    states = r["result"]
                    try:
                        for state in states:
                            id = state["id"]
                            # find the correct lock in the returned list of sensors
                            for lock in self._sensor_list:
                                if id == lock.id:

                                    lock.connected, lock.state, lock.battery_level, lock.is_charging = self.parse_lock_properties(state)
                                    _LOGGER.debug("Id: %s, State: %d, battery: %d", lock.state, lock.is_charging, lock.battery_level)
                                    break
                    except KeyError:
                        _LOGGER.error("result: %s", r.json())

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
            
    def find_lock(self, id):
        for lock in self._sensor_list:
            if id == lock.id:
                return lock
        raise TedeeClientException("This Id not found")

    async def update(self, id):
        await self.get_state()
        return await self.get_battery(id)