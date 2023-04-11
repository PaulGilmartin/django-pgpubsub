from dataclasses import dataclass
import datetime
from typing import Dict, List, Set, Tuple

from pgpubsub.channel import Channel


def test_deserialize_1():
    @dataclass
    class MyChannel(Channel):
        arg1: str
        arg2: Dict[int, int]
        default_arg1: float = 0.0

    deserialized = _deserialize(MyChannel, arg1='1', arg2={1: 2}, default_arg1=3.4)
    assert {'arg1': '1', 'arg2': {1: 2},
            'default_arg1': 3.4} == deserialized


def test_deserialize_2():
    @dataclass
    class MyChannel(Channel):
        arg1: Dict[str, bool]
        default_arg1: bool = False
        default_arg2: int = 0

    deserialized = _deserialize(
        MyChannel, arg1={'Paul': False}, default_arg1=True)
    assert {'arg1': {'Paul': False},
            'default_arg1': True,
            'default_arg2': 0} == deserialized


def test_deserialize_3():
    @dataclass
    class MyChannel(Channel):
        arg1: datetime.date
        arg2: Dict[datetime.date, bool]
        arg3: Dict[str, datetime.datetime]

    deserialized = _deserialize(
        MyChannel,
        arg1=datetime.date(2021, 1, 1),
        arg2={
            datetime.date(2021, 1, 7): True,
            datetime.date(2021, 1, 17): False,
        },
        arg3={'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
    )

    assert {
        'arg1': datetime.date(2021, 1, 1),
        'arg2': {datetime.date(2021, 1, 7): True, datetime.date(2021, 1, 17): False},
        'arg3': {'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
    } == deserialized


def test_deserialize_4():
    @dataclass
    class MyChannel(Channel):
        arg1: List[datetime.date]
        arg2: Set[float]
        arg3: Tuple[str]

    deserialized = _deserialize(
        MyChannel,
        arg1=[datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
        arg2={1.0, 2.1},
        arg3=('hello', 'world'),
    )
    assert {
        'arg1': [datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
        'arg2': {1.0, 2.1},
        'arg3': ('hello', 'world'),
    } == deserialized


def _deserialize(channel_cls, **kwargs):
    serialized = channel_cls(**kwargs).serialize()
    return channel_cls.deserialize(serialized)
