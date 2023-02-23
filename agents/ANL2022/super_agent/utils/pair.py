from abc import ABC
from collections import defaultdict


class Pair(ABC):
    def __init__(self):
        self._value_type = -1
        self._vlist = defaultdict()

    @property
    def value_type(self):
        return self._value_type

    @property
    def vlist(self):
        return self._vlist

    @value_type.setter
    def value_type(self, value_type):
        self._value_type = value_type
