import os, sys, time, signal, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from thermostat.runtime import load_config, build_runtime

RUN = True
def handle_sig(sig, frame):
    global RUN; RUN = False

def main():
    cfg = load_config()
    ctrl, actuators, gpio_cleanup = build_runtime(cfg)
    signal.signal(signal.SIGINT, handle_sig); signal.signal(signal.SIGTERM, handle_sig)
    print("[APP] Starting thermostat loop. Ctrl+C to exit.")
    try:
        while RUN:
            ctrl.tick(); time.sleep(2.0)
    finally:
        print("[APP] Shutting down, GPIO safe-off.")
        try: actuators.all_off()
        finally: gpio_cleanup()

if __name__ == "__main__":
    sys.exit(main())
