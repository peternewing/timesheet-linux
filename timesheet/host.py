"""GTK-free host companion installer for the Flatpak UI."""
import argparse,json
from . import desktop

def main():
    p=argparse.ArgumentParser(description='Install or start the host capture companion')
    p.add_argument('--install',action='store_true');p.add_argument('--background',action='store_true')
    args=p.parse_args()
    if args.install: print(json.dumps(desktop.install(host_only=True),indent=2))
    elif args.background: desktop.start_collector()
    else:p.error('Choose --install or --background')

if __name__=='__main__':main()
