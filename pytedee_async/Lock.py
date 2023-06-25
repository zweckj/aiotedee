'''
Created on 02.11.2020

@author: joerg
'''

from enum import Enum


'''class State(Enum):
    Unknown = 0
    Unlocked = 2
    Half Open = 3
    Unlocking = 4
    Locking = 5
    Locked = 6
    Pull = 7'''

    
class Lock(object):
    '''
    classdocs
    '''

    def __init__(self, name, id):
        '''
        Constructor
        '''
        self._name = name
        self._id = id
        self._state = 0
        self._battery_level = None
        self._is_connected = False
        self._is_charging = False
        
    @property
    def name(self):
        return self._name
    
    @property
    def id(self):
        return self._id
    
    @property
    def is_state_locked(self):
        return self._state == 6
    
    @property
    def is_state_unlocked(self):
        return self._state == 2
    
    @property
    def state(self):
        return self._state
    
    @state.setter
    def state(self, status):
        self._state = status
        
    @property
    def battery_level(self):
        return self._battery_level
    
    @battery_level.setter
    def battery_level(self, level):
        self._battery_level = level

    @property
    def is_connected(self):
        return self._is_connected 
    
    @is_connected.setter
    def is_connected(self, connected):
        self._is_connected = connected
    
    @property
    def is_charging(self):
        return self._is_charging
    
    @is_charging.setter
    def is_charging(self, isCharging):
        self._is_charging = isCharging
       
    @property
    def is_enabled_pullspring(self):
        return self._is_enabled_pullspring
    
    @is_enabled_pullspring.setter
    def is_enabled_pullspring(self, isEnabled):
        self._is_enabled_pullspring = isEnabled
    
    @property
    def duration_pullspring(self):
        return self._duration_pullspring
        
    @duration_pullspring.setter
    def duration_pullspring(self, duration):
        self._duration_pullspring = duration
        