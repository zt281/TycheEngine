# tyche/cli/__main__.py
import argparse
import os
import re
import sys

_NAME_RE = re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')

# NOTE spec deviation: imports corrected to actual package paths.
# Spec shows `from tyche.module import Module` / `from tyche.model import ModuleConfig`
# which do not exist. Correct paths are tyche.core.module and tyche.core.config.
_STRATEGY_TEMPLATE = '''\
from tyche.core.module import Module
from tyche.core.config import ModuleConfig


class {class_name}(Module):
    """Auto-generated strategy scaffold."""

    def on_start(self):
        pass  # subscribe to topics here

    def on_stop(self):
        pass

    def on_quote(self, topic, quote):
        pass

    # NOTE spec deviation: on_bar signature corrected to match Module base class.
    # Spec shows on_bar(self, topic, msg) — omitting interval causes TypeError at runtime.
    def on_bar(self, topic, bar, interval):
        pass


if __name__ == "__main__":
    cfg = ModuleConfig.from_file("config/modules/{name}.toml")
    {class_name}(cfg.nexus_address, cfg.bus_xsub, cfg.bus_xpub).run()
'''

# NOTE spec deviation: spec shows `cpu_core = null` which is invalid TOML (no null type).
# Using commented example `# cpu_core = 4` instead — valid TOML, communicates optionality.
_CONFIG_TEMPLATE = '''\
[module]
service_name = "{name}"
nexus_address = "tcp://localhost:5555"
bus_xsub = "tcp://localhost:5556"
bus_xpub = "tcp://localhost:5557"
# cpu_core = 4
metrics_enabled = false
'''


def _to_pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="tyche")
    subparsers = parser.add_subparsers(dest="command")
    ns_parser = subparsers.add_parser("new-strategy", help="Generate a strategy scaffold")
    ns_parser.add_argument("name", help="Strategy name — must match [a-z][a-z0-9_]*")
    args = parser.parse_args()

    if args.command != "new-strategy":
        parser.print_help()
        sys.exit(1)

    name = args.name
    if not _NAME_RE.match(name):
        print("Error: name must match [a-z][a-z0-9_]*", file=sys.stderr)
        sys.exit(1)

    class_name = _to_pascal_case(name)

    os.makedirs("strategies", exist_ok=True)
    strategy_path = os.path.join("strategies", f"{name}.py")
    with open(strategy_path, "w") as f:
        f.write(_STRATEGY_TEMPLATE.format(name=name, class_name=class_name))

    os.makedirs(os.path.join("config", "modules"), exist_ok=True)
    config_path = os.path.join("config", "modules", f"{name}.toml")
    with open(config_path, "w") as f:
        f.write(_CONFIG_TEMPLATE.format(name=name))

    print(f"Created {strategy_path}")
    print(f"Created {config_path}")


if __name__ == "__main__":
    main()
