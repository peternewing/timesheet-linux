"""GTK-free host companion installer for the Flatpak UI."""
import argparse,json
from . import desktop

def main():
    p=argparse.ArgumentParser(description='Install or start the host capture companion')
    actions=p.add_mutually_exclusive_group(required=True)
    actions.add_argument('--install',action='store_true');actions.add_argument('--uninstall',action='store_true');actions.add_argument('--background',action='store_true')
    args=p.parse_args()
    if args.install: print(json.dumps(desktop.install(host_only=True),indent=2))
    elif args.uninstall: print(desktop.uninstall(host_only=True))
    elif args.background: desktop.start_collector()

if __name__=='__main__':main()
