import time
from open_packet.ax25.timer import Timer


def test_timer_not_running_initially():
    t = Timer()
    assert not t.running
    assert not t.expired


def test_timer_running_after_start():
    t = Timer()
    t.start(10.0)
    assert t.running
    assert not t.expired  # 10 s hasn't elapsed yet


def test_timer_expired_after_deadline():
    t = Timer()
    t.start(0.001)
    time.sleep(0.01)
    assert t.expired


def test_timer_stop_clears_running():
    t = Timer()
    t.start(10.0)
    t.stop()
    assert not t.running
    assert not t.expired


def test_timer_restart_resets_deadline():
    t = Timer()
    t.start(0.001)
    time.sleep(0.01)
    assert t.expired
    t.start(10.0)   # restart with a long timeout
    assert not t.expired
