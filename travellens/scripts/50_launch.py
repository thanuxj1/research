"""Check the system, then run all of it on one port.

  python scripts/50_launch.py                 preflight, then serve on 8778
  python scripts/50_launch.py --port 9000
  python scripts/50_launch.py --check         preflight only, serve nothing
  python scripts/50_launch.py --host 0.0.0.0  reachable from the network
  python scripts/50_launch.py --force         serve despite failed checks

Serves:

    /            the contributor portal
    /dashboard   the research dashboard
    /docs        the API

One process. The portal calls the API on its own origin, so there is no CORS
question and nothing to configure.

Preflight fixes nothing. It compares things that must agree -- a page against
the tree it renders, the published thresholds against the measured ones, every
aspect against the labels behind it -- and names the command that reconciles
each. A dashboard built from a stale tree looks entirely normal, which is why
it is checked here rather than noticed later.

If SUBMISSIONS_DATABASE_URL is set, every /analyse writes to the hosted
research corpus. Combining that with a non-loopback host is refused outright.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from travellens.launch import DEFAULT_PORT, preflight, report, serve


def main() -> int:
    args = sys.argv[1:]

    def opt(flag, default):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                raise SystemExit("{} needs a value".format(flag))
            return args[i + 1]
        return default

    port = int(opt("--port", os.environ.get("PORT") or DEFAULT_PORT))
    host = opt("--host", "127.0.0.1")

    if "--check" in args:
        return 0 if report(preflight()) else 1
    return serve(port=port, host=host, skip_checks="--force" in args)


if __name__ == "__main__":
    raise SystemExit(main())
