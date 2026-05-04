import net.address as address
import net.tcp as tcp


class DecServer:
    def __init__(self, bind_address: address.NetAddress) -> None:
        self.sock = tcp.TCPSocket(bind_address)
        self.is_running = False

    def start(self):
        self.sock.bind()
        self.sock.listen()
        self.is_running = True

    def end(self):
        self.is_running = False
        self.sock.close()

    def loop(self):
        try:
            while self.is_running:
                self._iter()
        except KeyboardInterrupt:
            self.end()

    def _process_registration(self):
        pass

    def _process_discovery(self):
        pass

    def _process_inc_message(self):
        pass

    def _get_msgs_for_peer(self):
        pass

    def _keep_alive(self):
        pass

    def _iter(self):
        pass
