# tests/integration/test_module_e2e.py
import time, threading, zmq, pytest
import tyche_core

# Use non-conflicting ports (25555-25557 used by other tests)
NEXUS = "tcp://127.0.0.1:25600"
XSUB  = "tcp://127.0.0.1:25601"
XPUB  = "tcp://127.0.0.1:25602"

@pytest.fixture
def engine():
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    n = Nexus(address=NEXUS, cpu_core=None)
    b = Bus(xsub_address=XSUB, xpub_address=XPUB, cpu_core=None)
    threading.Thread(target=n.run, daemon=True).start()
    threading.Thread(target=b.run, daemon=True).start()
    time.sleep(0.15)
    yield n, b
    n.stop(); b.stop()

def test_module_registers_with_nexus(engine):
    from tyche.core.module import Module
    nexus, _ = engine

    class Mod(Module):
        service_name = "test.reg"
        cpu_core = None

    m = Mod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.3)
    assert "test.reg" in nexus.registry
    m.stop()

def test_module_receives_typed_quote(engine):
    from tyche.core.module import Module

    received = []

    class QuoteMod(Module):
        service_name = "test.quotemod"
        cpu_core = None

        def on_start(self):
            self.subscribe("EQUITY.NYSE.AAPL.QUOTE")

        def on_quote(self, topic: str, quote):
            received.append(quote)

    m = QuoteMod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.2)

    q = tyche_core.PyQuote(42, 99.5, 10.0, 100.0, 5.0, 12345)
    payload = bytes(tyche_core.serialize_quote(q))
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(XSUB)
    time.sleep(0.05)
    pub.send_multipart([b"EQUITY.NYSE.AAPL.QUOTE", (0).to_bytes(8, 'big'), payload])
    time.sleep(0.2)

    assert len(received) >= 1
    assert abs(received[0].ask_price - 100.0) < 0.001
    pub.close(); ctx.term(); m.stop()

def test_module_receives_typed_bar(engine):
    from tyche.core.module import Module

    received = []

    class BarMod(Module):
        service_name = "test.barmod"
        cpu_core = None

        def on_start(self):
            self.subscribe("EQUITY.NYSE.AAPL.BAR.M5")

        def on_bar(self, topic: str, bar, interval):
            received.append((bar, interval))

    m = BarMod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.2)

    bar = tyche_core.PyBar(1, 100.0, 105.0, 99.0, 103.0, 500.0,
                           tyche_core.BarInterval.M5, 0)
    payload = bytes(tyche_core.serialize_bar(bar))
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(XSUB)
    time.sleep(0.05)
    pub.send_multipart([b"EQUITY.NYSE.AAPL.BAR.M5", (0).to_bytes(8, 'big'), payload])
    time.sleep(0.2)

    assert len(received) >= 1
    recv_bar, recv_interval = received[0]
    assert recv_interval == tyche_core.BarInterval.M5
    assert abs(recv_bar.close - 103.0) < 0.001
    pub.close(); ctx.term(); m.stop()
