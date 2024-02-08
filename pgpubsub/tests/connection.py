
def simulate_listener_does_not_receive_notifications(pg_connection):
    pg_connection.notifies = []
    pg_connection.poll()
    assert 0 == len(pg_connection.notifies)
